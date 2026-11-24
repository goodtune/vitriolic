"""
The scorer's page and the venue's timekeeper write the match's event log: a
score, a correction, a start. The scoreboard itself is tested in
``test_compops_scoreboard``.
"""

from freezegun import freeze_time

from tournamentcontrol.competition.models import Match, MatchEvent
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_compops_scoreboard import (
    ScoreboardFixture,
    at,
)


@freeze_time("2026-10-08 19:05 +10:00")
class ScorerEventTests(ScoreboardFixture):
    """The 19:00 match on Field 1: halves of 15 minutes, started on time."""

    def test_add_records_a_score_with_who_and_when(self):
        self.press("scorer-score", side="home", step="up")
        event = self.first.events.get()
        self.assertEqual(
            (
                event.kind,
                event.side,
                event.points,
                event.recorded_by,
                event.recorded_at,
                event.period,
                event.remaining,
            ),
            ("score", "home", 1, self.scorer, at(19, 5), 1, 600),
        )

    def test_take_off_reverses_the_sides_latest_score(self):
        self.press("scorer-score", side="home", step="up")
        self.press("scorer-score", side="away", step="up")
        self.press("scorer-score", side="home", step="up")
        latest = self.first.events.filter(side="home").last()
        self.press("scorer-score", side="home", step="down")
        correction = self.first.events.get(kind=MatchEvent.Kind.CORRECTION)
        self.assertEqual(
            (correction.reverses, correction.recorded_by), (latest, self.scorer)
        )
        self.first.refresh_from_db()
        self.assertEqual(
            (
                self.first.home_team_progress_score,
                self.first.away_team_progress_score,
            ),
            (1, 1),
        )
        self.assertEqual(self.first.events.totals(), {"home": 1, "away": 1})

    def test_score_kept_before_the_log_is_still_taken_off(self):
        Match.objects.filter(pk=self.first.pk).update(home_team_progress_score=2)
        self.press("scorer-score", side="home", step="down")
        self.first.refresh_from_db()
        self.assertEqual(self.first.home_team_progress_score, 1)
        self.assertEqual(self.first.events.count(), 0)


@freeze_time("2026-10-08 19:05 +10:00")
class StartEventTests(ScoreboardFixture):
    """A venue whose clocks are started by hand."""

    def setUp(self):
        super().setUp()
        self.venue.scoreboard_auto_start = False
        self.venue.save()

    def test_scorer_starting_the_clock_records_a_start_once(self):
        self.press("scorer-start")
        with freeze_time("2026-10-08 19:06 +10:00"):
            self.press("scorer-start")
        event = self.first.events.get()
        self.assertEqual(
            (
                event.kind,
                event.side,
                event.recorded_by,
                event.recorded_at,
                event.period,
                event.remaining,
            ),
            ("start", "", self.scorer, at(19, 5), 1, 900),
        )

    def test_timekeeper_records_a_start_for_each_clock_it_starts(self):
        self.venue.slug = "the-park"
        self.venue.slug_locked = True
        self.venue.save()
        field2 = factories.GroundFactory.create(venue=self.venue, title="Field 2")
        other = self.match(19, self.fji, self.nzl, ground=field2)
        # A clock the ground's scorer started keeps its start, and its event.
        self.press("scorer-start")
        url = self.reverse(
            "compops:timekeeper-start",
            competition="pacific-cup",
            season="pc26",
            venue="the-park",
            kick_off=int(at(19).timestamp()),
        )
        with self.login(self.scorer), self.captureOnCommitCallbacks(execute=True):
            self.post(url)
            self.post(url)
        self.assertEqual(
            {
                match: list(match.events.values_list("kind", "recorded_by"))
                for match in (self.first, other, self.second)
            },
            {
                self.first: [("start", self.scorer.pk)],
                other: [("start", self.scorer.pk)],
                self.second: [],
            },
        )
