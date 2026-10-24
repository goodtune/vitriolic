import collections
import functools
import hashlib
import logging
from datetime import date, timedelta
from operator import or_

from django.conf import settings
from django.contrib.sitemaps import views as sitemaps_views
from django.core.cache import cache
from django.db.models import Case, Count, F, Max, Prefetch, Q, Sum, When
from django.http import Http404, HttpResponse, HttpResponseGone
from django.shortcuts import get_object_or_404
from django.urls import include, path, re_path, reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.http import urlencode
from django.utils.module_loading import import_string
from django.utils.translation import gettext
from django.views.decorators.cache import cache_page, patch_cache_control
from guardian.utils import get_40x_or_None
from icalendar import Calendar, Event, vUri

from touchtechnology.admin.shells import ShellTemplatesMixin
from touchtechnology.admin.sites import site as admin_site
from touchtechnology.common.sites import Application
from touchtechnology.common.utils import get_perms_for_model
from tournamentcontrol.competition.decorators import competition_by_slug_m
from tournamentcontrol.competition.forms import (
    ConfigurationForm,
    DivisionTournamentScheduleForm,
    MultiConfigurationForm,
)
from tournamentcontrol.competition.models import (
    Competition,
    Ground,
    Match,
    Season,
    Team,
    Venue,
)
from tournamentcontrol.competition.utils import (
    matches_timeline,
    team_needs_progressing,
)

LOG = logging.getLogger(__name__)


def match_location(place):
    """
    Describe a ``Place`` for the iCalendar ``LOCATION`` and ``GEO`` properties.

    ``Match.play_at`` points at a ``Place``, which will be either a ``Venue``
    or one of the ``Ground`` records beneath it. Grounds are named for the
    playing surface alone ("Field 3"), so we qualify them with their venue to
    give the calendar client something it can resolve to a point on a map.

    Returns a ``(label, coordinates)`` tuple; either element may be ``None``.
    """
    if place is None:
        return None, None

    def coordinates(place):
        # A half-entered latlng yields fewer pieces than we need; treat it as
        # having no coordinates rather than raising.
        pieces = place.location
        if pieces and len(pieces) >= 2:
            return pieces[0], pieces[1]
        return None

    # The reverse accessor for a multi-table inheritance child raises
    # RelatedObjectDoesNotExist, a subclass of AttributeError, so getattr with
    # a default tells us whether this Place is really a Ground.
    ground = getattr(place, "ground", None)

    if ground is None:
        return place.title, coordinates(place)

    # Individual playing surfaces are often mapped only at the venue.
    label = f"{ground.title}, {ground.venue.title}"
    return label, coordinates(ground) or coordinates(ground.venue)


THUMBNAIL_CACHE_TTL = 300  # 5 minutes

# Calendar subscribers (iOS, Google Calendar) poll their feeds constantly and
# every refresh would otherwise render the whole feed from scratch. Letting
# shared caches (a CDN, or Django's cache middleware) hold the feed for a few
# minutes means a schedule change takes that much longer to reach subscribers.
CALENDAR_CACHE_TTL = getattr(settings, "TOURNAMENTCONTROL_CALENDAR_CACHE_TTL", 600)

# Once the last match in a feed is this long past it will never change again
# in any way a subscriber cares about, so the feed can be held for much longer.
CALENDAR_ARCHIVE_AFTER = timedelta(
    seconds=getattr(settings, "TOURNAMENTCONTROL_CALENDAR_ARCHIVE_AFTER", 3 * 86400)
)
CALENDAR_ARCHIVE_CACHE_TTL = getattr(
    settings, "TOURNAMENTCONTROL_CALENDAR_ARCHIVE_CACHE_TTL", 7 * 86400
)
# How long the rendered archived feed is kept in Django's cache; short enough
# that a correction to an old match reaches subscribers within a day.
CALENDAR_ARCHIVE_RENDER_TTL = 86400


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


class CompetitionSite(Application):
    kwargs_form_class = ConfigurationForm

    def __init__(self, name="competition", app_name="competition", **kwargs):
        # store the node for future reference
        self.node = kwargs.get("node")
        super().__init__(name=name, app_name=app_name, **kwargs)
        self._competitions = Competition.objects.filter(enabled=True)
        if "competition" in kwargs and kwargs["competition"]:
            self._competitions = self._competitions.filter(slug=kwargs["competition"])

    def venue_urls(self):
        return [
            path("<slug:venue>/", self.venue, name="venue"),
            re_path(
                r"^(?P<venue>[^/]+)/(?P<datestr>\d{8})/$", self.venue, name="venue"
            ),
            path("<slug:venue>/ground/<slug:ground>/", self.ground, name="ground"),
            re_path(
                r"^(?P<venue>[^/]+)/ground/(?P<ground>[^/]+)/(?P<datestr>\d{8})/$",
                self.ground,
                name="ground",
            ),
        ]

    def season_urls(self):
        return [
            path("", self.season, name="season"),
            path("fixtures/", self.season_fixtures, name="season-fixtures"),
            path("videos/", self.season_videos, name="season-videos"),
            path(
                "thumbnail/",
                cache_page(THUMBNAIL_CACHE_TTL)(self.season_thumbnail),
                name="season-thumbnail",
            ),
            path(
                "thumbnail/<int:width>x<int:height>/",
                cache_page(THUMBNAIL_CACHE_TTL)(self.season_thumbnail),
                name="season-thumbnail",
            ),
            path("club:<slug:club>/", self.club, name="club"),
            path("club:<slug:club>.ics", self.calendar, name="calendar"),
            path("venue/", include(self.venue_urls())),
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
            path(
                "<slug:division>/match:<int:match>/thumbnail/",
                cache_page(THUMBNAIL_CACHE_TTL)(self.match_thumbnail),
                name="match-thumbnail",
            ),
            path(
                "<slug:division>/match:<int:match>/thumbnail/<int:width>x<int:height>/",
                cache_page(THUMBNAIL_CACHE_TTL)(self.match_thumbnail),
                name="match-thumbnail",
            ),
            path("<slug:division>/<slug:team>.ics", self.calendar, name="calendar"),
            path("<slug:division>/<slug:team>/", self.team, name="team"),
            path(
                "<slug:division>/<slug:team>/timeline/",
                self.team_timeline,
                name="team-timeline",
            ),
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
        seasons = Season.objects.navigation()
        return self._competitions.prefetch_related(Prefetch("seasons", seasons))

    def index(self, request, **kwargs):
        return self.generic_list(
            request,
            self.competitions,
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
            competition.seasons.defer("live_stream_thumbnail_image"),
            slug=season.slug,
            templates=templates,
            extra_context=extra_context,
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
        # each team's row shows its next match, or else its last one
        extra_context["teams"] = Team.prefetch_next_and_last_match(
            extra_context["teams"]
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
    def season_fixtures(self, request, competition, season, extra_context, **kwargs):
        """
        Experimental season-wide fixture navigator: every match in the
        season grouped by day, filterable by division, team, and place.
        Only available when the season has opted in via
        ``enable_experimental_views``.

        The full page renders only a light shell — filter controls,
        selection counts, and one heading per day (built from a single
        aggregate query, without materialising any match rows). Each
        day's fixture table is fetched separately via the ``day`` GET
        parameter: htmx swaps it in lazily as the day scrolls into view,
        and the same URLs work as plain links without JavaScript. This
        keeps every request small — a tournament season can hold close
        to a thousand matches, far too many to render in one response.
        """
        if not season.enable_experimental_views:
            raise Http404("Experimental views are not enabled for this season.")

        # Keep the base query narrow — matches plus the joins needed for
        # filtering and ordering only. Wide select_related chains (teams,
        # clubs, and especially the *_eval_related self-joins back onto
        # the match table) produced pathological query plans on large
        # production datasets; the related objects are fetched with a
        # handful of flat prefetch queries instead.
        team_qs = Team.objects.select_related("club", "division")
        matches = (
            season.matches.exclude(is_bye=True)
            # matches without a scheduled date cannot appear in a
            # day-by-day navigator
            .filter(date__isnull=False, stage__division__draft=False)
            .select_related(None)
            .select_related("play_at", "stage__division", "stage_group")
            # never drag live-stream thumbnail blobs out of the database
            # for a list view — hundreds of matches each carrying an image
            # is hundreds of megabytes per request at tournament scale
            .defer("live_stream_thumbnail_image")
            .prefetch_related(
                Prefetch("home_team", queryset=team_qs),
                Prefetch("away_team", queryset=team_qs),
                "home_team_undecided",
                "away_team_undecided",
                "home_team_eval_related",
                "away_team_eval_related",
            )
            .order_by("date", "time", "play_at__ground__order", "pk")
        )

        divisions = season.divisions.public()

        division = None
        division_slug = request.GET.get("division")
        if division_slug:
            division = get_object_or_404(divisions, slug=division_slug)
            matches = matches.filter(stage__division=division)

        teams = Team.objects.filter(division__season=season, division__draft=False)
        if division is not None:
            teams = teams.filter(division=division)
        team_choices = (
            teams.order_by("title", "slug").values_list("slug", "title").distinct()
        )

        team_slug = request.GET.get("team")
        if team_slug:
            # a slug may legitimately match several teams (the same nation
            # entered in multiple divisions), but zero matches is a bad
            # filter value — treat it like the place filter and 404
            selected = teams.filter(slug=team_slug)
            if not selected.exists():
                raise Http404("No team matches the given filter.")
            matches = matches.filter(
                Q(home_team__in=selected) | Q(away_team__in=selected)
            )

        venues = season.venues.prefetch_related("grounds")

        selected_place = None
        place_pk = request.GET.get("place")
        if place_pk:
            try:
                place_pk = int(place_pk)
            except ValueError:
                raise Http404("Invalid place.")
            try:
                selected_place = season.venues.get(pk=place_pk)
                # a venue selection includes matches scheduled directly at
                # the venue and on any of its grounds
                matches = matches.filter(
                    Q(play_at=selected_place) | Q(play_at__ground__venue=selected_place)
                )
            except Venue.DoesNotExist:
                selected_place = get_object_or_404(
                    Ground.objects.filter(venue__season=season), pk=place_pk
                )
                matches = matches.filter(play_at=selected_place)

        # one cheap aggregate builds the day index — no match rows are
        # materialised for the page shell
        day_index = list(
            matches.order_by()
            .values("date")
            .annotate(count=Count("pk"))
            .order_by("date")
        )

        selected_day = None
        day_matches = None
        day_param = request.GET.get("day")
        if day_param:
            try:
                selected_day = date.fromisoformat(day_param)
            except ValueError:
                raise Http404("Invalid day.")
            # a well-formed day outside the current selection is a bad
            # filter value — treat it like the other filters and 404
            if not any(each["date"] == selected_day for each in day_index):
                raise Http404("No matches on this day.")
            day_matches = list(matches.filter(date=selected_day))

        # echo the active filters into the per-day fragment URLs
        filter_params = {}
        if division is not None:
            filter_params["division"] = division.slug
        if team_slug:
            filter_params["team"] = team_slug
        if selected_place is not None:
            filter_params["place"] = selected_place.pk
        filter_query = urlencode(filter_params)
        if filter_query:
            filter_query += "&"

        # the same candidate chain serves the htmx fragment response and
        # the {% include %} for the selected day on the full page, so
        # per-competition/season template overrides apply to both
        day_template_names = self.template_path(
            "_season_fixtures_day.html", competition.slug, season.slug
        )

        context = {
            "selected_day": selected_day,
            "day_matches": day_matches,
            "day_template_names": day_template_names,
        }
        context.update(extra_context)

        # request.htmx is set by django_htmx.middleware.HtmxMiddleware,
        # which is required — see tournamentcontrol.competition.E001
        if request.htmx and selected_day is not None:
            # htmx fragment: just the one day's fixture table
            return self.render(request, day_template_names, context)

        team_ids = set()
        for home_team_id, away_team_id in (
            matches.prefetch_related(None)
            .values_list("home_team", "away_team")
            .iterator()
        ):
            team_ids.update((home_team_id, away_team_id))
        team_ids.discard(None)

        context.update(
            {
                "divisions": divisions,
                "team_choices": team_choices,
                "venues": venues,
                "selected_division": division,
                "selected_team": team_slug,
                "selected_place": selected_place,
                "day_index": day_index,
                "filter_query": filter_query,
                "match_count": sum(each["count"] for each in day_index),
                "team_count": len(team_ids),
            }
        )

        templates = self.template_path(
            "season_fixtures.html", competition.slug, season.slug
        )
        return self.render(request, templates, context)

    @competition_by_slug_m
    def team_timeline(
        self, request, competition, season, division, team, extra_context, **kwargs
    ):
        """
        Experimental team-centric timeline: the season from one team's
        point of view — results so far, the gap between games, what is
        next, and the progression matches that are still to resolve.
        Only available when the season has opted in via
        ``enable_experimental_views``.
        """
        if not season.enable_experimental_views:
            raise Http404("Experimental views are not enabled for this season.")
        if division.draft:
            raise Http404("Division is not visible in the front-end.")

        timeline = matches_timeline(team.matches_by_date())

        record = team.ladder_summary.aggregate(
            played=Sum("played"),
            win=Sum("win"),
            loss=Sum("loss"),
            draw=Sum("draw"),
        )

        team_qs = Team.objects.select_related("club", "division")
        undecided = (
            division.matches.filter(team_needs_progressing)
            .exclude(is_bye=True)
            .select_related(None)
            .select_related("play_at", "stage__division", "stage_group")
            .defer("live_stream_thumbnail_image")
            .prefetch_related(
                Prefetch("home_team", queryset=team_qs),
                Prefetch("away_team", queryset=team_qs),
                "home_team_undecided",
                "away_team_undecided",
                "home_team_eval_related",
                "away_team_eval_related",
            )
            .order_by("date", "time", "play_at__ground__order", "pk")
        )
        tzinfo = timezone.get_current_timezone()
        undecided_by_date = collections.OrderedDict()
        for match in undecided:
            undecided_by_date.setdefault(match.get_date(tzinfo), []).append(match)

        context = {
            "timeline": timeline,
            "record": record,
            "undecided_by_date": undecided_by_date,
        }
        context.update(extra_context)

        templates = self.template_path(
            "team_timeline.html",
            competition.slug,
            season.slug,
            division.slug,
            team.slug,
        )
        return self.render(request, templates, context)

    def _place_context(self, matches, day=None):
        """
        Build the shared context for the venue and ground views: the days
        on which the place hosts public matches, and those matches grouped
        by day — narrowed to ``day`` when one is selected.
        """
        matches = matches.exclude(is_bye=True).filter(
            date__isnull=False, stage__division__draft=False
        )

        dates = list(matches.dates("date", "day"))
        if day is not None:
            # a well-formed day without matches at this place is a bad
            # filter value, just like on the season fixtures navigator
            if day not in dates:
                raise Http404("No matches on this day.")
            matches = matches.filter(date=day)

        # keep the query narrow and fetch the teams with flat prefetch
        # queries — see season_fixtures for the reasoning
        team_qs = Team.objects.select_related("club", "division")
        matches = (
            matches.select_related(None)
            .select_related("play_at", "stage__division", "stage_group")
            .defer("live_stream_thumbnail_image")
            .prefetch_related(
                Prefetch("home_team", queryset=team_qs),
                Prefetch("away_team", queryset=team_qs),
                "home_team_undecided",
                "away_team_undecided",
                "home_team_eval_related",
                "away_team_eval_related",
            )
            .order_by("date", "time", "play_at__ground__order", "pk")
        )

        matches_by_date = collections.OrderedDict()
        for match in matches:
            matches_by_date.setdefault(match.date, []).append(match)

        return {
            "dates": dates,
            "selected_date": day,
            "matches_by_date": matches_by_date,
        }

    @competition_by_slug_m
    def venue(
        self, request, competition, season, venue, extra_context, date=None, **kwargs
    ):
        """
        Every public match at a venue — scheduled on the venue itself or on
        any of its grounds — grouped by day, optionally for a single day.
        """
        matches = season.matches.filter(
            Q(play_at=venue) | Q(play_at__ground__venue=venue)
        )
        context = self._place_context(matches, date)
        context.update(extra_context)

        templates = self.template_path(
            "venue.html", competition.slug, season.slug, venue.slug
        )
        return self.render(request, templates, context)

    @competition_by_slug_m
    def ground(
        self,
        request,
        competition,
        season,
        venue,
        ground,
        extra_context,
        date=None,
        **kwargs,
    ):
        """
        Every public match on a single ground of a venue, grouped by day,
        optionally for a single day.
        """
        matches = season.matches.filter(play_at=ground)
        context = self._place_context(matches, date)
        context.update(extra_context)

        templates = self.template_path(
            "ground.html",
            competition.slug,
            season.slug,
            venue.slug,
            ground.slug,
        )
        return self.render(request, templates, context)

    @competition_by_slug_m
    def calendar(self, request, season, club=None, division=None, team=None, **kwargs):
        if season.disable_calendar:
            # The GONE response informs client that they should remove this
            # resource from their cache. When a calendar has been added to
            # user's mobile device they may never look at it again, but we
            # continue to process the requests which can have poor performance.
            # Try to influence a cleanup of clients.
            return HttpResponseGone()

        if team is not None:
            matches = Match.objects.filter(Q(home_team=team) | Q(away_team=team))
        elif division is not None:
            matches = Match.objects.filter(stage__division=division)
        elif club is not None:
            matches = Match.objects.filter(
                Q(home_team__club=club) | Q(away_team__club=club),
                stage__division__season=season,
            )
        else:
            matches = Match.objects.filter(stage__division__season=season)

        # Do not include matches which have not had the time scheduled
        matches = matches.exclude(datetime__isnull=True)

        # Fetch only the fields needed for calendar event generation.
        # Team titles are provided by MatchManager's _team_titles() SQL
        # annotations (home_team_title, away_team_title), so we don't need
        # to select_related the team objects or use match.title (which
        # triggers per-match template rendering and potential N+1 queries).
        matches = matches.select_related(
            "stage__division__season__competition",
            "play_at__ground__venue",
        ).only(
            "uuid",
            "datetime",
            "play_at__title",
            "play_at__latlng",
            "play_at__ground__venue__title",
            "play_at__ground__venue__latlng",
            "stage__title",
            "stage__division__title",
            "stage__division__slug",
            "stage__division__season__slug",
            "stage__division__season__competition__slug",
        )

        # Remove any matches that are part of a draft division unless being
        # viewed by a superuser.
        if not request.user.is_superuser:
            matches = matches.exclude(stage__division__draft=True)

        # A feed whose last match finished some time ago is archived: it will
        # not change again, so it can be cached for a long time. An empty feed
        # is treated as live because matches may yet be scheduled.
        last_match = matches.aggregate(last=Max("datetime"))["last"]
        archived = (
            last_match is not None
            and last_match + CALENDAR_ARCHIVE_AFTER < timezone.now()
        )

        # The rendered archived feed is shared by everyone except superusers,
        # who see draft divisions. It names the host in its links, so the key
        # does too.
        render_key = None
        if archived and not request.user.is_superuser:
            identity = f"{request.get_host()}|{request.path}"
            digest = hashlib.sha256(identity.encode()).hexdigest()
            render_key = f"competition.calendar.{digest}"
            body = cache.get(render_key)
            if body is not None:
                return self._calendar_response(request, body, archived)

        cal = Calendar()
        cal.add("prodid", f"-//Tournament Control//{request.get_host()}//")
        cal.add("version", "2.0")

        # Cache reverse() URL templates per division to avoid calling it for
        # every match. All matches in the same division produce URLs that
        # differ only in the match pk.
        _url_templates = {}

        for match in matches.order_by("datetime", "play_at"):
            event = Event()
            event["uid"] = match.uuid.hex

            # Use SQL-computed title annotations instead of match.title to
            # avoid per-match template rendering and N+1 queries for
            # undecided teams. The annotations are plain text, a bye too.
            home = match.home_team_title or ""
            away = match.away_team_title or ""
            if home and away:
                summary = f"{home} vs {away}"
            elif home or away:
                summary = home or away
            else:
                summary = "TBD"
            event.add("summary", summary)

            # The division and stage are not a location; they belong in
            # CATEGORIES (machine readable) and DESCRIPTION (human readable,
            # because most clients do not surface CATEGORIES at all).
            division = f"{match.stage.division.title} ({match.stage.title})"
            event.add("categories", [match.stage.division.title, match.stage.title])

            location, coordinates = match_location(match.play_at)
            if location:
                event.add("location", location)
            if coordinates:
                event.add("geo", coordinates)
                # Apple devices ignore GEO; this proprietary property is what
                # drops the pin on the map in their calendar applications.
                event.add(
                    "x-apple-structured-location",
                    vUri(f"geo:{coordinates[0]},{coordinates[1]}"),
                    parameters={
                        "VALUE": "URI",
                        "X-ADDRESS": location,
                        "X-APPLE-RADIUS": "100",
                        "X-TITLE": location,
                    },
                )

            event.add("dtstart", match.datetime)

            # FIXME match duration should not be hardcoded
            event.add("dtend", match.datetime + timedelta(minutes=45))
            # FIXME should be the last modified time of the match. An archived
            # feed uses a fixed stamp so its ETag does not change on every fetch.
            event.add("dtstamp", last_match if archived else timezone.now())

            # Determine the resource uri to the detailed match view.
            # Cache the URL pattern per division to avoid repeated reverse().
            div_id = match.stage.division_id
            if div_id not in _url_templates:
                try:
                    uri = reverse(
                        "competition:match",
                        kwargs={
                            "match": match.pk,
                            "division": match.stage.division.slug,
                            "season": match.stage.division.season.slug,
                            "competition": match.stage.division.season.competition.slug,
                        },
                    )
                    _url_templates[div_id] = uri.replace(
                        f"match:{match.pk}/", "match:{}/"
                    )
                except NoReverseMatch:
                    LOG.exception("Unable to resolve url for %r", match)
                    _url_templates[div_id] = None

            url_template = _url_templates[div_id]
            if url_template is not None:
                uri = request.build_absolute_uri(url_template.format(match.pk))
                event.add("url", uri)
                event.add("description", f"{division}\n\n{uri}")
            else:
                event.add("description", division)

            cal.add_component(event)

        body = cal.to_ical()
        if render_key is not None:
            cache.set(render_key, body, CALENDAR_ARCHIVE_RENDER_TTL)
        return self._calendar_response(request, body, archived)

    def _calendar_response(self, request, body, archived):
        # For development server turn back plain text to make debugging easier
        content_type = "text/plain" if settings.DEBUG else "text/calendar"
        response = HttpResponse(body, content_type=content_type)

        # Superusers see draft divisions, so their feed must never be stored
        # where it could be served to anyone else. Varying on Cookie keeps a
        # cached public feed from being served to a signed-in superuser.
        patch_vary_headers(response, ["Cookie"])
        if request.user.is_superuser:
            patch_cache_control(response, private=True)
        else:
            ttl = CALENDAR_ARCHIVE_CACHE_TTL if archived else CALENDAR_CACHE_TTL
            # Let a shared cache keep serving the previous copy while it
            # fetches a new one, so a subscriber never waits for generation.
            patch_cache_control(
                response, public=True, max_age=ttl, stale_while_revalidate=ttl
            )
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

    @competition_by_slug_m
    def season_thumbnail(
        self, request, competition, season, width=None, height=None, **kwargs
    ):
        """
        Serve season thumbnail images.

        URLs:
        - /season/thumbnail/ - serves original image
        - /season/thumbnail/<width>x<height>/ - serves resized image
        """
        return season.live_stream_thumbnail_response(width=width, height=height)

    @competition_by_slug_m
    def match_thumbnail(
        self,
        request,
        competition,
        season,
        division,
        match,
        width=None,
        height=None,
        **kwargs,
    ):
        """
        Serve match thumbnail images.

        URLs:
        - /match/thumbnail/ - serves original image (falls back to season thumbnail)
        - /match/thumbnail/<width>x<height>/ - serves resized image
        """
        return match.live_stream_thumbnail_response(width=width, height=height)


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


class TournamentCalculatorSite(ShellTemplatesMixin, Application):
    @property
    def shell(self):
        return admin_site.shell

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


competition = CompetitionSite()
registration = RegistrationSite()
calculator = TournamentCalculatorSite()
