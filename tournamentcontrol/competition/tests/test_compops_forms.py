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

from tournamentcontrol.competition.compops import events, streams
from tournamentcontrol.competition.models import SimpleScoreMatchStatistic
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)

TZ = ZoneInfo("Australia/Brisbane")

DAY_TEMPLATE = "tournamentcontrol/competition/compops/day.html"
BOOTH_TEMPLATE = "tournamentcontrol/competition/compops/booth.html"
SCORERS_TEMPLATE = "tournamentcontrol/competition/compops/scorers.html"


@freeze_time("2026-10-08 10:50 +10:00")
class FormsFixture(TestCase):
    def setUp(self):
        super().setUp()
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
        self.aus = factories.TeamFactory.create(
            division=self.division, title="Australia"
        )
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
        self.day_url = reverse("compops:day", kwargs=self.day_kw)
        self.booth_url = reverse("compops:booth", kwargs=self.booth_kw)

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
        return reverse(f"compops:{name}", kwargs={**self.day_kw, **extra})

    def submit(self, name, kw, data=None, **extra):
        """POST as a plain browser; the assertions read ``last_response``."""
        with self.login(self.operator), self.captureOnCommitCallbacks(execute=True):
            self.post(f"compops:{name}", data=data or {}, **kw, **extra)

    def assertDayPage(self):
        self.assert_http_200_ok()
        self.assertResponseTemplateUsed(DAY_TEMPLATE)
        self.assertResponseContains('<span class="brand">TOURNAMENT OPS</span>')

    def assertBoothPage(self):
        self.assert_http_200_ok()
        self.assertResponseTemplateUsed(BOOTH_TEMPLATE)
        self.assertResponseContains('<span class="brand">BOOTH</span>')


class ResultFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.match = self.make(8)

    def send(self, match, data):
        self.submit("match-result", self.day_kw, data, match_pk=match.pk)

    def test_valid_save_redirects_to_the_day_and_persists(self):
        self.send(self.match, {"home_team_score": 5, "away_team_score": 4})
        self.assert_http_302_found(url=self.day_url)
        self.match.refresh_from_db()
        self.assertEqual(
            (self.match.home_team_score, self.match.away_team_score), (5, 4)
        )

    def test_editing_an_entered_score_redirects_and_persists(self):
        done = self.make(9, home_team_score=3, away_team_score=1)
        self.send(done, {"home_team_score": 3, "away_team_score": 2})
        self.assert_http_302_found(url=self.day_url)
        done.refresh_from_db()
        self.assertEqual((done.home_team_score, done.away_team_score), (3, 2))

    def test_forfeit_with_a_winner_redirects_and_persists(self):
        self.send(
            self.match,
            {
                "home_team_score": "",
                "away_team_score": "",
                "is_forfeit": "on",
                "forfeit_winner": self.nzl.pk,
            },
        )
        self.assert_http_302_found(url=self.day_url)
        self.match.refresh_from_db()
        self.assertIs(self.match.is_forfeit, True)
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
        self.send(bye, {"bye_processed": "on"})
        self.assert_http_302_found(url=self.day_url)
        bye.refresh_from_db()
        self.assertIs(bye.bye_processed, True)

    def test_one_score_only_shows_the_error_in_the_day_page(self):
        self.send(self.match, {"home_team_score": 5, "away_team_score": ""})
        self.assertDayPage()
        self.assertResponseContains("<li>Both scores are required.</li>")
        self.assertResponseContains(
            '<input type="number" name="home_team_score" value="5" class="sc" '
            f'data-preserve-attr="value" id="m{self.match.pk}_home_team_score">'
        )
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_team_score)

    def test_one_score_only_on_an_entered_row_keeps_it_in_edit(self):
        done = self.make(9, home_team_score=3, away_team_score=1)
        self.send(done, {"home_team_score": 4, "away_team_score": ""})
        self.assertDayPage()
        self.assertResponseContains("<li>Both scores are required.</li>")
        self.assertResponseContains(
            '<input type="number" name="home_team_score" value="4" class="sc" '
            f'data-preserve-attr="value" id="m{done.pk}_home_team_score">'
        )
        # The cancel link only shows on a row being edited.
        url = self.url("match-result", match_pk=done.pk)
        self.assertResponseContains(
            f'<a class="btn" href="{url}" '
            f"data-on:click__prevent=\"@get('{url}')\">✕</a>"
        )
        done.refresh_from_db()
        self.assertEqual((done.home_team_score, done.away_team_score), (3, 1))

    def test_other_rows_keep_their_own_forms(self):
        other = self.make(8)
        self.send(self.match, {"home_team_score": 5, "away_team_score": ""})
        self.assertDayPage()
        self.assertResponseContains("<li>Both scores are required.</li>", count=1)
        body = self.last_response.content.decode()
        self.assertEqual(body.count(f'id="match-{other.pk}"'), 1)


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

    def send(self, data):
        self.submit("match-scorers", self.day_kw, data, match_pk=self.match.pk)

    def test_valid_save_redirects_to_the_day_and_persists_both_sides(self):
        self.send(self.payload([1, 1], [1]))
        self.assert_http_302_found(url=self.day_url)
        saved = SimpleScoreMatchStatistic.objects.filter(match=self.match)
        self.assertEqual(saved.count(), 3)
        self.assertEqual(
            {s.player_id: s.points for s in saved},
            {self.home[0].pk: 1, self.home[1].pk: 1, self.away[0].pk: 1},
        )

    def test_points_that_do_not_sum_show_the_formset_error_in_the_modal(self):
        self.send(self.payload([1, 0], [1]))
        self.assert_http_200_ok()
        self.assertResponseTemplateUsed(SCORERS_TEMPLATE)
        # The modal is a partial of the day page; Django 5.2 records no
        # template for it, so look for its Save button instead.
        self.assertResponseContains(
            '<button class="btn p" type="submit">Save scorers</button>'
        )
        self.assertResponseTemplateNotUsed(DAY_TEMPLATE)
        self.assertResponseContains(
            "<li>Total number of points (1) does not equal total number of "
            "scores (2) for this team.</li>"
        )
        self.assertEqual(
            SimpleScoreMatchStatistic.objects.filter(match=self.match).count(), 0
        )

    def test_the_error_page_works_without_javascript(self):
        self.send(self.payload([1, 0], [1]))
        body = self.last_response.content.decode()
        self.assertEqual(body.lstrip()[:15].lower(), "<!doctype html>")
        # The form posts on its own, with its token, and Save submits it.
        self.assertIn(f'<form method="post" action="{self.scorers_url}"', body)
        self.assertResponseContains(
            '<button class="btn p" type="submit">Save scorers</button>'
        )
        # Leaving is a link to the day, not a button that needs a script.
        self.assertResponseContains(f'<a class="btn" href="{self.day_url}">Cancel</a>')
        self.assertResponseContains(
            f'<a class="back" href="{self.day_url}">Back to the day</a>'
        )
        self.assertNotIn("$modal = false", body)

    def test_the_plain_get_is_the_same_page(self):
        with self.login(self.operator):
            self.get("compops:match-scorers", match_pk=self.match.pk, **self.day_kw)
        self.assert_http_200_ok()
        self.assertResponseTemplateUsed(SCORERS_TEMPLATE)
        self.assertResponseContains(f'<a class="btn" href="{self.day_url}">Cancel</a>')


class StreamFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.current = self.make(
            10,
            40,
            play_at=self.field1,
            live_stream=True,
            external_identifier="yt-now",
            live_stream_status="testing",
        )
        self.following = self.make(
            11, 20, play_at=self.field1, live_stream=True, external_identifier="yt-next"
        )
        self.event = factories.LiveStreamEventFactory.create(
            season=self.season,
            start=timezone.make_aware(datetime.datetime(2026, 10, 8, 17, 30), TZ),
        )

    def send(self, name, **extra):
        self.submit(name, self.day_kw, **extra)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_go_live_redirects_and_stores_the_status(self, build):
        build.return_value = youtube_mock("testing")
        self.send("match-stream", match_pk=self.current.pk, status="live")
        self.assert_http_302_found(url=self.day_url)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_match_without_a_broadcast_shows_the_error_in_the_day_page(self, build):
        build.return_value = youtube_mock()
        orphan = self.make(12, play_at=self.field1, live_stream=True)
        self.send("match-stream", match_pk=orphan.pk, status="live")
        self.assertDayPage()
        message = f"{streams.describe(orphan)}: {orphan} does not have a live stream identifier"
        self.assertResponseContains(f'<p class="warn">{escape(message)}</p>')
        self.assertEqual(events.recent(self.season.pk), [])

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_whole_slot_redirects_and_transitions_every_broadcast(self, build):
        build.return_value = youtube_mock("testing")
        self.send("slot-stream", slot_key="1040", status="live")
        self.assert_http_302_found(url=self.day_url)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_whole_slot_failure_shows_the_error_in_the_day_page(self, build):
        build.side_effect = RefreshError("expired")
        with self.assertLogs("tournamentcontrol.competition.compops.streams"):
            self.send("slot-stream", slot_key="1040", status="live")
        self.assertDayPage()
        message = f"{streams.describe(self.current)}: expired"
        self.assertResponseContains(f'<p class="warn">{escape(message)}</p>')
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "testing")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_event_redirects_and_stores_the_status(self, build):
        build.return_value = youtube_mock("ready")
        self.send("event-stream", event_pk=self.event.pk, status="testing")
        self.assert_http_302_found(url=self.day_url)
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_status, "testing")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_event_failure_shows_the_error_in_the_day_page(self, build):
        build.side_effect = RefreshError("expired")
        with self.assertLogs("tournamentcontrol.competition.compops.streams"):
            self.send("event-stream", event_pk=self.event.pk, status="testing")
        self.assertDayPage()
        message = f"{streams.describe(self.event)}: expired"
        self.assertResponseContains(f'<p class="warn">{escape(message)}</p>')


class LayoutFormTests(FormsFixture):
    def test_toggle_redirects_and_flips_the_session(self):
        with self.login(self.operator):
            self.post("compops:layout", **self.day_kw)
            self.assert_http_302_found(url=self.day_url)
            self.assertIs(self.client.session["compops_collapsed"], True)
            self.post("compops:layout", **self.day_kw)
            self.assertIs(self.client.session["compops_collapsed"], False)


class BoothFormTests(FormsFixture):
    def setUp(self):
        super().setUp()
        self.previous = self.make(
            9,
            20,
            play_at=self.field1,
            home_team_score=3,
            away_team_score=7,
            live_stream=True,
            external_identifier="yt-prev",
            live_stream_status="complete",
        )
        self.current = self.make(
            10,
            40,
            play_at=self.field1,
            live_stream=True,
            external_identifier="yt-now",
            live_stream_status="live",
        )
        self.following = self.make(
            11, 20, play_at=self.field1, live_stream=True, external_identifier="yt-next"
        )

    def send(self, name, **extra):
        self.submit(name, self.booth_kw, **extra)

    def onair(self):
        (section,) = re.findall(
            r'<section id="onair".*?</section>',
            self.last_response.content.decode(),
            flags=re.DOTALL,
        )
        return section

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_ending_the_broadcast_redirects_to_the_booth_and_stores_complete(
        self, build
    ):
        build.return_value = youtube_mock("live")
        self.send("booth-onair", status="complete")
        self.assert_http_302_found(url=self.booth_url)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "complete")

    def test_nothing_on_the_ground_shows_the_reason_in_the_lamp(self):
        self.current.delete()
        self.previous.delete()
        self.send("booth-onair", status="complete")
        self.assertBoothPage()
        self.assertInHTML(
            '<span class="warn">Nothing is on this ground right now.</span>',
            self.onair(),
        )

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_arming_redirects_to_the_booth_and_stores_testing(self, build):
        build.return_value = youtube_mock("ready")
        self.current.live_stream_status = "complete"
        self.current.save()
        self.send("booth-arm")
        self.assert_http_302_found(url=self.booth_url)
        self.following.refresh_from_db()
        self.assertEqual(self.following.live_stream_status, "testing")

    def test_a_refused_arm_shows_the_reason_in_the_lamp(self):
        self.send("booth-arm")
        self.assertBoothPage()
        self.assertInHTML(
            '<span class="warn">End the current broadcast first.</span>',
            self.onair(),
        )
        self.following.refresh_from_db()
        self.assertIsNone(self.following.live_stream_status)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_a_failed_transition_shows_the_reason_in_the_lamp(self, build):
        build.side_effect = RefreshError("expired")
        with self.assertLogs("tournamentcontrol.competition.compops.streams"):
            self.send("booth-onair", status="complete")
        self.assertBoothPage()
        message = f"{streams.describe(self.current)}: expired"
        self.assertInHTML(f'<span class="warn">{escape(message)}</span>', self.onair())
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "live")
