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

TZ = ZoneInfo("Australia/Brisbane")


@pytest.fixture
def tournament(transactional_db):
    today = timezone.localtime(timezone.now(), TZ).date()
    season = SeasonFactory.create(
        slug="pc26",
        slug_locked=True,
        competition__slug="pacific-cup",
        competition__slug_locked=True,
        timezone="Australia/Brisbane",
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
    stage = StageFactory.create(division__season=season)
    kickoff = timezone.make_aware(datetime.datetime.combine(today, datetime.time(8)), TZ)
    match = MatchFactory.create(
        stage=stage,
        datetime=kickoff,
        date=today,
        time=kickoff.time(),
        play_at=field1,
        external_identifier="yt-1",
        live_stream_status="live",
    )
    field2 = GroundFactory.create(
        venue=venue, title="Field 2", slug="field-2", slug_locked=True
    )
    scored_kickoff = timezone.make_aware(
        datetime.datetime.combine(today, datetime.time(9)), TZ
    )
    scored = MatchFactory.create(
        stage=stage,
        datetime=scored_kickoff,
        date=today,
        time=scored_kickoff.time(),
        play_at=field2,
        home_team_score=1,
        away_team_score=0,
    )
    return {
        "season": season,
        "ground": field1,
        "match": match,
        "scored": scored,
        "day_path": f"/ops/pacific-cup/pc26/{today:%Y%m%d}/",
        "booth_path": "/ops/pacific-cup/pc26/booth/field-1/",
    }


def test_score_entered_on_one_page_appears_on_another(
    ops_page, second_page, asgi_live_server, tournament
):
    ops_page.goto(asgi_live_server.url + tournament["day_path"])
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
    expect(second_page.locator("#results-count")).to_have_text("0")
    expect(second_page.locator("#activity li").first).to_contain_text("Score ·")


def test_ending_the_broadcast_from_ops_darkens_the_booth_lamp(
    ops_page, second_page, asgi_live_server, tournament
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
        expect(
            ops_page.locator(f"#stream-{tournament['ground'].pk} .badge")
        ).to_have_text("complete")
        expect(second_page.locator("#lamp")).to_have_text("OFF AIR")


def test_hold_button_needs_a_hold(ops_page, asgi_live_server, tournament):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        ops_page.goto(asgi_live_server.url + tournament["booth_path"])
        button = ops_page.locator("button[data-hold]")
        button.click()
        ops_page.wait_for_timeout(500)
        expect(ops_page.locator("#lamp")).to_have_text("ON AIR")
        box = button.bounding_box()
        ops_page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        ops_page.mouse.down()
        ops_page.wait_for_timeout(1700)
        ops_page.mouse.up()
        expect(ops_page.locator("#lamp")).to_have_text("OFF AIR")


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
        ops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(ops_page.locator("#lamp")).to_have_text("ON AIR")
        ops_page.wait_for_timeout(2000)
    assert 1 <= len(requests) <= 2, requests


def test_scorers_modal_opens_and_closes(ops_page, asgi_live_server, tournament):
    ops_page.goto(asgi_live_server.url + tournament["day_path"])
    expect(ops_page.locator("#modal")).to_be_hidden()
    ops_page.locator(
        f"#scorers-{tournament['scored'].pk} a", has_text="Enter scorers"
    ).click()
    expect(ops_page.locator("#modal")).to_be_visible()
    expect(ops_page.locator("#modal-body h3")).to_contain_text("1 – 0")
    ops_page.locator("#modal-body button", has_text="Close").click()
    expect(ops_page.locator("#modal")).to_be_hidden()


def test_booth_teams_picker_opens_and_closes(ops_page, asgi_live_server, tournament):
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        ops_page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(ops_page.locator("#modal")).to_be_hidden()
        ops_page.locator("button.teamsbtn").click()
        expect(ops_page.locator("#modal")).to_be_visible()
        ops_page.locator("#modal-body button", has_text="Close").click()
        expect(ops_page.locator("#modal")).to_be_hidden()


def test_collapsed_layout_puts_scorers_behind_a_tab(
    ops_page, asgi_live_server, tournament
):
    ops_page.set_viewport_size({"width": 1024, "height": 768})
    ops_page.goto(asgi_live_server.url + tournament["day_path"])
    ops_page.locator('button[title="collapse"]').click()
    expect(ops_page.locator("#main")).to_have_class("collapsed")
    expect(ops_page.locator(".rtabs")).to_be_visible()
    ops_page.locator("#slot-0800 .slot-h").click()
    expect(ops_page.locator("#slot-0800 .rows")).to_be_hidden()
    ops_page.locator(".rtabs a", has_text="Scorers").click()
    expect(ops_page.locator("#scorers")).to_be_visible()
    expect(ops_page.locator("#results")).to_be_hidden()
    ops_page.reload()
    expect(ops_page.locator("#main")).to_have_class("collapsed")


def test_without_javascript_the_form_still_posts(
    browser, asgi_live_server, ops_user, tournament
):
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{asgi_live_server.url}/accounts/login/")
    page.fill('input[name="username"]', "ops")
    page.fill('input[name="password"]', "password")
    page.click("button")
    page.goto(asgi_live_server.url + tournament["day_path"])
    row = page.locator(f"#match-{tournament['match'].pk}")
    row.locator('input[name="home_team_score"]').fill("2")
    row.locator('input[name="away_team_score"]').fill("2")
    row.locator('button[type="submit"]').click()
    expect(page).to_have_url(asgi_live_server.url + tournament["day_path"])
    expect(page.locator(f"#match-{tournament['match'].pk} .score")).to_have_text("2 – 2")
    context.close()
