import datetime
import inspect
import logging
import time

from dateutil.parser import parse
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.functional import wraps
from tournamentcontrol.competition.models import Club, Competition, Season

try:
    from urllib.parse import ParseResult
except ImportError:
    from urlparse import ParseResult

logger = logging.getLogger(__name__)


@method_decorator
def registration(f, *a, **kw):
    @wraps(f)
    def _decorated(*args, **kwargs):
        club_id = kwargs.pop("club_id", None)
        person_id = kwargs.pop("person_id", None)
        season_id = kwargs.pop("season_id", None)
        team_id = kwargs.pop("team_id", None)

        if club_id:
            club = get_object_or_404(Club, pk=club_id)
            kwargs["club"] = club

            if person_id:
                person = get_object_or_404(club.members, pk=person_id)
                kwargs["person"] = person

            if season_id:
                season = get_object_or_404(
                    Season, pk=season_id, competition__clubs=club
                )
                kwargs["season"] = season

                # Knowing the season implies the competition
                kwargs["competition"] = season.competition

                # List of teams for the season.
                kwargs["teams"] = club.teams.filter(division__season=season)

            if team_id:
                team = get_object_or_404(club.teams, pk=team_id)
                kwargs["team"] = team

                # Knowing the team implies the division, season, competition.
                kwargs["division"] = team.division
                kwargs["season"] = team.division.season
                kwargs["competition"] = team.division.season.competition

        extra_context = kwargs.pop("extra_context", {})
        extra_context.update(kwargs)
        kwargs["extra_context"] = extra_context

        return f(*args, **kwargs)

    return _decorated


def competition_by_pk(f, *a, **kw):
    @wraps(f)
    def _decorated(request, *args, **kwargs):
        competition_id = kwargs.pop("competition_id", None)
        division_id = kwargs.pop("division_id", None)
        season_id = kwargs.pop("season_id", None)
        stage_id = kwargs.pop("stage_id", None)
        team_id = kwargs.pop("team_id", None)
        venue_id = kwargs.pop("venue_id", None)
        ground_id = kwargs.pop("ground_id", None)
        pool_id = kwargs.pop("pool_id", None)
        match_id = kwargs.pop("match_id", None)

        datestr = kwargs.pop("datestr", None)
        timestr = kwargs.pop("timestr", None)

        if competition_id:
            competition = get_object_or_404(Competition, pk=competition_id)
            kwargs["competition"] = competition
            if season_id:
                season = get_object_or_404(
                    competition.seasons.select_related("competition",).prefetch_related(
                        "divisions__rank_division",
                        "referees__person__user",
                        "referees__club",
                        "timeslots",
                    ),
                    pk=season_id,
                )
                kwargs["season"] = season
                if division_id:
                    division = get_object_or_404(
                        season.divisions.select_related("season__competition"),
                        pk=division_id,
                    )
                    kwargs["division"] = division
                    if stage_id:
                        stage = get_object_or_404(
                            division.stages.select_related(
                                "division__season__competition"
                            ),
                            pk=stage_id,
                        )
                        kwargs["stage"] = stage
                        if team_id:
                            team = get_object_or_404(
                                stage.undecided_teams.select_related(
                                    "stage__division__season__competition"
                                ),
                                pk=team_id,
                            )
                            kwargs["team"] = team

                        if pool_id:
                            pool = get_object_or_404(
                                stage.pools.select_related(
                                    "stage__division__season__competition"
                                ),
                                pk=pool_id,
                            )
                            kwargs["pool"] = pool

                        if match_id:
                            match = get_object_or_404(
                                stage.matches.select_related(
                                    "stage__division__season__competition"
                                ),
                                pk=match_id,
                            )
                            kwargs["match"] = match

                    elif team_id:
                        team = get_object_or_404(
                            division.teams.select_related(
                                "division__season__competition"
                            ),
                            pk=team_id,
                        )
                        kwargs["team"] = team
                elif venue_id:
                    venue = get_object_or_404(
                        season.venues.select_related("season__competition"), pk=venue_id
                    )
                    kwargs["venue"] = venue
                    if ground_id:
                        ground = get_object_or_404(
                            venue.grounds.select_related("venue__season__competition"),
                            pk=ground_id,
                        )
                        kwargs["ground"] = ground

                        if match_id:
                            match = get_object_or_404(ground.matches, pk=match_id)
                            kwargs["match"] = match
                    elif match_id:
                        match = get_object_or_404(venue.matches, pk=match_id)
                        kwargs["match"] = match

        if datestr:
            kwargs["date"] = parse(datestr).date()
            if timestr:
                kwargs["time"] = datetime.time(*time.strptime(timestr, "%H%M")[3:5])

        kwargs["base_url"] = ParseResult(
            "https" if request.is_secure() else "http",
            request.get_host(),
            "/",
            "",
            "",
            "",
        ).geturl()

        extra_context = kwargs.pop("extra_context", {})
        extra_context.update(kwargs)
        kwargs["extra_context"] = extra_context

        return f(request, *args, **kwargs)

    return _decorated


competition_by_pk_m = method_decorator(competition_by_pk)


def competition_by_slug(f, *a, **kw):
    @wraps(f)
    def _decorated(*args, **kwargs):
        # deep dive into the object internals and fetch the Application
        # instance so we can call the sitemapnodes method.
        closure = inspect.getclosurevars(f.func)
        try:
            manager = closure.globals["competition"]._competitions
        except KeyError:
            manager = Competition.objects

        club_slug = kwargs.pop("club", None)
        competition_slug = kwargs.pop("competition", None)
        division_slug = kwargs.pop("division", None)
        pool_slug = kwargs.pop("pool", None)
        season_slug = kwargs.pop("season", None)
        stage_slug = kwargs.pop("stage", None)
        team_slug = kwargs.pop("team", None)
        match_pk = kwargs.pop("match", None)

        datestr = kwargs.pop("datestr", None)
        timestr = kwargs.pop("timestr", None)

        base = manager.prefetch_related(
            "seasons",
            "seasons__divisions",
            "seasons__divisions__stages",
            "seasons__divisions__teams",
        )

        # see if there is an original node, we might need it later
        o_node = kwargs.pop("node", None)

        if competition_slug:
            competition = get_object_or_404(base, slug=competition_slug)
            kwargs["competition"] = competition
            if season_slug:
                season = get_object_or_404(competition.seasons, slug=season_slug)
                kwargs["season"] = season

                # List of clubs participating in this season.
                kwargs["clubs"] = competition.clubs.filter(
                    teams__division__season=season
                ).distinct()

                # We should deprecate this if it is unused in templates.
                kwargs["other_seasons"] = competition.seasons.exclude(slug=season_slug)

                # So we can build a navigation hierarchy, select extra column
                # which tells us if the season in a list of seasons is the
                # current scope.
                kwargs["seasons"] = competition.seasons.extra(
                    select={"current": "id = %s"}, select_params=(season.pk,)
                )

                # List of venues setup for this season.
                kwargs["venues"] = season.venues.all()

                if division_slug:
                    division = get_object_or_404(season.divisions, slug=division_slug)
                    kwargs["division"] = division

                    # Because Division and StageGroup use the same template
                    # we will use special context value of parent as the base
                    # for ladders and matches_by_date (both models have these
                    # methods implemented.
                    kwargs["parent"] = division

                    # So we can build a navigation hierarchy, select extra
                    # column which tells us if the division in a list of
                    # divisions is the current scope.
                    kwargs["divisions"] = season.divisions.extra(
                        select={"current": "id = %s"}, select_params=(division.pk,)
                    )

                    if stage_slug:
                        stage = get_object_or_404(
                            division.stages.annotate(pool_count=Count("pools")),
                            slug=stage_slug,
                        )
                        kwargs["stage"] = stage

                        if pool_slug:
                            pool = get_object_or_404(stage.pools, slug=pool_slug)
                            kwargs["pool"] = pool

                            # Overload the parent set above.
                            kwargs["parent"] = pool

                    if team_slug:
                        team = get_object_or_404(
                            division.teams.select_related("club"), slug=team_slug
                        )
                        kwargs["team"] = team

                        # List of players for this team.
                        players = (
                            team.people.select_related("person")
                            .prefetch_related("person__user")
                            .filter(is_player=True)
                        )
                        players = players.extra(
                            select={"has_number": "number IS NULL"},
                            order_by=(
                                "has_number",
                                "number",
                                "person__last_name",
                                "person__first_name",
                            ),
                        )
                        kwargs["players"] = players

                    if match_pk:
                        match = get_object_or_404(division.matches, pk=match_pk)
                        kwargs["match"] = match

                elif match_pk:
                    match = get_object_or_404(season.matches, pk=match_pk)
                    kwargs["match"] = match

        if club_slug:
            club = get_object_or_404(Club, slug=club_slug)
            kwargs["club"] = club
            season = kwargs.get("season")
            if season:
                kwargs["teams"] = club.teams.filter(
                    division__season=season
                ).prefetch_related("division", "stage_group")

        if datestr:
            kwargs["date"] = parse(datestr).date()
            if timestr:
                kwargs["time"] = datetime.time(*time.strptime(timestr, "%H%M")[3:5])

        logger.debug("o_node = {0}".format(o_node))

        logger.debug('kwargs["node"] = {node}'.format(node=o_node))

        extra_context = kwargs.pop("extra_context", {})
        extra_context.update(kwargs)
        kwargs["extra_context"] = extra_context

        return f(*args, **kwargs)

    return _decorated


competition_by_slug_m = method_decorator(competition_by_slug)
