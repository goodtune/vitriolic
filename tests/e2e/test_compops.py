"""End-to-end tests for the Tournament Ops site under an ASGI server."""

import datetime
import re
from unittest import mock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone
from faker import Faker
from playwright.sync_api import expect

from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.models import TeamAssociation
from tournamentcontrol.competition.tests.factories import (
    GroundFactory,
    MatchFactory,
    PersonFactory,
    SeasonFactory,
    StageFactory,
    TeamAssociationFactory,
    TeamFactory,
    VenueFactory,
)
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)


SQUAD = 16

# The screenshots go on the pull request, so the fixture reads like a real
# tournament: a nation for each club and team, and a squad of made-up names.
NATIONS = ("Australia", "New Zealand", "Fiji", "Samoa", "Japan", "Singapore")


def player_name(team, number):
    """The name of the player wearing ``number`` for ``team``, as the pages show it."""
    person = TeamAssociation.objects.get(team=team, number=number).person
    return f"{person.first_name} {person.last_name}"


def wait_for_snapshot(page, season):
    """
    Wait until the day page has been brought up to date by its event stream.

    The stream's first push re-renders the lists, wiping a score typed before
    it lands. Pages cannot tell when that is, so publish an event and wait for
    it to show in the activity feed: the push carrying it follows the snapshot.
    """
    expect(page.locator(".sse")).not_to_have_class("down")
    events.publish(
        season.pk,
        "stream-changed",
        actor="e2e",
        summary="Page connected",
        kind="match",
        id=0,
        status="live",
    )
    expect(page.locator("#activity li", has_text="Page connected")).to_have_count(1)


def midday_zone(now):
    """Return the name of a whole-hour zone in which `now` is at midday.

    The ops site decides which match is a ground's current and next one by
    comparing kick-offs with the clock, and groups the day by the local date.
    Fixed kick-off times would therefore pass or fail depending on when the
    suite runs, and a run near local midnight would straddle two days. Placing
    the season in the zone where it is now 12:00 keeps every kick-off within
    an hour or so of midday, on the same local date, whatever the time of day.

    The `Etc/GMT` zones have an inverted sign: `Etc/GMT-10` is UTC+10.
    """
    offset = 12 - now.astimezone(datetime.UTC).hour
    if offset > 0:
        return f"Etc/GMT-{offset}"
    if offset < 0:
        return f"Etc/GMT+{-offset}"
    return "Etc/GMT"


@pytest.fixture
def tournament(transactional_db):
    now = timezone.now().replace(second=0, microsecond=0)
    zone_name = midday_zone(now)
    zone = ZoneInfo(zone_name)

    def kickoff_at(delta):
        kickoff = now + delta
        local = kickoff.astimezone(zone)
        return {"datetime": kickoff, "date": local.date(), "time": local.time()}

    live_kickoff = kickoff_at(datetime.timedelta(minutes=-20))
    scored_kickoff = kickoff_at(datetime.timedelta(minutes=-60))
    next_kickoff = kickoff_at(datetime.timedelta(minutes=40))
    today = live_kickoff["date"]

    season = SeasonFactory.create(
        slug="pc26",
        slug_locked=True,
        competition__slug="pacific-cup",
        competition__slug_locked=True,
        timezone=zone_name,
        statistics=True,
        **YOUTUBE_SEASON,
    )
    venue = VenueFactory.create(season=season)
    field1 = GroundFactory.create(
        venue=venue,
        title="Field 1",
        slug="field-1",
        slug_locked=True,
        live_stream=True,
    )
    field2 = GroundFactory.create(
        venue=venue, title="Field 2", slug="field-2", slug_locked=True
    )
    stage = StageFactory.create(division__season=season, division__title="Men's Open")
    home, away, fiji, samoa, japan, singapore = (
        TeamFactory.create(title=nation, club__title=nation, division=stage.division)
        for nation in NATIONS
    )
    match = MatchFactory.create(
        stage=stage,
        home_team=home,
        away_team=away,
        play_at=field1,
        external_identifier="yt-1",
        live_stream_status="live",
        **live_kickoff,
    )
    scored = MatchFactory.create(
        stage=stage,
        home_team=fiji,
        away_team=samoa,
        play_at=field2,
        home_team_score=1,
        away_team_score=0,
        **scored_kickoff,
    )
    upcoming = MatchFactory.create(
        stage=stage,
        home_team=japan,
        away_team=singapore,
        play_at=field1,
        external_identifier="yt-2",
        **next_kickoff,
    )
    # A squad of 16 for every team, as a real tournament has. The names are
    # seeded so that every run, and every screenshot, shows the same people.
    fake = Faker()
    fake.seed_instance(2026)
    teams = []
    for fixture in (match, scored, upcoming):
        for team in (fixture.home_team, fixture.away_team):
            if team not in teams:
                teams.append(team)
    for team in teams:
        for number in range(1, SQUAD + 1):
            person = PersonFactory.create(
                first_name=fake.first_name_male(),
                last_name=fake.last_name(),
                club=team.club,
                gender="M",
                user=None,
            )
            TeamAssociationFactory.create(
                team=team, person=person, number=number, is_player=True
            )
    return {
        "season": season,
        "teams": teams,
        "ground": field1,
        "match": match,
        "scored": scored,
        "upcoming": upcoming,
        "slot_key": live_kickoff["time"].strftime("%H%M"),
        "day_path": reverse(
            "compops:day",
            kwargs={
                "competition": "pacific-cup",
                "season": "pc26",
                "datestr": today.strftime("%Y%m%d"),
            },
        ),
        "booth_path": reverse(
            "compops:booth",
            kwargs={
                "competition": "pacific-cup",
                "season": "pc26",
                "ground": "field-1",
            },
        ),
    }


def test_score_entered_on_one_page_appears_on_another(
    compops_page, second_page, asgi_live_server, tournament, screenshot_dir
):
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(
        compops_page.locator(f"#stream-{tournament['ground'].pk} .badge").first
    ).to_be_visible()
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_dashboard_desktop.png"), full_page=True
    )
    second_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(second_page.locator(".sse")).not_to_have_class("down")
    row = compops_page.locator(f"#match-{tournament['match'].pk}")
    row.locator('input[name="home_team_score"]').fill("5")
    row.locator('input[name="away_team_score"]').fill("4")
    row.locator('button[type="submit"]').click()
    expect(
        compops_page.locator(f"#match-{tournament['match'].pk} .score")
    ).to_have_text("5 – 4")
    expect(second_page.locator(f"#match-{tournament['match'].pk} .score")).to_have_text(
        "5 – 4"
    )
    # Only the upcoming match is still waiting for a result.
    expect(second_page.locator("#results-count")).to_have_text("1")
    expect(second_page.locator("#activity li").first).to_contain_text("Score ·")
    second_page.screenshot(
        path=str(screenshot_dir / "compops_dashboard_score_pushed.png"), full_page=True
    )


def test_ending_the_broadcast_from_ops_darkens_the_booth_lamp(
    compops_page, second_page, asgi_live_server, tournament, screenshot_dir
):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        second_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(second_page.locator("#lamp")).to_have_text("ON AIR")
        compops_page.goto(asgi_live_server.url + tournament["day_path"])
        compops_page.locator(
            f"#stream-{tournament['ground'].pk} button", has_text="End"
        ).click()
        # The first badge is the current match, the second is the next one.
        expect(
            compops_page.locator(f"#stream-{tournament['ground'].pk} .badge").first
        ).to_have_text("complete")
        compops_page.screenshot(
            path=str(screenshot_dir / "compops_streams_ended.png"), full_page=True
        )
        expect(second_page.locator("#lamp")).to_have_text("OFF AIR")


def test_hold_button_needs_a_hold(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        button = compops_page.locator("button[data-hold]")
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        compops_page.screenshot(
            path=str(screenshot_dir / "compops_booth_on_air.png"), full_page=True
        )
        button.click()
        compops_page.wait_for_timeout(500)
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        box = button.bounding_box()
        compops_page.mouse.move(
            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        )
        compops_page.mouse.down()
        compops_page.wait_for_timeout(1700)
        compops_page.mouse.up()
        expect(compops_page.locator("#lamp")).to_have_text("OFF AIR")
        compops_page.screenshot(
            path=str(screenshot_dir / "compops_booth_off_air.png"), full_page=True
        )


def test_hold_button_can_be_held_from_the_keyboard(
    compops_page, asgi_live_server, tournament
):
    """
    Holding Space on the focused hold button ends the broadcast.

    The booth is on air, so its hold button is "HOLD TO END BROADCAST". The
    button is focused without the pointer, Space is held past the 1.5s hold
    and released, and the lamp must go off air just as a pointer hold does.
    """
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        button = compops_page.locator("button[data-hold]")
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        button.focus()
        compops_page.keyboard.down("Space")
        expect(button).to_have_class(re.compile(r"\bpressing\b"))
        compops_page.wait_for_timeout(1700)
        compops_page.keyboard.up("Space")
        expect(compops_page.locator("#lamp")).to_have_text("OFF AIR")


def test_hold_button_ignores_a_tap_of_the_space_bar(
    compops_page, asgi_live_server, tournament
):
    """
    A short tap of Space on the focused hold button does nothing.

    The key is released well inside the hold time, which cancels the hold;
    waiting past the hold time afterwards proves no submit was left pending,
    and the native click a Space press makes on a button never submits.
    """
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        button = compops_page.locator("button[data-hold]")
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        button.focus()
        compops_page.keyboard.press("Space")
        compops_page.wait_for_timeout(2000)
        expect(button).to_have_class("bigbtn end")
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")


def test_booth_opens_its_event_stream_once(compops_page, asgi_live_server, tournament):
    events_url = reverse(
        "compops:booth-events",
        kwargs={"competition": "pacific-cup", "season": "pc26", "ground": "field-1"},
    )
    requests = []
    compops_page.on(
        "request",
        lambda request: (
            requests.append(request.url)
            if urlsplit(request.url).path == events_url
            else None
        ),
    )
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        compops_page.wait_for_timeout(2000)
    assert 1 <= len(requests) <= 2, requests


def test_scorers_modal_opens_and_closes(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(compops_page.locator("#modal")).to_be_hidden()
    compops_page.locator(
        f"#scorers-{tournament['scored'].pk} a", has_text="Enter scorers"
    ).click()
    expect(compops_page.locator("#modal")).to_be_visible()
    expect(compops_page.locator("#modal-body h3")).to_contain_text("1 – 0")
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_scorers_modal.png"), full_page=True
    )
    compops_page.locator("#modal-body button", has_text="Close").click()
    expect(compops_page.locator("#modal")).to_be_hidden()


def test_booth_teams_picker_opens_and_closes(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(compops_page.locator("#modal")).to_be_hidden()
        compops_page.locator("button.teamsbtn").click()
        expect(compops_page.locator("#modal")).to_be_visible()
        compops_page.screenshot(
            path=str(screenshot_dir / "compops_booth_teams_picker.png"), full_page=True
        )
        compops_page.locator("#modal-body button", has_text="Close").click()
        expect(compops_page.locator("#modal")).to_be_hidden()


def test_booth_team_sheets_list_both_squads(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    home = tournament["match"].home_team
    away = tournament["match"].away_team
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        tables = compops_page.locator("#pane table")
        expect(tables).to_have_count(2)
        # The header row, then one for each of the squad.
        for index in (0, 1):
            expect(tables.nth(index).locator("tr")).to_have_count(SQUAD + 1)
        expect(tables.nth(0)).to_contain_text(player_name(home, 1))
        expect(tables.nth(0)).to_contain_text(player_name(home, SQUAD))
        expect(tables.nth(1)).to_contain_text(player_name(away, SQUAD))
        compops_page.screenshot(
            path=str(screenshot_dir / "compops_booth_team_sheets.png"), full_page=True
        )


def test_booth_team_modal_shows_the_squad(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    home = tournament["match"].home_team
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        compops_page.locator("button.teamsbtn").click()
        expect(compops_page.locator("#modal")).to_be_visible()
        compops_page.locator("#modal-body .tile").filter(
            has=compops_page.get_by_text(home.title, exact=True)
        ).click()
        expect(compops_page.locator("#modal-body h3")).to_have_text(home.title)
        squad = compops_page.locator("#modal-body table").first
        expect(squad.locator("tr")).to_have_count(SQUAD + 1)
        expect(squad).to_contain_text(player_name(home, 1))
        expect(squad).to_contain_text(player_name(home, SQUAD))
        compops_page.screenshot(
            path=str(screenshot_dir / "compops_booth_team_modal.png"), full_page=True
        )


def test_scorers_are_validated_then_saved(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    scored = tournament["scored"]
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    wait_for_snapshot(compops_page, tournament["season"])
    compops_page.locator(f"#scorers-{scored.pk} a", has_text="Enter scorers").click()
    modal = compops_page.locator("#modal-body")
    expect(modal.locator("tr")).to_have_count(2 * (SQUAD + 1))
    # A team may field 14, so stand two of each squad down.
    for side in ("home", "away"):
        for index in (SQUAD - 2, SQUAD - 1):
            modal.locator(f'select[name="{side}-{index}-played"]').select_option("0")
    # The score is 1 – 0 and the first home player is given 2.
    modal.locator('input[name="home-0-points"]').fill("2")
    modal.locator("button", has_text="Save scorers").click()
    error = modal.locator(".errorlist li")
    expect(error).to_have_text(
        "Total number of points (2) does not equal total number of scores (1) "
        "for this team."
    )
    expect(compops_page.locator("#modal")).to_be_visible()
    expect(modal.locator(".tot").first).to_have_class(re.compile(r"\bbad\b"))
    compops_page.screenshot(path=str(screenshot_dir / "compops_scorers_error.png"))
    modal.locator('input[name="home-0-points"]').fill("1")
    modal.locator("button", has_text="Save scorers").click()
    expect(compops_page.locator("#modal")).to_be_hidden()
    expect(compops_page.locator(f"#scorers-{scored.pk}")).to_have_count(0)
    expect(compops_page.locator("#activity li").first).to_contain_text("Scorers")
    compops_page.screenshot(path=str(screenshot_dir / "compops_scorers_saved.png"))


def test_a_single_score_is_refused_in_its_row(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    row = compops_page.locator(f"#match-{tournament['match'].pk}")
    row.locator('input[name="home_team_score"]').fill("3")
    row.locator('button[type="submit"]').click()
    expect(row.locator(".errorlist li")).to_have_text("Both scores are required.")
    expect(row.locator('input[name="home_team_score"]')).to_have_value("3")
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_result_validation.png"), full_page=True
    )


def test_collapsed_layout_puts_scorers_behind_a_tab(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    compops_page.set_viewport_size({"width": 1024, "height": 768})
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    compops_page.locator('button[title="collapse"]').click()
    expect(compops_page.locator("#main")).to_have_class("collapsed")
    expect(compops_page.locator(".rtabs")).to_be_visible()
    slot = compops_page.locator(f"#slot-{tournament['slot_key']}")
    slot.locator(".slot-h").click()
    expect(slot.locator(".rows")).to_be_hidden()
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_dashboard_ipad_folded_slot.png"),
        full_page=True,
    )
    compops_page.locator(".rtabs button", has_text="Scorers").click()
    expect(compops_page.locator("#scorers")).to_be_visible()
    expect(compops_page.locator("#results")).to_be_hidden()
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_dashboard_ipad_collapsed.png"),
        full_page=True,
    )
    compops_page.reload()
    expect(compops_page.locator("#main")).to_have_class("collapsed")


def test_without_javascript_the_form_still_posts(
    browser, asgi_live_server, compops_user, tournament, screenshot_dir
):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{asgi_live_server.url}/accounts/login/")
    page.fill('input[name="username"]', "compops")
    page.fill('input[name="password"]', "password")
    page.click("button")
    page.wait_for_load_state("networkidle")
    page.goto(asgi_live_server.url + tournament["day_path"])
    row = page.locator(f"#match-{tournament['match'].pk}")
    # One score only: the whole page comes back, with the error in the row.
    row.locator('input[name="home_team_score"]').fill("2")
    with page.expect_response(lambda r: r.request.method == "POST") as posted:
        row.locator('button[type="submit"]').click()
    assert posted.value.status == 200
    assert posted.value.url != asgi_live_server.url + tournament["day_path"]
    row = page.locator(f"#match-{tournament['match'].pk}")
    expect(row.locator(".errorlist li")).to_have_text("Both scores are required.")
    expect(row.locator('input[name="home_team_score"]')).to_have_value("2")
    expect(page.locator(".topbar .brand")).to_have_text("TOURNAMENT OPS")
    page.screenshot(
        path=str(screenshot_dir / "compops_no_javascript_validation.png"),
        full_page=True,
    )
    row.locator('input[name="away_team_score"]').fill("2")
    row.locator('button[type="submit"]').click()
    expect(page).to_have_url(asgi_live_server.url + tournament["day_path"])
    expect(page.locator(f"#match-{tournament['match'].pk} .score")).to_have_text(
        "2 – 2"
    )
    page.screenshot(
        path=str(screenshot_dir / "compops_no_javascript.png"), full_page=True
    )
    # Scorers: a refused save comes back as a page, and Cancel leaves it.
    scored = tournament["scored"]
    page.locator(f"#scorers-{scored.pk} a", has_text="Enter scorers").click()
    page.locator('input[name="home-0-points"]').fill("2")
    with page.expect_response(lambda r: r.request.method == "POST") as posted:
        page.locator("button", has_text="Save scorers").click()
    assert posted.value.status == 200
    # Both squads are checked on the page; the home side is the first.
    expect(page.locator(".errorlist li").first).to_have_text(
        "Total number of points (2) does not equal total number of scores (1) "
        "for this team."
    )
    page.screenshot(
        path=str(screenshot_dir / "compops_no_javascript_scorers.png"), full_page=True
    )
    page.locator("a", has_text="Cancel").click()
    expect(page).to_have_url(asgi_live_server.url + tournament["day_path"])
    context.close()
