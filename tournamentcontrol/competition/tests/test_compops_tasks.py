import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.db.models.signals import post_save
from django.utils import timezone
from freezegun import freeze_time
from google.auth.exceptions import RefreshError
from test_plus import TestCase

from tournamentcontrol.competition.compops import events, status
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tasks import refresh_all_live_stream_status
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
)

TZ = ZoneInfo("Australia/Brisbane")


def listing(**statuses):
    service = mock.Mock()
    service.liveBroadcasts.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": k, "status": {"lifeCycleStatus": v}} for k, v in statuses.items()
        ]
    }
    return service


@freeze_time("2026-10-08 10:50 +10:00")
class RefreshStatusTests(TestCase):
    def setUp(self):
        events.reset_backend()
        self.season = factories.SeasonFactory.create(
            timezone="Australia/Brisbane", **YOUTUBE_SEASON
        )
        stage = factories.StageFactory.create(division__season=self.season)
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 10, 40), TZ)
        self.match = factories.MatchFactory.create(
            stage=stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            external_identifier="yt1",
            live_stream_status="testing",
        )
        self.event = factories.LiveStreamEventFactory.create(
            season=self.season, start=when, external_identifier="ev1"
        )
        factories.MatchFactory.create(
            stage=stage,
            date=datetime.date(2026, 10, 9),
            external_identifier="tomorrow",
        )

    def test_only_today_with_identifiers(self):
        ids = [
            o.external_identifier
            for o in status.broadcasts_today(self.season, timezone.now())
        ]
        self.assertCountEqual(ids, ["yt1", "ev1"])

    def test_changed_status_is_stored_and_published(self):
        service = listing(yt1="live", ev1="ready")
        with self.captureOnCommitCallbacks(execute=True):
            changed = status.refresh_season_status(self.season, youtube=service)
        self.assertEqual(changed, 2)
        self.match.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(self.match.live_stream_status, "live")
        self.assertEqual(self.event.live_stream_status, "ready")
        published = events.recent(self.season.pk)
        self.assertEqual({e["actor"] for e in published}, {"youtube"})
        service.liveBroadcasts.return_value.list.assert_called_once_with(
            part="status", id="yt1,ev1", maxResults=50
        )

    def test_refresh_does_not_send_match_post_save(self):
        receiver = mock.Mock()
        post_save.connect(receiver, sender=Match, weak=False)
        self.addCleanup(post_save.disconnect, receiver, sender=Match)
        with self.captureOnCommitCallbacks(execute=True):
            changed = status.refresh_season_status(
                self.season, youtube=listing(yt1="live")
            )
        self.assertEqual(changed, 1)
        receiver.assert_not_called()

    def test_unchanged_status_publishes_nothing(self):
        service = listing(yt1="testing")
        with self.captureOnCommitCallbacks(execute=True):
            changed = status.refresh_season_status(self.season, youtube=service)
        self.assertEqual(changed, 0)
        self.assertEqual(events.recent(self.season.pk), [])

    def test_no_broadcasts_makes_no_call(self):
        other = factories.SeasonFactory.create(
            timezone="Australia/Brisbane", **YOUTUBE_SEASON
        )
        service = listing()
        self.assertEqual(status.refresh_season_status(other, youtube=service), 0)
        service.liveBroadcasts.assert_not_called()

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_refresh_all_covers_live_stream_seasons_with_matches_today(self, build):
        build.return_value = listing(yt1="live")
        factories.SeasonFactory.create(live_stream=False)
        with self.captureOnCommitCallbacks(execute=True):
            refresh_all_live_stream_status()
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_stream_status, "live")

    def test_mid_transition_status_fits_the_column(self):
        with self.captureOnCommitCallbacks(execute=True):
            status.refresh_season_status(
                self.season, youtube=listing(yt1="liveStarting")
            )
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_stream_status, "liveStarting")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_refresh_all_isolates_a_failing_season(self, build):
        other = factories.SeasonFactory.create(
            timezone="Australia/Brisbane", **YOUTUBE_SEASON
        )
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 10, 40), TZ)
        other_match = factories.MatchFactory.create(
            stage=factories.StageFactory.create(division__season=other),
            datetime=when,
            date=when.date(),
            time=when.time(),
            external_identifier="yt2",
            live_stream_status="testing",
        )
        # Whichever season is refreshed first fails; the other must still run.
        build.side_effect = [RefreshError("expired"), listing(yt1="live", yt2="live")]
        with self.assertLogs("tournamentcontrol.competition.tasks", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                changed = refresh_all_live_stream_status()
        self.assertEqual(changed, 1)
        self.match.refresh_from_db()
        other_match.refresh_from_db()
        statuses = {self.match.live_stream_status, other_match.live_stream_status}
        self.assertEqual(statuses, {"testing", "live"})
