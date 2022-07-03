import datetime
import functools
from operator import add, or_

from dateutil.parser import parse
from django import forms
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from first import first
from formtools.wizard.views import SessionWizardView

from touchtechnology.common.forms.fields import (
    ModelChoiceField,
    ModelMultipleChoiceField,
)
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
