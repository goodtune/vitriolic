from __future__ import unicode_literals

import collections
import datetime
import json
import logging

from dateutil.parser import parse
from dateutil.rrule import DAILY, WEEKLY
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.forms import array as PGA
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q
from django.forms import BooleanField as BooleanChoiceField
from django.forms.formsets import (
    DELETION_FIELD_NAME,
    INITIAL_FORM_COUNT,
    MAX_NUM_FORM_COUNT,
    ManagementForm,
    TOTAL_FORM_COUNT,
    formset_factory,
)
from django.forms.models import (
    BaseInlineFormSet,
    BaseModelFormSet,
    inlineformset_factory,
    modelformset_factory,
)
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, ngettext
from first import first
from googleapiclient.errors import HttpError
from modelforms.forms import ModelForm
from pyparsing import ParseException

from touchtechnology.common.forms.fields import (
    ModelChoiceField,
    ModelMultipleChoiceField,
    SelectDateField,
)
from touchtechnology.common.forms.mixins import (
    BootstrapFormControlMixin,
    SuperUserSlugMixin,
    UserMixin,
)
from touchtechnology.common.forms.tz import timezone_choice
from touchtechnology.common.forms.widgets import (
    SelectDateTimeWidget as SelectDateTimeWidgetBase,
)
from touchtechnology.content.forms import PlaceholderConfigurationBase
from tournamentcontrol.competition.calc import BonusPointCalculator, Calculator
from tournamentcontrol.competition.draw import seeded_tournament
from tournamentcontrol.competition.fields import URLField
from tournamentcontrol.competition.models import (
    ByeTeam,
    Club,
    ClubAssociation,
    ClubRole,
    Competition,
    Division,
    DivisionExclusionDate,
    DrawFormat,
    Ground,
    LadderEntry,
    Match,
    Person,
    Place,
    Season,
    SeasonAssociation,
    SeasonExclusionDate,
    SeasonMatchTime,
    SimpleScoreMatchStatistic,
    Stage,
    StageGroup,
    Team,
    TeamAssociation,
    TeamRole,
    UndecidedTeam,
    Venue,
    stage_group_position_re,
)
from tournamentcontrol.competition.signals.custom import score_updated
from tournamentcontrol.competition.utils import (
    FauxQueryset,
    legitimate_bye_match,
    match_unplayed,
    time_choice,
)

logger = logging.getLogger(__name__)

EMPTY = [("", "---")]
SCORE_FIELDS = set(["home_team_score", "away_team_score"])

valid_ladder_identifiers = collections.OrderedDict(
    (
        ("win", "Win"),
        ("draw", "Draw"),
        ("loss", "Loss"),
        ("bye", "Bye"),
        ("forfeit_for", "Win by forfeit"),
        ("forfeit_against", "Loss by forfeit"),
        # Other potential identifiers, but they don't really make sense as
        # variables for use in generating a ladder formula.
        #
        # 'score_for', 'score_against', 'played'
    )
)


def ladder_points_widget(name, **attrs):
    defaults = {"placeholder": valid_ladder_identifiers[name].lower()}
    defaults.update(attrs)
    return forms.TextInput(attrs=defaults)


class LadderPointsWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        self.attrs = attrs or {}

        widgets = tuple(
            [ladder_points_widget(n, **self.attrs) for n in valid_ladder_identifiers]
        )
        super(LadderPointsWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return ""
        values = []
        for i in valid_ladder_identifiers:
            ladder_entry = LadderEntry(**{i: 1})
            calc = Calculator(ladder_entry)
            calc.parse(value)
            values.append(calc.evaluate() or None)
        return values

    def format_output(self, rendered_widgets):
        output = ""
        for label, widget in zip(valid_ladder_identifiers.values(), rendered_widgets):
            output += """
                <div class="field_wrapper">
                    <label class="field_name">{label}</label>
                    <div class="field text_input short">
                        {widget}
                    </div>
                </div>
            """.format(
                label=label, widget=widget
            )
        return output


class MatchPlayedWidget(forms.widgets.Select):
    """
    Custom widget to show a Yes/No choice field for whether a player
    took part in a match or not.

    Based on django.forms.widget.NullBooleanSelect
    """

    def __init__(self, attrs=None):
        choices = (("1", _("Yes")), ("0", _("No")))
        super(MatchPlayedWidget, self).__init__(attrs, choices)

    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        return {"1": 1, "0": 0, True: 1, False: 0, "True": 1, "False": 0}.get(
            value, None
        )


class LadderPointsField(forms.MultiValueField):
    def __init__(self, max_length=None, *args, **kwargs):
        fields = tuple(
            map(
                lambda field: forms.IntegerField(required=False, initial=0),
                valid_ladder_identifiers,
            )
        )
        kwargs["widget"] = LadderPointsWidget()
        super(LadderPointsField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        parts = [
            "{}*{}".format(*each)
            for each in zip(data_list, valid_ladder_identifiers)
            if each[0]
        ]
        return " + ".join(parts)


class SelectDateTimeWidget(SelectDateTimeWidgetBase):
    def decompress(self, value):
        """
        Value is serialized as string, so we use the dateutil.parser
        functionality to restore it to primitive datetime instance before then
        calling the parent class decompress function.
        """
        if value:
            value = parse(value)
        return super(SelectDateTimeWidget, self).decompress(value)


class ConstructFormMixin(object):
    """
    When a custom FormSet requires the ability to pass keyword arguments to a
    child form, we can simply define the ``get_defaults`` method to return a
    dictionary to be passed through to the form constructor.
    """

    def get_defaults(self):
        return {}

    def _construct_form(self, i, **kwargs):
        defaults = self.get_defaults()
        defaults.update(kwargs)
        return super(ConstructFormMixin, self)._construct_form(i, **defaults)

    @property
    def empty_form(self):
        defaults = self.get_defaults()
        form = self.form(
            auto_id=self.auto_id,
            prefix=self.add_prefix("__prefix__"),
            empty_permitted=True,
            **defaults,
        )
        self.add_fields(form, None)
        return form


class ConfigurationForm(PlaceholderConfigurationBase):
    """
    Configuration of the specific division is performed by slug rather than
    primary key so that we can simply pass through fake url components to our
    underlying views.
    """

    def __init__(self, *args, **kwargs):
        super(ConfigurationForm, self).__init__(*args, **kwargs)

        competitions = Competition.objects.values_list("slug", "title")
        self.fields["competition"] = forms.ChoiceField(
            choices=EMPTY + list(competitions), required=False, label=_("Competition")
        )
        self.fields["competition"].widget.attrs.update({"class": "form-control"})

        seasons = Season.objects.values_list("slug", "title").distinct()
        self.fields["season"] = forms.ChoiceField(
            choices=EMPTY + list(seasons), required=False, label=_("Season")
        )
        self.fields["season"].widget.attrs.update({"class": "form-control"})

    def clean_season(self):
        competition_slug = self.cleaned_data.get("competition")
        season_slug = self.cleaned_data.get("season")
        if season_slug and not competition_slug:
            raise forms.ValidationError(
                _("You can't select a season without a competition.")
            )
        elif (
            season_slug
            and not Season.objects.filter(
                competition__slug=competition_slug, slug=season_slug
            ).exists()
        ):
            raise forms.ValidationError(_("Invalid season for this competition."))
        return season_slug


class MultiConfigurationForm(PlaceholderConfigurationBase):
    def __init__(self, *args, **kwargs):
        super(MultiConfigurationForm, self).__init__(*args, **kwargs)

        competitions = Competition.objects.values_list("slug", "title")
        self.fields["competition"] = forms.MultipleChoiceField(
            choices=list(competitions),
            required=True,
            label=_("Competition"),
            widget=forms.CheckboxSelectMultiple,
        )


class RankingConfigurationForm(PlaceholderConfigurationBase):
    def __init__(self, *args, **kwargs):
        super(RankingConfigurationForm, self).__init__(*args, **kwargs)
        self.fields["start"] = forms.CharField(required=False)
        self.fields["decay"] = forms.CharField(required=False)


class PersonEditForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Person
        fields = (
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "email",
            "home_phone",
            "work_phone",
            "mobile_phone",
            "user",
        )


class PersonMergeForm(PersonEditForm):
    merge = ModelMultipleChoiceField(
        label=_("Duplicates"),
        queryset=Person.objects.all(),
        label_from_instance="get_full_name",
        widget=forms.SelectMultiple,
        help_text=_(
            "Select the duplicate members that are to be merged "
            "into this retained record."
        ),
    )
    keep_old = forms.TypedChoiceField(
        choices=(("true", "Yes"), ("false", "No")), coerce=json.loads, initial="false"
    )

    def __init__(self, *args, **kwargs):
        super(PersonMergeForm, self).__init__(*args, **kwargs)
        self.fields["merge"].queryset = self.instance.club.members.exclude(
            pk=self.instance.pk
        )

    def save(self, *args, **kwargs):
        from tournamentcontrol.competition.merge import merge_model_objects

        keep = super(PersonMergeForm, self).save(*args, **kwargs)
        return merge_model_objects(
            keep, list(self.cleaned_data["merge"]), self.cleaned_data["keep_old"]
        )


class CompetitionForm(SuperUserSlugMixin, ModelForm):
    class Meta:
        model = Competition
        fields = (
            "title",
            "short_title",
            "rank_importance",
            "enabled",
            "copy",
            "slug",
            "slug_locked",
            "clubs",
        )
        labels = {
            "copy": _("Description"),
        }


class TimezoneMixin(object):
    """
    Mixin to remove the timezone field if we are not operating in a timezone
    aware state.
    """

    def __init__(self, *args, **kwargs):
        super(TimezoneMixin, self).__init__(*args, **kwargs)
        if not settings.USE_TZ:
            self.fields.pop("timezone", None)


class SeasonForm(
    SuperUserSlugMixin, TimezoneMixin, BootstrapFormControlMixin, ModelForm
):
    class Meta:
        model = Season
        fields = (
            "title",
            "short_title",
            "copy",
            "hashtag",
            "enabled",
            "live_stream",
            "live_stream_privacy",
            "live_stream_project_id",
            "live_stream_client_id",
            "live_stream_client_secret",
            "live_stream_thumbnail",
            "timezone",
            "start_date",
            "mode",
            "forfeit_notifications",
            "complete",
            "statistics",
            "mvp_results_public",
            "slug",
            "slug_locked",
        )
        labels = {
            "copy": _("Notes (Public)"),
            "live_stream_project_id": _("Project ID"),
            "live_stream_client_id": _("Client ID"),
            "live_stream_thumbnail": _("Thumbnail URL"),
        }
        help_texts = {
            "copy": _("Optional. Will be displayed in the front end if provided."),
            "live_stream_thumbnail": _(
                "URL to the default thumbnail image for all live streams."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["live_stream_client_secret"] = forms.CharField(
            label=_("Client Secret"),
            widget=forms.PasswordInput,
            help_text=_("Leave this blank to retain the previously set value."),
            required=False,
        )
        self.fields["live_stream_client_secret"].widget.attrs["class"] = "form-control"
        self.fields["live_stream_client_secret"].widget.attrs["placeholder"] = "*" * 10

    def clean_live_stream_client_secret(self):
        project_id = self.cleaned_data.get("live_stream_project_id")
        client_id = self.cleaned_data.get("live_stream_client_id")
        data = self.cleaned_data.get("live_stream_client_secret")
        original = self.instance.live_stream_client_secret
        if not data and original and (project_id or client_id):
            return original
        return data


class VenueForm(SuperUserSlugMixin, TimezoneMixin, ModelForm):
    class Meta:
        model = Venue
        fields = (
            "title",
            "short_title",
            "abbreviation",
            "timezone",
            "latlng",
            "slug",
            "slug_locked",
        )
        labels = {
            "latlng": _("Map"),
        }


class GroundForm(SuperUserSlugMixin, TimezoneMixin, ModelForm):
    class Meta:
        model = Ground
        fields = (
            "title",
            "short_title",
            "abbreviation",
            "timezone",
            "latlng",
            "slug",
            "slug_locked",
            "live_stream",
        )
        labels = {
            "latlng": _("Map"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.venue.season.live_stream:
            self.fields.pop("live_stream")


BaseGroundFormSet = inlineformset_factory(
    Venue, Ground, fk_name="venue", fields=("title", "abbreviation"), extra=0
)


class GroundFormSet(BaseGroundFormSet):
    def _construct_form(self, i, **kwargs):
        if i >= self.initial_form_count():
            kwargs["instance"] = self.model(order=i + 1)
        return super(GroundFormSet, self)._construct_form(i, **kwargs)


class DivisionForm(SuperUserSlugMixin, ModelForm):
    def __init__(self, *args, **kwargs):
        super(DivisionForm, self).__init__(*args, **kwargs)
        if self.instance.season.mode != DAILY:
            self.fields.pop("games_per_day", None)

    class Meta:
        model = Division
        fields = (
            "title",
            "short_title",
            "rank_division",
            "copy",
            "draft",
            "points_formula",
            "bonus_points_formula",
            "games_per_day",
            "forfeit_for_score",
            "forfeit_against_score",
            "include_forfeits_in_played",
            "slug",
            "slug_locked",
        )
        labels = {
            "copy": _("Notes (Public)"),
            "forfeit_for_score": _("Forfeit win score"),
            "forfeit_against_score": _("Forfeit loss score"),
            "include_forfeits_in_played": _("Add forfeits to played"),
        }
        help_texts = {
            "copy": _("Optional. Will be displayed in the front end if provided."),
        }
        widgets = {
            "bonus_points_formula": forms.TextInput,
        }

    def _clean_formula(self, field_name, calculator_class):
        """
        Generic clean function for both the formula fields.
        """
        fake = LadderEntry()
        formula = self.cleaned_data.get(field_name)
        parser = calculator_class(fake)
        try:
            parser.parse(formula)
        except ParseException:
            raise forms.ValidationError(_("Syntax of this points formula is invalid."))
        return formula

    def clean_points_formula(self):
        return self._clean_formula("points_formula", Calculator)

    def clean_bonus_points_formula(self):
        return self._clean_formula("bonus_points_formula", BonusPointCalculator)


class StageForm(SuperUserSlugMixin, ModelForm):
    def __init__(self, *args, **kwargs):
        super(StageForm, self).__init__(*args, **kwargs)
        if self.instance.order <= 1:
            self.fields.pop("follows")
        else:
            self_or_higher_order = Q(pk=self.instance.pk) | Q(
                order__gt=self.instance.order
            )
            self.fields["follows"].queryset = self.instance.division.stages.exclude(
                self_or_higher_order
            )
            self.fields["follows"].empty_label = _("Default")

    class Meta:
        model = Stage
        fields = (
            "title",
            "short_title",
            "follows",
            "rank_importance",
            "keep_ladder",
            "scale_group_points",
            "carry_ladder",
            "keep_mvp",
            "slug",
            "slug_locked",
        )


class StageGroupForm(SuperUserSlugMixin, ModelForm):
    teams = ModelMultipleChoiceField(queryset=None)

    def __init__(self, *args, **kwargs):
        super(StageGroupForm, self).__init__(*args, **kwargs)

        # build a queryset of teams in the division that are either assigned
        # to this pool or not assigned to any other pools in this stage
        other_pools = self.instance.stage.pools.exclude(pk=self.instance.pk)

        if self.instance.stage.order > 1 and not self.instance.teams.count():
            self._undecided = True
            queryset = self.instance.stage.undecided_teams.exclude(
                stage_group__in=other_pools
            )
            label_from_instance = "title"
            initial = self.instance.undecided_teams.all()
        else:
            self._undecided = False
            queryset = self.instance.stage.division.teams.exclude(
                stage_group__in=other_pools
            )
            label_from_instance = "title"
            initial = self.instance.teams.all()

        self.fields["teams"] = ModelMultipleChoiceField(
            queryset=queryset.order_by(*queryset.model._meta.ordering),
            initial=initial,
            required=False,
            label_from_instance=label_from_instance,
            help_text=_(
                "Teams can only belong to one pool per stage. Once "
                "selected in any pool a team will no longer appear "
                "for selection here."
            ),
        )

        if self.instance.matches.exists():
            self.fields.pop("teams", None)

    def save(self, *args, **kwargs):
        if self.instance.pk and "teams" in self.fields:
            if self._undecided:
                self.instance.undecided_teams = self.cleaned_data.get("teams")
            else:
                self.instance.teams = self.cleaned_data.get("teams")
        return super(StageGroupForm, self).save(*args, **kwargs)

    class Meta:
        model = StageGroup
        fields = (
            "title",
            "short_title",
            "rank_importance",
            "carry_ladder",
            "teams",
            "slug",
            "slug_locked",
        )


class StageGroupFormSetForm(ModelForm):
    def __init__(self, stage, *args, **kwargs):
        super(StageGroupFormSetForm, self).__init__(*args, **kwargs)

    class Meta:
        model = StageGroup
        fields = ("title",)


BaseStageGroupFormSet = inlineformset_factory(
    Stage, StageGroup, form=StageGroupFormSetForm, extra=0
)


class StageGroupFormSet(ConstructFormMixin, BaseStageGroupFormSet):
    def __init__(self, stage, *args, **kwargs):
        self.stage = stage
        super(StageGroupFormSet, self).__init__(*args, **kwargs)

    def get_defaults(self):
        return {"stage": self.stage}

    def _construct_form(self, i, **kwargs):
        if i >= self.initial_form_count():
            kwargs["instance"] = self.model(stage=self.stage, order=i + 1)
        return super(StageGroupFormSet, self)._construct_form(i, **kwargs)


class UndecidedTeamForm(UserMixin, ModelForm):
    class Meta:
        model = UndecidedTeam
        fields = (
            "formula",
            "label",
        )
        help_texts = {
            "formula": _(
                "If left blank you will need to manually progress a team and "
                "the <em>label</em> below will be required for display in "
                "the draw."
            ),
            "label": _(
                "Required if formula is left blank. If formula is set this "
                "value will be ignored and not saved."
            ),
        }

    def clean_formula(self):
        # TODO move to general clean and insert error back on field so that
        # validation of `label` is not impacted by this.
        formula = self.cleaned_data.get("formula").upper()
        if formula and not stage_group_position_re.match(formula):
            raise forms.ValidationError(_("This is not a valid team formula."))
        return formula

    def clean_label(self):
        formula = self.cleaned_data.get("formula")
        label = self.cleaned_data.get("label")
        if formula:
            label = ""
        elif not label:
            raise forms.ValidationError(
                _("You must specify a label when formula is blank.")
            )
        return label


class TeamForm(SuperUserSlugMixin, ModelForm):
    def __init__(self, division, *args, **kwargs):
        super(TeamForm, self).__init__(*args, **kwargs)
        if not division.season.competition.clubs.count():
            self.fields.pop("club")
        else:
            self.fields["club"].queryset = division.season.competition.clubs
            self.fields["title"].required = False

        timeslot_fields = ("timeslots_after", "timeslots_before")

        # If the season has timeslot rules, substitute the default SelectTime
        # field for a drop-down list of timeslots.
        if self.instance.division.season.mode != WEEKLY:
            for field in timeslot_fields:
                self.fields.pop(field, None)
                setattr(self.instance, field, None)
        elif self.instance.division.season.timeslots.count():
            timeslots = self.instance.division.season.get_timeslots()
            choices = [("", "")] + [time_choice(t) for t in timeslots]

            for field in timeslot_fields:
                self.fields[field] = forms.TimeField(
                    required=False,
                    widget=forms.Select,
                    label=self.fields[field].label,
                    help_text=self.fields[field].help_text,
                )
                self.fields[field].widget.attrs = {"class": "form-control"}
                self.fields[field].widget.choices = choices

                # Ensure that the currently set time is in the list if not in
                # the rruleset defined for the season.
                value = getattr(self.instance, field)
                if value:
                    initial = time_choice(value)
                    if initial not in choices:
                        self.fields[field].widget.choices.append(initial)
                        self.fields[field].widget.choices.sort()

        # Update the set of teams which we don't want this team to clash with
        # when allocating matches. Exclude self, and order by team name.
        queryset = self.fields["team_clashes"].queryset.filter(
            division__season=self.instance.division.season
        )
        # Also exclude teams in the same division, you have to play them so
        # this will result in a clash that time.
        queryset = queryset.exclude(division=self.instance.division)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields["team_clashes"].queryset = queryset.select_related(
            "division"
        ).order_by("title", "division")
        if not queryset.count():
            self.fields.pop("team_clashes", None)

    class Meta:
        model = Team
        fields = (
            "club",
            "title",
            "short_title",
            "rank_division",
            "copy",
            "names_locked",
            "slug",
            "slug_locked",
            "timeslots_after",
            "timeslots_before",
            "team_clashes",
        )
        labels = {
            "title": _("Name"),
            "short_title": _("Abbreviation"),
            "names_locked": _("Name is locked"),
            "copy": _("Notes (Public)"),
        }
        help_texts = {
            "copy": _("Optional. Will be displayed in the front end if provided."),
            "short_title": _(
                "The abbreviated version will be used in draws " "to save space."
            ),
        }

    class Media:
        js = ("tournamentcontrol/competition/js/team.js",)

    def clean_title(self):
        club = self.cleaned_data.get("club")
        title = self.cleaned_data.get("title")
        if not title and club:
            self.data["title"] = club.title
            return club.title
        return title


class DrawFormatForm(BootstrapFormControlMixin, ModelForm):
    def clean_text(self):
        from tournamentcontrol.competition.draw import DrawGenerator

        text = self.cleaned_data.get("text").strip()
        try:
            DrawGenerator.validate(text)
        except ValueError as e:
            raise forms.ValidationError(e.message)
        return text

    class Meta:
        model = DrawFormat
        fields = ("name", "text", "teams", "is_final")


class BaseMatchFormMixin(BootstrapFormControlMixin):
    def __init__(self, *args, **kwargs):
        super(BaseMatchFormMixin, self).__init__(*args, **kwargs)

        # set the queryset of the `home_team` and `away_team` fields
        team_ids = self.instance.stage.division.teams.values_list("id", flat=True)
        undecided_team_ids = self.instance.stage.undecided_teams.values_list(
            "id", flat=True
        )

        for prefix in ("home", "away"):
            for suffix, ids in (("", team_ids), ("_undecided", undecided_team_ids)):
                field = f"{prefix}_team{suffix}"
                if field in self.fields:
                    self.fields[field].queryset = self.fields[field].queryset.filter(
                        id__in=ids
                    )

        # If the season has timeslot rules, substitute the default SelectTime
        # field for a drop-down list of timeslots.
        if self.instance.stage.division.season.timeslots.count():
            timeslots = self.instance.stage.division.season.get_timeslots(
                self.instance.date
            )

            if self.instance.home_team and self.instance.home_team.timeslots_after:
                timeslots = [
                    timeslot
                    for timeslot in timeslots
                    if timeslot >= self.instance.home_team.timeslots_after
                ]

            if self.instance.away_team and self.instance.away_team.timeslots_after:
                timeslots = [
                    timeslot
                    for timeslot in timeslots
                    if timeslot >= self.instance.away_team.timeslots_after
                ]

            if self.instance.home_team and self.instance.home_team.timeslots_before:
                timeslots = [
                    timeslot
                    for timeslot in timeslots
                    if timeslot <= self.instance.home_team.timeslots_before
                ]

            if self.instance.away_team and self.instance.away_team.timeslots_before:
                timeslots = [
                    timeslot
                    for timeslot in timeslots
                    if timeslot <= self.instance.away_team.timeslots_before
                ]

            choices = [("", "")] + [time_choice(timeslot) for timeslot in timeslots]

            # Ensure that the currently set time is in the list if not in the
            # rruleset defined for the season.
            if self.instance.time:
                initial = time_choice(self.instance.time)
                if initial not in choices:
                    choices.append(initial)
                choices.sort()

            # Only replace the widget if we were able to resolve at least 1
            # timeslot from the season -- otherwise it will be impossible for
            # the user to set a value at all.
            if timeslots and "time" in self.fields:  # Check if in higher up?
                self.fields["time"] = forms.TimeField(
                    required=False, widget=forms.Select
                )
                self.fields["time"].widget.choices = choices
                self.fields["time"].widget.attrs.setdefault("class", "form-control")


def _match_edit_form_formfield_callback(field, **kwargs):
    """
    Customise fields in the :class:`MatchEditForm`

    Set the size of the videos array with
    `settings.TOURNAMENTCONTROL_COMPETITION_VIDEOS_ARRAY_SIZE` (default is 5)
    """
    if isinstance(field, ArrayField):
        size = getattr(settings, "TOURNAMENTCONTROL_COMPETITION_VIDEOS_ARRAY_SIZE", 5)
        formfield = PGA.SplitArrayField(
            URLField(required=False),
            size,
            remove_trailing_nulls=True,
            required=False,
            label=_("Video URLs"),
            help_text=_(
                "You can provide up to %(size)d videos per match. "
                "YouTube and Vimeo links are supported."
            )
            % {
                "size": size,
            },
        )
        return formfield
    return field.formfield(**kwargs)


class MatchEditForm(BaseMatchFormMixin, ModelForm):
    """
    Use this form to make sure that the data validates:

     * that if the `stage_group` is set, it is a group of the `division`
     * that both the `home_team` and `away_team` are in the `division`
    """

    formfield_callback = _match_edit_form_formfield_callback

    def __init__(self, *args, **kwargs):
        super(MatchEditForm, self).__init__(*args, **kwargs)

        # restrict the list of referees to those registered this season
        if "referees" in self.fields:
            self.fields[
                "referees"
            ].queryset = self.instance.stage.division.season.referees.all()

        # remove `stage_group` field if the `division` has no children
        if not self.instance.stage.pools.count():
            self.fields.pop("stage_group", None)
        elif "stage_group" in self.fields:
            self.fields["stage_group"].queryset = self.instance.stage.pools.all()

        # restrict the team choices if we have pools set
        if self.instance.stage_group:
            self.fields["home_team"].queryset = self.instance.stage_group.teams.all()
            self.fields["home_team"].empty_label = ""
            if self.instance.home_team:
                self.fields["home_team"].queryset |= Team.objects.filter(
                    pk=self.instance.home_team.pk
                )
            self.fields["away_team"].queryset = self.instance.stage_group.teams.all()
            self.fields["away_team"].empty_label = ""
            if self.instance.away_team:
                self.fields["away_team"].queryset |= Team.objects.filter(
                    pk=self.instance.away_team.pk
                )

        # remove team fields depending on if we are editing a match with known
        # teams, undecided teams, or teams that still need to be evaluated.
        if not self.instance.home_team and self.instance.stage.undecided_teams.count():
            self.fields.pop("home_team", None)

        if (
            not self.instance.home_team_undecided
            and not self.instance.stage.undecided_teams.count()
        ):
            self.fields.pop("home_team_undecided", None)
            try:
                empty_label = self.instance.get_home_team()["title"]
            except TypeError:
                empty_label = "---"
            self.fields["home_team"].empty_label = empty_label

        if not self.instance.away_team and self.instance.stage.undecided_teams.count():
            self.fields.pop("away_team", None)

        if (
            not self.instance.away_team_undecided
            and not self.instance.stage.undecided_teams.count()
        ):
            self.fields.pop("away_team_undecided", None)
            try:
                empty_label = self.instance.get_away_team()["title"]
            except TypeError:
                empty_label = "---"
            self.fields["away_team"].empty_label = empty_label

    def clean_home_team(self):
        pool = self.cleaned_data.get("stage_group")
        team = self.cleaned_data.get("home_team")
        if (
            pool
            and team
            and team not in pool.teams.all()
            and team != self.instance.home_team
        ):
            raise forms.ValidationError(
                _('Team "%(team)s" is not in pool "%(pool)s".')
                % {"team": team.title, "pool": pool.title}
            )
        if (
            team
            and team not in self.instance.stage.division.teams.all()
            and team != self.instance.home_team
        ):
            raise forms.ValidationError(_("This team is not in this division."))
        return team

    def clean_away_team(self):
        pool = self.cleaned_data.get("stage_group")
        team = self.cleaned_data.get("away_team")
        if (
            pool
            and team
            and team not in pool.teams.all()
            and team != self.instance.away_team
        ):
            raise forms.ValidationError(
                _('Team "%(team)s" is not in pool "%(pool)s".')
                % {"team": team.title, "pool": pool.title}
            )
        if (
            team
            and team not in self.instance.stage.division.teams.all()
            and team != self.instance.away_team
        ):
            raise forms.ValidationError(_("This team is not in this division."))
        if team and team == self.cleaned_data.get("home_team"):
            raise forms.ValidationError(
                _("Teams cannot be scheduled to play against itself.")
            )
        return team

    def clean_home_team_undecided(self):
        pool = self.cleaned_data.get("stage_group")
        team = self.cleaned_data.get("home_team_undecided")
        if pool and team and team not in pool.undecided_teams.all():
            raise forms.ValidationError(
                _('Team "%(team)s" is not in pool "%(pool)s".')
                % {"team": team.title, "pool": pool.title}
            )
        if team and team not in self.instance.stage.undecided_teams.all():
            raise forms.ValidationError(_("This team is not in this division."))
        return team

    def clean_away_team_undecided(self):
        pool = self.cleaned_data.get("stage_group")
        team = self.cleaned_data.get("away_team_undecided")
        if pool and team and team not in pool.undecided_teams.all():
            raise forms.ValidationError(
                _('Team "%(team)s" is not in pool "%(pool)s".')
                % {"team": team.title, "pool": pool.title}
            )
        if team and team not in self.instance.stage.undecided_teams.all():
            raise forms.ValidationError(_("This team is not in this division."))
        if team and team == self.cleaned_data.get("home_team_undecided"):
            raise forms.ValidationError(
                _("Teams cannot be scheduled to play against itself.")
            )
        return team

    def clean_videos(self):
        videos = self.cleaned_data.get("videos")
        if any(videos):
            return videos

    class Meta:
        model = Match
        fields = (
            "stage_group",
            "home_team",
            "away_team",
            "home_team_undecided",
            "away_team_undecided",
            "referees",
            "label",
            "round",
            "date",
            "include_in_ladder",
            "videos",
        )
        labels = {
            "home_team_undecided": _("Home team"),
            "away_team_undecided": _("Away team"),
        }


class MatchStreamForm(MatchEditForm):
    class Meta:
        model = Match
        fields = (
            "stage_group",
            "home_team",
            "away_team",
            "home_team_undecided",
            "away_team_undecided",
            "referees",
            "label",
            "round",
            "date",
            "include_in_ladder",
            "live_stream",
            "live_stream_thumbnail",
            # "external_identifier",
        )
        labels = {
            "home_team_undecided": _("Home team"),
            "away_team_undecided": _("Away team"),
            "live_stream_thumbnail": _("Thumbnail URL"),
        }
        help_texts = {
            "live_stream_thumbnail": _(
                "URL to the thumbnail image for the live stream. "
                "If not set for the match, the season default will be used."
            ),
        }


class DrawGenerationMatchForm(MatchEditForm):
    def has_changed(self):
        # This seems like a hack to make DrawGenerationMatchFormSet work on
        # Django 1.7, see django/forms/models.py:758 and save_new_objects
        # implementation.
        return True

    class Meta(MatchEditForm.Meta):
        fields = (
            "round",
            "home_team",
            "away_team",
            "home_team_undecided",
            "away_team_undecided",
            "date",
        )


BaseDrawGenerationMatchFormSet = modelformset_factory(
    Match, form=DrawGenerationMatchForm, extra=0, can_delete=True
)


class DrawGenerationMatchFormSet(BaseDrawGenerationMatchFormSet):
    def _construct_form(self, i, **kwargs):
        if i < self.initial_form_count() and not kwargs.get("instance"):
            kwargs["instance"] = self.get_queryset()[i]
        return super(BaseModelFormSet, self)._construct_form(i, **kwargs)

    def add_fields(self, form, index):
        """A hook for adding extra fields on to each form instance."""
        super(DrawGenerationMatchFormSet, self).add_fields(form, index)
        if self.can_delete:
            form.fields[DELETION_FIELD_NAME] = BooleanChoiceField(
                label=_("Skip"), required=False
            )

    def save(self, *args, **kwargs):
        matches = []
        for form in self.forms:
            if form.instance.home_team_eval_related is not None:
                form.instance.home_team_eval_related = Match.objects.get(
                    uuid=form.instance.home_team_eval_related.uuid
                )
            if form.instance.away_team_eval_related is not None:
                form.instance.away_team_eval_related = Match.objects.get(
                    uuid=form.instance.away_team_eval_related.uuid
                )
            matches.append(form.save())
        return matches


class MatchResultForm(BootstrapFormControlMixin, ModelForm):
    """
    This form is used to make it easy to enter results for a match.
    """

    def __init__(self, *args, **kwargs):
        super(MatchResultForm, self).__init__(*args, **kwargs)
        home_team = self.instance.home_team
        away_team = self.instance.away_team
        if self.instance.is_bye:
            self.fields.pop("home_team_score")
            self.fields.pop("away_team_score")
            self.fields.pop("is_forfeit")
            self.fields.pop("forfeit_winner")
            self.fields["bye_processed"].label = str(home_team or away_team)
        else:
            if home_team and away_team:
                self.fields["home_team_score"].label = str(home_team)
                self.fields["home_team_score"].widget.attrs["placeholder"] = home_team
                self.fields["away_team_score"].label = str(away_team)
                self.fields["away_team_score"].widget.attrs["placeholder"] = away_team
                self.fields["forfeit_winner"] = ModelChoiceField(
                    queryset=Team.objects.filter(id__in=[home_team.pk, away_team.pk]),
                    label_from_instance=lambda team: team.title,
                    empty_label=_("Double forfeit"),
                    help_text=_("Select the winning team."),
                    required=False,
                )
                # We have to manually set the class to form-control as this
                # isn't a model field.
                self.fields["forfeit_winner"].widget.attrs.setdefault(
                    "class", "form-control"
                )
            else:
                self.fields.pop("is_forfeit")
                self.fields.pop("forfeit_winner")
            self.fields.pop("bye_processed")

    def clean_forfeit_winner(self):
        if not self.cleaned_data.get("is_forfeit"):
            return None
        return self.cleaned_data.get("forfeit_winner")

    def clean(self):
        home_team_score = self.cleaned_data.get("home_team_score")
        away_team_score = self.cleaned_data.get("away_team_score")
        if home_team_score is not None and away_team_score is None:
            self.add_error("away_team_score", _("Both scores are required."))
        if away_team_score is not None and home_team_score is None:
            self.add_error("home_team_score", _("Both scores are required."))
        return self.cleaned_data

    def save(self, *args, **kwargs):
        logger.debug(
            'MatchResultForm.save: updated fields "%s"',
            '", "'.join(SCORE_FIELDS.intersection(self.changed_data)),
        )

        if SCORE_FIELDS.intersection(self.changed_data):
            for rec, res in score_updated.send_robust(sender=self, match=self.instance):
                receiver = "%s.%s" % (rec.__module__, rec.__name__)
                try:
                    if isinstance(res, Exception):
                        raise res
                    logger.debug("%s: %r", receiver, res)
                except:  # noqa
                    logger.exception('Receiver "%s" did not complete.', receiver)

        return super(MatchResultForm, self).save(*args, **kwargs)

    class Meta:
        model = Match
        fields = (
            "home_team_score",
            "away_team_score",
            "bye_processed",
            "is_forfeit",
            "forfeit_winner",
        )


MatchResultFormSet = modelformset_factory(Match, extra=0, form=MatchResultForm)


class MatchWashoutForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Match
        fields = ("is_washout",)


MatchWashoutFormSet = modelformset_factory(Match, extra=0, form=MatchWashoutForm)


class MatchScheduleForm(BaseMatchFormMixin, ModelForm):
    def __init__(self, ignore_clashes=False, *args, **kwargs):
        super(MatchScheduleForm, self).__init__(*args, **kwargs)
        self.ignore_clashes = ignore_clashes

        tzinfo = timezone.get_current_timezone()
        __, tzname = timezone_choice(tzinfo.zone)

        def label_from_instance(obj):
            try:
                label = f"{'-' * 3} {obj.ground.title}"
            except ObjectDoesNotExist:
                label = obj.venue.title
            if settings.USE_TZ:
                __, tz = timezone_choice(obj.timezone)
                if tz != tzname:
                    label += " ({tz})".format(tz=tz)
            return label

        venues = collections.OrderedDict()
        for venue in self.instance.stage.division.season.venues.all():
            venues.setdefault(venue, [])

        for ground in Ground.objects.filter(venue__in=venues):
            venues[ground.venue].append(ground)

        places = FauxQueryset(Place)
        for venue, grounds in venues.items():
            places.append(venue)
            for ground in grounds:
                places.append(ground)

        self.fields["play_at"].queryset = places
        self.fields["play_at"].label_from_instance = label_from_instance
        if not settings.USE_TZ:
            self.fields["play_at"].help_text = (
                _(
                    "If not set, the timezone "
                    "for this match will be "
                    "assumed to be "
                    "<em>%s</em>."
                )
                % tzname
            )

    class Meta:
        model = Match
        fields = (
            "time",
            "play_at",
        )

    def clean_time(self):
        time = self.cleaned_data.get("time")
        if not self.ignore_clashes:
            for field in ("home", "away"):
                team = getattr(self.instance, f"{field}_team")
                after = getattr(team, "timeslots_after", None)
                before = getattr(team, "timeslots_before", None)
                # Check for team time preferences, does not rely on other
                # forms so can be checked at the form level rather than
                # formset level.
                if time and after and time < after:
                    raise forms.ValidationError(
                        _("%(team)s must play after %(time)s."),
                        code="invalid",
                        params={
                            "team": team.title,
                            "time": after.strftime("%H:%M"),
                        },
                    )
                elif time and before and time > before:
                    raise forms.ValidationError(
                        _("%(team)s must play before %(time)s."),
                        code="invalid",
                        params={
                            "team": team.title,
                            "time": before.strftime("%H:%M"),
                        },
                    )
        return time


class MatchScheduleManagementForm(ManagementForm):
    """
    Custom ``ManagementForm`` which adds a field that can control the clean
    method of the bound formset.

    When we want to skip the clash validation checking we can allow this - for
    example when it will be impossible to save the form otherwise.
    """

    ignore_clashes = forms.BooleanField(initial=0)


BaseMatchScheduleFormSet = modelformset_factory(Match, extra=0, form=MatchScheduleForm)


class MatchScheduleFormSet(BaseMatchScheduleFormSet):
    def _management_form(self):
        """
        Taken directly from ``django.forms.formsets.BaseFormSet`` and adjusted
        to make use of our custom ``ManagementForm`` subclass.

        TODO: provide a patch to upstream Django which allows a formset to
              configure, by way of class attribute, the ManagementForm class
              to instantiate.
        """
        if self.is_bound:
            form = MatchScheduleManagementForm(
                data=self.data, auto_id=self.auto_id, prefix=self.prefix
            )
            if not form.is_valid():
                raise forms.ValidationError(
                    "MatchScheduleManagementForm data "
                    "is missing or has been tampered "
                    "with"
                )
        else:
            form = MatchScheduleManagementForm(
                auto_id=self.auto_id,
                prefix=self.prefix,
                initial={
                    TOTAL_FORM_COUNT: self.total_form_count(),
                    INITIAL_FORM_COUNT: self.initial_form_count(),
                    MAX_NUM_FORM_COUNT: self.max_num,
                },
            )
        return form

    management_form = property(_management_form)

    def _construct_form(self, i, **kwargs):
        # obtain the ManagementForm.cleaned_data or fake empty
        mfcd = getattr(self.management_form, "cleaned_data", {})
        # determine form properties
        ignore_clashes = bool(mfcd.get("ignore_clashes", False))
        # construct the form with our additional keyword arguments
        return super(MatchScheduleFormSet, self)._construct_form(
            i, ignore_clashes=ignore_clashes, **kwargs
        )

    def clean(self):
        if self.management_form.cleaned_data.get("ignore_clashes"):
            return

        if any(self.errors):
            return

        teams = {}
        scheduled = {}

        # Build up a table of all possible conflicts
        dates = self.queryset.dates("date", "day")
        for m in self.queryset.model._default_manager.exclude(
            pk__in=self.queryset
        ).exclude(play_at=None, time=None):
            if m.date in dates:
                teams.setdefault(m.home_team, []).append(m.time)
                teams.setdefault(m.away_team, []).append(m.time)
                scheduled.setdefault((m.play_at, m.time), []).append(m)

        for i in range(0, self.total_form_count()):
            match = self.forms[i].cleaned_data.get("id")
            play_at = self.forms[i].cleaned_data.get("play_at")
            time = self.forms[i].cleaned_data.get("time")

            if play_at and time:
                key = (play_at, time)
                if scheduled.get(key):
                    err = _(
                        "Another match is already scheduled for " "this time & place."
                    )
                    self.forms[i].add_error("play_at", err)
                scheduled.setdefault(key, []).append(match)

            if match.home_team and time:
                for t in match.home_team.team_clashes.all():
                    if time in teams.get(t, []):
                        self.forms[i].add_error("time", t)
                teams.setdefault(match.home_team, []).append(time)

            if match.away_team and time:
                for t in match.away_team.team_clashes.all():
                    if time in teams.get(t, []):
                        self.forms[i].add_error("time", t)
                teams.setdefault(match.away_team, []).append(time)


class RescheduleDateForm(forms.Form):
    def __init__(self, matches, date, *args, **kwargs):
        self.original = date
        self.matches = matches.filter(date=date)
        super(RescheduleDateForm, self).__init__(*args, **kwargs)
        self.fields["date"] = SelectDateField(initial=date)

    def clean(self):
        errors = {}

        try:
            super(RescheduleDateForm, self).clean()
        except ValidationError as e:
            e.update_error_dict(errors)

        value = self.cleaned_data.get("date")
        representative_match = self.matches.earliest("date")

        if value < representative_match.stage.division.season.start_date:
            errors.setdefault("date", []).append(
                "This date is before the start of the season"
            )

        if errors:
            raise forms.ValidationError(errors)

    def save(self, *args, **kwargs):
        date = self.cleaned_data.get("date", self.original)
        if self.original is not date:
            return (date, self.matches.values_list("pk", flat=True))


RescheduleDateFormSetBase = formset_factory(RescheduleDateForm)


class RescheduleDateFormSet(ConstructFormMixin, RescheduleDateFormSetBase):
    def __init__(self, matches, dates, *args, **kwargs):
        self.matches = matches
        self.dates = dates
        super(RescheduleDateFormSet, self).__init__(*args, **kwargs)

    def total_form_count(self):
        return len(self.dates)

    def get_defaults(self):
        return {"matches": self.matches}

    def _construct_form(self, i, **kwargs):
        return super(RescheduleDateFormSet, self)._construct_form(
            i, date=self.dates[i], **kwargs
        )

    def save(self, *args, **kwargs):
        update = {}
        for form in self.forms:
            try:
                date, pks = form.save()
                update.setdefault(date, set()).update(pks)
            except TypeError:
                pass
        count = 0
        for date, pks in update.items():
            for match in self.matches.filter(match_unplayed, pk__in=pks):
                match.date = date
                match.clean()
                match.save()
                count += 1
        return count


class ProgressMatchesForm(BaseMatchFormMixin, ModelForm):
    def __init__(self, instance, *args, **kwargs):
        super(ProgressMatchesForm, self).__init__(instance=instance, *args, **kwargs)
        instance.evaluated = True
        home_team, away_team = instance.eval()

        # lazily move this into the init so we can remove RedefineModelForm
        self.fields["home_team"].empty_label = ""
        self.fields["away_team"].empty_label = ""

        # set initial form values when available, prevents need for client
        # side javascript hack used previously.
        self.initial["home_team"] = home_team
        self.initial["away_team"] = away_team

        if (
            isinstance(home_team, ByeTeam)
            or self.instance.home_team
            or home_team is None
        ):
            self.fields.pop("home_team", None)
        elif self.instance.home_team_eval_related:
            self.fields["home_team"].queryset = self.fields[
                "home_team"
            ].queryset.filter(
                pk__in=(
                    self.instance.home_team_eval_related.home_team_id,
                    self.instance.home_team_eval_related.away_team_id,
                )
            )

        if (
            isinstance(away_team, ByeTeam)
            or self.instance.away_team
            or away_team is None
        ):
            self.fields.pop("away_team", None)
        elif self.instance.away_team_eval_related:
            self.fields["away_team"].queryset = self.fields[
                "away_team"
            ].queryset.filter(
                pk__in=(
                    self.instance.away_team_eval_related.home_team_id,
                    self.instance.away_team_eval_related.away_team_id,
                )
            )

    def has_changed(self):
        # Because we're setting the initial directly in the __init__ above we
        # need to always mark the data as changed.
        return True

    def save(self, *args, **kwargs):
        self.instance.stage.matches_needing_printing.add(self.instance)
        return super(ProgressMatchesForm, self).save(*args, **kwargs)

    class Meta:
        model = Match
        fields = (
            "home_team",
            "away_team",
        )


ProgressMatchesFormSet = modelformset_factory(Match, form=ProgressMatchesForm, extra=0)


class ProgressTeamsForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProgressTeamsForm, self).__init__(*args, **kwargs)
        teams = self.instance.choices.order_by("title")
        self.fields["team"] = ModelChoiceField(
            queryset=teams, label_from_instance="title"
        )

    def save(self, *args, **kwargs):
        team = self.cleaned_data.get("team")
        self.instance.home_games.update(home_team=team)
        self.instance.away_games.update(away_team=team)
        return self.instance

    class Meta:
        model = UndecidedTeam
        fields = ("id",)


BaseProgressTeamsFormSet = modelformset_factory(
    UndecidedTeam, form=ProgressTeamsForm, extra=0
)


class ProgressTeamsFormSet(BaseProgressTeamsFormSet):
    def __init__(self, stage, *args, **kwargs):
        self.stage = stage
        super(ProgressTeamsFormSet, self).__init__(*args, **kwargs)

    def get_queryset(self):
        qs = super(ProgressTeamsFormSet, self).get_queryset()
        return qs.filter(stage=self.stage)

    def clean(self):
        teams = {}

        for i, form in enumerate(self.forms):
            if not hasattr(form, "cleaned_data"):
                continue
            teams.setdefault(form.cleaned_data.get("team"), []).append(i)

        for team, rows in teams.items():
            if len(rows) > 1:
                for i in rows:
                    self.forms[i].add_error(
                        "team", _("You can only progress a team into one position.")
                    )

    def save(self, *args, **kwargs):
        res = super(ProgressTeamsFormSet, self).save(*args, **kwargs)
        self.stage.matches_needing_printing.set(
            self.stage.matches.exclude(legitimate_bye_match)
        )
        return res


class DrawGenerationForm(BootstrapFormControlMixin, forms.Form):
    start_date = SelectDateField()
    format = ModelChoiceField(queryset=DrawFormat.objects.all())
    rounds = forms.IntegerField(required=False, min_value=1)
    offset = forms.IntegerField(required=False)

    def __init__(self, initial, *args, **kwargs):
        super(DrawGenerationForm, self).__init__(*args, **kwargs)
        self.instance = initial

        # ensure we have an even number for filtering the `DrawFormat` table

        if isinstance(self.instance, Stage):
            teams = first(
                (self.instance.teams.count(), self.instance.undecided_teams.count()),
                default=0,
            )

        elif isinstance(self.instance, StageGroup):
            teams = first(
                (self.instance.undecided_teams.count(), self.instance.teams.count()),
                default=0,
            )

        else:
            teams = 0

        if teams % 2:
            teams += 1

        # produce a list of appropriate `DrawFormat` options
        suitable_draw_formats = DrawFormat.objects.filter(
            Q(teams__in=(teams, teams - 1)) if teams else Q()
        )
        self.fields["format"].queryset = suitable_draw_formats
        self.fields["format"].help_text = _(
            "Choose the competition format for this %s"
        ) % (self.instance._meta.verbose_name.lower(),)

        # determine the best logical start date
        start_date = self.instance.division.season.start_date or datetime.date.today()
        self.fields["start_date"].initial = start_date

    @property
    def generator(self):
        format = self.cleaned_data.get("format")
        start_date = self.cleaned_data.get("start_date")
        return format.generator(self.instance, start_date)

    def clean_start_date(self):
        start_date = self.cleaned_data.get("start_date")
        if not start_date:
            raise forms.ValidationError("foo")
        return start_date

    def clean_rounds(self):
        format = self.cleaned_data.get("format")
        rounds = self.cleaned_data.get("rounds")
        if not rounds and format:
            rounds = len(self.generator.rounds)
        return rounds

    def clean(self):
        data = super(DrawGenerationForm, self).clean()
        try:
            matches = self.get_matches()
        except AttributeError:
            logger.exception("Can't build draw without a format selection.")
        else:
            data.setdefault("matches", matches)
        return data

    def get_matches(self):
        n = self.cleaned_data.get("rounds")
        offset = self.cleaned_data.get("offset") or 0
        return self.generator.generate(n, offset)


DrawGenerationFormSetBase = formset_factory(
    form=DrawGenerationForm, extra=0, can_delete=True
)


class DrawGenerationFormSet(BootstrapFormControlMixin, DrawGenerationFormSetBase):
    def add_fields(self, form, index):
        """A hook for adding extra fields on to each form instance."""
        super(DrawGenerationFormSet, self).add_fields(form, index)
        if self.can_delete:
            form.fields[DELETION_FIELD_NAME] = BooleanChoiceField(
                label=_("Skip"), required=False
            )


class ImportCsvForm(forms.Form):
    csv = forms.FileField(
        label=_("File"),
        help_text=_(
            "Any columns in your data file that " "are unknown will be discarded."
        ),
    )

    def clean_csv(self):
        """
        The error handling could be better if we make use of `libmagic` but
        hopefully this will prevent the vast majority of failures.
        """
        csv = self.cleaned_data.get("csv")
        main, subtype = csv.content_type.split("/", 1)
        if main != "text":
            raise forms.ValidationError(_("You must submit a comma separated file."))
        return csv


class BaseClubAssociationFormSet(UserMixin, ConstructFormMixin, BaseInlineFormSet):
    def get_defaults(self):
        return {"user": self.user, "club": self.instance}


class BaseTeamAssociationFormSet(UserMixin, ConstructFormMixin, BaseInlineFormSet):
    def get_defaults(self):
        return {"user": self.user, "team": self.instance}


class BaseSeasonAssociationFormSet(UserMixin, ConstructFormMixin, BaseModelFormSet):
    def __init__(self, club, season, *args, **kwargs):
        self.club = club
        self.season = season
        super(BaseSeasonAssociationFormSet, self).__init__(*args, **kwargs)

    def get_defaults(self):
        return {"user": self.user, "club": self.club, "season": self.season}


class ClubAssociationForm(UserMixin, ModelForm):
    def __init__(self, club, *args, **kwargs):
        super(ClubAssociationForm, self).__init__(*args, **kwargs)
        self.fields["person"].queryset = club.members.all()
        if self.instance.person_id is None:
            self.fields["person"].required = False

    class Meta:
        model = ClubAssociation
        fields = (
            "person",
            "roles",
        )


class TeamAssociationForm(UserMixin, ModelForm):
    def __init__(self, team, *args, **kwargs):
        super(TeamAssociationForm, self).__init__(*args, **kwargs)
        self.fields["person"].queryset = team.club.members.all()
        self.fields[
            "roles"
        ].queryset = team.division.season.competition.team_roles.all()

    class Meta:
        model = TeamAssociation
        fields = (
            "number",
            "person",
            "is_player",
            "roles",
        )


class SeasonAssociationForm(UserMixin, ModelForm):
    def __init__(self, club, season, *args, **kwargs):
        super(SeasonAssociationForm, self).__init__(*args, **kwargs)
        self.fields["person"].queryset = club.members.all()
        self.fields["roles"].queryset = season.competition.club_roles.all()

        self.instance.club = club
        self.instance.season = season

    class Meta:
        model = SeasonAssociation
        fields = ("person", "roles")


ClubAssociationFormSet = inlineformset_factory(
    Club,
    ClubAssociation,
    form=ClubAssociationForm,
    formset=BaseClubAssociationFormSet,
    extra=0,
)

TeamAssociationFormSet = inlineformset_factory(
    Team,
    TeamAssociation,
    form=TeamAssociationForm,
    formset=BaseTeamAssociationFormSet,
    extra=0,
)

SeasonAssociationFormSet = modelformset_factory(
    SeasonAssociation,
    form=SeasonAssociationForm,
    formset=BaseSeasonAssociationFormSet,
    extra=0,
    can_delete=True,
)


class BaseSeasonExclusionFormSet(UserMixin, BaseInlineFormSet):
    pass


SeasonExclusionFormSet = inlineformset_factory(
    Season,
    SeasonExclusionDate,
    fields=("date",),
    formset=BaseSeasonExclusionFormSet,
    extra=0,
)


class BaseDivisionExclusionFormSet(UserMixin, BaseInlineFormSet):
    pass


DivisionExclusionFormSet = inlineformset_factory(
    Division,
    DivisionExclusionDate,
    fields=("date",),
    formset=BaseDivisionExclusionFormSet,
    extra=0,
)


class ClubRoleForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = ClubRole
        fields = ("name",)


class TeamRoleForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = TeamRole
        fields = ("name",)


class SimpleScoreMatchStatisticForm(ModelForm):
    class Meta:
        model = SimpleScoreMatchStatistic
        fields = ("played", "number", "points", "mvp")
        widgets = {
            "played": MatchPlayedWidget,
        }

    def has_changed(self):
        """
        Ensure that the entry is always updated, otherwise the default of
        played won't result in a cap being awarded *unless* one of the other
        fields is populated.
        """
        return True

    def clean_points(self):
        points = self.cleaned_data["points"]
        if points is None:
            return 0
        return points


BaseMatchStatisticFormset = modelformset_factory(
    SimpleScoreMatchStatistic,
    form=SimpleScoreMatchStatisticForm,
    extra=0,
)


class MatchStatisticFormset(BaseMatchStatisticFormset):
    def __init__(self, score, *args, **kwargs):
        super(MatchStatisticFormset, self).__init__(*args, **kwargs)
        self.score = score

    def _construct_form(self, i, **kwargs):
        if i < self.initial_form_count() and not kwargs.get("instance"):
            kwargs["instance"] = self.get_queryset()[i]
        return super(BaseModelFormSet, self)._construct_form(i, **kwargs)

    def clean(self):
        if any(self.errors):
            raise forms.ValidationError(
                _("There are errors you must fix " "before we can verify the scores.")
            )

        if self.score is None:
            raise forms.ValidationError(
                _(
                    "You must set the simple match score prior to entering "
                    "detailed match statistics."
                )
            )

        score = sum([f.cleaned_data["points"] for f in self.forms])
        if score != self.score:
            raise forms.ValidationError(
                _(
                    "Total number of points (%(points)d) does not equal total "
                    "number of scores (%(scores)d) for this team."
                )
                % {"points": score, "scores": self.score}
            )

        players = len([f for f in self.forms if f.cleaned_data["played"]])
        maximum = 14  # FIXME this maximum should not be hard-coded
        if players > maximum:
            message = (
                ngettext(
                    "A maximum of %(max)d players may participate in a match, "
                    "there is %(count)d selected.",
                    "A maximum of %(max)d players may participate in a match, "
                    "there are %(count)d selected.",
                    players,
                )
                % {"max": maximum, "count": players}
            )
            raise forms.ValidationError(message)

    def save(self, *args, **kwargs):
        # Should look into the correct solution. I think it should be to overload save_new
        # on the base Form to attach it to the team... that seems to be the only reason we
        # need to pre-populate with a "faux queryset" in the FormSet?
        stats = []
        for form in self.forms:
            stats.append(form.save())
        return stats


SeasonMatchTimeFormSet = inlineformset_factory(
    Season,
    SeasonMatchTime,
    fk_name="season",
    fields=(
        "start_date",
        "end_date",
        "start",
        "interval",
        "count",
    ),
    extra=0,
    can_delete=True,
)


class TournamentScheduleForm(BootstrapFormControlMixin, forms.Form):
    team_hook = forms.CharField(
        widget=forms.Textarea,
        label="Teams",
        help_text="Enter team names, one per line, in seeding order.",
    )
    days_available = forms.IntegerField(
        min_value=1,
        label="How many days of competition are there?",
        help_text="Including the final series.",
    )
    max_per_day = forms.IntegerField(
        initial=3,
        min_value=0,
        label="What is the daily maximum number of games a team may play?",
    )
    min_per_day = forms.IntegerField(
        initial=1,
        min_value=0,
        label="What is the daily minimum number of games a team must play?",
        help_text="Only applies to preliminary stages.",
    )

    def get_teams(self):
        return [line for line in self.cleaned_data["team_hook"].splitlines() if line]

    def get_context(self):
        assert self.is_valid()

        seeded_teams = self.get_teams()
        days_available = self.cleaned_data["days_available"]
        max_per_day = self.cleaned_data["max_per_day"]
        min_per_day = self.cleaned_data["min_per_day"]

        context = seeded_tournament(
            seeded_teams, days_available, max_per_day, min_per_day
        )
        return context


class DivisionTournamentScheduleForm(TournamentScheduleForm):
    team_hook = ModelChoiceField(
        queryset=(
            Division.objects.filter(teams__isnull=False)
            .order_by("season__competition", "season")
            .distinct()
            .select_related()
        ),
        label_from_instance=lambda o: "{} - {} - {}".format(
            o.season.competition.title,
            o.season.title,
            o.title,
        ),
        label="Division",
    )

    def get_absolute_url(self):
        division = self.cleaned_data["team_hook"]
        if division.matches.count():
            return reverse_lazy(
                "competition:division",
                kwargs=dict(
                    competition=division.season.competition.slug,
                    season=division.season.slug,
                    division=division.slug,
                ),
            )

    def get_teams(self):
        return self.cleaned_data["team_hook"].teams.order_by("order")


class StreamControlForm(forms.Form):
    status = forms.ChoiceField(
        label="Live Streaming Control",
        choices=(
            ("testing", "Testing"),
            ("live", "Start streaming"),
            ("complete", "Stop streaming"),
        ),
        widget=forms.RadioSelect,
        required=True,
        help_text=mark_safe(
            "Start streams about 1 minute before matches start.<br/>"
            "Stop streams about 1 minute after matches conclude."
        ),
    )

    def save(self, request, youtube, queryset):
        broadcast_status = self.cleaned_data["status"]

        for match in queryset:
            try:
                youtube.liveBroadcasts().transition(
                    broadcastStatus=broadcast_status,
                    id=match.external_identifier,
                    part="snippet,status",
                ).execute()
            except HttpError as exc:
                messages.error(request, f"{match}: {exc.reason}")
            else:
                messages.success(request, f"{match}: broadcast is {broadcast_status!r}")
