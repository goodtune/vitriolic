"""
Every form on the Tournament Ops site, posted as a plain browser without
JavaScript does: no ``Datastar-Request`` header.

A valid post redirects (to the day or the booth) and persists; one that is
refused answers 200 with the whole page, or the modal, carrying the reason.
"""

import datetime
import re
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from freezegun import freeze_time
from google.auth.exceptions import RefreshError
from test_plus import TestCase

from tournamentcontrol.competition.models import SimpleScoreMatchStatistic
from tournamentcontrol.competition.ops import events, streams
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)

TZ = ZoneInfo("Australia/Brisbane")

DAY_TEMPLATE = "tournamentcontrol/ops/day.html"
BOOTH_TEMPLATE = "tournamentcontrol/ops/booth.html"
MODAL_TEMPLATE = "tournamentcontrol/ops/fragments/scorers_modal.html"
SCORERS_TEMPLATE = "tournamentcontrol/ops/scorers.html"


@freeze_time("2026-10-08 10:50 +10:00")
class FormsFixture(TestCase):
    def setUp(self):
        events.reset_backend()
        self.operator = factories.UserFactory.create(is_staff=True)
        self.operator.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "change_match",
                    "add_simplescorematchstatistic",
                    "change_simplescorematchstatistic",
                    "stream_season",
                ]
            )
        )
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
            statistics=True,
            **YOUTUBE_SEASON,
        )
        venue = factories.VenueFactory.create(season=self.season)
        self.field1 = factories.GroundFactory.create(
            venue=venue,
            title="Field 1",
            slug="field-1",
            slug_locked=True,
            live_stream=True,
        )
        self.division = factories.DivisionFactory.create(
            season=self.season, title="Men's Open"
        )
        self.stage = factories.StageFactory.create(division=self.division)
        self.aus = factories.TeamFactory.create(division=self.division, title="Australia")
        self.nzl = factories.TeamFactory.create(
            division=self.division, title="New Zealand"
        )
        self.day_kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "datestr": "20261008",
        }
        self.booth_kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "ground": "field-1",
        }
        self.day_url = reverse("ops:day", kwargs=self.day_kw)
        self.booth_url = reverse("ops:booth", kwargs=self.booth_kw)

    def make(self, hour, minute=0, **kwargs):
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute), TZ)
        kwargs.setdefault("home_team", self.aus)
        kwargs.setdefault("away_team", self.nzl)
        return factories.MatchFactory.create(
            stage=self.stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            **kwargs,
        )

    def url(self, name, **extra):
        return reverse(f"ops:{name}", kwargs={**self.day_kw, **extra})

    def booth(self, name, **extra):
        return reverse(f"ops:{name}", kwargs={**self.booth_kw, **extra})

    def submit(self, url, data=None):
        """POST as a plain browser; ``assertResponseContains`` reads the result."""
        with self.login(self.operator), self.captureOnCommitCallbacks(execute=True):
            self.last_response = self.client.post(url, data or {})
        return self.last_response

    def assertDayPage(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, DAY_TEMPLATE)
        self.assertResponseContains('<span class="brand">TOURNAMENT OPS</span>')

    def assertBoothPage(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, BOOTH_TEMPLATE)
        self.assertResponseContains('<span class="brand">BOOTH</span>')


class ResultFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.match = self.make(8)

    def post(self, match, data):
        return self.submit(self.url("match-result", match_pk=match.pk), data)

    def test_valid_save_redirects_to_the_day_and_persists(self):
        response = self.post(self.match, {"home_team_score": 5, "away_team_score": 4})
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        self.match.refresh_from_db()
        self.assertEqual(
            (self.match.home_team_score, self.match.away_team_score), (5, 4)
        )

    def test_editing_an_entered_score_redirects_and_persists(self):
        done = self.make(9, home_team_score=3, away_team_score=1)
        response = self.post(done, {"home_team_score": 3, "away_team_score": 2})
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        done.refresh_from_db()
        self.assertEqual((done.home_team_score, done.away_team_score), (3, 2))

    def test_forfeit_with_a_winner_redirects_and_persists(self):
        response = self.post(
            self.match,
            {
                "home_team_score": "",
                "away_team_score": "",
                "is_forfeit": "on",
                "forfeit_winner": self.nzl.pk,
            },
        )
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_forfeit)
        self.assertEqual(self.match.forfeit_winner, self.nzl)

    def test_bye_is_processed(self):
        bye = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.aus,
            away_team=None,
            date=datetime.date(2026, 10, 8),
            time=None,
            datetime=None,
            is_bye=True,
        )
        response = self.post(bye, {"bye_processed": "on"})
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        bye.refresh_from_db()
        self.assertTrue(bye.bye_processed)

    def test_one_score_only_shows_the_error_in_the_day_page(self):
        response = self.post(self.match, {"home_team_score": 5, "away_team_score": ""})
        self.assertDayPage(response)
        self.assertResponseContains("<li>Both scores are required.</li>")
        self.assertResponseContains(
            '<input type="number" name="home_team_score" value="5" class="sc" '
            'id="id_home_team_score">'
        )
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_team_score)

    def test_one_score_only_on_an_entered_row_keeps_it_in_edit(self):
        done = self.make(9, home_team_score=3, away_team_score=1)
        response = self.post(done, {"home_team_score": 4, "away_team_score": ""})
        self.assertDayPage(response)
        self.assertResponseContains("<li>Both scores are required.</li>")
        self.assertResponseContains(
            '<input type="number" name="home_team_score" value="4" class="sc" '
            'data-preserve-attr="value" id="id_home_team_score">'
        )
        # The cancel link only shows on a row being edited.
        self.assertResponseContains(
            '<a class="btn" href="%s" data-on:click__prevent="@get(\'%s\')">✕</a>'
            % ((self.url("match-result", match_pk=done.pk),) * 2)
        )
        done.refresh_from_db()
        self.assertEqual((done.home_team_score, done.away_team_score), (3, 1))

    def test_other_rows_keep_their_own_forms(self):
        other = self.make(8)
        response = self.post(self.match, {"home_team_score": 5, "away_team_score": ""})
        self.assertDayPage(response)
        self.assertEqual(response.content.decode().count("<li>Both scores"), 1)
        self.assertIn('id="match-%d"' % other.pk, response.content.decode())


class ScorersFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.match = self.make(8, home_team_score=2, away_team_score=1)
        self.home = [self.player(self.aus, n) for n in (1, 2)]
        self.away = [self.player(self.nzl, 3)]
        self.scorers_url = self.url("match-scorers", match_pk=self.match.pk)

    def player(self, team, number):
        person = factories.PersonFactory.create()
        factories.TeamAssociationFactory.create(team=team, person=person, number=number)
        return person

    def payload(self, home_points, away_points):
        data = {}
        for prefix, people, points in (
            ("home", self.home, home_points),
            ("away", self.away, away_points),
        ):
            data.update(
                {
                    f"{prefix}-TOTAL_FORMS": str(len(people)),
                    f"{prefix}-INITIAL_FORMS": str(len(people)),
                    f"{prefix}-MIN_NUM_FORMS": "0",
                    f"{prefix}-MAX_NUM_FORMS": "1000",
                }
            )
            for i, pts in enumerate(points):
                data.update(
                    {
                        f"{prefix}-{i}-played": "1",
                        f"{prefix}-{i}-number": str(i + 1),
                        f"{prefix}-{i}-points": str(pts),
                        f"{prefix}-{i}-mvp": "",
                    }
                )
        return data

    def post(self, data):
        return self.submit(self.scorers_url, data)

    def test_valid_save_redirects_to_the_day_and_persists_both_sides(self):
        response = self.post(self.payload([1, 1], [1]))
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        saved = SimpleScoreMatchStatistic.objects.filter(match=self.match)
        self.assertEqual(saved.count(), 3)
        self.assertEqual(
            {s.player_id: s.points for s in saved},
            {self.home[0].pk: 1, self.home[1].pk: 1, self.away[0].pk: 1},
        )

    def test_points_that_do_not_sum_show_the_formset_error_in_the_modal(self):
        response = self.post(self.payload([1, 0], [1]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, SCORERS_TEMPLATE)
        self.assertTemplateUsed(response, MODAL_TEMPLATE)
        self.assertTemplateNotUsed(response, DAY_TEMPLATE)
        self.assertResponseContains(
            "<li>Total number of points (1) does not equal total number of "
            "scores (2) for this team.</li>"
        )
        self.assertFalse(
            SimpleScoreMatchStatistic.objects.filter(match=self.match).exists()
        )

    def test_the_error_page_works_without_javascript(self):
        response = self.post(self.payload([1, 0], [1]))
        body = response.content.decode()
        self.assertTrue(body.lstrip().lower().startswith("<!doctype html>"))
        # The form posts on its own, with its token, and Save submits it.
        self.assertIn('<form method="post" action="%s"' % self.scorers_url, body)
        self.assertResponseContains(
            '<button class="btn p" type="submit">Save scorers</button>'
        )
        # Leaving is a link to the day, not a button that needs a script.
        self.assertResponseContains('<a class="btn" href="%s">Cancel</a>' % self.day_url)
        self.assertResponseContains(
            '<a class="back" href="%s">Back to the day</a>' % self.day_url
        )
        self.assertNotIn("$modal = false", body)

    def test_the_plain_get_is_the_same_page(self):
        with self.login(self.operator):
            self.last_response = self.client.get(self.scorers_url)
        self.assertEqual(self.last_response.status_code, 200)
        self.assertTemplateUsed(self.last_response, SCORERS_TEMPLATE)
        self.assertResponseContains('<a class="btn" href="%s">Cancel</a>' % self.day_url)


class StreamFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.current = self.make(
            10, 40, play_at=self.field1, external_identifier="yt-now",
            live_stream_status="testing",
        )
        self.following = self.make(
            11, 20, play_at=self.field1, external_identifier="yt-next"
        )
        self.event = factories.LiveStreamEventFactory.create(
            season=self.season,
            start=timezone.make_aware(datetime.datetime(2026, 10, 8, 17, 30), TZ),
        )

    def post(self, name, **extra):
        return self.submit(self.url(name, **extra))

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_go_live_redirects_and_stores_the_status(self, build):
        build.return_value = youtube_mock("testing")
        response = self.post("match-stream", match_pk=self.current.pk, status="live")
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_match_without_a_broadcast_shows_the_error_in_the_day_page(self, build):
        build.return_value = youtube_mock()
        orphan = self.make(12, play_at=self.field1)
        response = self.post("match-stream", match_pk=orphan.pk, status="live")
        self.assertDayPage(response)
        message = "%s: %s does not have a live stream identifier" % (
            streams.describe(orphan),
            orphan,
        )
        self.assertResponseContains('<p class="warn">%s</p>' % escape(message))
        self.assertEqual(events.recent(self.season.pk), [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_whole_slot_redirects_and_transitions_every_broadcast(self, build):
        build.return_value = youtube_mock("testing")
        response = self.post("slot-stream", slot_key="1040", status="live")
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_whole_slot_failure_shows_the_error_in_the_day_page(self, build):
        build.side_effect = RefreshError("expired")
        with self.assertLogs("tournamentcontrol.competition.ops.streams"):
            response = self.post("slot-stream", slot_key="1040", status="live")
        self.assertDayPage(response)
        message = "%s: expired" % streams.describe(self.current)
        self.assertResponseContains('<p class="warn">%s</p>' % escape(message))
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "testing")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_event_redirects_and_stores_the_status(self, build):
        build.return_value = youtube_mock("ready")
        response = self.post("event-stream", event_pk=self.event.pk, status="testing")
        self.assertRedirects(response, self.day_url, fetch_redirect_response=False)
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_status, "testing")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_event_failure_shows_the_error_in_the_day_page(self, build):
        build.side_effect = RefreshError("expired")
        with self.assertLogs("tournamentcontrol.competition.ops.streams"):
            response = self.post(
                "event-stream", event_pk=self.event.pk, status="testing"
            )
        self.assertDayPage(response)
        message = "%s: expired" % streams.describe(self.event)
        self.assertResponseContains('<p class="warn">%s</p>' % escape(message))


class LayoutFormTests(FormsFixture):
    def test_toggle_redirects_and_flips_the_session(self):
        with self.login(self.operator):
            response = self.client.post(self.url("layout"))
            self.assertRedirects(
                response, self.day_url, fetch_redirect_response=False
            )
            self.assertTrue(self.client.session["ops_collapsed"])
            self.client.post(self.url("layout"))
            self.assertFalse(self.client.session["ops_collapsed"])


class BoothFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.previous = self.make(
            9, 20, play_at=self.field1, home_team_score=3, away_team_score=7,
            external_identifier="yt-prev", live_stream_status="complete",
        )
        self.current = self.make(
            10, 40, play_at=self.field1, external_identifier="yt-now",
            live_stream_status="live",
        )
        self.following = self.make(
            11, 20, play_at=self.field1, external_identifier="yt-next"
        )

    def post(self, name, **extra):
        return self.submit(self.booth(name, **extra))

    def onair(self, response):
        match = re.search(
            r'<section id="onair".*?</section>',
            response.content.decode(),
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "no #onair section in the page")
        return match.group(0)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_ending_the_broadcast_redirects_to_the_booth_and_stores_complete(
        self, build
    ):
        build.return_value = youtube_mock("live")
        response = self.post("booth-onair", status="complete")
        self.assertRedirects(response, self.booth_url, fetch_redirect_response=False)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "complete")

    def test_nothing_on_the_ground_shows_the_reason_in_the_lamp(self):
        self.current.delete()
        self.previous.delete()
        response = self.post("booth-onair", status="complete")
        self.assertBoothPage(response)
        self.assertIn(
            '<span class="warn">Nothing is on this ground right now.</span>',
            self.onair(response),
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_arming_redirects_to_the_booth_and_stores_testing(self, build):
        build.return_value = youtube_mock("ready")
        self.current.live_stream_status = "complete"
        self.current.save()
        response = self.post("booth-arm")
        self.assertRedirects(response, self.booth_url, fetch_redirect_response=False)
        self.following.refresh_from_db()
        self.assertEqual(self.following.live_stream_status, "testing")

    def test_a_refused_arm_shows_the_reason_in_the_lamp(self):
        response = self.post("booth-arm")
        self.assertBoothPage(response)
        self.assertIn(
            '<span class="warn">End the current broadcast first.</span>',
            self.onair(response),
        )
        self.following.refresh_from_db()
        self.assertIsNone(self.following.live_stream_status)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_failed_transition_shows_the_reason_in_the_lamp(self, build):
        build.side_effect = RefreshError("expired")
        with self.assertLogs("tournamentcontrol.competition.ops.streams"):
            response = self.post("booth-onair", status="complete")
        self.assertBoothPage(response)
        message = "%s: expired" % streams.describe(self.current)
        self.assertIn(
            '<span class="warn">%s</span>' % escape(message), self.onair(response)
        )
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")
