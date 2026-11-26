"""End-to-end tests for the Tournament Ops site under an ASGI server."""

import datetime
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from faker import Faker
from googleapiclient.errors import HttpError
from guardian.shortcuts import assign_perm
from playwright.sync_api import expect

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Placeholder
from tournamentcontrol.competition.compops import events, streams
from tournamentcontrol.competition.compops.scoreboard import Clock
from tournamentcontrol.competition.compops.sites import CompOpsSite
from tournamentcontrol.competition.models import Division, Match, TeamAssociation
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

    The stream's first push, the snapshot, re-renders the lists. It keeps a
    score being typed and leaves alone the rows a person is working in, so it
    discards nothing; a test waits for it to act on a page that is up to date,
    or to see what the snapshot did. Pages cannot tell when that is, so
    publish an event and wait for it to show in the activity feed: the push
    carrying it follows the snapshot.
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


@contextmanager
def snapshot_held(snapshot="snapshot_fragments"):
    """
    Hold a page's snapshot back until the block ends, so it lands on whatever
    the block did, as the snapshot of a reconnect does. ``snapshot`` names
    the method of ``CompOpsSite`` that renders it: the day page's by default,
    ``"booth_snapshot"`` for a booth.
    """
    release = threading.Event()
    render = getattr(CompOpsSite, snapshot)

    def late_snapshot(site, *args):
        release.wait(10)
        return render(site, *args)

    with mock.patch.object(CompOpsSite, snapshot, late_snapshot):
        try:
            yield
        finally:
            release.set()


def refusing_youtube(reason):
    """A YouTube service that refuses every transition with ``reason``."""
    service = youtube_mock("testing")
    service.liveBroadcasts.return_value.transition.return_value.execute.side_effect = (
        HttpError(resp=mock.Mock(status=400, reason=reason), content=b"")
    )
    return service


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
        title="Pacific Cup 2026",
        slug="pc26",
        slug_locked=True,
        competition__title="Pacific Cup",
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
        live_stream=True,
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
        live_stream=True,
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


def test_home_leads_down_to_any_day_of_any_season(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    page = compops_page
    season = tournament["season"]
    stage = tournament["match"].stage
    today = tournament["match"].date
    yesterday = today - datetime.timedelta(days=1)
    MatchFactory.create(
        stage=stage, date=yesterday, home_team_score=3, away_team_score=2
    )
    MatchFactory.create(stage=stage, date=yesterday)
    MatchFactory.create(stage=stage, date=today + datetime.timedelta(days=1))
    for title, competition, offset in (
        ("World Cup 2027", "World Cup", 30),
        ("European Championships 2026", "European Championships", -5),
        ("Asia Pacific Championships 2025", "Asia Pacific Championships", -400),
    ):
        MatchFactory.create(
            stage__division__season=SeasonFactory.create(
                title=title, competition__title=competition, timezone=season.timezone
            ),
            date=today + datetime.timedelta(days=offset),
        )
    SeasonFactory.create(
        title="World Cup 2031",
        competition__title="World Cup (draft)",
        timezone=season.timezone,
        enabled=False,
    )

    page.goto(asgi_live_server.url + reverse("compops:index"))
    now = page.locator("section.now li")
    expect(now.locator(".title")).to_have_text(season.title)
    expect(now.locator("a.btn")).to_have_text("Open today")
    expect(page.locator("section.all li")).to_have_count(5)
    # How long ago a season ended is only said while it is news.
    expect(page.locator("section.recent .note")).to_have_text(["ended 5 days ago"])
    page.screenshot(
        path=str(screenshot_dir / "compops_home_desktop.png"), full_page=True
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(screenshot_dir / "compops_home_phone.png"))
    page.set_viewport_size({"width": 1280, "height": 720})

    # A season that ended is two steps from any of its days.
    now.locator("a.item").click()
    expect(page.locator("main h1")).to_have_text(season.title)
    days = page.locator("ul.list li")
    expect(days).to_have_count(3)
    expect(days.nth(0).locator(".state")).to_have_text("1 result missing")
    expect(days.nth(1).locator(".tag")).to_have_text("Today")
    page.screenshot(
        path=str(screenshot_dir / "compops_season_desktop.png"), full_page=True
    )
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(screenshot_dir / "compops_season_phone.png"))
    page.set_viewport_size({"width": 1280, "height": 720})

    days.nth(0).locator("a.item").click()
    expect(page.locator(".topbar .day")).to_have_text(
        f"{yesterday:%A} {yesterday.day} {yesterday:%B}"
    )
    page.screenshot(
        path=str(screenshot_dir / "compops_day_navigation.png"), full_page=True
    )
    page.locator('.topbar a[rel="next"]').click()
    expect(page).to_have_url(asgi_live_server.url + tournament["day_path"])
    page.locator(".topbar a.brand").click()
    expect(page).to_have_url(asgi_live_server.url + reverse("compops:index"))


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


def test_comms_team_watches_the_booth_without_its_controls(
    compops_page,
    browser,
    login,
    asgi_live_server,
    tournament,
    django_user_model,
    screenshot_dir,
):
    # No staff flag and no permission of their own: only the group's right
    # to watch this season's booths.
    comms = Group.objects.create(name="Comms team")
    assign_perm("competition.commentate_season", comms, tournament["season"])
    django_user_model.objects.create_user(
        username="comms", password="password"
    ).groups.add(comms)
    context = browser.new_context(viewport={"width": 1024, "height": 768})
    page = context.new_page()
    try:
        login(page, asgi_live_server.url, "comms")
        page.goto(asgi_live_server.url + tournament["booth_path"])
        expect(page.locator("#lamp")).to_have_text("ON AIR")
        expect(page.locator("#onair button")).to_have_count(0)
        expect(page.locator("#pane.sheets")).to_be_visible()
        page.screenshot(
            path=str(screenshot_dir / "compops_booth_watch_only.png"), full_page=True
        )
        page.locator("nav.tabs button", has_text="Ladder").click()
        expect(page.locator("#pane.ladder")).to_be_visible()

        # The lamp follows the broadcast as the ops desk runs it.
        with mock.patch(
            "tournamentcontrol.competition.models.build",
            return_value=youtube_mock("live"),
        ):
            compops_page.goto(asgi_live_server.url + tournament["day_path"])
            compops_page.locator(
                f"#stream-{tournament['ground'].pk} button", has_text="End"
            ).click()
            expect(page.locator("#lamp")).to_have_text("OFF AIR")
        expect(page.locator("#onair button")).to_have_count(0)

        # The rest of the site stays closed to them.
        assert page.goto(asgi_live_server.url + tournament["day_path"]).status == 403

        # The front door lists their seasons, and leads back to the booth.
        page.goto(asgi_live_server.url + reverse("compops:index"))
        expect(page.locator("main h1")).to_have_text("Commentary booths")
        expect(page.locator("ul.list li")).to_have_count(1)
        page.screenshot(
            path=str(screenshot_dir / "compops_front_door.png"), full_page=True
        )
        page.locator("a.item", has_text=tournament["season"].title).click()
        page.locator("a", has_text="Field 1").click()
        expect(page).to_have_url(asgi_live_server.url + tournament["booth_path"])
    finally:
        context.close()


def test_booth_clock_keeps_time_and_its_days_can_be_stepped_through(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    page = compops_page
    today = tournament["match"].date
    saturday = today + datetime.timedelta(days=2)
    MatchFactory.create(
        stage=tournament["match"].stage,
        home_team=tournament["teams"][2],
        away_team=tournament["teams"][3],
        play_at=tournament["ground"],
        live_stream=True,
        date=saturday,
        time=datetime.time(19, 0),
        datetime=tournament["match"].datetime + datetime.timedelta(days=2),
    )
    page.set_viewport_size({"width": 1024, "height": 768})
    page.goto(asgi_live_server.url + tournament["booth_path"])
    clock = page.locator("header .clock")
    # The browser keeps the clock: whatever it shows is put right in a second.
    clock.evaluate("el => { el.textContent = 'stopped' }")
    expect(clock).to_have_text(re.compile(r"^\d\d:\d\d$"), timeout=3000)

    # Another day of the ground: its matches, and nothing to press.
    page.locator('header a[rel="next"]').click()
    expect(page.locator("header .day")).to_have_text(
        f"{saturday:%A} {saturday.day} {saturday:%B}"
    )
    expect(page.locator("#onair button")).to_have_count(0)
    expect(page.locator("#strip .card").nth(2)).to_contain_text("19:00")
    expect(page.locator("#pane.sheets")).to_be_visible()
    # The page's requests, its event stream among them, stay on that day.
    page.locator("nav.tabs button", has_text="runsheet").click()
    expect(page.locator("#pane h4")).to_contain_text(f"{saturday:%a} {saturday.day}")
    expect(page.locator(".sse")).not_to_have_class("down")
    expect(page.locator("header .day")).to_have_text(
        f"{saturday:%A} {saturday.day} {saturday:%B}"
    )
    page.screenshot(
        path=str(screenshot_dir / "compops_booth_another_day.png"), full_page=True
    )
    page.locator("header a.today").click()
    expect(page.locator("#lamp")).to_have_text("ON AIR")


def test_booth_is_opened_on_the_next_match_and_put_on_air_from_there(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    page = compops_page
    upcoming = tournament["upcoming"]
    match_path = reverse(
        "compops:booth-match",
        kwargs={
            "competition": "pacific-cup",
            "season": "pc26",
            "ground": "field-1",
            "match_pk": upcoming.pk,
        },
    )
    page.set_viewport_size({"width": 1024, "height": 768})
    page.goto(asgi_live_server.url + tournament["booth_path"])
    expect(page.locator("#lamp")).to_have_text("ON AIR")

    # The next match's card opens the booth on that match.
    page.locator("#strip .card").nth(2).locator("a.teams").click()
    expect(page).to_have_url(asgi_live_server.url + match_path)
    expect(page.locator("#lamp")).to_have_text("OFF AIR")
    expect(page.locator("#onair .status b")).to_have_text("Next · Japan v Singapore")
    expect(page.locator("#strip .card.now .lab")).to_contain_text("This match")
    # Another match is on air, so this one cannot be put on air yet.
    expect(page.locator("#onair button[data-hold]")).to_have_count(0)
    on_air = page.locator("#onair .nocontrol a")
    expect(on_air).to_have_text("Australia v New Zealand is on air")
    page.screenshot(
        path=str(screenshot_dir / "compops_booth_match_blocked.png"), full_page=True
    )

    # End that broadcast from its own view; this match can then go on air.
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        on_air.click()
        expect(page.locator("#lamp")).to_have_text("ON AIR")
        hold(page, page.locator("button[data-hold]"))
        expect(page.locator("#lamp")).to_have_text("OFF AIR")
        page.goto(asgi_live_server.url + match_path)
        button = page.locator("#onair button[data-hold]")
        expect(button).to_have_text("HOLD TO GO ON AIR")
        page.screenshot(
            path=str(screenshot_dir / "compops_booth_match_ready.png"), full_page=True
        )
        hold(page, button)
        expect(page.locator("#lamp")).to_have_text("ON AIR")
        expect(page.locator("#onair .status b")).to_have_text(
            "Broadcasting · Japan v Singapore"
        )
    assert Match.objects.get(pk=upcoming.pk).live_stream_status == "live"

    page.locator("header a.today").click()
    expect(page).to_have_url(asgi_live_server.url + tournament["booth_path"])


def test_scoreboard_follows_the_scorer_and_counts_its_own_clock(
    page,
    browser,
    login,
    asgi_live_server,
    tournament,
    django_user_model,
    screenshot_dir,
):
    season = tournament["season"]
    match = tournament["match"]
    division = match.stage.division
    # Two periods of 25 minutes with a break of 5: the match on the ground
    # kicked off 20 minutes ago, so its first period has 5 minutes left.
    Division.objects.filter(pk=division.pk).update(period_minutes=25, break_minutes=5)
    names = {"competition": "pacific-cup", "season": "pc26", "ground": "field-1"}
    base = asgi_live_server.url

    # Anyone may see the board: this page is not signed in.
    page.goto(base + reverse("compops:scoreboard", kwargs=names))
    expect(page.locator("#sb-home-name")).to_have_text("Australia")
    expect(page.locator("#sb-away-name")).to_have_text("New Zealand")
    expect(page.locator("#sb-home-score")).to_have_text("0")
    expect(page.locator("#sb-label")).to_have_text("1st Half")
    expect(page.locator("#sb-dots li.on")).to_have_count(1)

    # The clock counts by itself, with nothing pushed to it.
    time = page.locator("#sb-time")
    expect(time).to_have_text(re.compile(r"^0[0-5]:\d\d$"))
    before = time.text_content()
    page.wait_for_timeout(1500)
    assert time.text_content() != before

    # The page's sum is the server's: the same moments at the same times.
    clock = Clock(start=match.datetime, periods=2, period=1500, pause=300)
    for seconds in (
        -90,
        0,
        0.4,
        1439.9,
        1440.06,
        1490.75,
        1499.5,
        1500,
        1799,
        1800,
        3299.2,
        3300,
        9000,
    ):
        now = match.datetime + datetime.timedelta(seconds=seconds)
        counted = page.evaluate(
            """([data, now]) => window.compopsScoreboard.momentAt(data, now)""",
            [
                {
                    "start": str(clock.start_ms),
                    "periods": "2",
                    "period": "1500",
                    "pause": "300",
                },
                now.timestamp() * 1000,
            ],
        )
        expected = clock.at(now)
        assert (counted["kind"], counted["index"], counted["remaining"]) == (
            expected.kind,
            expected.index,
            expected.remaining,
        ), seconds
        # And shown the same: a period's last minute to a tenth of a second.
        shown = page.evaluate("m => window.compopsScoreboard.display(m)", counted)
        assert shown == expected.display, seconds
        # And called the same: halves, with half time between them.
        called = page.evaluate(
            "([data, m]) => window.compopsScoreboard.labelOf(data, m)",
            [{"names": clock.names_json}, counted],
        )
        assert called == expected.label, seconds

    # A half time longer than the other breaks is counted from the list of
    # phases the server sends, and called half time.
    quarters = Clock(start=match.datetime, periods=4, period=600, pause=120, half=600)
    for seconds in (599.5, 600, 719, 1320, 1919.2, 1920, 2640, 3239.9, 3240):
        now = match.datetime + datetime.timedelta(seconds=seconds)
        data = {
            "start": str(quarters.start_ms),
            "periods": "4",
            "period": "600",
            "pause": "120",
            "phases": quarters.phases_json,
            "names": quarters.names_json,
        }
        counted = page.evaluate(
            """([data, now]) => {
                const m = window.compopsScoreboard.momentAt(data, now);
                return [m.kind, m.index, m.remaining,
                        window.compopsScoreboard.labelOf(data, m)];
            }""",
            [data, now.timestamp() * 1000],
        )
        expected = quarters.at(now)
        assert counted == [
            expected.kind,
            expected.index,
            expected.remaining,
            expected.label,
        ], seconds

    # The horn needs one tap before a browser will play it.
    page.locator("#sb-sound").click()
    expect(page.locator("#sb-sound")).to_be_hidden()

    # A scorer, who is not staff, keeps the score from a phone.
    scorer = django_user_model.objects.create_user(
        username="scorer", password="password"
    )
    assign_perm("competition.score_season", scorer, season)
    phone = browser.new_context(viewport={"width": 390, "height": 844})
    scoring = phone.new_page()
    try:
        login(scoring, base, "scorer")
        scoring.goto(base + reverse("compops:scorer", kwargs=names))
        add_home = scoring.get_by_role("button", name="Add one to Australia")
        add_home.click()
        expect(scoring.locator("#sc-home-score")).to_have_text("1")
        add_home.click()
        scoring.get_by_role("button", name="Add one to New Zealand").click()
        expect(scoring.locator("#sc-home-score")).to_have_text("2")
        expect(scoring.locator("#sc-away-score")).to_have_text("1")
        scoring.screenshot(path=str(screenshot_dir / "compops_scoreboard_scorer.png"))

        # Each tap reaches the board as it is made.
        expect(page.locator("#sb-home-score")).to_have_text("2")
        expect(page.locator("#sb-away-score")).to_have_text("1")
        page.screenshot(path=str(screenshot_dir / "compops_scoreboard_display.png"))

        scoring.get_by_role("button", name="Take one off Australia").click()
        expect(page.locator("#sb-home-score")).to_have_text("1")
    finally:
        phone.close()
    refreshed = Match.objects.get(pk=match.pk)
    assert (
        refreshed.home_team_progress_score,
        refreshed.away_team_progress_score,
        refreshed.home_team_score,
    ) == (1, 1, None)

    # The same board, to lay over the stream.
    page.goto(base + reverse("compops:scoreboard-overlay", kwargs=names))
    expect(page.locator("#sb-home-score")).to_have_text("1")
    expect(page.locator("#sb-sound")).to_have_count(0)
    page.screenshot(path=str(screenshot_dir / "compops_scoreboard_overlay.png"))

    # Between periods the clock counts down to the next, in another colour.
    Division.objects.filter(pk=division.pk).update(period_minutes=18)
    page.goto(base + reverse("compops:scoreboard", kwargs=names))
    expect(page.locator("#sb-label")).to_have_text("Half time")
    expect(page.locator("#sb-clock")).to_have_class(re.compile(r"\bbreak\b"))
    period_colour = "rgb(244, 246, 248)"
    expect(page.locator("#sb-time")).not_to_have_css("color", period_colour)
    page.screenshot(path=str(screenshot_dir / "compops_scoreboard_break.png"))


def test_scoreboard_drawn_by_a_template_written_in_the_admin(
    page,
    browser,
    login,
    asgi_live_server,
    tournament,
    django_user_model,
    screenshot_dir,
):
    season = tournament["season"]
    match = tournament["match"]
    division = match.stage.division
    Division.objects.filter(pk=division.pk).update(period_minutes=25, break_minutes=5)
    names = {"competition": "pacific-cup", "season": "pc26", "ground": "field-1"}
    base = asgi_live_server.url
    example = Path(__file__).parents[2] / "docs" / "examples" / "scoreboard-split.html"

    # The page opens drawn by the usual template.
    page.goto(base + reverse("compops:scoreboard", kwargs=names))
    expect(page.locator("#board")).to_have_attribute("data-template", "default")
    expect(page.locator(".badge")).to_have_count(0)

    scorer = django_user_model.objects.create_user(
        username="scorer", password="password"
    )
    assign_perm("competition.score_season", scorer, season)
    phone = browser.new_context(viewport={"width": 390, "height": 844})
    scoring = phone.new_page()
    try:
        login(scoring, base, "scorer")
        scoring.goto(base + reverse("compops:scorer", kwargs=names))
        add_home = scoring.get_by_role("button", name="Add one to Australia")

        # The division is given a template of its own. The next update brings
        # a board drawn by it, and the page loads itself again to match.
        Division.objects.filter(pk=division.pk).update(
            scoreboard_template=example.read_text()
        )
        add_home.click()
        expect(page.locator(".badge")).to_be_visible()
        expect(page.locator("#board")).to_have_attribute(
            "data-template", re.compile(rf"^division:{division.pk}:")
        )
        expect(page.locator("#sb-home-score")).to_have_text("1")

        # It is still a live board: the clock counts and a tap arrives.
        time = page.locator("#sb-time")
        before = time.text_content()
        page.wait_for_timeout(1500)
        assert time.text_content() != before
        add_home.click()
        expect(page.locator("#sb-home-score")).to_have_text("2")
    finally:
        phone.close()

    # A picture behind it, and every block readable over it: at least half
    # opaque, with a border.
    assert page.evaluate("getComputedStyle(document.body).backgroundImage").startswith(
        "url("
    )
    for panel in page.locator(".panel").all():
        colour, border = panel.evaluate(
            """el => {
                const style = getComputedStyle(el);
                return [style.backgroundColor, parseFloat(style.borderTopWidth)];
            }"""
        )
        opacity = float(re.search(r"rgba\([^)]*,\s*([\d.]+)\)", colour).group(1))
        assert opacity >= 0.5 and border >= 1, (colour, border)
    page.screenshot(path=str(screenshot_dir / "compops_scoreboard_custom_template.png"))

    page.goto(base + reverse("compops:scoreboard-overlay", kwargs=names))
    expect(page.locator("#sb-home-score")).to_have_text("2")
    page.screenshot(
        path=str(screenshot_dir / "compops_scoreboard_custom_overlay.png"),
        omit_background=True,
    )


SCORER_NAMES = {"competition": "pacific-cup", "season": "pc26", "ground": "field-1"}


@contextmanager
def scorer_phone(browser, login, base, season, django_user_model):
    """A scorer, who is not staff, signed in on a phone at Field 1's scorer page."""
    scorer = django_user_model.objects.create_user(
        username="scorer", password="password"
    )
    assign_perm("competition.score_season", scorer, season)
    phone = browser.new_context(viewport={"width": 390, "height": 844})
    scoring = phone.new_page()
    try:
        login(scoring, base, "scorer")
        scoring.goto(base + reverse("compops:scorer", kwargs=SCORER_NAMES))
        yield scoring
    finally:
        phone.close()


def test_scorer_says_who_scored_and_the_score_shows_it(
    browser, login, asgi_live_server, tournament, django_user_model, screenshot_dir
):
    match = tournament["match"]
    seven = TeamAssociation.objects.get(team=match.home_team, number=7)
    with scorer_phone(
        browser, login, asgi_live_server.url, tournament["season"], django_user_model
    ) as scoring:
        scoring.get_by_role("button", name="Add one to Australia").click()
        # The score is in at once; the question comes after it.
        expect(scoring.locator("#sc-home-score")).to_have_text("1")
        pick = scoring.locator("#sc-pick-home")
        expect(pick).to_be_visible()
        expect(pick.get_by_role("button")).to_have_count(SQUAD + 2)
        scoring.screenshot(path=str(screenshot_dir / "compops_scorer_who_scored.png"))
        pick.get_by_role("button", name=seven.numbered_name).click()
        expect(pick).to_be_hidden()
        expect(scoring.locator(".sc-who-name").first).to_have_text(seven.numbered_name)
        scoring.screenshot(
            path=str(screenshot_dir / "compops_scorer_who_scored_named.png")
        )

        # It can be changed while it is the team's latest, or skipped.
        scoring.get_by_role("button", name="Change").click()
        expect(pick).to_be_visible()
        pick.get_by_role("button", name="Skip").click()
        expect(pick).to_be_hidden()
    (event,) = match.events.all()
    assert (event.kind, event.side, event.player_id) == (
        "score",
        "home",
        seven.person_id,
    )


def test_turning_the_question_off_lasts_through_a_reload(
    browser, login, asgi_live_server, tournament, django_user_model
):
    with scorer_phone(
        browser, login, asgi_live_server.url, tournament["season"], django_user_model
    ) as scoring:
        toggle = scoring.locator(".sc-ask")
        expect(toggle).to_have_attribute("aria-pressed", "true")
        toggle.click()
        expect(toggle).to_have_attribute("aria-pressed", "false")
        expect(toggle).to_have_text(
            "Not asking who scored · turn on", use_inner_text=True
        )

        scoring.reload()
        expect(scoring.locator(".sc-ask")).to_have_attribute("aria-pressed", "false")
        scoring.get_by_role("button", name="Add one to Australia").click()
        expect(scoring.locator("#sc-home-score")).to_have_text("1")
        # Asked or not, the score was the press's; give a question the time
        # it would take to come, and see it did not.
        scoring.wait_for_timeout(500)
        expect(scoring.locator("#sc-pick-home")).to_be_hidden()
        # The scorer can still name the scorer, by asking for it.
        scoring.get_by_role("button", name="Who scored?").first.click()
        expect(scoring.locator("#sc-pick-home")).to_be_visible()

        # On again, and the next score asks.
        scoring.locator(".sc-ask").click()
        expect(scoring.locator(".sc-ask")).to_have_attribute("aria-pressed", "true")
        scoring.get_by_role("button", name="Skip").click()
        scoring.get_by_role("button", name="Add one to Australia").click()
        expect(scoring.locator("#sc-home-score")).to_have_text("2")
        expect(scoring.locator("#sc-pick-home")).to_be_visible()


def test_public_match_page_follows_the_live_score_without_a_reload(
    page,
    browser,
    login,
    asgi_live_server,
    tournament,
    django_user_model,
    screenshot_dir,
):
    placeholder, _ = Placeholder.objects.get_or_create(
        path="tournamentcontrol.competition.sites.CompetitionSite",
        namespace="competition",
    )
    SitemapNode.objects.create(
        title="Competitions", slug="competitions", object=placeholder
    )
    match = tournament["match"]
    # Halves of 25 minutes: 20 minutes in, the first has 5 left.
    Division.objects.filter(pk=match.stage.division_id).update(
        period_minutes=25, break_minutes=5
    )
    division = match.stage.division
    base = asgi_live_server.url
    # The competition pages hang off the sitemap node made above, so their
    # names are not in this process's URLconf: the address is spelt out, as
    # test_mysideline.py spells out its pages.
    match_url = (
        f"{base}/competitions/pacific-cup/pc26/{division.slug}/match:{match.pk}/"
    )
    with scorer_phone(
        browser, login, base, tournament["season"], django_user_model
    ) as scoring:
        # At a venue whose clocks start on time, the first score starts it.
        scoring.get_by_role("button", name="Add one to Australia").click()
        expect(scoring.locator("#sc-home-score")).to_have_text("1")

        page.goto(match_url)
        live = page.locator("#match-live")
        expect(live.locator(".live-flag")).to_have_text("Live")
        expect(live.locator(".points").first).to_have_text("1")
        expect(live.locator(".live-event")).to_have_count(1)

        scoring.get_by_role("button", name="Add one to New Zealand").click()
        scoring.get_by_role("button", name="Add one to Australia").click()
        expect(live.locator(".points").first).to_have_text("2")
        expect(live.locator(".points").last).to_have_text("1")
        expect(live.locator(".live-event")).to_have_count(3)
        expect(live.locator(".live-event .clock").first).to_have_text(
            re.compile(r"^0[0-5]:\d\d · 1st Half$")
        )
        page.screenshot(
            path=str(screenshot_dir / "match_page_live_score.png"), full_page=True
        )

        scoring.get_by_role("button", name="Take one off Australia").click()
        expect(live.locator(".points").first).to_have_text("1")
        expect(live.locator(".live-event")).to_have_count(2)


def hold(page, button):
    """Press and hold a hold-button for longer than it asks."""
    box = button.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(1700)
    page.mouse.up()


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


def test_hold_button_stays_pressed_when_the_booth_is_updated(
    compops_page, asgi_live_server, tournament
):
    """
    A push from the event stream does not drop the pressed look mid-hold.

    The stream re-renders the on-air section in place, which resets the
    button's class. The button is marked once it is held, and an event is
    published; the push takes the mark away, so waiting for that proves the
    re-render has happened, and the button must still read as pressed.
    """
    with mock.patch(
        "tournamentcontrol.competition.models.build", return_value=youtube_mock("live")
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        compops_page.goto(asgi_live_server.url + tournament["booth_path"])
        button = compops_page.locator("button[data-hold]")
        expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
        expect(compops_page.locator(".sse")).not_to_have_class("down")
        button.focus()
        compops_page.keyboard.down("Space")
        expect(button).to_have_class(re.compile(r"\bpressing\b"))
        button.evaluate("el => el.setAttribute('data-before-push', '')")
        events.publish(
            tournament["season"].pk,
            "stream-changed",
            actor="e2e",
            summary="Booth updated",
            kind="match",
            id=0,
            status="live",
        )
        expect(button).not_to_have_attribute("data-before-push", "")
        expect(button).to_have_class(re.compile(r"\bpressing\b"))
        compops_page.keyboard.up("Space")
        expect(button).not_to_have_class(re.compile(r"\bpressing\b"))


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
    """
    A result with one score is refused, and its row says why.

    The test waits for the event stream's first push before it types, so the
    refusal is made on a page that is up to date, as a person makes it.
    test_a_refusal_keeps_its_error_when_the_snapshot_lands_after_it covers
    the push landing after the refusal.
    """
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    wait_for_snapshot(compops_page, tournament["season"])
    row = compops_page.locator(f"#match-{tournament['match'].pk}")
    row.locator('input[name="home_team_score"]').fill("3")
    row.locator('button[type="submit"]').click()
    expect(row.locator(".errorlist li")).to_have_text("Both scores are required.")
    expect(row.locator('input[name="home_team_score"]')).to_have_value("3")
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_result_validation.png"), full_page=True
    )


def test_a_refusal_keeps_its_error_when_the_snapshot_lands_after_it(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    """
    A refused result keeps its error, and its score, when the event stream's
    snapshot lands after the refusal, as the snapshot of a reconnect does.

    The snapshot re-renders the results with unbound forms. The test holds it
    back until the refusal is on the page, then lets it through, waits for it,
    and finishes the result to show the row still works.
    """
    with snapshot_held():
        compops_page.goto(asgi_live_server.url + tournament["day_path"])
        row = compops_page.locator(f"#match-{tournament['match'].pk}")
        row.locator('input[name="home_team_score"]').fill("3")
        row.locator('button[type="submit"]').click()
        expect(row.locator(".errorlist li")).to_have_text("Both scores are required.")
    wait_for_snapshot(compops_page, tournament["season"])
    expect(row.locator(".errorlist li")).to_have_text("Both scores are required.")
    expect(row.locator('input[name="home_team_score"]')).to_have_value("3")
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_result_error_kept.png"), full_page=True
    )
    row.locator('input[name="away_team_score"]').fill("2")
    row.locator('button[type="submit"]').click()
    expect(row.locator(".score")).to_have_text("3 – 2")
    expect(row.locator(".errorlist")).to_have_count(0)


def test_an_open_edit_stays_open_when_the_snapshot_lands_after_it(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    """
    An entered result opened for editing stays open, with the score being
    typed, when the event stream's snapshot lands after it, as the snapshot
    of a reconnect does.

    The snapshot renders the result as entered, with its Edit link. The test
    holds it back until the row is open and a score typed, then lets it
    through, waits for it, and saves to show the row still works.
    """
    scored = tournament["scored"]
    with snapshot_held():
        compops_page.goto(asgi_live_server.url + tournament["day_path"])
        # A slot whose results are all in is folded.
        compops_page.locator(f"#slot-{scored.time:%H%M}-h").click()
        row = compops_page.locator(f"#match-{scored.pk}")
        row.locator("a", has_text="Edit").click()
        row.locator('input[name="home_team_score"]').fill("2")
    wait_for_snapshot(compops_page, tournament["season"])
    expect(row.locator('input[name="home_team_score"]')).to_have_value("2")
    expect(row.locator('input[name="away_team_score"]')).to_have_value("0")
    expect(row.locator("a", has_text="✕")).to_be_visible()
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_edit_kept.png"), full_page=True
    )
    row.locator('button[type="submit"]').click()
    expect(row.locator(".score")).to_have_text("2 – 0")


def centre_x(locator):
    """The x-centre of the box ``locator`` matches, in CSS pixels."""
    box = locator.bounding_box()
    return box["x"] + box["width"] / 2


def score_inputs_centre_x(row):
    """The x-centre of the pair of score inputs in ``row``."""
    home = row.locator('input[name="home_team_score"]').bounding_box()
    away = row.locator('input[name="away_team_score"]').bounding_box()
    return (home["x"] + away["x"] + away["width"]) / 2


def test_the_score_sits_in_the_same_column_in_every_row_state(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    """
    The score is at the same place in a read-only row (Edit), an empty row
    (Forfeit… and Save) and a row open for editing (Save and ✕), so the
    scores read down one column whatever the actions beside them.
    """
    match, scored = tournament["match"], tournament["scored"]
    compops_page.set_viewport_size({"width": 1600, "height": 900})
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    wait_for_snapshot(compops_page, tournament["season"])
    # A slot whose results are all in is folded.
    compops_page.locator(f"#slot-{scored.time:%H%M}-h").click()
    readonly = compops_page.locator(f"#match-{scored.pk}")
    expected = centre_x(readonly.locator(".score"))
    empty = compops_page.locator(f"#match-{match.pk}")
    assert score_inputs_centre_x(empty) == pytest.approx(expected, abs=1)
    readonly.locator("a", has_text="Edit").click()
    expect(readonly.locator("a", has_text="✕")).to_be_visible()
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_score_column.png"), full_page=True
    )
    assert score_inputs_centre_x(readonly) == pytest.approx(expected, abs=1)


def test_a_reconnect_brings_the_page_up_to_date_around_the_rows_being_worked_on(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    """
    A reconnect of the event stream sends the snapshot again. It brings the
    rows nobody is working in up to date, and leaves an open Edit and a
    refused result as they are.

    A page that is hidden closes its stream and reopens it when it is shown,
    as a phone does when it sleeps; the test fires that event. The upcoming
    match is given a result the stream is not told about, so only the
    snapshot can show it: it also shows that the first snapshot did not mark
    the rows it updated as held.
    """
    match, scored, upcoming = (
        tournament["match"],
        tournament["scored"],
        tournament["upcoming"],
    )
    compops_page.goto(asgi_live_server.url + tournament["day_path"])
    wait_for_snapshot(compops_page, tournament["season"])
    refused = compops_page.locator(f"#match-{match.pk}")
    refused.locator('input[name="home_team_score"]').fill("3")
    refused.locator('button[type="submit"]').click()
    expect(refused.locator(".errorlist li")).to_have_text("Both scores are required.")
    # A slot whose results are all in is folded.
    compops_page.locator(f"#slot-{scored.time:%H%M}-h").click()
    editing = compops_page.locator(f"#match-{scored.pk}")
    editing.locator("a", has_text="Edit").click()
    editing.locator('input[name="home_team_score"]').fill("2")
    Match.objects.filter(pk=upcoming.pk).update(home_team_score=4, away_team_score=1)
    compops_page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    expect(compops_page.locator(f"#match-{upcoming.pk} .score")).to_have_text("4 – 1")
    expect(refused.locator(".errorlist li")).to_have_text("Both scores are required.")
    expect(refused.locator('input[name="home_team_score"]')).to_have_value("3")
    expect(editing.locator('input[name="home_team_score"]')).to_have_value("2")
    expect(editing.locator("a", has_text="✕")).to_be_visible()
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_reconnect_keeps_work.png"), full_page=True
    )


def test_a_refused_stream_action_keeps_its_message_when_the_snapshot_lands_after_it(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    """
    A refused stream action keeps its message, in its ground's block of the
    streams column, when the event stream's snapshot lands after it, as the
    snapshot of a reconnect does, and through a push about another stream.
    A push about that ground releases it.

    YouTube refuses to take the upcoming match live. The test holds the
    snapshot back until the refusal is on the page, then lets it through and
    waits for it; the push wait_for_snapshot makes is about no ground on the
    page, so it leaves the block alone as well. Then the match is armed from
    the booth, and the push about it clears the message.
    """
    season, ground, upcoming = (
        tournament["season"],
        tournament["ground"],
        tournament["upcoming"],
    )
    block = compops_page.locator(f"#stream-{ground.pk}")
    message = "Field 1 · Japan v Singapore: Stream is inactive"
    with mock.patch(
        "tournamentcontrol.competition.models.build",
        return_value=refusing_youtube("Stream is inactive"),
    ):
        with snapshot_held():
            compops_page.goto(asgi_live_server.url + tournament["day_path"])
            block.locator(".next button", has_text="Go live").click()
            expect(block.locator("p.warn")).to_have_text(message)
        wait_for_snapshot(compops_page, season)
    expect(block.locator("p.warn")).to_have_text(message)
    expect(block.locator(".next .badge")).to_have_text("no status")
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_stream_error_kept.png"), full_page=True
    )
    Match.objects.filter(pk=upcoming.pk).update(live_stream_status="testing")
    streams.publish_change(upcoming, "testing", actor="booth")
    expect(block.locator(".next .badge")).to_have_text("testing")
    expect(block.locator("p.warn")).to_have_count(0)
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_stream_error_released.png"),
        full_page=True,
    )


def test_a_refused_booth_action_keeps_its_reason_when_the_snapshot_lands_after_it(
    compops_page, asgi_live_server, tournament, screenshot_dir
):
    """
    A refused booth action keeps its reason in the lamp when the booth's
    event stream sends its snapshot after the refusal, as the snapshot of a
    reconnect does, and through a push about another ground. A push about
    this ground releases it.

    YouTube refuses to end the broadcast. The test holds the snapshot back
    until the reason is in the lamp, then lets it through. The lamp is held,
    so the strip is marked and watched to see the snapshot and the pushes
    land. Then ops end the broadcast from the day page, and the push about
    it clears the reason and darkens the lamp.
    """
    match, scored = tournament["match"], tournament["scored"]
    reason = (
        "Field 1 · Australia v New Zealand: The request cannot be completed "
        "because you have exceeded your quota."
    )
    warn = compops_page.locator("#onair .warn")
    strip = compops_page.locator("#strip")
    with mock.patch(
        "tournamentcontrol.competition.models.build",
        return_value=refusing_youtube(
            "The request cannot be completed because you have exceeded your quota."
        ),
    ):
        compops_page.set_viewport_size({"width": 1024, "height": 768})
        with snapshot_held("booth_snapshot"):
            compops_page.goto(asgi_live_server.url + tournament["booth_path"])
            button = compops_page.locator("button[data-hold]")
            expect(button).to_have_text("HOLD TO END BROADCAST")
            box = button.bounding_box()
            compops_page.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            compops_page.mouse.down()
            compops_page.wait_for_timeout(1700)
            compops_page.mouse.up()
            expect(warn).to_have_text(reason)
            strip.evaluate("el => el.setAttribute('data-before-snapshot', '')")
        expect(strip).not_to_have_attribute("data-before-snapshot", "")
    expect(warn).to_have_text(reason)
    expect(compops_page.locator("#lamp")).to_have_text("ON AIR")
    compops_page.screenshot(
        path=str(screenshot_dir / "compops_booth_reason_kept.png"), full_page=True
    )
    # A push about another ground brings the strip up to date around the lamp.
    strip.evaluate("el => el.setAttribute('data-before-push', '')")
    streams.publish_change(scored, "live", actor="e2e")
    expect(strip).not_to_have_attribute("data-before-push", "")
    expect(warn).to_have_text(reason)
    Match.objects.filter(pk=match.pk).update(live_stream_status="complete")
    streams.publish_change(match, "complete", actor="ops")
    expect(compops_page.locator("#lamp")).to_have_text("OFF AIR")
    expect(warn).to_have_count(0)


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
