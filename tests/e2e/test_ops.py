"""End-to-end tests for the Tournament Ops site under an ASGI server."""

import datetime
from unittest import mock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from tournamentcontrol.competition.tests.factories import (
    GroundFactory,
    MatchFactory,
    SeasonFactory,
    StageFactory,
    VenueFactory,
)
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)


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
    stage = StageFactory.create(division__season=season)
    match = MatchFactory.create(
        stage=stage,
        play_at=field1,
        external_identifier="yt-1",
        live_stream_status="live",
        **live_kickoff,
    )
    scored = MatchFactory.create(
        stage=stage,
        play_at=field2,
        home_team_score=1,
        away_team_score=0,
        **scored_kickoff,
    )
    upcoming = MatchFactory.create(
        stage=stage,
        play_at=field1,
        external_identifier="yt-2",
        **next_kickoff,
    )
    return {
        "season": season,
        "ground": field1,
        "match": match,
        "scored": scored,
        "upcoming": upcoming,
        "slot_key": live_kickoff["time"].strftime("%H%M"),
        "day_path": f"/ops/pacific-cup/pc26/{today:%Y%m%d}/",
        "booth_path": "/ops/pacific-cup/pc26/booth/field-1/",
    }


def test_score_entered_on_one_page_appears_on_another(
    ops_page, second_page, asgi_live_server, tournament, screenshot_dir
):
    ops_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(
        ops_page.locator(f"#stream-{tournament['ground'].pk} .badge").first
    ).to_be_visible()
    ops_page.screenshot(
        path=str(screenshot_dir / "ops_dashboard_desktop.png"), full_page=True
    )
    second_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(second_page.locator(".sse")).not_to_have_class("down")
    row = ops_page.locator(f"#match-{tournament['match'].pk}")
    row.locator('input[name="home_team_score"]').fill("5")
    row.locator('input[name="away_team_score"]').fill("4")
    row.locator('button[type="submit"]').click()
    expect(ops_page.locator(f"#match-{tournament['match'].pk} .score")).to_have_text(
        "5 – 4"
    )
    expect(second_page.locator(f"#match-{tournament['match'].pk} .score")).to_have_text(
        "5 – 4"
    )
    # Only the upcoming match is still waiting for a result.
    expect(second_page.locator("#results-count")).to_have_text("1")
    expect(second_page.locator("#activity li").first).to_contain_text("Score ·")
    second_page.screenshot(
        path=str(screenshot_dir / "ops_dashboard_score_pushed.png"), full_page=True
    )


def test_ending_the_broadcast_from_ops_darkens_the_booth_lamp(
    ops_page, second_page, asgi_live_server, tournament, screenshot_dir
):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        second_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(second_page.locator("#lamp")).to_have_text("ON AIR")
        ops_page.goto(asgi_live_server.url + tournament["day_path"])
        ops_page.locator(
            f"#stream-{tournament['ground'].pk} button", has_text="End"
        ).click()
        # The first badge is the current match, the second is the next one.
        expect(
            ops_page.locator(f"#stream-{tournament['ground'].pk} .badge").first
        ).to_have_text("complete")
        ops_page.screenshot(
            path=str(screenshot_dir / "ops_streams_ended.png"), full_page=True
        )
        expect(second_page.locator("#lamp")).to_have_text("OFF AIR")


def test_hold_button_needs_a_hold(
    ops_page, asgi_live_server, tournament, screenshot_dir
):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        ops_page.set_viewport_size({"width": 1024, "height": 768})
        ops_page.goto(asgi_live_server.url + tournament["booth_path"])
        button = ops_page.locator("button[data-hold]")
        expect(ops_page.locator("#lamp")).to_have_text("ON AIR")
        ops_page.screenshot(
            path=str(screenshot_dir / "ops_booth_on_air.png"), full_page=True
        )
        button.click()
        ops_page.wait_for_timeout(500)
        expect(ops_page.locator("#lamp")).to_have_text("ON AIR")
        box = button.bounding_box()
        ops_page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        ops_page.mouse.down()
        ops_page.wait_for_timeout(1700)
        ops_page.mouse.up()
        expect(ops_page.locator("#lamp")).to_have_text("OFF AIR")
        ops_page.screenshot(
            path=str(screenshot_dir / "ops_booth_off_air.png"), full_page=True
        )


def test_booth_opens_its_event_stream_once(ops_page, asgi_live_server, tournament):
    events_url = tournament["booth_path"] + "events/"
    requests = []
    ops_page.on(
        "request",
        lambda request: requests.append(request.url)
        if urlsplit(request.url).path == events_url
        else None,
    )
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        ops_page.set_viewport_size({"width": 1024, "height": 768})
        ops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(ops_page.locator("#lamp")).to_have_text("ON AIR")
        ops_page.wait_for_timeout(2000)
    assert 1 <= len(requests) <= 2, requests


def test_scorers_modal_opens_and_closes(
    ops_page, asgi_live_server, tournament, screenshot_dir
):
    ops_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(ops_page.locator("#modal")).to_be_hidden()
    ops_page.locator(
        f"#scorers-{tournament['scored'].pk} a", has_text="Enter scorers"
    ).click()
    expect(ops_page.locator("#modal")).to_be_visible()
    expect(ops_page.locator("#modal-body h3")).to_contain_text("1 – 0")
    ops_page.screenshot(
        path=str(screenshot_dir / "ops_scorers_modal.png"), full_page=True
    )
    ops_page.locator("#modal-body button", has_text="Close").click()
    expect(ops_page.locator("#modal")).to_be_hidden()


def test_booth_teams_picker_opens_and_closes(
    ops_page, asgi_live_server, tournament, screenshot_dir
):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        ops_page.set_viewport_size({"width": 1024, "height": 768})
        ops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(ops_page.locator("#modal")).to_be_hidden()
        ops_page.locator("button.teamsbtn").click()
        expect(ops_page.locator("#modal")).to_be_visible()
        ops_page.screenshot(
            path=str(screenshot_dir / "ops_booth_teams_picker.png"), full_page=True
        )
        ops_page.locator("#modal-body button", has_text="Close").click()
        expect(ops_page.locator("#modal")).to_be_hidden()


def test_collapsed_layout_puts_scorers_behind_a_tab(
    ops_page, asgi_live_server, tournament, screenshot_dir
):
    ops_page.set_viewport_size({"width": 1024, "height": 768})
    ops_page.goto(asgi_live_server.url + tournament["day_path"])
    ops_page.locator('button[title="collapse"]').click()
    expect(ops_page.locator("#main")).to_have_class("collapsed")
    expect(ops_page.locator(".rtabs")).to_be_visible()
    slot = ops_page.locator(f"#slot-{tournament['slot_key']}")
    slot.locator(".slot-h").click()
    expect(slot.locator(".rows")).to_be_hidden()
    ops_page.screenshot(
        path=str(screenshot_dir / "ops_dashboard_ipad_folded_slot.png"), full_page=True
    )
    ops_page.locator(".rtabs a", has_text="Scorers").click()
    expect(ops_page.locator("#scorers")).to_be_visible()
    expect(ops_page.locator("#results")).to_be_hidden()
    ops_page.screenshot(
        path=str(screenshot_dir / "ops_dashboard_ipad_collapsed.png"), full_page=True
    )
    ops_page.reload()
    expect(ops_page.locator("#main")).to_have_class("collapsed")


def test_without_javascript_the_form_still_posts(
    browser, asgi_live_server, ops_user, tournament, screenshot_dir
):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{asgi_live_server.url}/accounts/login/")
    page.fill('input[name="username"]', "ops")
    page.fill('input[name="password"]', "password")
    page.click("button")
    page.wait_for_load_state("networkidle")
    page.goto(asgi_live_server.url + tournament["day_path"])
    row = page.locator(f"#match-{tournament['match'].pk}")
    row.locator('input[name="home_team_score"]').fill("2")
    row.locator('input[name="away_team_score"]').fill("2")
    row.locator('button[type="submit"]').click()
    expect(page).to_have_url(asgi_live_server.url + tournament["day_path"])
    expect(page.locator(f"#match-{tournament['match'].pk} .score")).to_have_text("2 – 2")
    page.screenshot(
        path=str(screenshot_dir / "ops_no_javascript.png"), full_page=True
    )
    context.close()
