import datetime
import functools
import json
from dataclasses import asdict
from operator import add, or_

from dateutil.parser import parse
from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from first import first
from formtools.wizard.views import SessionWizardView

from touchtechnology.common.forms.fields import (
    ModelChoiceField,
    ModelMultipleChoiceField,
)
from tournamentcontrol.competition.ai import (
    AICompetitionService,
    CompetitionPlan,
    DivisionStructure,
    PoolStructure,
    StageStructure,
)
from tournamentcontrol.competition.ai.executor import execute_competition_plan
from tournamentcontrol.competition.models import Season
from tournamentcontrol.competition.tasks import generate_pdf_scorecards
from tournamentcontrol.competition.utils import generate_scorecards

##############################################################################
# Scorecard Report
##############################################################################


def combine_date_time_tuple(t):
    return datetime.datetime.combine(*t)


def q_date_from_datetime(dt):
    return Q(date=dt.date())


def q_date_time_from_datetime(dt):
    return Q(date=dt.date(), time=dt.time())


no_date_or_time = Q(date__isnull=True) | Q(time__isnull=True)


class SeasonForm(forms.Form):
    """
    Step 1. Select which season you want to generate a report of.
    """

    def __init__(self, *args, **kwargs):
        super(SeasonForm, self).__init__(*args, **kwargs)

        seasons = (
            Season.objects.exclude(complete=True)
            .select_related("competition")
            .order_by("-start_date")
        )
        self.fields["season"] = ModelChoiceField(
            queryset=seasons,
            label_from_instance=lambda s: "{0} {1}".format(
                s.competition.title, s.title
            ),
        )


class FilterForm(forms.Form):
    """
    Step 2. Provide fields to allow the admin to filter the matches for
    inclusion in the report.
    """

    def __init__(self, season, *a, **kw):
        super(FilterForm, self).__init__(*a, **kw)

        # given a Season instance get all the matches which should have a
        # scorecard produced.
        self.matches = season.matches.exclude(no_date_or_time)

        # allow filtering by division
        self.fields["division"] = ModelMultipleChoiceField(
            queryset=season.divisions.all(), label_from_instance="title", required=False
        )

        # allow filtering by date
        dates = self.matches.order_by("date").values_list("date", flat=True).distinct()

        date_choices = zip(dates, dates)
        self.fields["dates"] = forms.MultipleChoiceField(
            choices=date_choices, widget=forms.CheckboxSelectMultiple, required=False
        )

        # allow filtering by timeslot
        timeslots = (
            self.matches.order_by("date", "time").values_list("date", "time").distinct()
        )

        datetimes = [combine_date_time_tuple(t) for t in timeslots]
        datetime_choices = zip(datetimes, datetimes)
        self.fields["timeslots"] = forms.MultipleChoiceField(
            choices=datetime_choices,
            widget=forms.CheckboxSelectMultiple,
            required=False,
        )

        # allow configurable templates to be rendered
        template_choices = (
            ("", _("Choose a report template...")),
            ("scorecards.html", "Scorecards"),
            ("signon.html", "Sign-on Sheet"),
            ("mvp.html", "Most Valuable Player"),
        )

        self.fields["template"] = forms.ChoiceField(
            choices=template_choices, label=_("Template")
        )

        output_choices = (
            ("", _("Choose an output format...")),
            ("pdf", _("PDF")),
            ("html", _("HTML")),
        )
        self.fields["format"] = forms.ChoiceField(
            choices=output_choices, label=_("Output as")
        )

    def clean(self):
        data = self.cleaned_data.copy()
        query_filter = Q()

        dates = self.cleaned_data.get("dates")
        timeslots = self.cleaned_data.get("timeslots")

        if dates:
            date_list = [q_date_from_datetime(parse(d)) for d in dates]
            query_filter |= functools.reduce(or_, date_list)

        if timeslots:
            timeslot_list = [q_date_time_from_datetime(parse(t)) for t in timeslots]
            query_filter |= functools.reduce(or_, timeslot_list)

        divisions = self.cleaned_data.get("division")

        if divisions:
            query_filter &= Q(stage__division__in=divisions)

        matches = self.matches.filter(query_filter)
        if not matches.count():
            raise forms.ValidationError(
                _("There are no matches that satisfy " "your criteria.")
            )

        data["matches"] = matches

        return data


class ScorecardWizardBase(SessionWizardView):
    def get_context_data(self, form, **kwargs):
        context = super(ScorecardWizardBase, self).get_context_data(form, **kwargs)
        context.update(self.extra_context)
        return context

    def get_form_kwargs(self, step):
        # pass the cleaned_data from the previous step into the current step
        return self.get_cleaned_data_for_step(self.get_prev_step(step=step)) or {}

    def get_template_names(self):
        return self.app.template_path("scorecards/report.html")

    def done(self, form_list, **kwargs):
        data = self.get_all_cleaned_data()
        mode = data.get("format")
        season = data.pop("season")
        matches = data.pop("matches")
        template = data.pop("template")

        extra_context = {
            "competition": season.competition,
            "season": season,
        }

        templates = self.app.template_path(
            template, season.competition.slug, season.slug
        )

        if mode == "pdf":
            kw = {}
            if hasattr(self.request, "tenant"):
                kw["_schema_name"] = self.request.tenant.schema_name
                kw["base_url"] = self.request.build_absolute_uri("/")

            result = generate_pdf_scorecards.delay(
                matches, templates, extra_context, **kw
            )

            reverse_kwargs = {
                "competition_id": season.competition_id,
                "season_id": season.pk,
                "result_id": result.id,
            }

            redirect_to = self.app.reverse(
                "competition:season:scorecards-async", kwargs=reverse_kwargs
            )
            response = HttpResponseRedirect(redirect_to)
        else:
            output = generate_scorecards(matches, templates, extra_context)
            response = HttpResponse(output)

        return response


def scorecardwizard_factory(**kwargs):
    return type("ScorecardWizard", (ScorecardWizardBase,), kwargs)


##############################################################################
# Draw Generation
##############################################################################


class DrawGenerationWizard(SessionWizardView):
    extra_context = {}
    redirect_to = None
    stage = None
    template_name = "tournamentcontrol/competition/admin/draw_generation/wizard.html"

    def get_form_initial(self, step):
        if step == "0":
            if self.stage.pools.count():
                queryset = self.stage.pools.all()
            else:
                queryset = self.stage.division.stages.filter(pk=self.stage.pk)
            return queryset

    def get_form_kwargs(self, step):
        if step == "1":
            data = self.get_cleaned_data_for_step("0")
            matches = functools.reduce(add, [d["matches"] for d in data])
            return {"queryset": matches}
        return {}

    def get_context_data(self, form, **kwargs):
        context = super(DrawGenerationWizard, self).get_context_data(
            form=form, **kwargs
        )
        context.update(self.extra_context)
        context.update(
            {
                "model": self.stage.matches.none(),
            }
        )
        return context

    def done(self, form_list, **kwargs):
        first(reversed(form_list)).save()
        return HttpResponseRedirect(self.redirect_to)


##############################################################################
# AI Competition Structure Generation
##############################################################################


class AIPromptForm(forms.Form):
    """
    Step 1. Input natural language prompt for AI competition generation.
    """

    prompt = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "cols": 80,
                "placeholder": "Example: Build a competition for 19 Mixed Open teams. The competition must be completed in 5 days of play, inclusive of a finals series. Teams may not play any more than 3 matches each day, but should expect no less than 2 matches until the elimination stages. The top teams must play off to determine Gold, Silver and Bronze medalists. All other teams must play off to fill out the finishing order from 1-19.",
            }
        ),
        label=_("Competition Description"),
        help_text=_(
            "Describe your competition requirements in natural language. "
            "Include details like number of teams, days available, matches per day, "
            "finals structure, etc."
        ),
        max_length=2000,
    )

    include_existing_teams = forms.BooleanField(
        required=False,
        initial=False,
        label=_("Use existing teams from season"),
        help_text=_(
            "Check this box to use teams already added to this season. "
            "Otherwise, placeholder team names will be generated."
        ),
    )


class AIPlanReviewForm(forms.Form):
    """
    Step 2. Review the AI-generated plan before execution.
    """

    # This will be populated dynamically based on the plan
    plan_data = forms.CharField(widget=forms.HiddenInput())

    approve_plan = forms.BooleanField(
        required=True,
        label=_("I approve this plan"),
        help_text=_(
            "Check this box to confirm you want to execute this plan. "
            "This will create divisions, stages, pools, teams, and matches."
        ),
    )

    def __init__(self, plan: CompetitionPlan = None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if plan:
            self.initial["plan_data"] = json.dumps(asdict(plan))
            self.plan = plan
        else:
            self.plan = None

    def get_plan(self) -> CompetitionPlan:
        """Get the CompetitionPlan from form data."""
        if hasattr(self, "plan") and self.plan:
            return self.plan

        if "plan_data" in self.cleaned_data:
            data = json.loads(self.cleaned_data["plan_data"])

            # Reconstruct the plan from JSON
            divisions = []
            for div_data in data.get("divisions", []):
                stages = []
                for stage_data in div_data.get("stages", []):
                    pools = []
                    for pool_data in stage_data.get("pools", []):
                        pools.append(PoolStructure(**pool_data))

                    stage_data_copy = stage_data.copy()
                    stage_data_copy["pools"] = pools
                    stages.append(StageStructure(**stage_data_copy))

                div_data_copy = div_data.copy()
                div_data_copy["stages"] = stages
                divisions.append(DivisionStructure(**div_data_copy))

            plan_data = data.copy()
            plan_data["divisions"] = divisions

            return CompetitionPlan(**plan_data)

        return None


class AICompetitionWizardBase(SessionWizardView):
    """Base wizard for AI competition structure generation."""

    extra_context = {}
    template_name = "tournamentcontrol/competition/admin/ai_competition/wizard.html"

    def __init__(self, season=None, app=None, **kwargs):
        super().__init__(**kwargs)
        self.season = season or getattr(self, "season", None)
        self.app = app or getattr(self, "app", None)
        self.ai_service = AICompetitionService()

    def get_form_kwargs(self, step):
        """Provide additional kwargs for form initialization."""
        kwargs = super().get_form_kwargs(step)

        if step == "1":  # Plan review step
            # Get plan from previous step
            prompt_data = self.get_cleaned_data_for_step("0")
            if prompt_data:
                plan = self._generate_plan(prompt_data)
                kwargs["plan"] = plan

        return kwargs

    def get_context_data(self, form, **kwargs):
        """Add extra context for template rendering."""
        context = super().get_context_data(form=form, **kwargs)
        context.update(self.extra_context)
        context.update(
            {
                "season": self.season,
                "step_title": self._get_step_title(),
                "ai_available": self.ai_service.is_available(),
            }
        )

        # Add plan data for review step
        if self.steps.current == "1":
            prompt_data = self.get_cleaned_data_for_step("0")
            if prompt_data:
                context["plan"] = self._generate_plan(prompt_data)

        return context

    def _get_step_title(self):
        """Get title for current step."""
        step_titles = {
            "0": _("Step 1: Describe Your Competition"),
            "1": _("Step 2: Review Generated Plan"),
        }
        return step_titles.get(self.steps.current, _("AI Competition Builder"))

    def _generate_plan(self, prompt_data):
        """Generate plan from prompt data."""
        if not hasattr(self, "_cached_plan"):
            prompt = prompt_data["prompt"]

            # Prepare context about the season
            context = {
                "season_title": self.season.title,
                "competition_title": self.season.competition.title,
                "existing_teams": [],
            }

            # Add existing teams if requested
            if prompt_data.get("include_existing_teams"):
                context["existing_teams"] = [
                    team.title for team in self.season.teams.all()
                ]

            self._cached_plan = self.ai_service.generate_plan(prompt, context)

        return self._cached_plan

    def done(self, form_list, **kwargs):
        """Execute the plan when wizard is completed."""
        forms = list(form_list)
        review_form = forms[1]  # AIPlanReviewForm

        plan = review_form.get_plan()
        if plan and review_form.cleaned_data["approve_plan"]:
            try:
                execute_competition_plan(self.season, plan)

                # Add success message
                messages.success(
                    self.request,
                    _("Competition structure has been created successfully!"),
                )

            except Exception as e:
                # Add error message
                messages.error(
                    self.request,
                    _("Error creating competition structure: {}").format(str(e)),
                )

        # Redirect to season edit page
        return HttpResponseRedirect(
            reverse(
                "admin:fixja:competition:season:edit",
                kwargs={
                    "competition_id": self.season.competition_id,
                    "season_id": self.season.pk,
                },
            )
        )


def ai_competition_wizard_factory(**kwargs):
    """Factory function to create AI competition wizard class."""
    return type("AICompetitionWizard", (AICompetitionWizardBase,), kwargs)
