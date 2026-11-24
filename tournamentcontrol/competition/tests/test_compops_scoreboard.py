"""
The scoreboard of a ground: its clock, the match it shows, the pages that
show it and the scorer's buttons. The clock's counting in the browser, and a
score reaching a board as it is tapped, are in ``tests/e2e/test_compops.py``.
"""

import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from touchtechnology.admin.tests.shells import by_shell
from tournamentcontrol.competition.compops import events, scoreboard
from tournamentcontrol.competition.compops.scoreboard import Clock, Moment
from tournamentcontrol.competition.forms import (
    CompetitionForm,
    DivisionForm,
    MatchEditForm,
    MatchStreamForm,
    SeasonForm,
    StageForm,
    VenueForm,
)
from tournamentcontrol.competition.models import Match
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

    def test_last_minute_of_a_period_is_shown_to_a_tenth_of_a_second(self):
        def shown(seconds_left, clock=self.clock, end=at(19, 15)):
            return clock.at(end - datetime.timedelta(seconds=seconds_left)).display

        self.assertEqual(
            [shown(left) for left in (61, 60, 59.96, 59.94, 30, 9.25, 0.04)],
            ["01:01", "01:00", "59.9", "59.9", "30.0", "9.2", "0.0"],
        )
        # Only a period is: a break and the wait for a start count in seconds.
        self.assertEqual(
            (shown(30.5, end=at(19, 17)), shown(30.5, end=at(19))),
            ("00:31", "00:31"),
        )

    def test_break_starts_the_moment_a_period_ends(self):
        end = at(19, 15)
        tick = datetime.timedelta(milliseconds=1)
        self.assertEqual(
            (self.clock.at(end - tick).kind, self.clock.at(end).kind),
            ("period", "break"),
        )

    def test_clock_not_started_waits_at_a_full_period(self):
        waiting = Clock(start=None, periods=2, period=900, pause=120)
        self.assertEqual(
            (waiting.at(at(19, 5)), waiting.end, waiting.start_ms),
            (Moment("ready", None, 1, 900), None, None),
        )

    def test_moment_is_named_and_shown_as_a_time(self):
        waiting = Clock(start=None, periods=2, period=900, pause=120)
        moments = [
            self.clock.at(at(17, 30)),
            self.clock.at(at(19, 5)),
            self.clock.at(at(19, 15, 59)),
            self.clock.at(at(19, 20)),
            self.clock.at(at(20)),
            waiting.at(at(19)),
        ]
        self.assertEqual(
            [(moment.label, moment.display) for moment in moments],
            [
                ("Starts in", "1:30:00"),
                ("1st Half", "10:00"),
                ("Half time", "01:01"),
                ("2nd Half", "12:00"),
                ("Full time", "00:00"),
                ("Ready", "15:00"),
            ],
        )

    def test_periods_are_named_from_how_many_there_are(self):
        def names(periods, pause=120, name=""):
            return Clock(at(19), periods, 600, pause, name).names

        self.assertEqual(
            [names(2), names(3), names(4), names(4, pause=0)],
            [
                ["1st Half", "Half time", "2nd Half"],
                ["1st Period", "Break", "2nd Period", "Break", "3rd Period"],
                [
                    "1st Quarter",
                    "Quarter time",
                    "2nd Quarter",
                    "Half time",
                    "3rd Quarter",
                    "Three-quarter time",
                    "4th Quarter",
                ],
                ["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"],
            ],
        )

    def test_half_time_may_be_longer_than_the_other_breaks(self):
        # Netball: quarters of 15 minutes, 4 minutes between, 12 at half time.
        clock = Clock(at(19), 4, 900, 240, half=720)
        self.assertEqual(
            (clock.phases, clock.length),
            (
                [
                    ("period", 900),
                    ("break", 240),
                    ("period", 900),
                    ("break", 720),
                    ("period", 900),
                    ("break", 240),
                    ("period", 900),
                ],
                datetime.timedelta(minutes=80),
            ),
        )
        # 38 minutes in is 4 minutes into half time, with 8 to go.
        self.assertEqual(
            clock.at(at(19, 38)), Moment("break", 3, 3, 480, label="Half time")
        )

    def test_half_time_is_the_break_in_the_middle_of_an_even_number(self):
        def breaks(periods, **kwargs):
            clock = Clock(at(19), periods, 600, 120, **kwargs)
            return [
                (name, seconds)
                for name, (kind, seconds) in zip(clock.names, clock.phases)
                if kind == "break"
            ]

        self.assertEqual(
            [
                breaks(2, half=600),
                # An odd number of periods has no middle to break at.
                breaks(3, half=600),
                breaks(6),
                # A sport that names its periods has a half time once it has
                # a length of its own, and none of half time is no break.
                breaks(6, name="Chukka", half=300),
                breaks(4, half=0),
            ],
            [
                [("Half time", 600)],
                [("Break", 120), ("Break", 120)],
                [
                    ("Break", 120),
                    ("Break", 120),
                    ("Half time", 120),
                    ("Break", 120),
                    ("Break", 120),
                ],
                [
                    ("Break", 120),
                    ("Break", 120),
                    ("Half time", 300),
                    ("Break", 120),
                    ("Break", 120),
                ],
                [("Quarter time", 120), ("Three-quarter time", 120)],
            ],
        )

    def test_match_of_one_period_has_no_name_for_it(self):
        # There is nothing to tell it from: no name, and no dots to count.
        clock = Clock(at(19), 1, 600, 120)
        self.assertEqual((clock.names, clock.at(at(19, 5)).label), ([""], ""))

    def test_period_may_be_given_a_name_of_its_own(self):
        # The breaks of a sport that names its own periods are only breaks.
        self.assertEqual(
            Clock(at(19), 4, 420, 180, "Chukka").names,
            [
                "1st Chukka",
                "Break",
                "2nd Chukka",
                "Break",
                "3rd Chukka",
                "Break",
                "4th Chukka",
            ],
        )

    def test_numbers_are_said_as_places(self):
        self.assertEqual(
            [
                scoreboard.ordinal(n)
                for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111)
            ],
            [
                "1st",
                "2nd",
                "3rd",
                "4th",
                "11th",
                "12th",
                "13th",
                "21st",
                "22nd",
                "23rd",
                "101st",
                "111th",
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

    def test_stage_or_match_may_have_a_timing_of_its_own(self):
        # Rugby sevens: halves of 7 minutes, but of 10 in the final.
        self.division.period_minutes = 7
        self.division.break_minutes = 2
        self.division.save()
        finals = factories.StageFactory.create(
            division=self.division, period_minutes=10
        )
        pool_match = self.match(19, self.aus, self.nzl)
        final = factories.MatchFactory.create(
            stage=finals, play_at=self.field1, datetime=at(21), date=DAY
        )
        replay = factories.MatchFactory.create(
            stage=finals,
            play_at=self.field1,
            datetime=at(22),
            date=DAY,
            periods=4,
            period_minutes=5,
            break_minutes=0,
        )
        self.assertEqual(
            [
                (clock.periods, clock.period, clock.pause)
                for clock in (
                    scoreboard.clock_for(match, self.field1)
                    for match in (pool_match, final, replay)
                )
            ],
            # The match's own, else its stage's, else its division's, each
            # number on its own: the final keeps the division's break.
            [(2, 420, 120), (2, 600, 120), (4, 300, 0)],
        )

    def test_stage_or_match_may_have_a_half_time_of_its_own(self):
        self.division.periods = 4
        self.division.period_minutes = 10
        self.division.break_minutes = 2
        self.division.save()
        finals = factories.StageFactory.create(
            division=self.division, half_time_minutes=10
        )
        final = factories.MatchFactory.create(
            stage=finals, play_at=self.field1, datetime=at(21), date=DAY
        )
        decider = factories.MatchFactory.create(
            stage=finals,
            play_at=self.field1,
            datetime=at(22),
            date=DAY,
            half_time_minutes=15,
        )
        self.assertEqual(
            [
                scoreboard.clock_for(match, self.field1).half
                for match in (self.first, final, decider)
            ],
            # Nothing says: half time is as long as any other break.
            [None, 600, 900],
        )

    def test_stage_or_match_may_name_its_periods_for_itself(self):
        self.division.period_name = "Chukka"
        self.division.save()
        finals = factories.StageFactory.create(division=self.division)
        final = factories.MatchFactory.create(
            stage=finals,
            play_at=self.field1,
            datetime=at(21),
            date=DAY,
            period_name="Round",
        )
        self.first.refresh_from_db()
        self.assertEqual(
            [
                scoreboard.clock_for(match, self.field1).names[0]
                for match in (self.first, final)
            ],
            ["1st Chukka", "1st Round"],
        )

    def test_stage_may_give_a_clock_to_a_division_that_has_none(self):
        self.division.period_minutes = None
        self.division.save()
        self.stage.period_minutes = 10
        self.stage.save()
        self.first.refresh_from_db()
        self.assertEqual(scoreboard.clock_for(self.first, self.field1).period, 600)

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
            '<div class="sb-label" id="sb-label">1st Half</div>',
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
            'data-periods="2" data-period="900" data-pause="120" '
            'data-names="[&quot;1st Half&quot;, &quot;Half time&quot;, '
            '&quot;2nd Half&quot;]" data-phases="[[&quot;period&quot;, 900], '
            '[&quot;break&quot;, 120], [&quot;period&quot;, 900]]">',
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
            f'<main id="board" class="sb-board" data-template="default" '
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

    def test_match_of_one_period_shows_no_name_and_no_dots(self):
        self.division.periods = 1
        self.division.save()
        self.get("compops:scoreboard", **self.kw)
        content = self.last_response.content.decode()
        self.assertResponseContains('<div class="sb-label" id="sb-label"></div>')
        self.assertResponseContains('<div class="sb-time" id="sb-time">10:00</div>')
        self.assertEqual(content.count('id="sb-dots"'), 0)

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
            f'<a class="btn" href="{self.reverse("compops:scoreboard-overlay", **self.kw)}">'
            "Overlay</a>"
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


@freeze_time("2026-10-08 19:00:30 +10:00")
class TimekeeperTests(ScoreboardFixture):
    """A venue's clocks are started together, by one press."""

    def setUp(self):
        super().setUp()
        self.venue.slug = "the-park"
        self.venue.slug_locked = True
        self.venue.scoreboard_auto_start = False
        self.venue.save()
        self.field2 = factories.GroundFactory.create(
            venue=self.venue, title="Field 2", slug="field-2", slug_locked=True
        )
        self.other = self.match(19, self.fji, self.nzl, ground=self.field2)
        self.venue_kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "venue": "the-park",
        }

    def start_url(self, hour):
        return self.reverse(
            "compops:timekeeper-start",
            kick_off=int(at(hour).timestamp()),
            **self.venue_kw,
        )

    def start(self, hour=19):
        with (
            self.login(self.scorer),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.post(self.start_url(hour))

    def started(self):
        return [
            Match.objects.get(pk=match.pk).clock_started_at
            for match in (self.first, self.other, self.second)
        ]

    def test_timekeeper_needs_a_login_and_the_right_to_score(self):
        self.assertLoginRequired("compops:timekeeper", **self.venue_kw)
        with self.login(self.outsider):
            self.get("compops:timekeeper", **self.venue_kw)
            self.assert_http_403_forbidden()
            self.post(self.start_url(19))
            self.assert_http_403_forbidden()
        self.assertEqual(self.started(), [None, None, None])

    def test_page_has_the_round_being_played_and_the_next_each_with_a_button(self):
        with self.login(self.scorer):
            self.get_check_200("compops:timekeeper", **self.venue_kw)
        self.assertResponseContains("<h1>Timekeeper · %s</h1>" % self.venue.title)
        content = self.last_response.content.decode()
        self.assertEqual(
            [
                content.count(f'<form method="post" action="{self.start_url(hour)}">')
                for hour in (19, 20)
            ],
            [1, 1],
        )
        self.assertResponseContains(
            '<button class="btn p" type="submit">Start 2 clocks</button>'
        )
        self.assertResponseContains(
            '<button class="btn p" type="submit">Start 1 clock</button>'
        )

    def test_one_press_starts_every_field_of_the_round_at_one_moment(self):
        self.start()
        self.assert_http_302_found(
            url=self.reverse("compops:timekeeper", **self.venue_kw)
        )
        now = at(19, 0, 30)
        # The round that follows waits for its own press.
        self.assertEqual(self.started(), [now, now, None])
        (event,) = events.get_backend().recent(
            events.channel(self.season.pk, scoreboard.SCOPE)
        )
        self.assertEqual(
            (event["type"], event["venue"], event["actor"]),
            ("scoreboard-changed", self.venue.pk, self.scorer.get_username()),
        )
        # Its button has gone, and a second press changes nothing.
        with freeze_time("2026-10-08 19:02 +10:00"):
            self.start()
            with self.login(self.scorer):
                self.get_check_200("compops:timekeeper", **self.venue_kw)
        self.assertEqual(self.started(), [now, now, None])
        self.assertEqual(
            self.last_response.content.decode().count(self.start_url(19)), 0
        )

    def test_clock_a_scorer_has_started_keeps_its_own_start(self):
        Match.objects.filter(pk=self.first.pk).update(clock_started_at=at(18, 59))
        self.start()
        self.assertEqual(self.started(), [at(18, 59), at(19, 0, 30), None])

    def test_venue_whose_clocks_start_on_time_has_nothing_to_start(self):
        self.venue.scoreboard_auto_start = True
        self.venue.save()
        with self.login(self.scorer):
            self.get_check_200("compops:timekeeper", **self.venue_kw)
        self.assertEqual(self.last_response.content.count(b"<button"), 0)
        self.start()
        self.assertEqual(self.started(), [None, None, None])

    def test_round_that_is_not_in_hand_is_404(self):
        with self.login(self.scorer):
            self.post(self.start_url(23))
        self.assert_http_404_not_found()

    def test_list_of_scoreboards_leads_a_scorer_to_each_venues_timekeeper(self):
        url = self.reverse("compops:timekeeper", **self.venue_kw)
        season = {"competition": "pacific-cup", "season": "pc26"}
        for user, count in ((self.scorer, 1), (self.outsider, 0)):
            with self.subTest(user=user), self.login(user):
                self.get_check_200("compops:scoreboard-index", **season)
                self.assertEqual(
                    self.last_response.content.decode().count(f'href="{url}"'), count
                )


class SettingsFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)
        cls.streamed = factories.MatchFactory.create(
            stage__division__season__live_stream=True, label="Final", round=3
        )

    def test_division_form_has_the_timing_of_its_matches(self):
        fields = DivisionForm(instance=factories.DivisionFactory.create()).fields
        self.assertEqual(
            [
                name
                for name in fields
                if "period" in name or "break" in name or "half" in name
            ],
            [
                "periods",
                "period_minutes",
                "break_minutes",
                "half_time_minutes",
                "period_name",
            ],
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

    def test_division_page_shows_the_timing_without_unfolding_anything(self):
        # A new division has no clock until its period length is set, so the
        # Workbook does not tuck the timing away with the rarely used fields.
        division = factories.DivisionFactory.create()
        superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)
        with self.login(superuser):
            self.get_check_200(division.urls["edit"])
        content = self.last_response.content.decode()
        field = content.index('name="period_minutes"')
        self.assertEqual(
            by_shell(
                workbook=(
                    content.count('<h3 class="wb-group-title">Match timing'),
                    field < content.index('<details class="wb-group wb-group-folded"'),
                ),
                explorer=(1, True),
            ),
            (1, True),
        )

    def test_stage_and_match_forms_have_a_timing_of_their_own(self):
        timing = [
            "periods",
            "period_minutes",
            "break_minutes",
            "half_time_minutes",
            "period_name",
        ]
        match = factories.MatchFactory.create()
        for form in (
            StageForm(instance=match.stage),
            MatchEditForm(instance=match),
            MatchStreamForm(instance=self.streamed),
        ):
            with self.subTest(type(form).__name__):
                self.assertEqual(
                    (
                        [name for name in form.fields if name in timing],
                        [form.fields[name].required for name in timing],
                    ),
                    (timing, [False, False, False, False, False]),
                )

    def test_stream_form_has_every_field_of_the_edit_form_but_the_videos(self):
        # A live streamed season trades the video links for the broadcast.
        self.assertEqual(
            (
                [
                    name
                    for name in MatchEditForm.base_fields
                    if name not in MatchStreamForm.base_fields
                ],
                [
                    name
                    for name in MatchStreamForm.base_fields
                    if name not in MatchEditForm.base_fields
                ],
            ),
            (["videos"], ["live_stream"]),
        )

    def test_match_page_of_a_live_streamed_season_shows_the_timing(self):
        css, help_id = by_shell(
            workbook=('class="wb-input" ', "id_period_minutes_help"),
            explorer=("", "id_period_minutes_helptext"),
        )
        with self.login(self.superuser):
            self.get_check_200(self.streamed.urls["edit"])
        self.assertResponseContains(
            f'<input type="number" name="period_minutes" min="0" {css}'
            f'aria-describedby="{help_id}" id="id_period_minutes">'
        )

    def test_match_of_a_live_streamed_season_is_given_its_own_timing(self):
        match = self.streamed
        edit = match.url_names["edit"]
        data = {
            "home_team": match.home_team.pk,
            "away_team": match.away_team.pk,
            "label": match.label,
            "round": match.round,
            "date": match.date.isoformat(),
            "include_in_ladder": "1" if match.include_in_ladder else "0",
            "periods": "2",
            "period_minutes": "25",
            "break_minutes": "",
            "half_time_minutes": "10",
            "period_name": "Half",
            "live_stream": "0",
            "live_stream_thumbnail_image": "",
        }
        with self.login(self.superuser):
            self.post(edit.url_name, *edit.args, data=data)
        self.assert_http_302_found(url=match.stage.urls["edit"])
        match.refresh_from_db()
        self.assertEqual(
            (
                match.periods,
                match.period_minutes,
                match.break_minutes,
                match.half_time_minutes,
                match.period_name,
            ),
            (2, 25, None, 10, "Half"),
        )

    def test_venue_form_has_whether_its_clocks_start_on_time(self):
        form = VenueForm(instance=factories.VenueFactory.create())
        self.assertEqual(
            (
                "scoreboard_auto_start" in form.fields,
                form.initial["scoreboard_auto_start"],
            ),
            (True, True),
        )


#: The worked example of the docs, which a designer starts from.
EXAMPLE = Path(__file__).parents[3] / "docs" / "examples" / "scoreboard-split.html"

CUSTOM = (
    "<!doctype html><html><head><title>{{ ground.title }}</title>"
    '{{ styles }}{{ scripts }}</head><body class="mine {{ variant }}" {{ attrs }}>'
    '<h1 class="mine">{{ season.title }}</h1>'
    "{% board %}"
    '<b id="sb-home-score">{{ home.name }} {{ home.score }}</b>'
    '<b id="sb-away-score">{{ away.name }} {{ away.score }}</b>'
    '<div {{ clock_attrs }}><i id="sb-label">{{ moment.label }}</i>'
    '<i id="sb-time">{{ moment.display }}</i></div>'
    "{% endboard %}</body></html>"
)


@freeze_time("2026-10-08 19:05 +10:00")
class CustomTemplateTests(ScoreboardFixture):
    """A whole scoreboard page, written in the admin for a scope."""

    def write(self, owner, source=CUSTOM):
        owner.scoreboard_template = source
        owner.save()

    def test_nearest_scope_to_the_match_has_its_template_used(self):
        competition = self.season.competition
        owners = [self.stage, self.division, self.season, competition]
        used = []
        for owner in owners:
            self.write(owner, f"{CUSTOM}<!-- {type(owner).__name__} -->")
        for owner in owners:
            self.first.refresh_from_db()
            self.season.refresh_from_db()
            key, source = scoreboard.template_for(self.season, self.first)
            used.append((key.rsplit(":", 1)[0], source.rsplit(" ", 2)[1]))
            # The next out is used once this one is emptied.
            self.write(owner, "  ")
        self.first.refresh_from_db()
        self.season.refresh_from_db()
        self.assertEqual(
            (used, scoreboard.template_for(self.season, self.first)),
            (
                [
                    (f"stage:{self.stage.pk}", "Stage"),
                    (f"division:{self.division.pk}", "Division"),
                    (f"season:{self.season.pk}", "Season"),
                    (f"competition:{competition.pk}", "Competition"),
                ],
                (None, None),
            ),
        )

    def test_ground_with_no_match_today_takes_the_seasons_template(self):
        self.write(self.division)
        self.write(self.season, f"{CUSTOM}<!-- Season -->")
        key, source = scoreboard.template_for(self.season, None)
        self.assertEqual(
            (key.rsplit(":", 1)[0], source.endswith("<!-- Season -->")),
            (f"season:{self.season.pk}", True),
        )

    def test_page_is_drawn_by_the_template(self):
        self.write(self.division)
        self.get("compops:scoreboard", **self.kw)
        self.assert_http_200_ok()
        content = self.last_response.content.decode()
        key, _ = scoreboard.template_for(self.season, self.first)
        board_url = self.reverse("compops:scoreboard-board", **self.kw)
        events_url = self.reverse("compops:scoreboard-events", **self.kw)
        start = int(at(19).timestamp() * 1000)
        now = int(at(19, 5).timestamp() * 1000)
        for piece in (
            f'<h1 class="mine">{self.season.title}</h1>',
            # The part the live updates replace, and which template drew it.
            f'<div id="board" data-template="{key}" '
            f"data-on-interval__duration.20s=\"@get('{board_url}')\">"
            '<b id="sb-home-score">Australia 0</b>',
            # What the page's script counts the clock from.
            f'<div id="sb-clock" data-match="{self.first.pk}" data-now="{now}" '
            f'data-start="{start}" data-periods="2" data-period="900" '
            'data-pause="120" data-names="[&quot;1st Half&quot;, &quot;Half time&quot;, '
            '&quot;2nd Half&quot;]" data-phases="[[&quot;period&quot;, 900], '
            '[&quot;break&quot;, 120], [&quot;period&quot;, 900]]">'
            '<i id="sb-label">1st Half</i>'
            '<i id="sb-time">10:00</i></div>',
            # What every scoreboard page needs, whatever it looks like.
            'class="mine display" data-signals__ifmissing="{board: \'display\'}" '
            'data-indicator="connected" '
            f"data-effect=\"@get('{events_url}', {{retryMaxCount: 1000}})\"",
            '<script src="/static/tournamentcontrol/competition/compops/scoreboard.js">'
            "</script>",
        ):
            with self.subTest(piece[:40]):
                self.assertIn(piece, content)
        # None of the usual page is there.
        self.assertEqual(content.count("sb-brand"), 0)

    def test_overlay_is_drawn_by_the_same_template(self):
        self.write(self.division)
        self.get("compops:scoreboard-overlay", **self.kw)
        self.assertIn('class="mine overlay"', self.last_response.content.decode())

    def test_live_update_is_the_templates_board_alone(self):
        self.write(self.division)
        self.get("compops:scoreboard-board", **self.kw)
        content = self.last_response.content.decode()
        self.assertEqual(
            (
                content.startswith('<div id="board" data-template="division:'),
                content.endswith("</div></div>"),
                content.count("<html"),
            ),
            (True, True, 0),
        )

    def test_template_is_given_plain_values_and_nothing_to_follow(self):
        # A season holds its YouTube secrets; a template could follow an
        # object to them, so it is never given one.
        self.season.live_stream_client_secret = "hush"
        self.season.live_stream_refresh_token = "hush"
        self.write(
            self.season,
            "{% board %}[{{ season.live_stream_client_secret }}]"
            "[{{ season.live_stream_refresh_token }}][{{ season.competition }}]"
            "[{{ request }}][{{ user }}][{{ home.team }}][{{ match.division }}]"
            "{% endboard %}",
        )
        self.get("compops:scoreboard", **self.kw)
        content = self.last_response.content.decode()
        self.assertEqual(content.count("hush"), 0)
        self.assertIn("[][][][][][][Men&#x27;s Open]", content)

    def test_usual_board_says_it_was_drawn_by_the_usual_template(self):
        self.get("compops:scoreboard", **self.kw)
        self.assertIn(
            '<main id="board" class="sb-board" data-template="default"',
            self.last_response.content.decode(),
        )

    def test_key_changes_when_the_template_is_edited(self):
        self.write(self.division)
        before, _ = scoreboard.template_for(self.season, self.first)
        self.write(self.division, CUSTOM.replace("mine", "ours"))
        self.first.refresh_from_db()
        after, _ = scoreboard.template_for(self.season, self.first)
        self.assertEqual(
            (before.rsplit(":", 1)[0], after.rsplit(":", 1)[0], before == after),
            (f"division:{self.division.pk}",) * 2 + (False,),
        )


class TemplateCheckTests(TestCase):
    def test_template_must_draw_a_board_and_reach_for_nothing_else(self):
        cases = {
            "nothing written": ("", None),
            "a page with a board": (CUSTOM, None),
            "no board": (
                "<p>{{ home.score }}</p>",
                "Put {% board %} and {% endboard %} around the part that changes "
                "while a match is played: the live updates replace what is "
                "between them.",
            ),
            "another tag library": (
                "{% load static %}{% board %}{% endboard %}",
                "This is not a template: 'static' is not a registered tag library. "
                "Must be one of:\n",
            ),
            "another template": (
                '{% board %}{% include "base.html" %}{% endboard %}',
                "A scoreboard template cannot include or extend another "
                "template (base.html).",
            ),
            "a tag left open": (
                "{% board %}{% if home %}",
                "This is not a template: Unclosed tag on line 1: 'if'. "
                "Looking for one of: elif, else, endif.",
            ),
        }
        for name, (source, problem) in cases.items():
            with self.subTest(name):
                self.assertEqual(scoreboard.check_template(source), problem)

    def test_example_in_the_docs_is_a_template_that_draws_a_board(self):
        self.assertEqual(scoreboard.check_template(EXAMPLE.read_text()), None)

    def test_each_scopes_form_takes_a_template_and_refuses_a_bad_one(self):
        match = factories.MatchFactory.create()
        stage = match.stage
        season = stage.division.season
        forms = {
            "competition": CompetitionForm(instance=season.competition),
            "season": SeasonForm(instance=season),
            "division": DivisionForm(instance=stage.division),
            "stage": StageForm(instance=stage),
        }
        for name, form in forms.items():
            with self.subTest(name):
                form.cleaned_data = {"scoreboard_template": "<p>No board</p>"}
                with self.assertRaisesMessage(ValidationError, "Put {% board %}"):
                    form.clean_scoreboard_template()
                form.cleaned_data = {"scoreboard_template": CUSTOM}
                self.assertEqual(form.clean_scoreboard_template(), CUSTOM)


class FrontDoorTests(ScoreboardFixture):
    """``score_season`` alone finds the season's scoreboards from the front door."""

    def row(self, name, season=None):
        season = season or self.season
        url = reverse(
            f"compops:{name}",
            kwargs={"competition": season.competition.slug, "season": season.slug},
        )
        return (
            f'<a class="item" href="{url}">'
            f'<span class="title">{season.title}</span>'
            f'<span class="comp">{season.competition.title}</span>'
            '<span class="when">8 Oct 2026</span></a>'
        )

    def scoreboards_button(self):
        url = reverse(
            "compops:scoreboard-index",
            kwargs={"competition": "pacific-cup", "season": "pc26"},
        )
        return f'<a class="btn" href="{url}">Scoreboards</a>'

    @freeze_time(at(12))
    def test_front_door_leads_a_scorer_to_the_scoreboards_they_may_keep(self):
        # Played the same day, with no permission on it.
        closed = factories.MatchFactory.create(date=DAY).stage.division.season
        with self.login(self.scorer):
            self.get("compops:index")
        self.assert_http_200_ok()
        self.assertResponseContains("<h1>Scoreboards</h1>")
        self.assertResponseContains(self.row("scoreboard-index"))
        content = self.last_response.content.decode()
        self.assertEqual(
            (
                content.count(self.row("scoreboard-index", closed)),
                content.count(self.scoreboards_button()),
                content.count("All events"),
            ),
            (0, 0, 0),
        )

    @freeze_time(at(12))
    def test_front_door_leads_to_the_booths_and_the_scoreboards_of_who_has_both(self):
        assign_perm("competition.commentate_season", self.scorer, self.season)
        with self.login(self.scorer):
            self.get("compops:index")
        self.assertResponseContains("<h1>Events</h1>")
        self.assertResponseContains(self.row("booth-index"))
        self.assertResponseContains(self.scoreboards_button())

    def test_front_door_is_closed_to_someone_with_no_season(self):
        with self.login(self.outsider):
            self.get("compops:index")
        self.assert_http_403_forbidden()

    def test_list_of_scoreboards_offers_the_scorer_only_to_who_may_score(self):
        url = self.reverse("compops:scorer", **self.kw)
        link = f'<a class="btn" href="{url}">Scorer</a>'
        season = {"competition": "pacific-cup", "season": "pc26"}
        for user, count in ((self.scorer, 1), (self.outsider, 0)):
            with self.subTest(user=user), self.login(user):
                self.get_check_200("compops:scoreboard-index", **season)
                self.assertEqual(self.last_response.content.decode().count(link), count)
        self.get_check_200("compops:scoreboard-index", **season)
        self.assertEqual(self.last_response.content.decode().count(link), 0)
