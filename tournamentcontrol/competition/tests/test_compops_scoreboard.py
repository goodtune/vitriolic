"""
The scoreboard of a ground: its clock, the match it shows, the pages that
show it and the scorer's buttons. The clock's counting in the browser, and a
score reaching a board as it is tapped, are in ``tests/e2e/test_compops.py``.
"""

import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group
from django.utils import timezone
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from tournamentcontrol.competition.compops import events, scoreboard
from tournamentcontrol.competition.compops.scoreboard import Clock, Moment
from tournamentcontrol.competition.forms import DivisionForm, VenueForm
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_compops_results import DATASTAR

TZ = ZoneInfo("Australia/Brisbane")
DAY = datetime.date(2026, 10, 8)


def at(hour, minute=0, second=0):
    return timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute, second), TZ)


class ClockTests(TestCase):
    """Two periods of 15 minutes with a break of 2, from 19:00."""

    clock = Clock(start=at(19), periods=2, period=900, pause=120)

    def test_phases_are_the_periods_and_the_breaks_between(self):
        self.assertEqual(
            (self.clock.phases, self.clock.end),
            ([("period", 900), ("break", 120), ("period", 900)], at(19, 32)),
        )
        self.assertEqual(Clock(at(19), 3, 600, 0).phases, [("period", 600)] * 3)

    def test_clock_counts_down_through_each_phase(self):
        moments = {
            "an hour and a half before": (at(17, 30), Moment("before", None, 1, 5400)),
            "ten seconds before": (at(18, 59, 50), Moment("before", None, 1, 10)),
            "the start": (at(19), Moment("period", 0, 1, 900)),
            "five minutes in": (at(19, 5), Moment("period", 0, 1, 600)),
            "the break": (at(19, 15), Moment("break", 1, 2, 120)),
            "the second period": (at(19, 17), Moment("period", 2, 2, 900)),
            "its last second": (at(19, 31, 59), Moment("period", 2, 2, 1)),
            "the end": (at(19, 32), Moment("over", None, None, 0)),
            "long after": (at(23), Moment("over", None, None, 0)),
        }
        for name, (now, moment) in moments.items():
            with self.subTest(name):
                self.assertEqual(self.clock.at(now), moment)

    def test_part_of_a_second_left_reads_as_a_whole_one(self):
        now = at(19) + datetime.timedelta(seconds=899.6)
        self.assertEqual(self.clock.at(now), Moment("period", 0, 1, 1))

    def test_clock_not_started_waits_at_a_full_period(self):
        waiting = Clock(start=None, periods=2, period=900, pause=120)
        self.assertEqual(
            (waiting.at(at(19, 5)), waiting.end, waiting.start_ms),
            (Moment("ready", None, 1, 900), None, None),
        )

    def test_moment_is_named_and_shown_as_a_time(self):
        self.assertEqual(
            [
                (moment.label, moment.display)
                for moment in (
                    Moment("before", None, 1, 5400),
                    Moment("period", 0, 1, 600),
                    Moment("break", 1, 2, 61),
                    Moment("over", None, None, 0),
                    Moment("ready", None, 1, 900),
                )
            ],
            [
                ("Starts in", "1:30:00"),
                ("Period 1", "10:00"),
                ("Break", "01:01"),
                ("Full time", "00:00"),
                ("Ready", "15:00"),
            ],
        )


class ScoreboardFixture(TestCase):
    def setUp(self):
        super().setUp()
        events.reset_backend()
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
        )
        self.venue = factories.VenueFactory.create(season=self.season)
        self.field1 = factories.GroundFactory.create(
            venue=self.venue, title="Field 1", slug="field-1", slug_locked=True
        )
        self.division = factories.DivisionFactory.create(
            season=self.season, title="Men's Open", period_minutes=15, break_minutes=2
        )
        self.stage = factories.StageFactory.create(division=self.division)
        self.aus = self.team("Australia", "AUS")
        self.nzl = self.team("New Zealand", "NZL")
        self.fji = self.team("Fiji", "")
        self.first = self.match(19, self.aus, self.nzl)
        self.second = self.match(20, self.fji, self.aus)
        self.scorer = factories.UserFactory.create()
        assign_perm("competition.score_season", self.scorer, self.season)
        self.outsider = factories.UserFactory.create()
        self.kw = {"competition": "pacific-cup", "season": "pc26", "ground": "field-1"}

    def team(self, title, abbreviation):
        return factories.TeamFactory.create(
            division=self.division, title=title, club__abbreviation=abbreviation
        )

    def match(self, hour, home, away, ground=None, **kwargs):
        when = at(hour)
        return factories.MatchFactory.create(
            stage=self.stage,
            home_team=home,
            away_team=away,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=ground or self.field1,
            **kwargs,
        )

    def press(self, name, match=None, user=None, **kwargs):
        """Press a button of the scorer's page; the answer is ``last_response``."""
        with (
            self.login(user or self.scorer),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.post(
                f"compops:{name}",
                match_pk=(match or self.first).pk,
                extra=DATASTAR,
                **self.kw,
                **kwargs,
            )
        return b"".join(self.last_response.streaming_content).decode()


class BoardMatchTests(ScoreboardFixture):
    """Which match the board shows: 19:00 and 20:00, each over in 32 minutes."""

    def shown(self, hour, minute=0):
        return scoreboard.board_match(self.field1, at(hour, minute))

    def test_board_shows_the_match_being_played_then_the_next_to_come(self):
        times = {
            "before the first": ((18, 0), self.first),
            "during the first": ((19, 20), self.first),
            "just after it ends": ((19, 33), self.first),
            "two minutes after": ((19, 34), self.second),
            "during the second": ((20, 10), self.second),
            "after the last": ((22, 0), self.second),
        }
        for name, (time, match) in times.items():
            with self.subTest(name):
                self.assertEqual(self.shown(*time), match)

    def test_match_with_no_clock_keeps_the_board_until_the_next_ones_time(self):
        self.division.period_minutes = None
        self.division.save()
        self.assertEqual(
            (self.shown(19, 59), self.shown(20, 0)), (self.first, self.second)
        )

    def test_match_whose_clock_was_never_started_keeps_the_board(self):
        self.venue.scoreboard_auto_start = False
        self.venue.save()
        self.assertEqual(
            (self.shown(19, 59), self.shown(20, 0)), (self.first, self.second)
        )

    def test_ground_with_nothing_today_shows_no_match(self):
        other = factories.GroundFactory.create(venue=self.venue)
        self.assertEqual(scoreboard.board_match(other, at(19)), None)

    def test_clock_starts_on_time_or_when_the_scorer_starts_it(self):
        on_time = scoreboard.clock_for(self.first, self.field1)
        self.venue.scoreboard_auto_start = False
        self.venue.save()
        self.field1.refresh_from_db()
        waiting = scoreboard.clock_for(self.first, self.field1)
        self.first.clock_started_at = at(19, 4)
        started = scoreboard.clock_for(self.first, self.field1)
        self.assertEqual(
            (on_time, waiting.start, started.start),
            (Clock(at(19), 2, 900, 120), None, at(19, 4)),
        )

    def test_division_with_no_period_length_has_no_clock(self):
        self.division.period_minutes = None
        self.division.save()
        self.first.refresh_from_db()
        self.assertEqual(scoreboard.clock_for(self.first, self.field1), None)

    def test_team_is_coded_by_its_club_else_the_start_of_its_name(self):
        self.assertEqual(
            (
                scoreboard.team_code(self.first, "home"),
                scoreboard.team_code(self.second, "home"),
            ),
            ("AUS", "FIJ"),
        )

    def test_score_is_the_progress_score_else_the_result_else_nothing(self):
        scores = []
        for progress, result in ((None, None), (None, 4), (2, 4), (0, 4)):
            self.first.home_team_progress_score = progress
            self.first.home_team_score = result
            scores.append(scoreboard.score(self.first, "home"))
        self.assertEqual(scores, [0, 4, 2, 0])


@freeze_time("2026-10-08 19:05 +10:00")
class DisplayTests(ScoreboardFixture):
    def test_anyone_may_see_the_board(self):
        self.first.home_team_progress_score = 3
        self.first.away_team_progress_score = 1
        self.first.save()
        self.get("compops:scoreboard", **self.kw)
        self.assert_http_200_ok()
        for element in (
            '<div class="sb-digits" id="sb-home-score">3</div>',
            '<div class="sb-digits" id="sb-away-score">1</div>',
            '<div class="sb-name" id="sb-home-name">Australia</div>',
            '<div class="sb-name" id="sb-away-name">New Zealand</div>',
            '<span class="sb-code">AUS</span>',
            '<div class="sb-label" id="sb-label">Period 1</div>',
            '<div class="sb-time" id="sb-time">10:00</div>',
            '<ol class="sb-dots" id="sb-dots"><li class="period on"></li>'
            '<li class="break"></li><li class="period"></li></ol>',
        ):
            with self.subTest(element):
                self.assertResponseContains(element)

    def test_clock_carries_what_the_page_counts_from(self):
        self.get("compops:scoreboard", **self.kw)
        start = int(at(19).timestamp() * 1000)
        now = int(at(19, 5).timestamp() * 1000)
        self.assertIn(
            f'<section id="sb-clock" class="sb-clock period" '
            f'data-match="{self.first.pk}" data-now="{now}" data-start="{start}" '
            'data-periods="2" data-period="900" data-pause="120">',
            self.last_response.content.decode(),
        )

    def test_board_listens_for_changes_and_asks_again_by_itself(self):
        self.get("compops:scoreboard", **self.kw)
        content = self.last_response.content.decode()
        events_url = self.reverse("compops:scoreboard-events", **self.kw)
        board_url = self.reverse("compops:scoreboard-board", **self.kw)
        self.assertIn(
            'class="scoreboard display" data-signals__ifmissing="{board: \'display\'}" '
            'data-indicator="connected" '
            f"data-effect=\"@get('{events_url}', {{retryMaxCount: 1000}})\"",
            content,
        )
        self.assertIn(
            f'<main id="board" class="sb-board" '
            f"data-on-interval__duration.20s=\"@get('{board_url}')\">",
            content,
        )

    def test_overlay_is_the_same_board_with_no_horn_to_turn_on(self):
        self.get("compops:scoreboard-overlay", **self.kw)
        self.assert_http_200_ok()
        content = self.last_response.content.decode()
        self.assertEqual(
            (
                content.count('class="scoreboard overlay"'),
                content.count('id="sb-home-score"'),
                content.count('id="sb-sound"'),
            ),
            (1, 1, 0),
        )
        self.get("compops:scoreboard", **self.kw)
        self.assertResponseContains(
            '<button type="button" id="sb-sound" class="sb-sound">'
            "Tap to turn the horn on</button>"
        )

    def test_board_fragment_is_the_board_alone(self):
        self.get("compops:scoreboard-board", **self.kw)
        self.assert_http_200_ok()
        content = self.last_response.content.decode().strip()
        self.assertEqual(
            (content.startswith('<main id="board"'), content.endswith("</main>")),
            (True, True),
        )

    def test_division_with_no_period_length_shows_the_score_and_no_clock(self):
        self.division.period_minutes = None
        self.division.save()
        self.get("compops:scoreboard", **self.kw)
        content = self.last_response.content.decode()
        self.assertEqual(
            (content.count('id="sb-home-score"'), content.count('id="sb-clock"')),
            (1, 0),
        )

    def test_ground_with_nothing_today_says_so(self):
        other = factories.GroundFactory.create(
            venue=self.venue, title="Field 9", slug="field-9", slug_locked=True
        )
        self.get("compops:scoreboard", **{**self.kw, "ground": other.slug})
        self.assertResponseContains(
            '<p class="sb-empty">No matches on Field 9 today.</p>'
        )

    def test_unknown_ground_is_404(self):
        self.get("compops:scoreboard", **{**self.kw, "ground": "nowhere"})
        self.assert_http_404_not_found()

    def test_index_lists_every_ground_of_the_season(self):
        self.get("compops:scoreboard-index", competition="pacific-cup", season="pc26")
        self.assert_http_200_ok()
        self.assertResponseContains(
            f'<a class="btn" href="{self.reverse("compops:scorer", **self.kw)}">'
            "Scorer</a>"
        )


@freeze_time("2026-10-08 19:05 +10:00")
class ScorerTests(ScoreboardFixture):
    def score_url(self, side, step, match=None):
        return self.reverse(
            "compops:scorer-score",
            match_pk=(match or self.first).pk,
            side=side,
            step=step,
            **self.kw,
        )

    def test_scorer_needs_a_login_and_the_right_to_score(self):
        self.assertLoginRequired("compops:scorer", **self.kw)
        with self.login(self.outsider):
            self.get("compops:scorer", **self.kw)
        self.assert_http_403_forbidden()

    def test_scorer_need_not_be_staff_and_may_be_one_of_a_group(self):
        crew = Group.objects.create(name="Scorers")
        assign_perm("competition.score_season", crew, self.season)
        self.outsider.groups.add(crew)
        for user in (self.scorer, self.outsider):
            with self.subTest(user=user), self.login(user):
                self.get("compops:scorer", **self.kw)
                self.assert_http_200_ok()

    def test_page_has_a_button_to_add_and_to_take_off_for_each_team(self):
        with self.login(self.scorer):
            self.get("compops:scorer", **self.kw)
        content = self.last_response.content.decode()
        for side in ("home", "away"):
            for step in ("up", "down"):
                with self.subTest(side=side, step=step):
                    url = self.score_url(side, step)
                    self.assertIn(f'<form method="post" action="{url}"', content)
        self.assertResponseContains('<h2 class="sc-name">Australia</h2>')
        self.assertResponseContains(
            '<output class="sc-score" id="sc-home-score">0</output>'
        )
        # Nothing to take off a score of nothing.
        self.assertResponseContains(
            '<button class="sc-btn" type="submit" '
            'aria-label="Take one off Australia" disabled>−</button>'
        )

    def test_button_adds_one_and_the_scorer_is_sent_the_new_score(self):
        body = self.press("scorer-score", side="home", step="up")
        self.assert_http_200_ok()
        self.assertIn('<output class="sc-score" id="sc-home-score">1</output>', body)
        self.press("scorer-score", side="home", step="up")
        self.press("scorer-score", side="away", step="up")
        self.press("scorer-score", side="home", step="down")
        self.first.refresh_from_db()
        self.assertEqual(
            (
                self.first.home_team_progress_score,
                self.first.away_team_progress_score,
                # The result is not the scoreboard's to change.
                self.first.home_team_score,
            ),
            (1, 1, None),
        )

    def test_score_does_not_go_below_nothing(self):
        self.press("scorer-score", side="away", step="down")
        self.first.refresh_from_db()
        self.assertEqual(self.first.away_team_progress_score, 0)

    def test_press_tells_the_grounds_boards_and_not_the_ops_desk(self):
        self.press("scorer-score", side="home", step="up")
        backend = events.get_backend()
        (event,) = backend.recent(events.channel(self.season.pk, scoreboard.SCOPE))
        self.assertEqual(
            (event["type"], event["ground"], event["match"], event["actor"]),
            (
                "scoreboard-changed",
                self.field1.pk,
                self.first.pk,
                self.scorer.get_username(),
            ),
        )
        self.assertEqual(events.recent(self.season.pk), [])

    def test_form_post_without_scripts_returns_to_the_scorers_page(self):
        with self.login(self.scorer):
            self.post(
                "compops:scorer-score",
                match_pk=self.first.pk,
                side="home",
                step="up",
                **self.kw,
            )
        self.assert_http_302_found(url=self.reverse("compops:scorer", **self.kw))
        self.first.refresh_from_db()
        self.assertEqual(self.first.home_team_progress_score, 1)

    def test_press_needs_a_login_and_the_right_to_score(self):
        self.post(
            "compops:scorer-score",
            match_pk=self.first.pk,
            side="home",
            step="up",
            **self.kw,
        )
        self.assert_http_302_found()
        with self.login(self.outsider):
            self.post(
                "compops:scorer-score",
                match_pk=self.first.pk,
                side="home",
                step="up",
                **self.kw,
            )
        self.assert_http_403_forbidden()
        self.first.refresh_from_db()
        self.assertEqual(self.first.home_team_progress_score, None)

    def test_button_that_does_not_exist_is_404(self):
        elsewhere = self.match(
            19,
            self.fji,
            self.nzl,
            ground=factories.GroundFactory.create(venue=self.venue),
        )
        cases = (
            {"side": "referee", "step": "up"},
            {"side": "home", "step": "sideways"},
            {"side": "home", "step": "up", "match": elsewhere},
        )
        for case in cases:
            with self.subTest(case):
                with self.login(self.scorer):
                    self.post(
                        "compops:scorer-score",
                        match_pk=case.get("match", self.first).pk,
                        side=case["side"],
                        step=case["step"],
                        **self.kw,
                    )
                self.assert_http_404_not_found()

    def test_scorer_page_asks_for_its_own_copy_of_the_board(self):
        # The page says it is the scorer's (the ``board`` signal); so asked,
        # the board is sent with the buttons, to those who may press them.
        signals = {"datastar": '{"board": "scorer"}'}
        with self.login(self.scorer):
            self.get(
                "compops:scoreboard-board", data=signals, extra=DATASTAR, **self.kw
            )
        body = b"".join(self.last_response.streaming_content).decode()
        self.assertIn('<main id="scorer"', body)
        with self.login(self.outsider):
            self.get(
                "compops:scoreboard-board", data=signals, extra=DATASTAR, **self.kw
            )
        self.assert_http_403_forbidden()


@freeze_time("2026-10-08 19:05 +10:00")
class ManualStartTests(ScoreboardFixture):
    """A venue whose clocks the scorer starts by hand."""

    def setUp(self):
        super().setUp()
        self.venue.scoreboard_auto_start = False
        self.venue.save()

    def test_board_waits_at_a_full_period_until_the_clock_is_started(self):
        self.get("compops:scoreboard", **self.kw)
        self.assertResponseContains('<div class="sb-label" id="sb-label">Ready</div>')
        self.assertResponseContains('<div class="sb-time" id="sb-time">15:00</div>')
        self.assertIn('data-start=""', self.last_response.content.decode())

    def test_scorer_starts_the_clock_once(self):
        start = self.reverse("compops:scorer-start", match_pk=self.first.pk, **self.kw)
        with self.login(self.scorer):
            self.get("compops:scorer", **self.kw)
        self.assertIn(
            f'<form class="sc-start" method="post" action="{start}"',
            self.last_response.content.decode(),
        )
        body = self.press("scorer-start")
        self.first.refresh_from_db()
        self.assertEqual(self.first.clock_started_at, at(19, 5))
        self.assertEqual(body.count("Start the clock"), 0)
        # A second press, a minute later, changes nothing.
        with freeze_time("2026-10-08 19:06 +10:00"):
            self.press("scorer-start")
        self.first.refresh_from_db()
        self.assertEqual(self.first.clock_started_at, at(19, 5))

    def test_venue_whose_clocks_start_on_time_has_no_start_button(self):
        self.venue.scoreboard_auto_start = True
        self.venue.save()
        with self.login(self.scorer):
            self.get("compops:scorer", **self.kw)
        self.assertEqual(self.last_response.content.count(b"Start the clock"), 0)


class SettingsFormTests(TestCase):
    def test_division_form_has_the_timing_of_its_matches(self):
        fields = DivisionForm(instance=factories.DivisionFactory.create()).fields
        self.assertEqual(
            [name for name in fields if name.endswith(("periods", "_minutes"))],
            ["periods", "period_minutes", "break_minutes"],
        )

    def test_division_saved_without_its_timing_keeps_what_it_has(self):
        # A form that does not send the timing (an older page, the MCP tools)
        # neither fails nor puts the timing back to the default.
        division = factories.DivisionFactory.create(
            periods=4, period_minutes=10, break_minutes=3
        )
        data = {
            "title": division.title,
            "points_formula_0": "3",
            "points_formula_1": "2",
            "points_formula_2": "1",
            "points_formula_3": "",
            "points_formula_4": "",
            "points_formula_5": "",
            "bonus_points_formula": "",
            "forfeit_for_score": "5",
            "forfeit_against_score": "0",
            "include_forfeits_in_played": "1",
            "games_per_day": "2",
            "color": "#ffffff",
        }
        form = DivisionForm(data=data, instance=division)
        self.assertEqual(form.errors, {})
        form.save()
        division.refresh_from_db()
        self.assertEqual((division.periods, division.break_minutes), (4, 3))

    def test_venue_form_has_whether_its_clocks_start_on_time(self):
        form = VenueForm(instance=factories.VenueFactory.create())
        self.assertEqual(
            (
                "scoreboard_auto_start" in form.fields,
                form.initial["scoreboard_auto_start"],
            ),
            (True, True),
        )
