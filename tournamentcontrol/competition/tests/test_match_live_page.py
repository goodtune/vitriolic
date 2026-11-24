"""
The public match page while the match is being played: the live score,
marked as live and not as the result, and the chronology of its events,
kept up to date by an event stream from Tournament Ops when it is mounted.
"""

import datetime
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.utils import timezone
from test_plus import TestCase

from tournamentcontrol.competition.models import MatchEvent
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")
WHEN = timezone.make_aware(datetime.datetime(2026, 10, 8, 19), TZ)
DATASTAR_JS = "/static/tournamentcontrol/competition/compops/datastar-1.0.4.js"


class LiveFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.match = factories.MatchFactory.create(
            stage__division__season__slug="pc26",
            stage__division__season__slug_locked=True,
            stage__division__season__competition__slug="pacific-cup",
            stage__division__season__competition__slug_locked=True,
            home_team__title="Australia",
            away_team__title="New Zealand",
            datetime=WHEN,
            date=WHEN.date(),
            time=WHEN.time(),
        )
        cls.player = factories.TeamAssociationFactory.create(
            team=cls.match.home_team,
            is_player=True,
            person__first_name="Jo",
            person__last_name="Bloggs",
        ).person
        cls.scorer = factories.UserFactory.create(username="ground-scorer")
        division = cls.match.stage.division
        cls.args = (
            division.season.competition.slug,
            division.season.slug,
            division.slug,
            cls.match.pk,
        )

    def score(self, side, player=None, remaining=None):
        event = self.match.record_event(
            MatchEvent.Kind.SCORE, side, recorded_by=self.scorer, player=player
        )
        if remaining is not None:
            MatchEvent.objects.filter(pk=event.pk).update(period=1, remaining=remaining)
        return event

    def content(self):
        return self.last_response.content.decode()


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.live_urls")
class LivePageTests(LiveFixture):
    def test_match_in_progress_shows_the_live_score_and_its_events(self):
        self.score("home", player=self.player, remaining=754)
        self.score("away")
        self.get_check_200("competition:match", *self.args)
        self.assertResponseContains('<p class="live-flag">Live</p>')
        self.assertResponseContains(
            '<p class="live-score">'
            '<span class="team">Australia</span> <span class="points">1</span>'
            '<span class="dash">–</span>'
            '<span class="points">1</span> <span class="team">New Zealand</span>'
            "</p>"
        )
        self.assertResponseContains(
            '<li class="live-event score">'
            '<span class="clock">12:34 · P1</span> '
            '<span class="kind">Score</span> '
            '<span class="team">Australia</span> '
            '<span class="player">Jo Bloggs</span></li>'
        )
        self.assertResponseContains(
            '<li class="live-event score">'
            '<span class="clock"></span> '
            '<span class="kind">Score</span> '
            '<span class="team">New Zealand</span></li>'
        )
        # Nothing of who kept the score.
        self.assertNotIn("ground-scorer", self.content())

    def test_page_listens_to_tournament_ops_for_changes(self):
        self.score("home")
        self.get_check_200("competition:match", *self.args)
        stream = self.reverse(
            "compops:match-live",
            competition="pacific-cup",
            season="pc26",
            match_pk=self.match.pk,
        )
        content = self.content()
        self.assertIn(
            f'<div class="match-live-stream" data-effect="@get(\'{stream}\', '
            '{retryMaxCount: 1000})">',
            content,
        )
        self.assertIn(f'<script type="module" src="{DATASTAR_JS}"></script>', content)

    def test_match_not_in_progress_has_no_live_block(self):
        self.get_check_200("competition:match", *self.args)
        content = self.content()
        self.assertNotIn('id="match-live"', content)
        self.assertNotIn(DATASTAR_JS, content)

    def test_match_with_a_result_has_no_live_block(self):
        self.score("home")
        self.match.home_team_score, self.match.away_team_score = 1, 0
        self.match.save()
        self.get_check_200("competition:match", *self.args)
        self.assertNotIn('id="match-live"', self.content())


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class LivePageWithoutTournamentOpsTests(LiveFixture):
    """A project that does not mount Tournament Ops (it needs ASGI)."""

    def test_live_score_is_shown_from_the_server_with_no_stream(self):
        self.score("home", player=self.player)
        self.get_check_200("competition:match", *self.args)
        self.assertResponseContains('<p class="live-flag">Live</p>')
        content = self.content()
        self.assertIn('<section id="match-live" class="match-live"', content)
        self.assertNotIn("data-effect", content)
        self.assertNotIn(DATASTAR_JS, content)
