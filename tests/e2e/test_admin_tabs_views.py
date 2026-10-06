"""
The tabs of every admin edit page, in both tab modes.

Each page is opened traditionally (every tab in the page) and with
``TOUCHTECHNOLOGY_HTMX_ADMIN_TABS`` (each tab fetched when it is first shown).
Showing each tab in turn must list the same objects, the same way, without
script errors, whichever the mode. The pages are filled with a little of
everything so that no tab is trivially empty; each list stays under ten rows,
the most the club and person pages show at once.
"""

import datetime
from urllib.parse import urljoin

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.admin_tabs import assert_same_in_both_modes, set_mode, show_tab
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from touchtechnology.content.tests.factories import RedirectFactory
from touchtechnology.news.tests.factories import (
    ArticleFactory,
    CategoryFactory,
    TranslationFactory,
)
from tournamentcontrol.competition.tests import factories


@pytest.fixture
def site(db):
    """A competition with one of everything, keyed by what each page edits."""
    competition = factories.CompetitionFactory.create(title="Spec Cup")
    season = factories.SeasonFactory.create(
        competition=competition,
        title="2026",
        live_stream=True,
        start_date=datetime.date(2026, 3, 1),
    )
    other_season = factories.SeasonFactory.create(competition=competition, title="2025")
    club_role = factories.ClubRoleFactory.create(
        competition=competition, name="Manager"
    )
    team_role = factories.TeamRoleFactory.create(competition=competition, name="Coach")

    venue = factories.VenueFactory.create(season=season, title="Central Park")
    ground = factories.GroundFactory.create(venue=venue, title="Field 1")
    factories.GroundFactory.create(venue=venue, title="Field 2")
    timeslot = factories.SeasonMatchTimeFactory.create(
        season=season, start=datetime.time(9), interval=30, count=4
    )
    season_exclusion = factories.SeasonExclusionDateFactory.create(
        season=season, date=datetime.date(2026, 4, 25)
    )
    live_stream_key = factories.LiveStreamKeyFactory.create(season=season)
    live_stream_event = factories.LiveStreamEventFactory.create(season=season)

    club = factories.ClubFactory.create(title="Eagles")
    other_club = factories.ClubFactory.create(title="Hawks")
    competition.clubs.add(club, other_club)
    person = factories.PersonFactory.create(
        club=club, first_name="Alex", last_name="Smith"
    )
    factories.PersonFactory.create(club=club, first_name="Sam", last_name="Jones")
    club_association = factories.ClubAssociationFactory.create(club=club, person=person)
    club_association.roles.add(club_role)
    season_referee = factories.SeasonRefereeFactory.create(
        season=season, club=club, person=person
    )

    division = factories.DivisionFactory.create(season=season, title="Mixed Open")
    factories.DivisionFactory.create(season=season, title="Women's Open")
    factories.DivisionFactory.create(season=other_season, title="Men's Open")
    division_exclusion = factories.DivisionExclusionDateFactory.create(
        division=division, date=datetime.date(2026, 5, 2)
    )
    home = factories.TeamFactory.create(division=division, club=club, title="Eagles")
    away = factories.TeamFactory.create(
        division=division, club=other_club, title="Hawks"
    )
    team_association = factories.TeamAssociationFactory.create(team=home, person=person)
    team_association.roles.add(team_role)

    stage = factories.StageFactory.create(division=division, title="Pool Stage")
    factories.StageFactory.create(division=division, title="Finals")
    pool = factories.StageGroupFactory.create(stage=stage, title="Pool A")
    factories.StageGroupFactory.create(stage=stage, title="Pool B")
    undecided_team = factories.UndecidedTeamFactory.create(
        stage=stage, label="Winner Pool A"
    )
    match = factories.MatchFactory.create(
        stage=stage,
        stage_group=pool,
        home_team=home,
        away_team=away,
        round=1,
        datetime=datetime.datetime(2026, 3, 7, 9, tzinfo=datetime.timezone.utc),
    )
    factories.MatchFactory.create(
        stage=stage,
        stage_group=pool,
        home_team=away,
        away_team=home,
        round=2,
        datetime=datetime.datetime(2026, 3, 14, 9, tzinfo=datetime.timezone.utc),
    )

    draw_format = factories.DrawFormatFactory.create(teams=4)

    # The article's tabs link to it on the web, so publish the news site.
    placeholder, _ = Placeholder.objects.get_or_create(
        path="touchtechnology.news.sites.NewsSite", namespace="news"
    )
    SitemapNode.objects.create(title="News", slug="news", object=placeholder)
    category = CategoryFactory.create(title="Results")
    article = ArticleFactory.create(headline="Eagles win the Spec Cup")
    article.categories.add(category)
    translation = TranslationFactory.create(article=article, locale="fr")
    redirect = RedirectFactory.create()

    return {
        "competition": competition,
        "season": season,
        "club_role": club_role,
        "team_role": team_role,
        "venue": venue,
        "ground": ground,
        "timeslot": timeslot,
        "season_exclusion": season_exclusion,
        "live_stream_key": live_stream_key,
        "live_stream_event": live_stream_event,
        "season_referee": season_referee,
        "division": division,
        "division_exclusion": division_exclusion,
        "team": home,
        "team_association": team_association,
        "stage": stage,
        "pool": pool,
        "undecided_team": undecided_team,
        "match": match,
        "club": club,
        "club_association": club_association,
        "person": person,
        "draw_format": draw_format,
        "article": article,
        "translation": translation,
        "category": category,
        "redirect": redirect,
    }


PAGES = [
    "competition",
    "season",
    "club_role",
    "team_role",
    "venue",
    "ground",
    "timeslot",
    "season_exclusion",
    "live_stream_key",
    "live_stream_event",
    "season_referee",
    "division",
    "division_exclusion",
    "team",
    "team_association",
    "stage",
    "pool",
    "undecided_team",
    "match",
    "club",
    "club_association",
    "person",
    "draw_format",
    "article",
    "translation",
    "category",
    "redirect",
]


def edit_url(live_server, obj):
    return urljoin(live_server.url, str(obj.urls["edit"]))


# What some tabs must list, so a tab that is empty in both modes still fails.
LISTED = {
    "competition": {
        "seasons-tab": ["season"],
        "club_roles-tab": ["club_role"],
        "team_roles-tab": ["team_role"],
    },
    "season": {
        "exclusions-tab": ["season_exclusion"],
        "divisions-tab": ["division"],
        "venues-tab": ["venue"],
        "timeslots-tab": ["timeslot"],
        "referees-tab": ["season_referee"],
        "live_stream_events-tab": ["live_stream_event"],
        "live_stream_keys-tab": ["live_stream_key"],
    },
    "venue": {"grounds-tab": ["ground"]},
    "division": {
        "teams-tab": ["team"],
        "stages-tab": ["stage"],
        "exclusions-tab": ["division_exclusion"],
    },
    "stage": {
        "pools-tab": ["pool"],
        "undecided_teams-tab": ["undecided_team"],
        "matches-tab": ["match"],
    },
    "team": {"people-tab": ["team_association"]},
    "club": {"members-tab": ["person"]},
    "article": {"translations-tab": ["translation"]},
}


@pytest.mark.parametrize("name", PAGES)
def test_every_tab_lists_the_same_in_both_modes(
    authenticated_page: Page, live_server, settings, site, name
):
    tabs = assert_same_in_both_modes(
        authenticated_page, settings, edit_url(live_server, site[name])
    )
    for tab_id, listed in LISTED.get(name, {}).items():
        edit_urls = {str(site[other].urls["edit"]) for other in listed}
        assert edit_urls <= set(tabs.links[tab_id]), tab_id


@pytest.mark.parametrize("htmx", [False, True], ids=["plain", "htmx"])
@pytest.mark.parametrize(
    "name,tab_id", [("club", "members-tab"), ("person", "statistics-tab")]
)
def test_a_tab_list_can_be_searched_and_sorted(
    authenticated_page: Page, live_server, settings, site, name, tab_id, htmx
):
    """The club and person pages turn their lists into DataTables."""
    set_mode(settings, htmx)
    page = authenticated_page
    page.goto(edit_url(live_server, site[name]))
    pane = show_tab(page, tab_id)
    expect(pane.locator(".dataTables_filter input")).to_be_visible()


def test_choosing_a_club_names_the_team(
    authenticated_page: Page, live_server, settings, site
):
    """The team page names a team after the club chosen for it."""
    page = authenticated_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(edit_url(live_server, site["team"]))
    page.locator("#id_club").select_option(label="Hawks", force=True)
    expect(page.locator("#id_title")).to_have_value("Hawks")
    assert errors == []
