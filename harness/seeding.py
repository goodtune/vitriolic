"""Seed a harness database with an invented association.

Everything here is made up: the clubs, the people, the venues and the news.
The seed is idempotent. It is five blocks and each one is skipped when its
marker already exists, so a second run, on this day or a later one, changes
nothing. Each block runs in one transaction.

The organisation is built through ``AdminToolset``, the tools the MCP server
offers an administrator, so the seed exercises the same rules the admin does.
Only what no tool covers (clubs, people, roles, stream keys, score sheets,
statistics, and moving a finals match on to its teams) uses models or the test
factories.
"""

import datetime
import io
import itertools
import logging
import math
import random
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from enrolment.models import SchoolYear
from enrolment.seeding import FIRST_NAMES, LAST_NAMES

from harness.images import photo
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Chunk, Page, PageContent, Redirect
from touchtechnology.news.models import Article, Category, Translation
from tournamentcontrol.competition.mcp.admin import AdminToolset
from tournamentcontrol.competition.models import (
    Club,
    ClubAssociation,
    ClubRole,
    Competition,
    Match,
    MatchScoreSheet,
    Person,
    Season,
    SeasonReferee,
    Team,
    TeamAssociation,
    TeamRole,
)
from tournamentcontrol.competition.tests.factories import (
    LiveStreamEventFactory,
    LiveStreamKeyFactory,
    SimpleScoreMatchStatisticFactory,
)
from tournamentcontrol.competition.utils import round_robin_format

logger = logging.getLogger(__name__)

User = get_user_model()

PASSWORD = "password"

COMPETITION_SLUG = "harbour-touch-league"
TIMEZONE = "Australia/Sydney"
WEDNESDAY = 2

CLUBS = [
    ("Seacliff Sharks", "SEA"),
    ("Ferndale Foxes", "FER"),
    ("Millbrook Magpies", "MIL"),
    ("Oakridge Owls", "OAK"),
    ("Pinecrest Panthers", "PIN"),
    ("Riverbend Rays", "RIV"),
    ("Stonegate Stags", "STO"),
    ("Willowmere Wolves", "WIL"),
]

#: Venues, with the coordinates of an invented place and its fields.
VENUES = [
    ("Anchor Park", (-33.830, 151.240), ["Field 1", "Field 2", "Field 3"]),
    ("Lantern Reserve", (-33.800, 151.280), ["Field 1", "Field 2"]),
]

#: Each division and how many of the clubs enter a team, from the first.
DIVISIONS = [("Men's Open", 8), ("Women's Open", 7), ("Mixed Open", 6)]

#: Every division plays seven regular rounds, then two rounds of finals.
REGULAR_ROUNDS = 7
FINALS_ROUNDS = 2

FINALS_FORMAT = (
    "ROUND Semi Finals\n"
    "1: P1 vs P4 Semi 1\n"
    "2: P2 vs P3 Semi 2\n"
    "ROUND Grand Final\n"
    "3: W1 vs W2 Final"
)

#: The finals of a division whose regular season is played in two pools: the
#: winner of each pool meets the runner up of the other.
POOL_FINALS_FORMAT = (
    "ROUND Semi Finals\n"
    "1: G1P1 vs G2P2 Semi 1\n"
    "2: G2P1 vs G1P2 Semi 2\n"
    "ROUND Grand Final\n"
    "3: W1 vs W2 Final"
)

#: The division of the finished season that plays its regular season in two
#: pools of three, a single round robin in each.
POOLED_SEASON = "Autumn 2026"
POOLED_DIVISION = "Mixed Open"
POOLS = ["Pool A", "Pool B"]

CLUB_ROLES = ["President", "Secretary", "Treasurer"]
TEAM_ROLES = ["Captain", "Coach"]

PEOPLE_PER_CLUB = 3
PEOPLE_PER_TEAM = 2

#: Where the current season is up to. The played rounds are the first five.
PLAYED_ROUNDS = 5

#: A scripted result, found by the division and the round it happens in.
CURRENT_SEASON_SCRIPT = {
    ("Men's Open", 2): "draw",
    ("Men's Open", 3): "forfeit",
    ("Women's Open", 5): "unresulted",
}


def seed(stdout=None) -> dict[str, int]:
    """
    Add what is missing, then return the number of rows of each model the
    seed touches. The counts are also written to ``stdout`` when it is given,
    one ``Model: n`` to a line.
    """
    anchor = timezone.localdate()
    blocks = [
        ("users", _seed_users),
        ("organisation", _seed_organisation),
        ("content", _seed_content),
        ("news", _seed_news),
        ("enrolment", _seed_enrolment),
    ]
    for name, block in blocks:
        with transaction.atomic():
            if block(anchor):
                logger.info("Seeded %s", name)
            else:
                logger.info("Skipped %s, it is already there", name)

    counts = _counts()
    if stdout is not None:
        for model, count in counts.items():
            stdout.write("%s: %d\n" % (model, count))
    return counts


def main(argv: list[str]) -> int:
    """``python -m harness seed``."""
    # The demo project's LOGGING sends everything to a null handler, so this
    # module reports its progress on its own.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("seed: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    seed(stdout=sys.stdout)
    return 0


def _counts() -> dict[str, int]:
    """Rows per model in the apps the seed fills, leaving out the empty ones."""
    labels = {"auth", "common", "competition", "content", "enrolment", "news"}
    models = [
        model
        for model in apps.get_models()
        if model._meta.app_label in labels and model is not Permission
    ]
    names = [model._meta.object_name for model in models]
    counts = {}
    for model in models:
        name = model._meta.object_name
        if names.count(name) > 1:
            name = model._meta.label
        count = model._base_manager.count()
        if count:
            counts[name] = count
    return dict(sorted(counts.items()))


# =============================================================================
# 1. Users
# =============================================================================


def _seed_users(anchor) -> bool:
    if User.objects.filter(username="admin").exists():
        return False

    User.objects.create_superuser(
        "admin", "admin@example.org", PASSWORD, first_name="Site", last_name="Admin"
    )

    editors = Group.objects.create(name="Editors")
    editors.permissions.set(
        Permission.objects.filter(
            content_type__app_label="news",
            codename__in=[
                "%s_%s" % (action, model)
                for action in ("add", "change")
                for model in ("article", "category", "translation")
            ],
        )
        | Permission.objects.filter(
            content_type__app_label="content",
            codename__in=["add_page", "change_page"],
        )
    )
    editor = User.objects.create_user(
        "editor",
        "editor@example.org",
        PASSWORD,
        first_name="Edith",
        last_name="Editor",
        is_staff=True,
    )
    editor.groups.add(editors)

    scorer = User.objects.create_user(
        "scorer",
        "scorer@example.org",
        PASSWORD,
        first_name="Sam",
        last_name="Scorer",
        is_staff=True,
    )
    scorer.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label="competition",
            codename__in=["change_match", "add_simplescorematchstatistic"],
        )
    )
    return True


# =============================================================================
# 2. The organisation
# =============================================================================


def _seed_organisation(anchor) -> bool:
    if Competition.objects.filter(slug=COMPETITION_SLUG).exists():
        return False

    admin = User.objects.get(username="admin")
    tools = AdminToolset(request=SimpleNamespace(user=admin))

    # No tool creates a club, so the clubs and the people in them are models.
    clubs = [
        Club.objects.create(title=title, slug=slugify(title), abbreviation=abbreviation)
        for title, abbreviation in CLUBS
    ]
    competition = tools.create_competition(
        title="Harbour Touch League",
        slug=COMPETITION_SLUG,
        club_ids=[club.pk for club in clubs],
    )["competition"]
    competition = Competition.objects.get(pk=competition["id"])

    club_roles = [
        ClubRole.objects.create(competition=competition, name=name)
        for name in CLUB_ROLES
    ]
    for name in TEAM_ROLES:
        TeamRole.objects.create(competition=competition, name=name)
    people = _people(clubs, club_roles)

    round_robin = {
        teams: tools.create_draw_format(
            name="Round robin (%d teams)" % teams,
            text=round_robin_format(list(range(1, teams + 1))),
            teams=teams,
        )["draw_format"]["id"]
        for teams in (6, 8)
    }
    pool_round_robin = tools.create_draw_format(
        name="Round robin (3 teams)",
        text=round_robin_format(list(range(1, 4))),
        teams=3,
    )["draw_format"]["id"]
    finals = tools.create_draw_format(
        name="Top four finals", text=FINALS_FORMAT, teams=4, is_final=True
    )["draw_format"]["id"]
    pool_finals = tools.create_draw_format(
        name="Cross-pool finals", text=POOL_FINALS_FORMAT, teams=4, is_final=True
    )["draw_format"]["id"]
    formats = {
        "round_robin": round_robin,
        "pool_round_robin": pool_round_robin,
        "finals": finals,
        "pool_finals": pool_finals,
    }

    # The last Wednesday before the seed date is the fifth round of the
    # current season, which began four weeks before it. The finished season
    # ended with its finals two weeks before the current one began.
    week = datetime.timedelta(weeks=1)
    fifth_round = _wednesday_before(anchor)
    current_start = fifth_round - (PLAYED_ROUNDS - 1) * week
    finished_start = current_start - (2 + REGULAR_ROUNDS + FINALS_ROUNDS - 1) * week

    finished = _build_season(
        tools,
        competition,
        clubs,
        formats,
        title=POOLED_SEASON,
        start=finished_start,
        pooled=POOLED_DIVISION,
    )
    current = _build_season(
        tools,
        competition,
        clubs,
        formats,
        title="Spring 2026",
        start=current_start,
        # The break after the regular season, and a bye week for Mixed Open.
        season_exclusions=[current_start + (REGULAR_ROUNDS) * week],
        division_exclusions={
            "Mixed Open": [current_start + (REGULAR_ROUNDS - 1) * week]
        },
    )

    for season in (finished, current):
        _people_in_teams(season, people)

    _play(tools, finished, rounds=None, script={})
    _finish(tools, finished)
    _play(tools, current, rounds=PLAYED_ROUNDS, script=CURRENT_SEASON_SCRIPT)

    _extras(current, people, clubs)
    return True


def _wednesday_before(day: datetime.date) -> datetime.date:
    """The last Wednesday strictly before ``day``."""
    return day - datetime.timedelta(days=(day.weekday() - WEDNESDAY) % 7 or 7)


def _people(clubs, club_roles):
    """Three people in each club, each with a role in it. Returns them by club."""
    people = {}
    for club_index, club in enumerate(clubs):
        people[club.pk] = []
        for index in range(PEOPLE_PER_CLUB):
            number = club_index * PEOPLE_PER_CLUB + index
            first_name = FIRST_NAMES[number % len(FIRST_NAMES)]
            last_name = LAST_NAMES[(number * 7 + 3) % len(LAST_NAMES)]
            person = Person.objects.create(
                club=club,
                first_name=first_name,
                last_name=last_name,
                gender="FM"[number % 2],
                date_of_birth=datetime.date(1980 + number % 20, 1 + number % 12, 15),
                email="%s.%s@example.org" % (first_name.lower(), last_name.lower()),
            )
            association = ClubAssociation.objects.create(club=club, person=person)
            association.roles.add(club_roles[index])
            people[club.pk].append(person)
    return people


def _build_season(
    tools,
    competition,
    clubs,
    formats,
    *,
    title,
    start,
    season_exclusions=(),
    division_exclusions=None,
    pooled=None,
):
    """
    A season with its venues, time slots, divisions, teams and stages, and the
    draw for both stages built and scheduled on Wednesday nights from ``start``.
    The regular season of the division titled ``pooled`` is played in two
    pools, and its finals are drawn across them.
    """
    season_id = tools.create_season(
        competition_id=competition.pk,
        title=title,
        timezone=TIMEZONE,
        start_date=start,
        mode="season",
    )["season"]["id"]

    grounds = []
    for venue_title, (latitude, longitude), field_titles in VENUES:
        venue_id = tools.create_venue(
            season_id,
            title=venue_title,
            latitude=latitude,
            longitude=longitude,
            zoom=15,
        )["venue"]["id"]
        grounds += [
            ground["id"]
            for ground in tools.create_grounds(
                [{"venue_id": venue_id, "title": field} for field in field_titles]
            )["grounds"]
        ]

    times = tools.create_timeslot(
        season_id, start=datetime.time(18, 0), interval=45, count=4
    )["times"]

    if season_exclusions:
        tools.add_season_exclusion_dates(season_id, list(season_exclusions))

    divisions = tools.create_divisions(
        [
            {
                "season_id": season_id,
                "title": division_title,
                "points_formula": "3*win + 2*draw + 1*loss",
                "forfeit_for_score": 5,
                "forfeit_against_score": 0,
            }
            for division_title, __ in DIVISIONS
        ]
    )["divisions"]
    divisions = dict(zip((title for title, __ in DIVISIONS), divisions))

    tools.create_teams(
        [
            {"division_id": divisions[division_title]["id"], "club_id": club.pk}
            for division_title, count in DIVISIONS
            for club in clubs[:count]
        ]
    )

    stages = tools.create_stages(
        [
            spec
            for division in divisions.values()
            for spec in (
                {"division_id": division["id"], "title": "Regular Season"},
                {
                    "division_id": division["id"],
                    "title": "Finals",
                    "keep_ladder": False,
                },
            )
        ]
    )["stages"]
    regular, finals = stages[0::2], stages[1::2]

    for division_title, dates in (division_exclusions or {}).items():
        tools.add_division_exclusion_dates(divisions[division_title]["id"], dates)

    # One build for each stage, or for each pool of the pooled division.
    builds = []
    for index, (stage, (division_title, count)) in enumerate(zip(regular, DIVISIONS)):
        if division_title == pooled:
            for pool_id in _pools(tools, stage["id"], divisions[division_title]["id"]):
                builds.append(
                    (
                        index,
                        {
                            "pool_id": pool_id,
                            "draw_format_id": formats["pool_round_robin"],
                            "start_date": start,
                        },
                    )
                )
        else:
            builds.append(
                (
                    index,
                    {
                        "stage_id": stage["id"],
                        "draw_format_id": formats["round_robin"][8 if count > 6 else 6],
                        "start_date": start,
                        "rounds": REGULAR_ROUNDS,
                        "alternate_home_away_on_repeat": True,
                    },
                )
            )
    built = tools.build_draw([build for __, build in builds])["builds"]
    last_dates = {}
    for (index, __), build in zip(builds, built):
        last_dates[index] = max(last_dates.get(index, ""), build["last_date"])
    # The finals start the week after each division's last regular round.
    tools.build_draw(
        [
            {
                "stage_id": stage["id"],
                "draw_format_id": formats[
                    "pool_finals" if division_title == pooled else "finals"
                ],
                "start_date": datetime.date.fromisoformat(last_dates[index])
                + datetime.timedelta(weeks=1),
            }
            for index, (stage, (division_title, __)) in enumerate(
                zip(finals, DIVISIONS)
            )
        ]
    )

    season = Season.objects.get(pk=season_id)
    _schedule(tools, season, times, grounds)
    return season


def _pools(tools, stage_id, division_id):
    """
    Split the teams of a division between the pools of its stage, alternating
    down the teams in the order they were entered. Returns the pool ids.
    """
    pools = tools.create_pools(
        [{"stage_id": stage_id, "title": title} for title in POOLS]
    )["pools"]
    team_ids = list(
        Team.objects.filter(division_id=division_id)
        .order_by("order", "pk")
        .values_list("pk", flat=True)
    )
    for index, pool in enumerate(pools):
        tools.update_pool(pool["id"], team_ids=team_ids[index :: len(pools)])
    return [pool["id"] for pool in pools]


def _schedule(tools, season, times, grounds):
    """
    Give every match that is played (not a bye) a time and a ground, filling
    each night from the first kick-off. The slots a night uses are spread
    across the grounds and the times.
    """
    slots = [
        (datetime.time.fromisoformat(time), ground)
        for ground in grounds
        for time in times
    ]
    # A stride that shares no factor with the number of slots visits them all.
    stride = next(n for n in range(7, len(slots) + 7) if math.gcd(n, len(slots)) == 1)
    matches = Match.objects.filter(stage__division__season=season, is_bye=False)
    matches = matches.order_by("date", "stage__division__order", "round", "pk")
    items = []
    for __, night in itertools.groupby(matches, key=lambda match: match.date):
        for index, match in enumerate(night):
            time, ground = slots[index * stride % len(slots)]
            items.append({"match_id": match.pk, "time": time, "place_id": ground})
    tools.schedule_matches(items)


def _people_in_teams(season, people):
    """Two people from the club in each team, with a role in it."""
    roles = list(TeamRole.objects.filter(competition=season.competition))
    teams = Team.objects.filter(division__season=season).select_related("club")
    for team in teams:
        for index, person in enumerate(people[team.club_id][:PEOPLE_PER_TEAM]):
            association = TeamAssociation.objects.create(
                team=team, person=person, number=7 + index * 2
            )
            association.roles.add(roles[index])


def _play(tools, season, *, rounds, script):
    """
    Record the results of the regular season up to ``rounds`` (all of them
    when ``None``). ``script`` says which match in a round is a draw, a
    forfeit, or played without anyone entering the result.
    """
    for division in season.divisions.all():
        regular = division.stages.get(title="Regular Season")
        matches = regular.matches.order_by("round", "pk")
        if rounds is not None:
            matches = matches.filter(round__lte=rounds)
        scripted = set()
        for match in matches:
            if match.is_bye:
                tools.record_match_result(match.pk, bye_processed=True, verbose=False)
                continue
            what = script.get((division.title, match.round))
            if what and match.round not in scripted:
                scripted.add(match.round)
            else:
                what = None
            _result(tools, division, match, what)


def _result(tools, division, match, what=None):
    """Record one result: a close game of touch, or the scripted `what`."""
    rng = random.Random(
        "%s/%s/%s/%s"
        % (division.pk, match.round, match.home_team_id, match.away_team_id)
    )
    home, away = rng.randint(2, 9), rng.randint(2, 9)
    if what == "unresulted":
        return
    if what == "draw":
        away = home
    elif what == "forfeit":
        tools.record_match_result(
            match.pk,
            is_forfeit=True,
            forfeit_winner_id=match.away_team_id,
            home_team_score=division.forfeit_against_score,
            away_team_score=division.forfeit_for_score,
            verbose=False,
        )
        return
    elif home == away:
        home += 1
    tools.record_match_result(
        match.pk, home_team_score=home, away_team_score=away, verbose=False
    )


def _finish(tools, season):
    """
    Play the finals of a season whose regular season is done. Each finals
    match goes on to the teams its formula names, as it does when the admin
    progresses it, and the winners of the semi finals meet in the final.
    """
    for division in season.divisions.all():
        finals = division.stages.get(title="Finals")
        for round_number in (
            finals.matches.order_by("round").values_list("round", flat=True).distinct()
        ):
            for match in finals.matches.filter(round=round_number).order_by("pk"):
                # No tool puts a team on a match and keeps its formula.
                match.home_team, match.away_team = match.eval()
                match.evaluated = True
                match.save()
                _result(tools, division, match)


def _extras(season, people, clubs):
    """Referee, stream key and event, score sheet and statistics."""
    SeasonReferee.objects.create(
        season=season, club=clubs[0], person=people[clubs[0].pk][-1]
    )

    # The tools that make these talk to YouTube, which the harness never does.
    key = LiveStreamKeyFactory.create(
        season=season,
        title="Camera position A",
        external_identifier="harness-stream-a",
        stream_key="harb-0001-demo",
    )
    tz = ZoneInfo(TIMEZONE)
    night = Match.objects.filter(
        stage__division__season=season, home_team__isnull=False, round__gt=PLAYED_ROUNDS
    ).earliest("date")
    LiveStreamEventFactory.create(
        season=season,
        title="Round six commentary desk",
        description="Commentary from the desk beside Field 1 at Anchor Park.",
        start=datetime.datetime.combine(night.date, datetime.time(17, 30), tz),
        stop=datetime.datetime.combine(night.date, datetime.time(21, 15), tz),
        external_identifier="harness-event-1",
        stream_key=key,
    )

    played = (
        Match.objects.filter(
            stage__division__season=season,
            stage__division__title="Men's Open",
            round=1,
            home_team_score__isnull=False,
        )
        .select_related("home_team", "away_team")
        .earliest("pk")
    )
    # The image is a Cloudinary public id; nothing is uploaded.
    MatchScoreSheet.objects.create(match=played, image="harness/score-sheet")
    for team, score in (
        (played.home_team, played.home_team_score),
        (played.away_team, played.away_team_score),
    ):
        for index, association in enumerate(team.people.order_by("number")):
            SimpleScoreMatchStatisticFactory.create(
                match=played,
                player=association.person,
                number=association.number,
                played=1,
                points=score - score // 2 if index == 0 else score // 2,
                mvp=1 if team == played.home_team and index == 0 else None,
            )


# =============================================================================
# 3. Content
# =============================================================================


def _seed_content(anchor) -> bool:
    # The slug the sitemap serves at the root of the site, as a plain string.
    root_slug = str(settings.TOUCHTECHNOLOGY_SITEMAP_ROOT or "home")
    if SitemapNode.objects.filter(parent__isnull=True, slug=root_slug).exists():
        return False

    def page(title, paragraphs, parent=None, slug=None, **node):
        page = Page.objects.create(description=paragraphs[0][:255])
        for sequence, paragraph in enumerate(paragraphs, start=1):
            PageContent.objects.create(
                page=page, label="copy", sequence=sequence, copy="<p>%s</p>" % paragraph
            )
        return SitemapNode.objects.create(
            title=title,
            slug=slug or slugify(title),
            parent=parent,
            object=page,
            **node,
        )

    home = page(
        "Home",
        [
            (
                "Welcome to the Harbour Touch League, a mixed-ability touch "
                "football competition played on Wednesday nights at Anchor Park "
                "and Lantern Reserve."
            ),
            (
                "Eight clubs enter men's, women's and mixed teams. Fixtures, "
                "results and ladders are updated after every round."
            ),
        ],
        slug=root_slug,
    )
    page(
        "About the association",
        [
            (
                "The association runs two seasons a year, autumn and spring, with "
                "seven rounds of regular play followed by finals."
            ),
            (
                "Every club is run by volunteers. If you would like to help, "
                "speak to your club secretary."
            ),
        ],
        parent=home,
    )
    page(
        "Contact",
        ["Write to the association at hello@example.org."],
        parent=home,
        hidden_from_navigation=True,
    )

    Chunk.objects.create(
        slug="footer-address",
        copy="<p>Harbour Touch League, PO Box 100, Anchor Bay.</p>",
    )
    Chunk.objects.create(
        slug="season-banner",
        copy="<p>Spring 2026 is under way. Come and watch on Wednesday night.</p>",
    )
    Redirect.objects.create(
        source_url="/fixtures/",
        destination_url=home.get_absolute_url(),
        label="Old fixtures address",
    )
    return True


# =============================================================================
# 4. News
# =============================================================================

#: Headline, category, days before the seed date, whether it has a picture.
ARTICLES = [
    ("Spring season opens with a full draw", "Club news", 40, True),
    ("Referee workshop returns in November", "Club news", 26, False),
    ("Round two ends in a draw at the top of the Men's Open", "Results", 19, True),
    ("Seacliff Sharks edge a thriller at Anchor Park", "Results", 12, False),
    ("Round five results and ladder movements", "Results", 5, True),
]


def _seed_news(anchor) -> bool:
    if Category.objects.filter(title="Club news").exists():
        return False

    categories = {
        title: Category.objects.create(title=title, slug=slugify(title))
        for title in ("Club news", "Results")
    }
    for headline, category, days, with_photo in ARTICLES:
        article = Article.objects.create(
            headline=headline,
            slug=slugify(headline),
            abstract="%s. Read the full report from the association." % headline,
            copy=(
                "<p>%s.</p><p>The association thanks every volunteer, referee "
                "and supporter who made Wednesday night possible.</p>" % headline
            ),
            published=datetime.datetime.combine(
                anchor - datetime.timedelta(days=days),
                datetime.time(9, 0),
                datetime.UTC,
            ),
            byline="Harbour Touch League media team",
            keywords="touch, harbour, %s" % category.lower(),
            image=photo(headline, size=(1200, 800)) if with_photo else None,
        )
        article.categories.add(categories[category])

    translated = Article.objects.get(slug=slugify(ARTICLES[0][0]))
    Translation.objects.create(
        article=translated,
        locale="es",
        headline="La temporada de primavera comienza con un calendario completo",
        abstract="Lea el informe completo de la asociacion.",
        copy="<p>La temporada de primavera comienza con un calendario completo.</p>",
    )
    return True


# =============================================================================
# 5. Enrolment
# =============================================================================


def _seed_enrolment(anchor) -> bool:
    # The command is idempotent itself, so it is always run; it only reports
    # that it seeded something when there was no school year before.
    already = SchoolYear.objects.exists()
    call_command("seed_enrolment", stdout=io.StringIO())
    return not already
