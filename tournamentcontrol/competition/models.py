# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import collections
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

import django
import pytz
from cloudinary.models import CloudinaryField
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MINUTELY, WEEKLY, rrule, rruleset
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres import fields as PG
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, DateField, DateTimeField, Q, Sum, TimeField
from django.db.models.deletion import CASCADE, PROTECT, SET_NULL
from django.template import Template
from django.template.loader import get_template
from django.utils import timezone
from django.utils.functional import cached_property, lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from google_auth_oauthlib.flow import Flow
from requests import HTTPError

from touchtechnology.admin.mixins import AdminUrlMixin as BaseAdminUrlMixin
from touchtechnology.common.db.models import (
    BooleanField,
    ForeignKey,
    HTMLField,
    LocationField,
    ManyToManyField,
)
from touchtechnology.common.models import SitemapNodeBase
from tournamentcontrol.competition.constants import (
    GENDER_CHOICES,
    LiveStreamPrivacy,
    PYTZ_TIME_ZONE_CHOICES,
    SEASON_MODE_CHOICES,
    WIN_LOSE,
)
from tournamentcontrol.competition.managers import (
    LadderEntryManager,
    MatchManager,
)
from tournamentcontrol.competition.mixins import ModelDiffMixin
from tournamentcontrol.competition.query import (
    DivisionQuerySet,
    StageQuerySet,
    StatisticQuerySet,
)
from tournamentcontrol.competition.signals import match_forfeit
from tournamentcontrol.competition.utils import (
    FauxQueryset,
    combine_and_localize,
    stage_group_position,
    stage_group_position_re,
    team_and_division,
)
from tournamentcontrol.competition.validators import validate_hashtag

logger = logging.getLogger(__name__)
lazy_get_template = lazy(get_template, Template)

match_title_tpl = lazy_get_template("tournamentcontrol/competition/_match_title.txt")

stage_group_position_tpl = lazy_get_template(
    "tournamentcontrol/competition/_stage_group_position.txt"
)

win_lose_team_tpl = lazy_get_template(
    "tournamentcontrol/competition/_win_lose_team.txt"
)


class AdminUrlMixin(BaseAdminUrlMixin):
    def _get_url_args(self):
        return (self.pk,)


class RankDivisionMixin(models.Model):
    rank_division_parent_attr = None

    rank_division = models.ForeignKey(
        "RankDivision", null=True, blank=True, on_delete=PROTECT
    )

    @property
    def rank_division_parent(self):
        return getattr(self, self.rank_division_parent_attr)

    def get_rank_division(self):
        if self.rank_division is not None:
            return self.rank_division
        if self.rank_division_parent_attr:
            return self.rank_division_parent.get_rank_division()

    class Meta:
        abstract = True


class RankImportanceMixin(models.Model):
    rank_importance_parent_attr = None

    rank_importance = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True
    )

    @property
    def rank_importance_parent(self):
        if isinstance(self.rank_importance_parent_attr, str):
            return getattr(self, self.rank_importance_parent_attr)
        if isinstance(self.rank_importance_parent_attr, (list, tuple)):
            for attr in self.rank_importance_parent_attr:
                obj = getattr(self, attr)
                if obj is not None:
                    return obj

    def get_rank_importance(self):
        if self.rank_importance is not None:
            return self.rank_importance
        if self.rank_importance_parent_attr:
            return self.rank_importance_parent.get_rank_importance()

    class Meta:
        abstract = True


class TimeZoneChoiceField(forms.ChoiceField):
    """
    Simple customisation of a ``forms.ChoiceField`` that allows a default
    declaration of ``PYTZ_TIME_ZONE_CHOICES`` to fill the ``choices`` without
    the need to add this on the model field declaration.

    ``PYTZ_TIME_ZONE_CHOICES`` is dependant upon the currently installed
    version of ``pytz`` and this was affecting the migrations framework.
    """

    def __init__(self, max_length=None, *args, **kwargs):
        choices = kwargs.pop("choices", PYTZ_TIME_ZONE_CHOICES)
        if django.VERSION[:2] >= (1, 11):
            kwargs.pop("empty_value", None)
        super(TimeZoneChoiceField, self).__init__(choices=choices, *args, **kwargs)


class TimeZoneField(models.CharField):
    """
    Simple customisation of a ``models.CharField`` that allows a default
    declaration of ``PYTZ_TIME_ZONE_CHOICES`` to fill the ``choices`` without
    the need to add this on the model field declaration.

    ``PYTZ_TIME_ZONE_CHOICES`` is dependant upon the currently installed
    version of ``pytz`` and this was affecting the migrations framework.
    """

    def deconstruct(self):
        name, path, args, kwargs = super(TimeZoneField, self).deconstruct()
        return name, "django.db.models.CharField", args, kwargs

    def formfield(self, form_class=TimeZoneChoiceField, *args, **kwargs):
        required = kwargs.pop("required", settings.USE_TZ)
        return super(TimeZoneField, self).formfield(
            form_class=form_class, required=required, *args, **kwargs
        )


class LadderPointsField(models.TextField):
    def formfield(self, form_class=None, **kwargs):
        from tournamentcontrol.competition.forms import (
            LadderPointsField as LadderPointsFormField,
        )

        if form_class is None:
            form_class = LadderPointsFormField
        return super(LadderPointsField, self).formfield(form_class=form_class, **kwargs)


class TwitterField(models.CharField):
    def formfield(self, form_class=None, **kwargs):
        if form_class is None:
            form_class = forms.RegexField
            kwargs.setdefault("regex", r"^@[\w_]+$")
        return super(TwitterField, self).formfield(form_class=form_class, **kwargs)


class OrderedSitemapNode(SitemapNodeBase):
    copy = HTMLField(blank=True)
    order = models.PositiveIntegerField(default=1)

    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.title)

    def __str__(self):
        return self.title

    class Meta:
        abstract = True
        ordering = ("order",)


class Competition(AdminUrlMixin, RankImportanceMixin, OrderedSitemapNode):
    enabled = BooleanField(default=True)
    clubs = ManyToManyField("Club", blank=True, related_name="competitions")

    def _get_admin_namespace(self):
        return "admin:fixja:competition"

    class Meta(OrderedSitemapNode.Meta):
        pass


class Club(AdminUrlMixin, SitemapNodeBase):
    email = models.EmailField(max_length=255, blank=True)
    website = models.URLField(max_length=255, blank=True)
    twitter = TwitterField(
        max_length=50,
        blank=True,
        help_text=_("Official Twitter name for use in " 'social "mentions"'),
    )
    facebook = models.URLField(max_length=255, blank=True)
    youtube = models.URLField(max_length=255, blank=True)
    primary = ForeignKey(
        "Person",
        blank=True,
        null=True,
        related_name="+",
        verbose_name=_("Primary contact"),
        label_from_instance="get_full_name",
        help_text=_("Appears on the front-end with other " "club information."),
        on_delete=PROTECT,
    )
    primary_position = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Position"),
        help_text=_("Position of the primary " "contact"),
    )
    abbreviation = models.CharField(
        max_length=3,
        blank=True,
        help_text=_("Optional 3-letter " "abbreviation to be used on " "scoreboards."),
    )

    class Meta:
        ordering = ("title",)

    @cached_property
    def _mvp_related(self):
        """
        Supercedes _mvp_annotate due to GROUP BY exceptions. Take full control
        of the query. See the history for the earlier implementation.
        """
        query = """
            SELECT
                "competition_person"."uuid",
                "competition_person"."first_name",
                "competition_person"."last_name",
                "competition_person"."gender",
                "competition_person"."date_of_birth",
                "competition_person"."club_id",
                "competition_person"."user_id",
                SUM("competition_simplescorematchstatistic"."played") AS "stats_played",
                MIN("competition_match"."date") AS "debut",
                SUM("competition_simplescorematchstatistic"."points") AS "stats_points",
                COUNT("competition_teamassociation"."id") AS "teams_count",
                "%(user)s"."id"
            FROM
                "competition_person"
            LEFT OUTER JOIN
                "competition_simplescorematchstatistic" ON
                ("competition_person"."uuid" = "competition_simplescorematchstatistic"."player_id")
            LEFT OUTER JOIN
                "competition_match" ON
                ("competition_simplescorematchstatistic"."match_id" = "competition_match"."id")
            LEFT OUTER JOIN
                "competition_teamassociation" ON (
                    "competition_person"."uuid" = "competition_teamassociation"."person_id"
                    AND (
                        "competition_match"."home_team_id" = "competition_teamassociation"."team_id"
                        OR "competition_match"."away_team_id" = "competition_teamassociation"."team_id"
                    )
                )
            LEFT OUTER JOIN
                "%(user)s" ON ("competition_person"."user_id" = "%(user)s"."id")
            WHERE
                "competition_person"."club_id" = %%(club)s
            GROUP BY
                "competition_person"."uuid",
                "competition_person"."first_name",
                "competition_person"."last_name",
                "competition_person"."gender",
                "competition_person"."date_of_birth",
                "competition_person"."club_id",
                "competition_person"."user_id",
                "%(user)s"."id"
            ORDER BY
                "competition_person"."last_name" ASC,
                "competition_person"."first_name" ASC
        """ % {
            "user": get_user_model()._meta.db_table
        }
        params = {
            "club": self.pk,
        }
        members = FauxQueryset(Person)
        for member in Person.objects.raw(query, params):
            members.append(member)
        res = {
            "members": members,
        }
        return res

    @cached_property
    def _mvp_select_related(self):
        res = {
            "teams": [
                "division__season__competition",
            ],
        }
        return res

    @cached_property
    def _mvp_only(self):
        res = {
            "teams": [
                "club",
                "title",
                "division__title",
                "division__short_title",
                "division__season__title",
                "division__season__short_title",
                "division__season__start_date",
                "division__season__competition__title",
                "division__season__competition__short_title",
                "division__season__competition__order",
            ],
        }
        return res

    def _get_admin_namespace(self):
        return "admin:fixja:club"

    def __str__(self):
        return self.title

    @property
    def matches(self):
        home = Match.objects.filter(home_team__club=self).select_related(
            "home_team", "away_team"
        )
        away = Match.objects.filter(away_team__club=self).select_related(
            "home_team", "away_team"
        )
        return home | away


class RankDivision(AdminUrlMixin, OrderedSitemapNode):
    enabled = BooleanField(default=True)

    class Meta(OrderedSitemapNode.Meta):
        pass


class RankTeam(models.Model):
    club = models.ForeignKey(Club, on_delete=CASCADE)
    division = models.ForeignKey(RankDivision, on_delete=CASCADE)

    class Meta:
        ordering = ("division",)
        unique_together = ("club", "division")

    def __str__(self):
        return "%s (%s)" % (self.club, self.division)

    def __repr__(self):
        return "%r, %r" % (self.club, self.division)

    def natural_key(self):
        return "{} {}".format(self.club.title, self.division.title)


class RankPoints(models.Model):
    team = models.ForeignKey(RankTeam, on_delete=CASCADE)
    points = models.DecimalField(default=0, max_digits=6, decimal_places=3)
    date = models.DateField()

    class Meta:
        ordering = ("-date", "team", "-points")

    def __str__(self):
        return "%r, %r, %r" % (self.team, self.points, self.date)


class Person(AdminUrlMixin, models.Model):
    """
    This is not tied to the `django.contrib.auth.models.User` model because
    I don't want to clutter the user-space with hundreds of accounts that may
    never be used for authentication.

    We should however make it easy to clone a `Person` into a `User` at some
    point - not just now though.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    club = ForeignKey(
        "competition.Club",
        related_name="members",
        label_from_instance="title",
        on_delete=PROTECT,
    )

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)

    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = DateField(blank=True, null=True)

    email = models.EmailField(blank=True)
    home_phone = models.CharField(max_length=30, blank=True)
    work_phone = models.CharField(max_length=30, blank=True)
    mobile_phone = models.CharField(max_length=30, blank=True)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=SET_NULL
    )

    def _get_admin_namespace(self):
        return "admin:fixja:club:person"

    def _get_url_args(self):
        return (self.club_id, self.pk)

    @cached_property
    def _mvp_select_related(self):
        res = {
            "statistics": [
                "match__stage__division__season__competition",
                "match__home_team",
                "match__away_team",
            ],
        }
        return res

    class Meta:
        ordering = ("last_name", "first_name")
        verbose_name_plural = "people"

    def __str__(self):
        return self.get_full_name

    @property
    def get_full_name(self):
        return "{}, {}".format(self.last_name, self.first_name)

    @cached_property
    def age(self):
        if self.date_of_birth:
            age = relativedelta(timezone.now().date(), self.date_of_birth)
            return age.years

    @cached_property
    def teams(self):
        return Team.objects.filter(
            pk__in=self.teamassociation_set.values_list("team_id", flat=True)
        )

    @cached_property
    def can_delete(self):
        if self.statistics.exists():
            return False

        now = timezone.now()
        if self.teamassociation_set.filter(team__division__season__start_date__lt=now):
            return False

        return True

    @cached_property
    def stats(self):
        return self.statistics.aggregate(
            played=Sum("played"),
            points=Sum("points"),
        )


class Season(AdminUrlMixin, RankImportanceMixin, OrderedSitemapNode):
    rank_importance_parent_attr = "competition"

    competition = ForeignKey(Competition, related_name="seasons", on_delete=PROTECT)
    hashtag = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        validators=[validate_hashtag],
        verbose_name="Hash Tag",
        help_text=mark_safe(
            _("Your official <em>hash tag</em> " "for social media promotions.")
        ),
    )
    enabled = BooleanField(default=True)
    start_date = DateField(blank=True, null=True)
    mode = models.IntegerField(
        choices=SEASON_MODE_CHOICES,
        default=WEEKLY,
        help_text=_(
            "Used by the draw wizard to help "
            "you set your match dates & times "
            "automatically."
        ),
    )
    statistics = BooleanField(
        default=True,
        help_text=_(
            "Set to No if you do not wish to "
            "keep scoring or most valuable "
            "player statistics."
        ),
    )
    mvp_results_public = DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("MVP public at"),
        help_text=_(
            "The time when the results "
            "of the MVP voting will be "
            "made public on the "
            "website. Leave blank to "
            "show at all times."
        ),
    )

    live_stream = BooleanField(default=False)
    live_stream_privacy = models.CharField(
        max_length=20,
        choices=LiveStreamPrivacy.choices,
        default=LiveStreamPrivacy.PRIVATE,
    )

    live_stream_project_id = models.CharField(max_length=100, blank=True, null=True)
    live_stream_client_id = models.CharField(max_length=200, blank=True, null=True)
    live_stream_client_secret = models.CharField(max_length=100, blank=True, null=True)
    live_stream_token = models.CharField(max_length=1000, null=True)
    live_stream_refresh_token = models.CharField(max_length=200, null=True)
    live_stream_token_uri = models.URLField(null=True)
    live_stream_scopes = PG.ArrayField(models.CharField(max_length=200), null=True)
    live_stream_thumbnail = models.URLField(null=True)

    complete = BooleanField(
        default=False,
        help_text=_(
            "Set to indicate this season is in "
            "the past. Optimises progression "
            "calculations."
        ),
    )
    disable_calendar = BooleanField(
        default=False,
        help_text=_(
            "Set to prevent the iCalendar feature "
            "for this season. Will hide icon in "
            "front-end and disable functionality. "
            "Batch process may disable after last "
            "match of tournament has taken place."
        ),
    )
    timezone = TimeZoneField(max_length=50, blank=True, null=True)

    forfeit_notifications = ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name=None,
        help_text=_(
            "When a team advises they are forfeiting, notify the "
            "opposition team plus these people."
        ),
    )

    class Meta(OrderedSitemapNode.Meta):
        unique_together = (
            ("title", "competition"),
            ("slug", "competition"),
        )

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season"

    def _get_url_args(self):
        return (self.competition_id, self.pk)

    def __repr__(self):
        return "<Season: {} - {}>".format(self.competition, self)

    def flow(self, **kwargs):
        "Generate an authorization Flow"
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": self.live_stream_client_id,
                    "project_id": self.live_stream_project_id,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": self.live_stream_client_secret,
                    "redirect_uris": [],
                }
            },
            scopes=[
                "https://www.googleapis.com/auth/youtube",
                "https://www.googleapis.com/auth/youtube.force-ssl",
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtubepartner",
            ],
            **kwargs,
        )

    @cached_property
    def youtube(self):
        return build(
            "youtube",
            "v3",
            credentials=Credentials(
                client_id=self.live_stream_client_id,
                client_secret=self.live_stream_client_secret,
                token=self.live_stream_token,
                refresh_token=self.live_stream_refresh_token,
                token_uri=self.live_stream_token_uri,
                scopes=self.live_stream_scopes,
            ),
        )

    @property
    def datetimes(self):
        if not hasattr(self, "_dates"):
            queryset = self.matches.exclude(
                Q(date__isnull=True)
                | Q(time__isnull=True)
                | Q(play_at__timezone__isnull=True)
            )
            values_list = queryset.values_list(
                "date", "time", "play_at__timezone"
            ).distinct()
            self._dates = sorted([combine_and_localize(*v) for v in values_list])
        return self._dates

    @property
    def dates(self):
        return [dt.date() for dt in self.datetimes]

    @property
    def matches(self):
        return Match.objects.filter(stage__division__season=self).select_related(
            "home_team", "away_team"
        )

    @property
    def clubs(self):
        ids = (
            Team.objects.filter(division__season=self)
            .values_list("club", flat=True)
            .distinct()
        )
        return self.competition.clubs.filter(pk__in=ids)

    def get_places(self):
        venues = self.venues.values_list("pk", flat=True)
        grounds = Ground.objects.filter(venue__in=venues)
        pks = (
            set(venues)
            .difference(grounds.values_list("venue", flat=True))
            .union(grounds.values_list("pk", flat=True))
        )
        return Place.objects.filter(pk__in=pks)

    def get_timeslots(self, date=None):
        # work out the timeslot rules to exclude
        exc = Q()
        if date is not None:
            # exclude rules that expired on a day earlier than the
            # specified date
            exc |= Q(end_date__isnull=False, end_date__lt=date)
            # exclude rules that start after the date specified
            exc |= Q(start_date__isnull=False, start_date__gt=date)
        # build our ruleset and consume it as a list
        rset = rruleset()
        for timeslot in self.timeslots.exclude(exc):
            rset.rrule(timeslot.rrule())
        return [dt.time() for dt in rset]


class Place(AdminUrlMixin, OrderedSitemapNode):
    abbreviation = models.CharField(max_length=20, blank=True, null=True)
    latlng = LocationField(max_length=100)
    timezone = TimeZoneField(max_length=50, blank=True, null=True)

    class Meta(OrderedSitemapNode.Meta):
        pass

    @property
    def location(self):
        if not hasattr(self, "_latlng_pieces"):
            try:
                self._latlng_pieces = [Decimal(p) for p in self.latlng.split(",")]
            except InvalidOperation:
                self._latlng_pieces = None
        return self._latlng_pieces

    @property
    def latitude(self):
        return self.location and self.location[0]

    @property
    def longitude(self):
        return self.location and self.location[1]

    @property
    def zoom(self):
        return self.location and self.location[2]


class Venue(Place):
    """
    A venue where a season will be played. May have a number of grounds; see
    below. A match will be scheduled to take place on either at a venue or
    on a particular ground.
    """

    season = ForeignKey(Season, related_name="venues", on_delete=PROTECT)

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:venue"

    def _get_url_args(self):
        return (self.season.competition_id, self.season_id, self.pk)


class Ground(Place):
    """
    A ground (in some sports it may be a court or field) is an individual
    playing surface at a given venue.
    """

    venue = ForeignKey(Venue, related_name="grounds", on_delete=PROTECT)
    live_stream = BooleanField(default=False)
    external_identifier = models.CharField(
        max_length=50, blank=True, null=True, unique=True, db_index=True
    )
    stream_key = models.CharField(
        max_length=50, blank=True, null=True, unique=True, db_index=True
    )

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:venue:ground"

    def _get_url_args(self):
        return (
            self.venue.season.competition_id,
            self.venue.season_id,
            self.venue_id,
            self.pk,
        )


class Division(
    AdminUrlMixin,
    ModelDiffMixin,
    RankDivisionMixin,
    RankImportanceMixin,
    OrderedSitemapNode,
):
    """
    A model that represents a division within a competition.
    """

    rank_importance_parent_attr = "season"

    season = ForeignKey(Season, related_name="divisions", on_delete=PROTECT)

    points_formula = LadderPointsField(
        blank=True, null=True, verbose_name=_("Points system")
    )
    bonus_points_formula = models.TextField(blank=True, null=True)

    forfeit_for_score = models.SmallIntegerField(null=True)
    forfeit_against_score = models.SmallIntegerField(null=True)
    include_forfeits_in_played = BooleanField(default=True)

    games_per_day = models.SmallIntegerField(
        null=True,
        help_text=_(
            "In Tournament mode, specify how many matches "
            "per day should be scheduled by the automatic "
            "draw generator."
        ),
    )

    draft = BooleanField(
        default=False,
        help_text=_(
            "Marking a division as draft will "
            "prevent matches from being visible "
            "in the front-end."
        ),
    )

    # This is an advanced feature, we would not wish to surface it under
    # normal circumstances, but the theory is that we can use the report URL
    # to construct the minimum data for a division.
    sportingpulse_url = models.URLField(
        max_length=1024, blank=True, null=True, editable=False
    )

    objects = DivisionQuerySet.as_manager()

    class Meta(OrderedSitemapNode.Meta):
        unique_together = (
            ("title", "season"),
            ("slug", "season"),
        )

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division"

    def _get_url_args(self):
        return (self.season.competition_id, self.season_id, self.pk)

    @property
    def matches(self):
        return Match.objects.filter(stage__division=self).select_related(
            "home_team", "away_team"
        )

    def ladders(self):
        res = collections.OrderedDict()
        for stage in self.stages.exclude(keep_ladder=False).annotate(
            pool_count=Count("pools")
        ):
            res.update(stage.ladders())
        return res

    def matches_by_date(self):
        res = collections.OrderedDict()
        for stage in self.stages.all():
            res.update(stage.matches_by_date())
        return res


class Stage(AdminUrlMixin, RankImportanceMixin, OrderedSitemapNode):
    rank_importance_parent_attr = "division"

    division = ForeignKey(
        Division, related_name="stages", label_from_instance="title", on_delete=PROTECT
    )
    follows = ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=SET_NULL,
        related_name="preceeds",
        label_from_instance="title",
        help_text=mark_safe(
            _(
                "When progressing teams into this stage, which earlier stage "
                "should be used for determining positions.<br>"
                "Default is the immediately preceeding stage."
            )
        ),
    )

    keep_ladder = BooleanField(
        default=True,
        verbose_name="Keep a ladder",
        help_text=mark_safe(
            _(
                "Set this to <b>No</b> if this stage does not need to keep a "
                "competition ladder.<br>Usually set to No for a Final "
                "Series or a Knockout stage."
            )
        ),
    )

    scale_group_points = BooleanField(
        default=False,
        help_text=mark_safe(
            _(
                "In stages with multiple pools, adjust points in "
                "the smaller groups to compensate for the reduced "
                "opportunity to score points.<br>You "
                "<strong>should</strong> also set 0 points for Bye "
                "matches."
            )
        ),
    )

    carry_ladder = BooleanField(
        default=False,
        verbose_name="Carry over points",
        help_text=mark_safe(
            _(
                "Set this to <b>Yes</b> if this stage should carry over values "
                "from the previous stage."
            )
        ),
    )

    keep_mvp = BooleanField(
        default=True,
        verbose_name="Keep MVP stats",
        help_text=mark_safe(
            _(
                "Set this to <b>No</b> if this stage does not need to keep "
                "track of MVP points.<br>Usually set to No for a Final Series."
            )
        ),
    )

    matches_needing_printing = ManyToManyField(
        "Match", blank=True, related_name="to_be_printed"
    )

    objects = StageQuerySet.as_manager()

    class Meta(OrderedSitemapNode.Meta):
        unique_together = (
            ("title", "division"),
            ("slug", "division"),
        )

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:stage"

    def _get_url_args(self):
        return (
            self.division.season.competition_id,
            self.division.season_id,
            self.division_id,
            self.pk,
        )

    def __str__(self):
        return self.title

    @property
    def teams(self):
        if self.order > 1:
            team_ids = set()
            for home_team, away_team in self.matches.values_list(
                "home_team", "away_team"
            ):
                if home_team is not None:
                    team_ids.add(home_team)
                if away_team is not None:
                    team_ids.add(away_team)
            return self.division.teams.filter(pk__in=team_ids)
        else:
            return self.division.teams

    @property
    def comes_after(self):
        if self.follows:
            return self.follows
        after = self.division.stages.filter(order__lt=self.order)
        if after:
            return after.latest("order")
        raise Stage.DoesNotExist

    def ladders(self):
        res = collections.OrderedDict()
        if self.pools.count():
            for pool in self.pools.all():
                res.setdefault(self, collections.OrderedDict()).update(pool.ladders())
        else:
            summary = self.ladder_summary.select_related("team__club")
            res.setdefault(self, summary)
        return res

    def matches_by_date(self):
        tzinfo = timezone.get_current_timezone()
        res = collections.OrderedDict()
        for match in (
            self.matches.select_related(
                "play_at",
                "stage__division",
                "home_team__club",
                "home_team__division",
                "away_team__club",
                "away_team__division",
            )
            .annotate(
                statistics_count=Count("statistics"),
                videos_count=Count("videos"),
                referee_count=Count("referees"),
            )
            .order_by("datetime", "date", "time", "round")
        ):
            res.setdefault(self, collections.OrderedDict()).setdefault(
                match.get_date(tzinfo), []
            ).append(match)
        return res


class StageGroup(AdminUrlMixin, RankImportanceMixin, OrderedSitemapNode):
    """
    A model which represents a sub-grouping of a division; often called a
    'pool', but could also be used to represent a combined division.
    """

    rank_importance_parent_attr = "stage"

    stage = ForeignKey(Stage, related_name="pools", on_delete=PROTECT)
    carry_ladder = BooleanField(
        default=False,
        verbose_name="Carry over points",
        help_text=mark_safe(
            _(
                "Set this to <b>Yes</b> if the ladder for this pool should "
                "carry over values from the previous stage.<br>"
                "Will only apply for matches played against teams that are "
                "now in this group."
            )
        ),
    )

    class Meta(OrderedSitemapNode.Meta):
        verbose_name = "pool"
        unique_together = ("stage", "order")

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:stage:stagegroup"

    def _get_url_args(self):
        return (
            self.stage.division.season.competition_id,
            self.stage.division.season_id,
            self.stage.division_id,
            self.stage_id,
            self.pk,
        )

    @property
    def division(self):
        return self.stage.division

    @property
    def ladder(self):
        team_ids = set()
        for m in self.matches:
            if m.home_team is not None:
                team_ids.add(m.home_team_id)
            if m.away_team is not None:
                team_ids.add(m.away_team_id)
        return LadderSummary.objects.filter(stage=self.stage, team__in=team_ids)

    def ladders(self):
        return {self: self.ladder_summary.select_related("team__club")}

    def matches_by_date(self):
        tzinfo = timezone.get_current_timezone()
        res = collections.OrderedDict()
        matches = self.matches.select_related(
            "play_at",
            "stage__division",
            "home_team__club",
            "home_team__division",
            "away_team__club",
            "away_team__division",
        )
        for match in matches.annotate(
            statistics_count=Count("statistics"),
            video_count=Count("videos"),
            referee_count=Count("referees"),
        ):
            res.setdefault(self, collections.OrderedDict()).setdefault(
                match.get_date(tzinfo), []
            ).append(match)
        return res


class Team(AdminUrlMixin, RankDivisionMixin, OrderedSitemapNode):
    """
    A model which represents a team in a competition. A team may not yet be
    placed into a division, as it might only be at the nomination stage.

    A team has a name which will usually be set by the team manager, but may
    over-ruled and locked by an administrator (for example, to remove a name
    which contains profanity) on a per-team basis.
    """

    rank_division_parent_attr = "division"

    names_locked = BooleanField(
        default=False,
        help_text=mark_safe(
            _(
                "When the team name is locked, the team manager will not be "
                "able to change their team name.<br>"
                "As a tournament manager you can always change the names."
            )
        ),
    )

    club = ForeignKey(
        Club,
        blank=True,
        null=True,
        on_delete=SET_NULL,
        related_name="teams",
        label_from_instance="title",
    )
    division = ForeignKey(
        Division,
        blank=True,
        null=True,
        related_name="teams",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    stage_group = ForeignKey(
        StageGroup,
        verbose_name=_("Pool"),
        blank=True,
        null=True,
        on_delete=SET_NULL,
        related_name="teams",
        label_from_instance="title",
    )

    timeslots_after = TimeField(
        blank=True,
        null=True,
        verbose_name=_("Start after"),
        help_text=_(
            "Specify the earliest time that "
            "this team can play. Leave blank "
            "for no preference."
        ),
    )
    timeslots_before = TimeField(
        blank=True,
        null=True,
        verbose_name=_("Start before"),
        help_text=_(
            "Specify the latest time that "
            "this team can play. Leave blank "
            "for no preference."
        ),
    )
    team_clashes = ManyToManyField(
        "self",
        blank=True,
        verbose_name=_("Don't clash"),
        label_from_instance=team_and_division,
        symmetrical=True,
        help_text=_("Select any teams that must " "not play at the same time."),
    )

    class Meta:
        ordering = (
            "-division__season__start_date",
            "division__order",
            "stage_group__order",
            "order",
        )
        unique_together = (("title", "division"),)

    def clean(self):
        errors = {}

        # Ensure the Meta.unique_together constraint is applied consistently
        other_teams = self.division.teams.exclude(pk=self.pk)
        if other_teams.filter(title__iexact=self.title):
            errors.setdefault("title", []).append(
                _("Team name must be unique in this division.")
            )

        if errors:
            raise ValidationError(errors)

        return super(Team, self).clean()

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:team"

    def _get_url_args(self):
        return (
            self.division.season.competition_id,
            self.division.season_id,
            self.division_id,
            self.pk,
        )

    def __cmp__(self, other):
        if self.division_id == other.division_id:
            return cmp(self.order, other.order)
        return cmp(self.division, other.division)

    def __repr__(self):
        return "<Team: %s>" % self.title

    def __str__(self):
        return self.title

    @property
    def matches(self):
        related = (
            "stage__division",
            "stage_group",
            "home_team__club",
            "away_team__club",
            "home_team__division",
            "away_team__division",
        )
        home = self.home_games.select_related(*related)
        away = self.away_games.select_related(*related)
        return home | away

    def future(self, offset=None):
        if offset is None:
            offset = 15  # FIXME add a value on a season
        dt = timezone.now() - timedelta(minutes=offset)
        d, t = dt.date(), dt.time()
        return self.matches.filter((Q(date__exact=d) & Q(time__gte=t)) | Q(date__gt=d))

    def past(self, offset=None):
        if offset is None:
            offset = 15  # FIXME add a value on a season
        dt = timezone.now() - timedelta(minutes=offset)
        d, t = dt.date(), dt.time()
        return self.matches.filter((Q(date__exact=d) & Q(time__lte=t)) | Q(date__lt=d))

    def next_match(self):
        matches = self.future()
        if matches.count():
            match = matches[0]
            match.next = True
            return match

    def last_match(self):
        matches = self.past()
        if matches.count():
            match = matches.reverse()[0]
            match.last = True
            return match

    def ladders(self):
        res = collections.OrderedDict()
        for stage in self.division.stages.filter(
            keep_ladder=True, ladder_summary__team=self
        ).annotate(pool_count=Count("pools")):
            if stage.pool_count:
                for pool in stage.pools.filter(ladder_summary__team=self):
                    summary = pool.ladder_summary.select_related(
                        "team__club", "team__division"
                    )
                    res.setdefault(stage, collections.OrderedDict()).setdefault(
                        pool, summary
                    )
            else:
                summary = stage.ladder_summary.select_related(
                    "team__club", "team__division"
                )
                res.setdefault(stage, summary)
        return res

    def matches_by_date(self):
        tzinfo = timezone.get_current_timezone()
        res = collections.OrderedDict()
        matches = self.matches.select_related(
            "play_at",
            "stage__division",
            "stage_group",
            "home_team__club",
            "home_team__division",
            "away_team__club",
            "away_team__division",
        )
        for m in matches.annotate(
            statistics_count=Count("statistics"), videos_count=Count("videos")
        ):
            res.setdefault(m.get_date(tzinfo), []).append(m)
        return res


class ByeTeam(object):
    def __init__(self, title="Bye", *args, **kwargs):
        super(ByeTeam, self).__init__(*args, **kwargs)
        self.pk = None
        self.title = mark_safe(
            '<span class="bye" title="%s">%s</span>' % (title, title)
        )

    def __nonzero__(self):
        return False

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        raise NotImplementedError


class UndecidedTeam(AdminUrlMixin, models.Model):
    """
    A model which represents a team in a competition that is dependant on the
    results of an earlier `Stage`. This type of entry fills a void in a draw by
    being assigned as a reference in a match. Upon "progressing" teams at the
    conclusion of a stage, these links will be updated by listeners to signals.
    """

    formula = models.CharField(max_length=20, blank=True)
    label = models.CharField(max_length=30, blank=True)
    stage = ForeignKey(
        Stage,
        related_name="undecided_teams",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    stage_group = ForeignKey(
        StageGroup,
        blank=True,
        null=True,
        on_delete=SET_NULL,
        related_name="undecided_teams",
        verbose_name=_("Pool"),
        label_from_instance="title",
    )

    class Meta:
        ordering = ("stage_group", "formula")
        # verbose_name = 'team'

    def __str__(self):
        return self.title

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:stage:undecidedteam"

    def _get_url_args(self):
        return (
            self.stage.division.season.competition_id,
            self.stage.division.season_id,
            self.stage.division_id,
            self.stage_id,
            self.pk,
        )

    @cached_property
    def choices(self):
        if self.formula:
            __, group, __ = stage_group_position(self.stage, self.formula)
            if group is not None:
                return group.teams
        return self.stage.division.teams

    @property
    def title(self):
        if not self.formula and self.label:
            return self.label

        stage, group, position = stage_group_position(self.stage, self.formula)

        c = {
            "stage": stage,
            "group": group,
            "position": position,
        }

        return stage_group_position_tpl.render(c).strip()

    @property
    def matches(self):
        home = self.home_games.select_related("home_team", "away_team")
        away = self.away_games.select_related("home_team", "away_team")
        return home | away


class ClubRole(AdminUrlMixin, models.Model):
    competition = ForeignKey(
        Competition,
        related_name="club_roles",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def _get_admin_namespace(self):
        return "admin:fixja:competition:clubrole"

    def _get_url_args(self):
        return (self.competition_id, self.pk)


class ClubAssociation(AdminUrlMixin, models.Model):
    club = ForeignKey(
        Club, related_name="staff", label_from_instance="title", on_delete=PROTECT
    )
    person = ForeignKey(Person, label_from_instance="get_full_name", on_delete=PROTECT)
    roles = ManyToManyField(ClubRole, label_from_instance="name")

    class Meta:
        ordering = ("person__last_name", "person__first_name")
        unique_together = ("club", "person")
        verbose_name = _("Official")
        verbose_name_plural = _("Officials")

    def _get_admin_namespace(self):
        return "admin:fixja:club:clubassociation"

    def _get_url_args(self):
        return (self.club_id, self.pk)


class TeamRole(AdminUrlMixin, models.Model):
    competition = ForeignKey(
        Competition,
        related_name="team_roles",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def _get_admin_namespace(self):
        return "admin:fixja:competition:teamrole"

    def _get_url_args(self):
        return (self.competition_id, self.pk)


class TeamAssociation(AdminUrlMixin, models.Model):
    team = ForeignKey(Team, related_name="people", on_delete=PROTECT)
    person = ForeignKey(
        Person, null=True, label_from_instance="get_full_name", on_delete=PROTECT
    )
    roles = ManyToManyField(TeamRole, blank=True, label_from_instance="name")
    number = models.IntegerField(blank=True, null=True)
    is_player = BooleanField(default=True)

    def __str__(self):
        return self.person.get_full_name

    class Meta:
        ordering = (
            "-is_player",
            "number",
            "person__last_name",
            "person__first_name",
        )
        unique_together = ("team", "person")
        verbose_name = "linked person"
        verbose_name_plural = "linked people"

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:team:teamassociation"

    def _get_url_args(self):
        return (
            self.team.division.season.competition_id,
            self.team.division.season_id,
            self.team.division_id,
            self.team_id,
            self.pk,
        )

    def statistics(self):
        stats = SimpleScoreMatchStatistic.objects.filter(
            player=self.person, player__teamassociation__team=self.team
        )
        stats = stats.filter(
            Q(match__home_team=self.team) | Q(match__away_team=self.team)
        )
        return stats.aggregate(
            played=Sum("played"),
            points=Sum("points"),
            mvp=Sum("mvp"),
        )


class SeasonReferee(AdminUrlMixin, models.Model):
    season = models.ForeignKey(Season, related_name="referees", on_delete=PROTECT)
    club = models.ForeignKey(Club, related_name="referees", on_delete=PROTECT)
    person = ForeignKey(Person, label_from_instance="get_full_name", on_delete=PROTECT)

    def __str__(self):
        return self.person.get_full_name

    class Meta:
        ordering = (
            "season",
            "person__last_name",
            "person__first_name",
        )
        unique_together = ("season", "person")
        verbose_name = _("referee")

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:seasonreferee"

    def _get_url_args(self):
        return (self.season.competition_id, self.season_id, self.pk)


class SeasonAssociation(AdminUrlMixin, models.Model):
    club = models.ForeignKey(Club, related_name="officials", on_delete=PROTECT)
    season = models.ForeignKey(Season, related_name="officials", on_delete=PROTECT)
    person = ForeignKey(Person, label_from_instance="get_full_name", on_delete=PROTECT)
    roles = ManyToManyField(ClubRole, label_from_instance="name")

    class Meta:
        ordering = (
            "club",
            "season",
            "person__last_name",
            "person__first_name",
        )
        unique_together = ("season", "person")


class Match(AdminUrlMixin, RankImportanceMixin, models.Model):
    uuid = models.UUIDField(
        primary_key=False,
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    rank_importance_parent_attr = ("stage_group", "stage")

    stage = ForeignKey(
        Stage,
        label_from_instance="title",
        null=True,
        related_name="matches",
        on_delete=PROTECT,
    )
    stage_group = ForeignKey(
        StageGroup,
        blank=True,
        null=True,
        verbose_name=_("Pool"),
        label_from_instance="title",
        related_name="matches",
        on_delete=PROTECT,
    )

    label = models.CharField(max_length=100, blank=True, null=True)

    home_team = ForeignKey(
        Team,
        blank=True,
        null=True,
        related_name="home_games",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    away_team = ForeignKey(
        Team,
        blank=True,
        null=True,
        related_name="away_games",
        label_from_instance="title",
        on_delete=PROTECT,
    )

    referees = ManyToManyField(SeasonReferee, blank=True, related_name="matches")

    # these fields are used when the home/away teams are to be determined by
    # some form of calculation - usually by a position within the ladder or
    # group/pool
    home_team_undecided = ForeignKey(
        UndecidedTeam,
        blank=True,
        null=True,
        related_name="home_games",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    home_team_eval = models.CharField(max_length=10, blank=True, null=True)
    home_team_eval_related = ForeignKey(
        "self",
        blank=True,
        null=True,
        related_name="+",
        label_from_instance="pk",
        on_delete=PROTECT,
    )
    away_team_undecided = ForeignKey(
        UndecidedTeam,
        blank=True,
        null=True,
        related_name="away_games",
        label_from_instance="title",
        on_delete=PROTECT,
    )
    away_team_eval = models.CharField(max_length=10, blank=True, null=True)
    away_team_eval_related = ForeignKey(
        "self",
        blank=True,
        null=True,
        related_name="+",
        label_from_instance="pk",
        on_delete=PROTECT,
    )

    evaluated = models.BooleanField(null=True)

    is_washout = BooleanField(default=False)

    date = DateField(blank=True, null=True)
    time = TimeField(blank=True, null=True)
    datetime = DateTimeField(blank=True, null=True)

    play_at = ForeignKey(
        Place, label_from_instance="title", blank=True, null=True, on_delete=SET_NULL
    )

    home_team_score = models.IntegerField(blank=True, null=True)
    away_team_score = models.IntegerField(blank=True, null=True)

    is_bye = BooleanField(default=False)
    bye_processed = BooleanField(default=False)

    is_forfeit = BooleanField(default=False)
    forfeit_winner = ForeignKey(
        Team,
        blank=True,
        null=True,
        related_name="+",
        label_from_instance="title",
        on_delete=PROTECT,
    )

    round = models.IntegerField(blank=True, null=True)

    include_in_ladder = BooleanField(default=True)

    external_identifier = models.CharField(
        max_length=20, blank=True, null=True, unique=True, db_index=True
    )

    videos = PG.ArrayField(
        models.URLField(),
        null=True,
    )
    live_stream = BooleanField(default=False)
    live_stream_bind = models.CharField(
        max_length=50, blank=True, null=True, db_index=True
    )
    live_stream_thumbnail = models.URLField(blank=True, null=True)

    objects = MatchManager()

    class Meta:
        get_latest_by = "datetime"
        ordering = (
            "date",
            "stage",
            "round",
            "is_bye",
            "time",
            "play_at__ground__order",
            "pk",
        )
        verbose_name_plural = "matches"

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:stage:match"

    def _get_url_args(self):
        return (
            self.stage.division.season.competition_id,
            self.stage.division.season_id,
            self.stage.division_id,
            self.stage_id,
            self.pk,
        )

    def get_date(self, tzinfo):
        dt = self.get_datetime(tzinfo)
        if dt is not None:
            return dt.date()
        return self.date

    def get_datetime(self, tzinfo=None):
        res = self.datetime
        if res is None:
            exclude = (
                Q(pk=self.pk)
                | Q(date__isnull=True)
                | Q(time__isnull=True)
                | Q(play_at__isnull=True)
            )
            # identify the matches which are in the same round as this match
            siblings = Match.objects.exclude(exclude).filter(
                stage=self.stage, round=self.round
            )
            # if we're part of a stage group, further filter the sibling list
            if self.stage_group:
                siblings = siblings.filter(stage_group=self.stage_group)
            if siblings:
                res = max([s.datetime for s in siblings])
        if res is not None and settings.USE_TZ and tzinfo is not None:
            return timezone.localtime(res, tzinfo)
        return res

    def forfeit(self, team, actor=None):
        """
        Update the Match to be recorded as a forfeit.

        Optionally provide detail of who notified the forfeit.

        :param team: the home_team or away_team, or None for double forfeit
        :param actor: the person who notified us of the forfeit
        :return: success of the operation
        """
        assert team in (self.home_team, self.away_team, None)

        if actor is not None:
            # If it is a double forfeit, ensure the actor is a member of
            # either the home or away team, or an admin.
            if team is None:
                team_association = self.home_team.people.filter(
                    person=actor
                ) | self.away_team.people.filter(person=actor)
            # Ensure the actor a member of the forfeiting team, or an admin.
            else:
                team_association = team.people.filter(person=actor)

            assert team_association.exists() or actor.is_staff

        # Matches that have already been forfeit can not be forfeit again.
        if self.is_forfeit:
            return False

        # Matches that already have a result can not be forfeit. We should not
        # have partial scores, but check for either to be not None.
        if self.home_team_score is not None or self.away_team_score is not None:
            return False

        self.is_forfeit = True

        # Set the match result based on who has forfeit.
        if self.home_team == team:
            self.forfeit_winner = self.away_team
            self.home_team_score = self.stage.division.forfeit_against_score
            self.away_team_score = self.stage.division.forfeit_for_score
        elif self.away_team == team:
            self.forfeit_winner = self.home_team
            self.home_team_score = self.stage.division.forfeit_for_score
            self.away_team_score = self.stage.division.forfeit_against_score
        else:
            self.home_team_score = self.stage.division.forfeit_against_score
            self.away_team_score = self.stage.division.forfeit_against_score

        self.save()

        # Send the match_forfeit signal so we can handle notifications
        match_forfeit.send(sender=self.__class__, match=self, team=team)

        return True

    def clean(self):
        # Remember, this will only fire if the `Match.save` method is invoked;
        # the `update` queryset method will cause this to be bypassed
        # altogether, so any `update` that changes the `date` or `time` fields
        # (such as rescheduling due to wet weather) should take this into
        # account.
        errors = {}

        if self.date is not None:
            if self.stage.division.season.start_date:
                if self.stage.division.season.start_date > self.date:
                    errors.setdefault("date", []).append(
                        _("This date is before the start of the season.")
                    )
            if self.stage.division.season.exclusions.filter(date=self.date):
                errors.setdefault("date", []).append(
                    _("This date has been excluded for this season.")
                )
            if self.stage.division.exclusions.filter(date=self.date):
                errors.setdefault("date", []).append(
                    _("This date has been excluded for this division.")
                )

        if self.stage_group and self.stage_group not in self.stage.pools.all():
            errors.setdefault("stage_group", []).append(
                _("This pool is not in the selected division")
            )

        if errors:
            raise ValidationError(errors)

        try:
            self.datetime = datetime.combine(self.date, self.time)
        except TypeError:
            self.datetime = None

        if self.datetime is not None and settings.USE_TZ:
            try:
                tzinfo = pytz.timezone(self.play_at.timezone)
            except (AttributeError, pytz.UnknownTimeZoneError):
                tzinfo = timezone.get_default_timezone()
            else:
                self.datetime = timezone.make_aware(self.datetime, tzinfo)

    @cached_property
    def title(self):
        context = {
            "home": self.get_home_team(),
            "away": self.get_away_team(),
        }
        return match_title_tpl.render(context)

    def _get_team(self, field, plain=False):
        team = getattr(self, field)
        if team:
            return team

        team_undecided = getattr(self, f"{field}_undecided")
        if team_undecided:
            team_eval = team_undecided.formula
            team_eval_related = None
        else:
            team_eval = getattr(self, f"{field}_eval")
            team_eval_related = getattr(self, f"{field}_eval_related")

        try:
            stage, group, position = stage_group_position_re.match(team_eval).groups()
        except (AttributeError, TypeError):
            logger.exception("Failed evaluating `stage_group_position` %s for %s", team_eval, self)
            if not team_undecided and self.is_bye:
                return ByeTeam()
            stage = group = position = None
        else:
            stage = self.stage.comes_after

        if team_undecided and stage is None:
            if plain:
                return str(team_undecided)
            return {"title": str(team_undecided)}
        elif team_eval in WIN_LOSE:
            context = {
                "position": WIN_LOSE[team_eval],
                "match": team_eval_related,
            }
            template = win_lose_team_tpl
        else:
            context = {
                "position": position,
                "stage": stage,
            }
            template = stage_group_position_tpl
            if group is not None:
                if stage.pools.count():
                    context["group"] = stage.pools.all()[int(group) - 1]
                else:
                    context["group"] = {
                        "title": mark_safe('<span class="error">ERROR</span>'),
                    }
                    context.setdefault("errors", []).append("Invalid group.")
        if plain:
            return template.render(context).strip()
        return {"title": template.render(context).strip()}

    def get_home_team(self):
        return self._get_team("home_team")

    def get_away_team(self):
        return self._get_team("away_team")

    def get_home_team_plain(self):
        return self._get_team("home_team", True)

    def get_away_team_plain(self):
        return self._get_team("away_team", True)

    def _winner_loser(self, win_lose):
        winner = loser = None

        if self.home_team_score is not None and self.away_team_score is not None:
            if self.is_forfeit:
                winner = self.forfeit_winner
            elif self.home_team_score > self.away_team_score:
                winner, loser = self.home_team, self.away_team
            elif self.home_team_score < self.away_team_score:
                winner, loser = self.away_team, self.home_team

        if win_lose == "W":
            return winner
        elif win_lose == "L":
            return loser
        else:
            return None

    winner = property(lambda self: self._winner_loser("W"))
    loser = property(lambda self: self._winner_loser("L"))

    def eval(self, lazy=True):
        """
        Attempt to populate the `home_team` and `away_team` fields as
        appropriate.

        When lazy=False we should always evaluate the teams, if possible.
        """
        try:
            stage = self.stage.comes_after
        except Stage.DoesNotExist:
            logger.warning(
                "Stage is first, %r should not be attempting to be " "evaluated.", self
            )
            return (self.home_team, self.away_team)

        positions = {
            index + 1: team
            for index, team in enumerate(
                stage.ladder_summary.values_list("team", flat=True)
            )
        }
        group_positions = {
            index + 1: [each.team for each in group.ladder]
            for index, group in enumerate(stage.pools.all())
        }
        res = [None, None]
        for index, field in enumerate(("home_team", "away_team")):
            team = self._get_team(field)
            is_team_model = not isinstance(team, Team)
            if not is_team_model:
                logger.warning("%r is not a Team instance.", team)
            if not lazy or not is_team_model:
                team_undecided = getattr(self, f"{field}_undecided")
                if team_undecided:
                    team_eval = team_undecided.formula
                    team_eval_related = None
                else:
                    team_eval = getattr(self, f"{field}_eval")
                    team_eval_related = getattr(self, f"{field}_eval_related")
                if team_eval in WIN_LOSE:
                    team = team_eval_related._winner_loser(team_eval)
                else:
                    try:
                        stage, group, position = stage_group_position_re.match(
                            team_eval
                        ).groups()
                    except (AttributeError, TypeError):
                        logger.exception("Failed evaluating `stage_group_position` %s for %s", team_eval, self)
                    else:
                        try:
                            try:
                                g = int(group)
                                p = int(position)
                                team = group_positions[g][p - 1]
                            except TypeError:
                                team = positions[int(position)]
                        except (IndexError, KeyError):
                            pass
                res[index] = team
        return tuple(res)

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"<Match: {self.round!s}: {self!s}>"


class LadderBase(models.Model):
    played = models.SmallIntegerField(default=0)
    win = models.SmallIntegerField(default=0)
    loss = models.SmallIntegerField(default=0)
    draw = models.SmallIntegerField(default=0)
    bye = models.SmallIntegerField(default=0)
    forfeit_for = models.SmallIntegerField(default=0)
    forfeit_against = models.SmallIntegerField(default=0)
    score_for = models.SmallIntegerField(default=0)
    score_against = models.SmallIntegerField(default=0)
    bonus_points = models.SmallIntegerField(default=0)
    points = models.DecimalField(default=0, max_digits=6, decimal_places=3)

    class Meta:
        abstract = True

    def __repr__(self):
        return "<%s: #%s>" % (self.__class__.__name__, self.pk)


class LadderEntry(LadderBase):
    match = ForeignKey(Match, related_name="ladder_entries", on_delete=CASCADE)
    team = ForeignKey(
        Team,
        related_name="ladder_entries",
        label_from_instance="title",
        on_delete=CASCADE,
    )
    opponent = ForeignKey(Team, null=True, on_delete=PROTECT)

    objects = LadderEntryManager()

    def __repr__(self):
        return "<LadderEntry: #%s>" % self.pk


class LadderSummary(LadderBase):
    stage = ForeignKey(Stage, related_name="ladder_summary", on_delete=CASCADE)
    stage_group = ForeignKey(
        StageGroup, null=True, related_name="ladder_summary", on_delete=CASCADE
    )
    team = ForeignKey(Team, related_name="ladder_summary", on_delete=PROTECT)
    difference = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    percentage = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    class Meta:
        ordering = (
            "stage",
            "-points",
            "-difference",
            "-percentage",
            "team__title",
        )
        unique_together = ("stage", "team")


class DrawFormat(AdminUrlMixin, models.Model):
    name = models.CharField(max_length=50)
    text = models.TextField(verbose_name="Formula")
    teams = models.PositiveIntegerField(blank=True, null=True)
    is_final = BooleanField(default=False)

    class Meta:
        ordering = ("teams", "name")

    def _get_admin_namespace(self):
        return "admin:fixja:format"

    def _get_url_args(self):
        return (self.pk,)

    def generator(self, stage, start_date=None):
        from tournamentcontrol.competition.draw import DrawGenerator

        generator = DrawGenerator(stage, start_date)
        generator.parse(self.text)
        return generator

    def __str__(self):
        return self.name


class ExclusionDateBase(AdminUrlMixin, models.Model):
    """
    Abstract base class that stores a date to exclude when generating a draw
    automatically from a DrawGenerator.
    """

    date = DateField()

    class Meta:
        abstract = True
        ordering = ("date",)


class SeasonExclusionDate(ExclusionDateBase):
    season = ForeignKey("Season", related_name="exclusions", on_delete=CASCADE)

    class Meta(ExclusionDateBase.Meta):
        unique_together = ("season", "date")
        verbose_name = "exclusion date"

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:seasonexclusiondate"

    def _get_url_args(self):
        return (self.season.competition_id, self.season_id, self.pk)


class DivisionExclusionDate(ExclusionDateBase):
    division = ForeignKey("Division", related_name="exclusions", on_delete=CASCADE)

    class Meta:
        unique_together = ("division", "date")
        verbose_name = "exclusion date"

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:divisionexclusiondate"

    def _get_url_args(self):
        return (
            self.division.season.competition_id,
            self.division.season_id,
            self.division_id,
            self.pk,
        )


class MatchTimeBase(models.Model):
    """
    Abstract base class that stores enough information to create a recurring
    rule set.
    """

    start = TimeField()
    interval = models.IntegerField()
    count = models.IntegerField()

    class Meta:
        abstract = True

    def rrule_dtstart(self):
        return timezone.now().replace(
            hour=self.start.hour, minute=self.start.minute, second=0
        )

    def rrule_kwargs(self):
        return {
            "dtstart": self.rrule_dtstart(),  # timestamp to start from
            "interval": self.interval,  # every N minutes
            "count": self.count,  # maximum number of timeslots
        }

    def rrule(self):
        return rrule(MINUTELY, **self.rrule_kwargs())


class SeasonMatchTime(AdminUrlMixin, MatchTimeBase):
    season = ForeignKey("Season", related_name="timeslots", on_delete=CASCADE)
    start_date = DateField(verbose_name="From", blank=True, null=True)
    end_date = DateField(verbose_name="Until", blank=True, null=True)

    class Meta:
        verbose_name = "time slot"

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:seasonmatchtime"

    def _get_url_args(self):
        return (self.season.competition_id, self.season_id, self.pk)

    def __str__(self):
        return "#{}".format(self.pk)


class MatchScoreSheet(AdminUrlMixin, models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, related_name="scoresheets", on_delete=CASCADE)
    image = CloudinaryField(verbose_name=_("Image"))

    def _get_admin_namespace(self):
        return "admin:fixja:competition:season:division:stage:match:matchscoresheet"

    def _get_url_args(self):
        return (
            self.match.stage.division.season.competition_id,
            self.match.stage.division.season_id,
            self.match.stage.division_id,
            self.match.stage_id,
            self.match_id,
            self.pk,
        )

    def __str__(self):
        return str(self.image)


class MatchStatisticBase(models.Model):
    match = ForeignKey("Match", related_name="statistics", on_delete=PROTECT)
    player = ForeignKey("Person", related_name="statistics", on_delete=PROTECT)
    number = models.IntegerField(blank=True, null=True)

    def team(self):
        if self.match.home_team.people.filter(person=self.player):
            team = self.match.home_team
        elif self.match.away_team.people.filter(person=self.player):
            team = self.match.away_team
        else:
            team = None
        return team

    class Meta:
        abstract = True
        ordering = ("match", "number")
        get_latest_by = "match"


class SimpleScoreMatchStatistic(MatchStatisticBase):
    played = models.SmallIntegerField(
        default=0,
        blank=True,
        validators=[
            validators.MinValueValidator(0),
            validators.MaxValueValidator(1),
        ],
    )
    points = models.SmallIntegerField(_("Points"), blank=True, null=True)
    mvp = models.SmallIntegerField(_("MVP"), blank=True, null=True)

    objects = StatisticQuerySet.as_manager()

    def clean(self):
        errors = {}

        if not self.played and self.points:
            errors["points"] = _("A person who did not play cannot score points.")

        if not self.played and self.mvp:
            errors["mvp"] = _("A person who did not play cannot earn MVP points.")

        if self.played and not self.number:
            errors["number"] = _("A person who played must have a shirt number.")

        if errors:
            raise ValidationError(errors)

    def __repr__(self):
        return "<Stat #%s: %s, %s, number=%s, played=%s>" % (
            self.pk,
            self.match,
            self.player,
            self.number,
            self.played,
        )
