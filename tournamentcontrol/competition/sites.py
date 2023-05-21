from __future__ import unicode_literals

import functools
import logging
import operator
from datetime import timedelta
from operator import or_

import pytz
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.sitemaps import views as sitemaps_views
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, Count, F, Q, Sum, When
from django.http import Http404, HttpResponse, HttpResponseGone
from django.shortcuts import get_object_or_404
from django.urls import include, path, re_path, reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext, gettext_lazy as _
from guardian.utils import get_40x_or_None
from icalendar import Calendar, Event

from touchtechnology.common.decorators import login_required_m
from touchtechnology.common.sites import Application
from touchtechnology.common.utils import get_perms_for_model
from tournamentcontrol.competition.dashboard import (
    matches_require_basic_results,
    matches_require_details_results,
)
from tournamentcontrol.competition.decorators import competition_by_slug_m
from tournamentcontrol.competition.forms import (
    ConfigurationForm,
    DivisionTournamentScheduleForm,
    MatchResultFormSet,
    MatchStatisticFormset,
    MultiConfigurationForm,
    RankingConfigurationForm,
    StreamControlForm,
)
from tournamentcontrol.competition.models import (
    Competition,
    Match,
    Person,
    SimpleScoreMatchStatistic,
)
from tournamentcontrol.competition.rank import (
    DayView as RankDay,
    DivisionView as RankDivision,
    IndexView as RankIndex,
    MonthView as RankMonth,
    TeamView as RankTeam,
    YearView as RankYear,
)
from tournamentcontrol.competition.utils import (
    FauxQueryset,
    team_needs_progressing,
)

LOG = logging.getLogger(__name__)


def permissions_required(
    request,
    model,
    instance=None,
    return_403=True,
    accept_global_perms=True,
    create=False,
    perms=None,
):
    # If no perms are specified, build sensible default using built in
    # permission types that come batteries included with Django.
    if perms is None:
        perms = get_perms_for_model(model, change=True)

        # When we're doing a creation we should have permission to create the object.
        if create:
            perms = get_perms_for_model(model, add=True)

    # Determine the user's permission to edit this object using the
    # get_40x_or_None - saves decorating view method with
    # @permission_required_or_403
    has_permission = get_40x_or_None(
        request,
        perms,
        obj=instance,
        return_403=return_403,
        accept_global_perms=accept_global_perms,
    )

    if has_permission is not None:
        return has_permission


class CompetitionAdminMixin(object):
    """
    Some administrative functions should be allowed to authenticated users on
    the front-end of the site. As long as we only use primitives from the base
    ``touchtechnology.common.sites.Application`` class it will integrate fine
    with both.
    """

    def day_runsheet(
        self, request, season, date, extra_context, templates=None, **kwargs
    ):
        matches = season.matches.filter(date=date).order_by(
            "is_bye", "datetime", "play_at"
        )
        templates = self.template_path(
            "runsheet.html", season.slug, season.competition.slug
        )
        return self.generic_list(
            request,
            matches,
            templates=templates,
            paginate_by=0,
            permission_required=False,
            extra_context=extra_context,
        )

    def match_results(
        self,
        request,
        competition,
        season,
        date,
        extra_context,
        redirect_to,
        division=None,
        time=None,
        **kwargs,
    ):
        matches = Match.objects.filter(
            stage__division__season=season,
            stage__division__season__competition=competition,
            date=date,
        )

        if division is not None:
            matches = matches.filter(stage__division=division)

        # ensure only matches with progressed teams are able to be updated
        matches = matches.exclude(team_needs_progressing, is_bye=False)
        matches = matches.exclude(home_team__isnull=True, away_team__isnull=True)

        # FIXME too complex, be verbose so we can all read and understand it
        if time is not None:
            base = Q(time=time)
            bye_kwargs = matches.filter(time=time).values("stage", "round")
            time_or_byes = functools.reduce(
                operator.or_, [Q(time__isnull=True, **kw) for kw in bye_kwargs], base
            )
            matches = matches.filter(time_or_byes)
        else:
            matches = matches.order_by("date", "time", "play_at")

        match_queryset = matches.filter(is_bye=False)
        bye_queryset = matches.filter(is_bye=True)

        if request.method == "POST":
            match_formset = MatchResultFormSet(
                data=request.POST, queryset=match_queryset, prefix="matches"
            )
            bye_formset = MatchResultFormSet(
                data=request.POST, queryset=bye_queryset, prefix="byes"
            )

            if match_formset.is_valid() and bye_formset.is_valid():
                match_formset.save()
                bye_formset.save()
                messages.success(request, _("Your changes have been saved."))
                return self.redirect(redirect_to)
        else:
            match_formset = MatchResultFormSet(
                queryset=match_queryset, prefix="matches"
            )
            bye_formset = MatchResultFormSet(queryset=bye_queryset, prefix="byes")

        context = {
            "competition": competition,
            "season": season,
            "date": date,
            "division": division,
            "match_formset": match_formset,
            "bye_formset": bye_formset,
            "matches": matches,
            "cancel_url": redirect_to,
        }
        context.update(extra_context)

        templates = self.template_path("match_results.html")
        return self.render(request, templates, context)

    def stream_control(
        self,
        request,
        competition,
        season,
        date,
        extra_context,
        redirect_to,
        time,
        **kwargs,
    ):
        # FIXME: absolute hack view in order to get this going in time for Euros
        match_queryset = Match.objects.filter(
            stage__division__season=season,
            stage__division__season__competition=competition,
            date=date,
            time=time,
            external_identifier__isnull=False,
        ).order_by("play_at")

        if request.method == "POST":
            form = StreamControlForm(data=request.POST)

            if form.is_valid():
                res = form.save(request, season.youtube, match_queryset)
                if isinstance(res, HttpResponse):
                    return res
                return self.redirect(redirect_to)
        else:
            form = StreamControlForm()

        context = {
            "competition": competition,
            "season": season,
            "date": date,
            "form": form,
            "matches": match_queryset,
            "cancel_url": redirect_to,
        }
        context.update(extra_context)

        templates = self.template_path("stream_control.html")
        return self.render(request, templates, context)

    def edit_match_detail(
        self, request, stage, match, extra_context, redirect_to, **kwargs
    ):
        conditions = {
            "home_team__isnull": False,
            "away_team__isnull": False,
            "home_team_score__isnull": False,
            "away_team_score__isnull": False,
        }

        if match is None:
            match = get_object_or_404(stage.matches, pk=match.pk, **conditions)

        def team_faux_queryset(team):
            stats = FauxQueryset(SimpleScoreMatchStatistic, team=team)
            for player in team.people.filter(is_player=True):
                try:
                    statistic = SimpleScoreMatchStatistic.objects.get(
                        match=match, player=player.person
                    )
                except ObjectDoesNotExist:
                    statistic = SimpleScoreMatchStatistic(
                        match=match,
                        player=player.person,
                        number=player.number,
                        played=1,
                    )
                stats.append(statistic)
            return stats

        home_queryset = team_faux_queryset(match.home_team)
        away_queryset = team_faux_queryset(match.away_team)

        if request.method == "POST":
            home = MatchStatisticFormset(
                data=request.POST,
                score=match.home_team_score,
                prefix="home",
                queryset=home_queryset,
            )

            away = MatchStatisticFormset(
                data=request.POST,
                score=match.away_team_score,
                prefix="away",
                queryset=away_queryset,
            )

            if home.is_valid() and away.is_valid():
                home.save()
                away.save()
                messages.success(request, _("Your changes have been saved."))
                return self.redirect(redirect_to)

        else:
            home = MatchStatisticFormset(
                prefix="home", score=match.home_team_score, queryset=home_queryset
            )
            away = MatchStatisticFormset(
                prefix="away", score=match.away_team_score, queryset=away_queryset
            )

        context = {
            "object": match,
            "formsets": (home, away),
        }
        context.update(extra_context)

        templates = self.template_path("match_detail.html")
        return self.render(request, templates, context)


class CompetitionSite(CompetitionAdminMixin, Application):
    kwargs_form_class = ConfigurationForm

    def __init__(self, name="competition", app_name="competition", **kwargs):
        # store the node for future reference
        self.node = kwargs.get("node")
        super().__init__(name=name, app_name=app_name, **kwargs)
        self._competitions = Competition.objects.filter(enabled=True)
        if "competition" in kwargs and kwargs["competition"]:
            self._competitions = self._competitions.filter(slug=kwargs["competition"])

    def result_urls(self):
        return [
            path("", self.results, name="results"),
            path("match/<int:match>/", self.edit_match_detail, name="match-details"),
            re_path(r"^(?P<datestr>\d{8})/$", self.results, name="results"),
            re_path(
                r"^(?P<datestr>\d{8})/(?P<timestr>\d{4})/$",
                self.match_results,
                name="match-results",
            ),
        ]

    def runsheet_urls(self):
        return [
            path("", self.runsheet, name="runsheet"),
            re_path(r"^(?P<datestr>\d{8})/$", self.day_runsheet, name="runsheet"),
        ]

    def stream_urls(self):
        return [
            path("", self.stream, name="stream"),
            re_path(r"^(?P<datestr>\d{8})/$", self.stream, name="stream"),
            re_path(
                r"^(?P<datestr>\d{8})/(?P<timestr>\d{4})/$",
                self.stream_control,
                name="stream-control",
            ),
        ]

    def season_urls(self):
        return [
            path("", self.season, name="season"),
            path("forfeit/", self.forfeit_list, name="forfeit-list"),
            path("forfeit/<int:match>/", self.forfeit, name="forfeit"),
            path("videos/", self.season_videos, name="season-videos"),
            path("club:<slug:club>/", self.club, name="club"),
            path("club:<slug:club>.ics", self.calendar, name="calendar"),
            path("results/", include(self.result_urls())),
            path("runsheet/", include(self.runsheet_urls())),
            path("stream/", include(self.stream_urls())),
            path("<slug:division>.ics", self.calendar, name="calendar"),
            path("<slug:division>/", self.division, name="division"),
            path("<slug:division>:<slug:stage>/", self.stage, name="stage"),
            path("<slug:division>:<slug:stage>:<slug:pool>/", self.pool, name="pool"),
            path("<slug:division>/match:<int:match>/", self.match, name="match"),
            path(
                "<slug:division>/match:<int:match>/video/",
                self.match_video,
                name="match-video",
            ),
            path("<slug:division>/<slug:team>.ics", self.calendar, name="calendar"),
            path("<slug:division>/<slug:team>/", self.team, name="team"),
        ]

    def competition_urls(self):
        return [
            path("", self.competition, name="competition"),
            path("<slug:season>.ics", self.calendar, name="calendar"),
            path("<slug:season>/", include(self.season_urls())),
        ]

    def get_urls(self):
        if self.kwargs.get("season") and self.kwargs.get("competition"):
            urlpatterns = [
                path("", include(self.season_urls()), kwargs=self.kwargs),
            ]
        elif self.kwargs.get("competition"):
            urlpatterns = [
                path("", include(self.competition_urls()), kwargs=self.kwargs),
            ]
        else:
            urlpatterns = [
                path("", self.index, name="index"),
                path("<slug:competition>/", include(self.competition_urls())),
            ]
        return urlpatterns

    def sitemap_index(
        self,
        request,
        node=None,
        competition=None,
        season=None,
        division=None,
        *args,
        **kwargs,
    ):
        # We need to "pop" the node keyword argument
        return sitemaps_views.index(request, *args, **kwargs)

    def sitemap_section(
        self,
        request,
        node=None,
        competition=None,
        season=None,
        division=None,
        *args,
        **kwargs,
    ):
        # We need to "pop" the node keyword argument
        return sitemaps_views.sitemap(request, *args, **kwargs)

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    @property
    def competitions(self):
        return self._competitions.prefetch_related("seasons")

    def index(self, request, **kwargs):
        return self.generic_list(
            request,
            self._competitions,
            templates=self.template_path("index.html"),
            paginate_by=self._competitions.count(),
            extra_context=kwargs,
        )

    @competition_by_slug_m
    def competition(self, request, competition, extra_context, **kwargs):
        templates = self.template_path("competition.html", competition.slug)
        return self.generic_detail(
            request,
            self._competitions,
            slug=competition.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def season(self, request, competition, season, extra_context, **kwargs):
        templates = self.template_path("season.html", competition.slug, season.slug)
        extra_context.update(
            season.matches.exclude(is_bye=True).aggregate(
                timeslot_count=Count("datetime", distinct=True),
                match_count=Count("pk", distinct=True),
                points_scored=Sum(
                    Case(
                        When(
                            statistics__match__stage__division__season=season,
                            then=F("statistics__points"),
                        )
                    )
                ),
                caps_awarded=Sum(
                    Case(
                        When(
                            statistics__match__stage__division__season=season,
                            then=F("statistics__played"),
                        )
                    )
                ),
            )
        )
        return self.generic_detail(
            request,
            competition.seasons,
            slug=season.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def runsheet(self, request, competition, season, extra_context, **kwargs):
        context = {"dates": season.matches.dates("date", "day")}
        context.update(extra_context)
        templates = self.template_path(
            "runsheet_list.html", competition.slug, season.slug
        )
        return self.render(request, templates, context)

    @competition_by_slug_m
    def day_runsheet(self, request, season, date, extra_context, **kwargs):
        return super().day_runsheet(request, season, date, extra_context, **kwargs)

    @competition_by_slug_m
    @login_required_m
    def results(self, request, competition, season, extra_context, date=None, **kwargs):
        has_permission = permissions_required(request, Match, return_403=False)
        if has_permission is not None:
            return has_permission

        if date is not None:
            matches = season.matches.filter(date=date)
        else:
            matches = season.matches

        # Allow super-user accounts visibility to look 1 year into the future.
        if request.user.is_superuser:
            now = timezone.now() + relativedelta(years=1)
        else:
            now = None

        # Filter the list of matches to those which require result entry
        basic_results = matches_require_basic_results(now, matches)
        details_results = matches_require_details_results(matches, True)

        context = {
            "datetimes": [
                timezone.localtime(each, pytz.timezone(season.timezone))
                for each in basic_results.datetimes("datetime", "minute")
            ],
            "details": details_results,
        }
        context.update(extra_context)
        templates = self.template_path("results.html", competition.slug, season.slug)
        return self.render(request, templates, context)

    @competition_by_slug_m
    @login_required_m
    def stream(self, request, competition, season, extra_context, date=None, **kwargs):
        has_permission = permissions_required(request, Match, return_403=False)
        if has_permission is not None:
            return has_permission

        if date is not None:
            matches = season.matches.filter(date=date)
        else:
            matches = season.matches

        # Allow super-user accounts visibility to look 1 year into the future.
        if request.user.is_superuser:
            now = timezone.now() + relativedelta(years=1)
        else:
            now = None

        # Filter the list of matches to those which require streaming control
        stream_start = matches.exclude(external_identifier__isnull=True)

        context = {
            "datetimes": [
                timezone.localtime(each, pytz.timezone(season.timezone))
                for each in stream_start.datetimes("datetime", "minute")
            ],
        }
        context.update(extra_context)
        templates = self.template_path("stream.html", competition.slug, season.slug)
        return self.render(request, templates, context)

    @competition_by_slug_m
    @login_required_m
    def match_results(
        self, request, competition, season, date, time, extra_context, **kwargs
    ):
        has_permission = permissions_required(request, Match, return_403=False)
        if has_permission is not None:
            return has_permission
        redirect_to = self.reverse("results", args=(competition.slug, season.slug))
        return super().match_results(
            request,
            competition=competition,
            season=season,
            date=date,
            time=time,
            extra_context=extra_context,
            redirect_to=redirect_to,
            **kwargs,
        )

    @competition_by_slug_m
    @login_required_m
    def stream_control(
        self, request, competition, season, date, time, extra_context, **kwargs
    ):
        has_permission = permissions_required(request, Match, return_403=False)
        if has_permission is not None:
            return has_permission
        redirect_to = self.reverse("stream", args=(competition.slug, season.slug))
        return super().stream_control(
            request,
            competition=competition,
            season=season,
            date=date,
            time=time,
            extra_context=extra_context,
            redirect_to=redirect_to,
            **kwargs,
        )

    @login_required_m
    @competition_by_slug_m
    def edit_match_detail(self, request, match, extra_context, **kwargs):
        has_permission = permissions_required(
            request, Match, instance=match, return_403=False
        )
        if has_permission is not None:
            return has_permission
        redirect_to = self.reverse(
            "results",
            args=(
                match.stage.division.season.competition.slug,
                match.stage.division.season.slug,
            ),
        )
        return super().edit_match_detail(
            request,
            stage=match.stage,
            match=match,
            extra_context=extra_context,
            redirect_to=redirect_to,
            **kwargs,
        )

    @competition_by_slug_m
    def season_videos(self, request, competition, season, extra_context, **kwargs):
        templates = self.template_path(
            "season_videos.html", competition.slug, season.slug
        )
        queryset = (
            Match.objects.select_related(
                "stage__division",
                "home_team__club",
                "away_team__club",
                "play_at",
            )
            .exclude(videos__isnull=True)
            .filter(stage__division__season=season)
            .order_by("datetime", "play_at")
        )
        return self.generic_list(
            request,
            queryset,
            paginate_by=1000,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def club(self, request, competition, season, club, extra_context, **kwargs):
        templates = self.template_path(
            "club.html", competition.slug, season.slug, club.slug
        )
        return self.generic_detail(
            request,
            season.clubs,
            slug=club.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def division(self, request, competition, season, division, extra_context, **kwargs):
        templates = self.template_path(
            "division.html", competition.slug, season.slug, division.slug
        )
        extra_context.update(
            division.matches.exclude(is_bye=True).aggregate(
                timeslot_count=Count("datetime", distinct=True),
                match_count=Count("pk", distinct=True),
                points_scored=Sum(
                    Case(
                        When(
                            statistics__match__stage__division=division,
                            then=F("statistics__points"),
                        )
                    )
                ),
                caps_awarded=Sum(
                    Case(
                        When(
                            statistics__match__stage__division=division,
                            then=F("statistics__played"),
                        )
                    )
                ),
            )
        )
        return self.generic_detail(
            request,
            season.divisions,
            slug=division.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def stage(
        self, request, competition, season, division, stage, extra_context, **kwargs
    ):
        templates = self.template_path(
            "stage.html", competition.slug, season.slug, division.slug, stage.slug
        )
        extra_context["parent"] = stage
        extra_context.update(
            stage.matches.exclude(is_bye=True).aggregate(
                timeslot_count=Count("datetime", distinct=True),
                match_count=Count("pk", distinct=True),
                points_scored=Sum(
                    Case(
                        When(
                            statistics__match__stage=stage, then=F("statistics__points")
                        )
                    )
                ),
                caps_awarded=Sum(
                    Case(
                        When(
                            statistics__match__stage=stage, then=F("statistics__played")
                        )
                    )
                ),
            )
        )
        return self.generic_detail(
            request,
            division.stages,
            slug=stage.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def pool(
        self,
        request,
        competition,
        season,
        division,
        stage,
        pool,
        extra_context,
        **kwargs,
    ):
        # FIXME sadly the template name was not changed when we refactored
        #       pools to be subordinates of Stage.
        templates = self.template_path(
            "divisiongroup.html",
            competition.slug,
            season.slug,
            division.slug,
            stage.slug,
            pool.slug,
        )
        extra_context.update(
            pool.matches.exclude(is_bye=True).aggregate(
                timeslot_count=Count("datetime", distinct=True),
                match_count=Count("pk", distinct=True),
                points_scored=Sum(
                    Case(
                        When(
                            statistics__match__stage_group=pool,
                            then=F("statistics__points"),
                        )
                    )
                ),
                caps_awarded=Sum(
                    Case(
                        When(
                            statistics__match__stage_group=pool,
                            then=F("statistics__played"),
                        )
                    )
                ),
            )
        )
        return self.generic_detail(
            request,
            stage.pools,
            slug=pool.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def team(
        self, request, competition, season, division, team, extra_context, **kwargs
    ):
        templates = self.template_path(
            "team.html", competition.slug, season.slug, division.slug, team.slug
        )

        extra_context.update(
            team.matches.exclude(is_bye=True).aggregate(
                timeslot_count=Count("datetime", distinct=True),
                match_count=Count("pk", distinct=True),
                points_scored=Sum(
                    Case(
                        When(
                            statistics__player__teamassociation__team=team,
                            then=F("statistics__points"),
                        )
                    )
                ),
                caps_awarded=Sum(
                    Case(
                        When(
                            statistics__player__teamassociation__team=team,
                            then=F("statistics__played"),
                        )
                    )
                ),
            )
        )
        return self.generic_detail(
            request,
            division.teams,
            slug=team.slug,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def calendar(self, request, season, club=None, division=None, team=None, **kwargs):
        if season.disable_calendar:
            # The GONE response informs client that they should remove this resource
            # from their cache. When a calendar has been added to user's mobile device
            # they may never look at it again, but we continue to process the requests
            # which can have poor performance. Try to influence a cleanup of clients.
            return HttpResponseGone()

        if team is not None:
            matches = team.matches
        elif division is not None:
            matches = division.matches
        elif club is not None:
            matches = club.matches.filter(stage__division__season=season)
        else:
            matches = season.matches

        # Do not include matches which have not had the time scheduled
        matches = matches.exclude(datetime__isnull=True)

        # Perform select_related to reduce extra queries
        matches = matches.select_related("stage__division__season__competition")

        # Reduce the size of the data set to return from the database
        matches = matches.defer(
            "date",
            "time",
            "home_team__copy",
            "home_team__names_locked",
            "home_team__order",
            "home_team__short_title",
            "home_team__timeslots_after",
            "home_team__timeslots_before",
            "home_team_score",
            "away_team__copy",
            "away_team__names_locked",
            "away_team__order",
            "away_team__short_title",
            "away_team__timeslots_after",
            "away_team__timeslots_before",
            "away_team_score",
            "bye_processed",
            "evaluated",
            "external_identifier",
            "forfeit_winner",
            "include_in_ladder",
            "is_bye",
            "is_forfeit",
            "is_washout",
            "rank_importance",
            "videos",
            "stage__division__season__competition__copy",
            "stage__division__season__competition__enabled",
            "stage__division__season__competition__order",
            "stage__division__season__competition__rank_importance",
            "stage__division__season__competition__short_title",
            "stage__division__season__competition__short_title",
            "stage__division__season__competition__slug_locked",
            "stage__division__season__competition__slug_locked",
            "stage__division__season__competition__title",
            "stage__division__season__complete",
            "stage__division__season__copy",
            "stage__division__season__disable_calendar",
            "stage__division__season__enabled",
            "stage__division__season__hashtag",
            "stage__division__season__mode",
            "stage__division__season__mvp_results_public",
            "stage__division__season__order",
            "stage__division__season__rank_importance",
            "stage__division__season__short_title",
            "stage__division__season__slug_locked",
            "stage__division__season__start_date",
            "stage__division__season__statistics",
            "stage__division__season__timezone",
            "stage__division__bonus_points_formula",
            "stage__division__copy",
            "stage__division__draft",
            "stage__division__forfeit_against_score",
            "stage__division__forfeit_for_score",
            "stage__division__games_per_day",
            "stage__division__include_forfeits_in_played",
            "stage__division__order",
            "stage__division__points_formula",
            "stage__division__rank_division",
            "stage__division__rank_importance",
            "stage__division__short_title",
            "stage__division__slug_locked",
            "stage__division__sportingpulse_url",
            "stage__carry_ladder",
            "stage__copy",
            "stage__follows",
            "stage__keep_ladder",
            "stage__keep_mvp",
            "stage__order",
            "stage__rank_importance",
            "stage__scale_group_points",
            "stage__short_title",
            "stage__slug_locked",
        )

        # Remove any matches that are part of a draft division unless being viewed
        # by a superuser.
        if not request.user.is_superuser:
            matches = matches.exclude(stage__division__draft=True)

        # For development server turn back plain text to make debugging easier
        if settings.DEBUG:
            content_type = "text/plain"
        else:
            content_type = "text/calendar"

        response = HttpResponse(content_type=content_type)

        cal = Calendar()
        cal.add("prodid", "-//Tournament Control//%s//" % request.get_host())
        cal.add("version", "2.0")

        for match in matches.order_by("datetime", "play_at"):
            event = Event()
            event["uid"] = match.uuid.hex
            event.add("summary", match.title)
            event.add("location", f"{match.stage.division.title} ({match.stage.title})")
            event.add("dtstart", match.datetime)

            # FIXME match duration should not be hardcoded
            event.add("dtend", match.datetime + timedelta(minutes=45))
            # FIXME should be the last modified time of the match
            event.add("dtstamp", timezone.now())

            try:
                # Determine the resource uri to the detailed match view
                uri = reverse(
                    "competition:match",
                    kwargs={
                        "match": match.pk,
                        "division": match.stage.division.slug,
                        "season": match.stage.division.season.slug,
                        "competition": match.stage.division.season.competition.slug,
                    },
                )
            except NoReverseMatch:
                LOG.exception("Unable to resolve url for %r", match)
            else:
                # Combine the resource uri with our current request context
                event.add("description", request.build_absolute_uri(uri))

            cal.add_component(event)

        response.write(cal.to_ical())
        return response

    @competition_by_slug_m
    def match(
        self, request, competition, season, division, match, extra_context, **kwargs
    ):
        if match.is_bye or match.home_team is None or match.away_team is None:
            # Temporary, realistically nobody should ever have this URL but we
            # will use GONE so that Google removes it from their index.
            return HttpResponseGone()
        templates = self.template_path(
            "match.html", competition.slug, season.slug, division.slug
        )
        return self.generic_detail(
            request,
            division.matches,
            pk=match.pk,
            templates=templates,
            extra_context=extra_context,
        )

    @competition_by_slug_m
    def match_video(
        self, request, competition, season, division, match, extra_context, **kwargs
    ):
        if match.is_bye or match.home_team is None or match.away_team is None:
            # Temporary, realistically nobody should ever have this URL but we
            # will use GONE so that Google removes it from their index.
            return HttpResponseGone()
        templates = self.template_path(
            "videos.html", competition.slug, season.slug, division.slug
        )
        return self.generic_detail(
            request,
            division.matches,
            pk=match.pk,
            templates=templates,
            extra_context=extra_context,
        )

        # TODO add related model to record videos
        # return self.generic_list(request, match.videos,
        #                          templates=templates,
        #                          extra_context=extra_context)

    @login_required_m
    @competition_by_slug_m
    def forfeit_list(self, request, competition, season, extra_context, **kwargs):
        """
        List the matches that the visitor is permitted to forfeit. Must only
        show matches for teams that they are a registered member of (either as
        a player or other role).
        """
        try:
            teams = request.user.person.teams
        except Person.DoesNotExist:
            raise Http404

        matches = season.matches.filter(Q(home_team=teams) | Q(away_team=teams))

        context = {
            "matches": matches,
        }
        context.update(extra_context)

        templates = self.template_path("forfeit_list.html")
        return self.render(request, templates, context)

    @login_required_m
    @competition_by_slug_m
    def forfeit(self, request, competition, season, extra_context, match, **kwargs):
        """
        View that will allow a team member to forfeit a match they are due to
        be playing in.
        """
        try:
            teams = request.user.person.teams
        except Person.DoesNotExist:
            raise Http404

        matches = season.matches.filter(Q(home_team=teams) | Q(away_team=teams))

        redirect = self.redirect(
            self.reverse(
                "forfeit-list",
                kwargs={
                    "competition": competition.slug,
                    "season": season.slug,
                },
            )
        )

        if match not in matches:
            messages.add_message(
                request,
                messages.ERROR,
                "Attempting to forfeit a match you are not involved in.",
            )
            return redirect

        # decide which team to forfeit
        if match.home_team in teams and match.away_team in teams:
            messages.add_message(
                request,
                messages.WARNING,
                _(
                    "You are a member of both teams for this match, please "
                    "contact the competition manager."
                ),
            )
            return redirect

        elif match.home_team in teams:
            team = match.home_team
        elif match.away_team in teams:
            team = match.away_team
        else:
            messages.add_message(
                request,
                messages.ERROR,
                _(
                    "You are not a member of either team, please contact the "
                    "competition manager."
                ),
            )
            return redirect

        if request.method == "POST":
            # use the forfeit API to advise who made lodged the forfeit
            UNABLE_TO_POST = _(
                "Unable to post forfeit, please contact the " "competition manager."
            )
            try:
                success = match.forfeit(team, request.user.person)
            except AssertionError:
                # logger.exception("Failed precondition checks")
                messages.add_message(request, messages.ERROR, UNABLE_TO_POST)

            if success:
                messages.add_message(
                    request,
                    messages.INFO,
                    _(
                        "The match has been forfeit, notifications will be sent "
                        "to affected parties shortly."
                    ),
                )
            else:
                messages.add_message(request, messages.ERROR, UNABLE_TO_POST)

            return redirect

        context = {
            "match": match,
            "team": team,
        }
        context.update(extra_context)

        templates = self.template_path("forfeit.html")
        return self.render(request, templates, context)


class MultiCompetitionSite(CompetitionSite):
    kwargs_form_class = MultiConfigurationForm

    @classmethod
    def verbose_name(cls):
        return gettext("Multiple Competitions")

    def __init__(self, name="competition", app_name="competition", **kwargs):
        self.node = kwargs.get("node")  # store the node for future reference
        super().__init__(name=name, app_name=app_name, **kwargs)
        self._competitions = Competition.objects.filter(enabled=True)
        if "competition" in kwargs:
            q = functools.reduce(or_, [Q(slug=slug) for slug in kwargs["competition"]])
            self._competitions = self._competitions.filter(q)

    def get_urls(self):
        urlpatterns = [
            path("", self.index, name="index"),
            path("<slug:competition>/", include(self.competition_urls())),
        ]
        return urlpatterns


class RegistrationSite(Application):
    def __init__(self, name="rego", app_name="rego", **kwargs):
        super().__init__(name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        return []


class TournamentCalculatorSite(Application):
    def __init__(self, name="calculator", app_name="calculator", **kwargs):
        self.form_class = import_string(
            kwargs.pop(
                "form_class",
                "tournamentcontrol.competition.forms.TournamentScheduleForm",
            )
        )
        super().__init__(name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        urlpatterns = [
            path("", self.index, kwargs={"form_class": self.form_class}, name="index"),
            path(
                "live/",
                self.index,
                kwargs={
                    "form_class": DivisionTournamentScheduleForm,
                    "template_name": "live.html",
                },
                name="division",
            ),
        ]
        return urlpatterns

    def index(self, request, form_class, template_name="index.html", **extra_context):
        context = {}

        if request.GET:
            form = form_class(data=request.GET)
        else:
            form = form_class()

        if form.is_valid():
            context.setdefault("data", form.get_context())

        context.setdefault("form", form)
        context.update(extra_context)

        templates = self.template_path(template_name)
        return self.render(request, templates, context)


class RankingSite(Application):
    kwargs_form_class = RankingConfigurationForm

    def __init__(self, name="ranking", app_name="ranking", **kwargs):
        super().__init__(name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        urlpatterns = [
            path("", RankIndex.as_view(), name="index"),
            path("<int:year>/", RankYear.as_view(), name="year"),
            path("<int:year>/<str:month>/", RankMonth.as_view(), name="month"),
            path("<int:year>/<str:month>/<int:day>/", RankDay.as_view(), name="day"),
            path(
                "<int:year>/<str:month>/<int:day>/<slug:slug>/",
                RankDivision.as_view(),
                name="rank",
            ),
            path(
                "<int:year>/<str:month>/<int:day>/<slug:slug>/<slug:team>/",
                RankTeam.as_view(),
                name="team",
            ),
        ]
        return urlpatterns


competition = CompetitionSite()
registration = RegistrationSite()
calculator = TournamentCalculatorSite()
ranking = RankingSite()
