from unittest import mock

from django.contrib.auth.models import Permission
from test_plus import TestCase

from tournamentcontrol.competition.exceptions import LiveStreamTransitionWarning
from tournamentcontrol.competition.forms import MatchStatisticFormset
from tournamentcontrol.competition.models import SimpleScoreMatchStatistic
from tournamentcontrol.competition.signals.custom import statistics_updated
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import FauxQueryset

YOUTUBE_SEASON = dict(
    live_stream=True,
    live_stream_project_id="p",
    live_stream_client_id="c.apps.googleusercontent.com",
    live_stream_client_secret="s",
    live_stream_token="t",
    live_stream_refresh_token="r",
    live_stream_token_uri="https://oauth2.googleapis.com/token",
    live_stream_scopes=["https://www.googleapis.com/auth/youtube"],
)


def youtube_mock(current_status=None):
    service = mock.Mock()
    items = [{"status": {"lifeCycleStatus": current_status}}] if current_status else []
    service.liveBroadcasts.return_value.list.return_value.execute.return_value = {
        "items": items
    }
    service.liveBroadcasts.return_value.transition.return_value.execute.return_value = {}
    return service


class MatchTransitionTests(TestCase):
    def setUp(self):
        self.season = factories.SeasonFactory.create(**YOUTUBE_SEASON)
        self.match = factories.MatchFactory.create(
            stage__division__season=self.season, external_identifier="yt1"
        )

    def test_transition_stores_status_and_time(self):
        self.match.transition_live_stream("live", youtube_mock("testing"))
        self.match.refresh_from_db()
        self.assertEqual(self.match.live_stream_status, "live")
        self.assertIsNotNone(self.match.live_stream_status_at)

    def test_failed_transition_leaves_status_untouched(self):
        service = youtube_mock("testing")
        service.liveBroadcasts.return_value.transition.return_value.execute.side_effect = (
            RuntimeError("boom")
        )
        with self.assertRaises(RuntimeError):
            self.match.transition_live_stream("live", service)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.live_stream_status)

    def test_transition_does_not_rebuild_ladder_entries(self):
        match = factories.MatchFactory.create(
            stage__division__season=self.season,
            external_identifier="yt2",
            home_team_score=2,
            away_team_score=1,
        )
        before = set(match.ladder_entries.values_list("pk", flat=True))
        self.assertEqual(len(before), 2)

        match.transition_live_stream("live", youtube_mock("testing"))

        match.refresh_from_db()
        self.assertEqual(match.live_stream_status, "live")
        self.assertEqual(
            set(match.ladder_entries.values_list("pk", flat=True)), before
        )


class LiveStreamEventTransitionTests(TestCase):
    def setUp(self):
        self.season = factories.SeasonFactory.create(**YOUTUBE_SEASON)
        self.event = factories.LiveStreamEventFactory.create(season=self.season)

    def test_event_transitions_like_a_match(self):
        service = youtube_mock("ready")
        with self.assertWarns(LiveStreamTransitionWarning):
            self.event.transition_live_stream("testing", service)
        service.liveBroadcasts.return_value.transition.assert_called_once_with(
            broadcastStatus="testing",
            id=self.event.external_identifier,
            part="snippet,status",
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_status, "testing")


class StreamSeasonPermissionTests(TestCase):
    def test_permission_exists(self):
        self.assertTrue(
            Permission.objects.filter(
                content_type__app_label="competition", codename="stream_season"
            ).exists()
        )


class StatisticsUpdatedSignalTests(TestCase):
    def test_formset_save_sends_signal(self):
        match = factories.MatchFactory.create(home_team_score=1, away_team_score=0)
        player = factories.PersonFactory.create()
        factories.TeamAssociationFactory.create(
            team=match.home_team, person=player, number=7
        )
        queryset = FauxQueryset(SimpleScoreMatchStatistic, team=match.home_team)
        queryset.append(
            SimpleScoreMatchStatistic(match=match, player=player, number=7, played=1)
        )
        data = {
            "home-TOTAL_FORMS": "1",
            "home-INITIAL_FORMS": "1",
            "home-MIN_NUM_FORMS": "0",
            "home-MAX_NUM_FORMS": "1000",
            "home-0-played": "1",
            "home-0-number": "7",
            "home-0-points": "1",
            "home-0-mvp": "",
        }
        formset = MatchStatisticFormset(
            match.home_team_score, data=data, prefix="home", queryset=queryset
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        received = []

        def receiver(sender, match, **kwargs):
            received.append(match)

        # Signal receivers are weakly referenced by default, which would let
        # the receiver be collected before the formset is saved.
        statistics_updated.connect(receiver, weak=False)
        self.addCleanup(statistics_updated.disconnect, receiver)
        formset.save()
        self.assertEqual(received, [match])
