"""
The event log of a match: what happened, recorded as it happened. The
progress scores the scoreboards read are a running total of its live score
events, kept in the same transaction.
"""

import datetime
import threading
from zoneinfo import ZoneInfo

from django.db import IntegrityError, connection, transaction
from django.db.models.signals import post_save
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from tournamentcontrol.competition.compops.scoreboard import Clock
from tournamentcontrol.competition.models import LadderEntry, Match, MatchEvent
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")


def at(hour, minute=0, second=0):
    return timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute, second), TZ)


def make_match(**kwargs):
    return factories.MatchFactory.create(datetime=at(19), date=at(19).date(), **kwargs)


class MatchEventTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.match = make_match()
        cls.scorer = factories.UserFactory.create()
        cls.person = factories.PersonFactory.create()

    def score(self, side, **kwargs):
        return self.match.record_event(
            MatchEvent.Kind.SCORE, side, recorded_by=self.scorer, **kwargs
        )

    def progress(self):
        self.match.refresh_from_db()
        return (
            self.match.home_team_progress_score,
            self.match.away_team_progress_score,
        )

    def test_score_is_recorded_and_added_to_the_progress_score(self):
        with freeze_time(at(19, 5)):
            event = self.score("home", player=self.person)
        self.assertEqual(
            (
                event.match,
                event.kind,
                event.side,
                event.points,
                event.player,
                event.recorded_by,
                event.recorded_at,
                event.reverses,
            ),
            (self.match, "score", "home", 1, self.person, self.scorer, at(19, 5), None),
        )
        self.assertEqual(self.progress(), (1, None))

    def test_events_are_in_the_order_they_were_recorded(self):
        with freeze_time(at(19, 5)) as frozen:
            first = self.score("home")
            # Two in the same instant are in the order they were written.
            second = self.score("away")
            frozen.tick(60)
            third = self.score("home")
        self.assertEqual(list(self.match.events.all()), [first, second, third])

    def test_take_back_reverses_the_sides_latest_live_score(self):
        first = self.score("home")
        latest = self.score("home")
        self.score("away")
        correction = self.match.take_back_score("home", recorded_by=self.scorer)
        self.assertEqual(
            (correction.kind, correction.side, correction.reverses),
            ("correction", "home", latest),
        )
        self.assertEqual(self.progress(), (1, 1))
        # The next goes back one more, and nothing is left to take back.
        second = self.match.take_back_score("home", recorded_by=self.scorer)
        self.assertEqual(second.reverses, first)
        self.assertEqual(self.progress(), (0, 1))
        self.assertEqual(self.match.take_back_score("home"), None)
        self.assertEqual(self.progress(), (0, 1))

    def test_live_events_are_neither_corrections_nor_reversed(self):
        start = self.match.record_event(MatchEvent.Kind.START)
        reversed_score = self.score("home")
        kept = self.score("away")
        self.match.take_back_score("home")
        self.assertCountEqual(self.match.events.live(), [start, kept])
        self.assertEqual(reversed_score.is_reversed, True)
        self.assertEqual(kept.is_reversed, False)

    def test_score_kept_before_the_log_is_taken_off_without_an_event(self):
        Match.objects.filter(pk=self.match.pk).update(home_team_progress_score=3)
        self.assertEqual(self.match.take_back_score("home"), None)
        self.assertEqual(self.progress(), (2, None))
        self.assertEqual(self.match.events.count(), 0)

    def test_progress_scores_agree_with_the_events_and_can_be_recounted(self):
        for side in ("home", "home", "away", "home"):
            self.score(side)
        self.match.take_back_score("home")
        self.assertEqual(self.match.events.totals(), {"home": 2, "away": 1})
        self.assertEqual(self.progress(), (2, 1))
        Match.objects.filter(pk=self.match.pk).update(
            home_team_progress_score=9, away_team_progress_score=None
        )
        self.match.recount_progress_scores()
        self.assertEqual(self.progress(), (2, 1))

    def test_recording_locks_the_match(self):
        with CaptureQueriesContext(connection) as queries:
            self.score("home")
            self.match.take_back_score("home")
        locks = [q["sql"] for q in queries if q["sql"].endswith("FOR UPDATE")]
        self.assertEqual(len(locks), 2)

    def test_clock_says_where_the_period_was(self):
        clock = Clock(start=at(19), periods=2, period=900, pause=120)
        event = self.score("home", moment=clock.at(at(19, 5, 30)))
        self.assertEqual((event.period, event.remaining), (1, 570))
        # In a break, before the start, or with no clock, there is no period.
        for moment in (clock.at(at(19, 15, 30)), clock.at(at(18, 59)), None):
            with self.subTest(moment=moment):
                event = self.score("away", moment=moment)
                self.assertEqual((event.period, event.remaining), (None, None))

    def test_correction_must_reverse_an_event_and_only_a_correction_may(self):
        score = self.score("home")
        cases = (
            {"kind": MatchEvent.Kind.CORRECTION},
            {"kind": MatchEvent.Kind.SCORE, "reverses": score},
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    MatchEvent.objects.create(match=self.match, side="home", **case)

    def test_an_event_is_reversed_once(self):
        score = self.score("home")
        self.match.reverse_event(score)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MatchEvent.objects.create(
                match=self.match, kind=MatchEvent.Kind.CORRECTION, reverses=score
            )

    def test_events_never_save_the_match(self):
        # The ladders are worked out when a match is saved (see apps.py);
        # the log must never set that off.
        saved = []

        def receiver(sender, instance, **kwargs):
            saved.append(instance.pk)

        post_save.connect(receiver, sender=Match)
        self.addCleanup(post_save.disconnect, receiver, sender=Match)
        ladders = LadderEntry.objects.count()
        self.match.record_event(MatchEvent.Kind.START)
        self.score("home")
        self.match.take_back_score("home")
        self.match.take_back_score("home")
        self.match.recount_progress_scores()
        self.assertEqual((saved, LadderEntry.objects.count()), ([], ladders))


class InProgressTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.waiting = make_match()
        cls.started = make_match()
        cls.started.record_event(MatchEvent.Kind.START)
        cls.scoring = make_match()
        cls.scoring.record_event(MatchEvent.Kind.SCORE, "home")
        cls.clocked = make_match(clock_started_at=at(19))
        cls.taken_back = make_match()
        cls.taken_back.record_event(MatchEvent.Kind.SCORE, "away")
        cls.taken_back.take_back_score("away")
        cls.finished = make_match(home_team_score=3, away_team_score=2)
        cls.finished.record_event(MatchEvent.Kind.START)
        cls.forfeited = make_match(is_forfeit=True, clock_started_at=at(19))
        cls.washed_out = make_match(is_washout=True, clock_started_at=at(19))
        cls.bye = make_match(is_bye=True, clock_started_at=at(19))

    def test_in_progress_has_started_and_has_no_result(self):
        self.assertCountEqual(
            Match.objects.in_progress(), [self.started, self.scoring, self.clocked]
        )

    def test_each_match_says_whether_it_is_in_progress(self):
        expected = {
            self.waiting: False,
            self.started: True,
            self.scoring: True,
            self.clocked: True,
            self.taken_back: False,
            self.finished: False,
            self.forfeited: False,
            self.washed_out: False,
            self.bye: False,
        }
        self.assertEqual({match: match.in_progress for match in expected}, expected)


class ConcurrentScorerTests(TransactionTestCase):
    """Two scorers of one match press at the same moment."""

    def setUp(self):
        self.match = make_match()

    def together(self, *presses):
        barrier = threading.Barrier(len(presses))
        errors = []

        def press(action):
            try:
                barrier.wait()
                action(Match.objects.get(pk=self.match.pk))
            except Exception as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=press, args=(p,)) for p in presses]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])

    def test_two_scores_at_once_both_count(self):
        self.together(*[lambda m: m.record_event(MatchEvent.Kind.SCORE, "home")] * 2)
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_team_progress_score, 2)
        self.assertEqual(self.match.events.totals(), {"home": 2, "away": 0})

    def test_two_take_backs_at_once_reverse_two_scores(self):
        self.match.record_event(MatchEvent.Kind.SCORE, "home")
        self.match.record_event(MatchEvent.Kind.SCORE, "home")
        self.together(*[lambda m: m.take_back_score("home")] * 2)
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_team_progress_score, 0)
        self.assertEqual(self.match.events.live().count(), 0)
