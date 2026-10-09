import datetime
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from tournamentcontrol.competition.ops import events
from tournamentcontrol.competition.ops.fragments import render_counts
from tournamentcontrol.competition.ops.sites import OpsSite
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")


class OpsFixture(TestCase):
    def setUp(self):
        self.staff = factories.UserFactory.create(is_staff=True)
        self.user = factories.UserFactory.create()
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
        )
        self.stage = factories.StageFactory.create(division__season=self.season)
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 8, 0), TZ)
        self.match = factories.MatchFactory.create(
            stage=self.stage, datetime=when, date=when.date(), time=when.time()
        )
        self.day_kwargs = {
            "competition": "pacific-cup",
            "season": "pc26",
            "datestr": "20261008",
        }


@freeze_time("2026-10-08 00:00 +10:00")
class IndexTests(OpsFixture):
    def test_login_required(self):
        self.assertLoginRequired("ops:index")

    def test_staff_required(self):
        with self.login(self.user):
            self.get("ops:index")
            self.response_403()

    def test_single_active_season_redirects_to_today(self):
        with self.login(self.staff):
            response = self.get("ops:index")
        self.assertRedirects(
            response,
            reverse("ops:day", kwargs=self.day_kwargs),
            fetch_redirect_response=False,
        )

    def test_two_active_seasons_are_listed(self):
        other = factories.SeasonFactory.create(timezone="Australia/Brisbane")
        factories.MatchFactory.create(
            stage__division__season=other, date=datetime.date(2026, 10, 8)
        )
        with self.login(self.staff):
            self.get("ops:index")
        self.response_200()
        url = reverse(
            "ops:season", kwargs={"competition": "pacific-cup", "season": "pc26"}
        )
        self.assertResponseContains(f'<a href="{url}">{self.season}</a>')


@freeze_time("2026-10-08 00:00 +10:00")
class DayPageTests(OpsFixture):
    def test_pending_forms_share_no_ids(self):
        # Datastar morphs by id, so two forms must not both claim one.
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 8, 0), TZ)
        other = factories.MatchFactory.create(
            stage=self.stage, datetime=when, date=when.date(), time=when.time()
        )
        self.staff.user_permissions.add(Permission.objects.get(codename="change_match"))
        with self.login(self.staff):
            self.get("ops:day", **self.day_kwargs)
        body = self.last_response.content.decode()
        ids = re.findall(r'\bid="([^"]*)"', body)
        self.assertIn("m%d_home_team_score" % self.match.pk, ids)
        self.assertIn("m%d_home_team_score" % other.pk, ids)
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_season_redirects_to_today_in_season_time_zone(self):
        with self.login(self.staff):
            response = self.get("ops:season", competition="pacific-cup", season="pc26")
        self.assertRedirects(
            response,
            reverse("ops:day", kwargs=self.day_kwargs),
            fetch_redirect_response=False,
        )

    def test_day_page_renders_every_panel(self):
        with self.login(self.staff):
            self.get("ops:day", **self.day_kwargs)
        self.response_200()
        self.assertResponseContains('<span id="results-count" class="count">1</span>')
        self.assertResponseContains(
            '<span id="scorers-count" class="count zero">0</span>'
        )
        self.assertResponseContains(
            '<span id="streams-count" class="count zero">0</span>'
        )
        self.assertResponseContains(
            '<li id="activity-empty" class="empty">Nothing has happened yet today.</li>'
        )

    def test_invalid_day_is_404(self):
        with self.login(self.staff):
            self.get(
                "ops:day", competition="pacific-cup", season="pc26", datestr="20261399"
            )
        self.response_404()

    def test_fragment_plain_and_datastar(self):
        with self.login(self.staff):
            plain = self.get("ops:activity", **self.day_kwargs)
            self.assertEqual(plain["Content-Type"], "text/html; charset=utf-8")
            self.assertResponseContains(
                '<li id="activity-empty" class="empty">Nothing has happened yet today.</li>'
            )
            streamed = self.client.get(
                reverse("ops:activity", kwargs=self.day_kwargs),
                headers={"Datastar-Request": "true"},
            )
        self.assertEqual(streamed["Content-Type"], "text/event-stream")
        body = b"".join(streamed.streaming_content).decode()
        self.assertIn("event: datastar-patch-elements", body)
        self.assertIn('data: elements <ul id="activity"', body)

    def test_activity_times_are_shown_in_the_season_time_zone(self):
        events.reset_backend()
        self.addCleanup(events.reset_backend)
        with (
            freeze_time("2026-10-07 23:15:30+00:00"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            events.publish(
                self.season.pk, "score-entered", actor="priya", summary="Score · x"
            )
        with self.login(self.staff):
            self.get("ops:activity", **self.day_kwargs)
        self.assertResponseContains(
            '<li class="score-entered"><time>09:15:30</time>'
            "<span>Score · x · priya</span></li>"
        )

    def test_count_ids_are_unique_on_the_page(self):
        with self.login(self.staff):
            response = self.get("ops:day", **self.day_kwargs)
        self.response_200()
        content = response.content.decode()
        for name in (
            "results-count",
            "results-count-tab",
            "scorers-count",
            "scorers-count-tab",
        ):
            self.assertEqual(content.count(f'id="{name}"'), 1, name)
        self.assertResponseContains(
            '<span id="results-count-tab" class="count">1</span>'
        )


class RenderCountsTests(TestCase):
    def test_returns_each_count_for_header_and_tab(self):
        request = RequestFactory().get("/")
        fragments = render_counts(
            request, results_pending=2, scorers=["a"], live_count=0
        )
        self.assertEqual(
            [f.strip() for f in fragments],
            [
                '<span id="results-count" class="count">2</span>',
                '<span id="results-count-tab" class="count">2</span>',
                '<span id="scorers-count" class="count">1</span>',
                '<span id="scorers-count-tab" class="count">1</span>',
                '<span id="streams-count" class="count zero">0</span>',
                '<span id="streams-count-rail" class="count zero">0</span>',
            ],
        )


@freeze_time("2026-10-08 00:00 +10:00")
class LayoutTests(OpsFixture):
    def test_toggle_collapses_then_expands(self):
        url = reverse("ops:layout", kwargs=self.day_kwargs)
        with self.login(self.staff):
            response = self.client.post(url, headers={"Datastar-Request": "true"})
            body = b"".join(response.streaming_content).decode()
            self.assertIn('data: elements <main id="main" class="collapsed">', body)
            self.assertTrue(self.client.session["ops_collapsed"])
            response = self.client.post(url)
            self.assertRedirects(
                response,
                reverse("ops:day", kwargs=self.day_kwargs),
                fetch_redirect_response=False,
            )
            self.assertFalse(self.client.session["ops_collapsed"])

    def test_day_page_honours_the_session(self):
        with self.login(self.staff):
            session = self.client.session
            session["ops_collapsed"] = True
            session.save()
            self.get("ops:day", **self.day_kwargs)
        self.assertResponseContains(
            '<button type="submit" title="expand"><span class="rail-l">Streams '
            '<span id="streams-count-rail" class="count zero">0</span></span></button>'
        )


class MiddlewareRequiredTests(TestCase):
    def test_site_without_the_datastar_middleware_is_refused(self):
        middleware = [
            path
            for path in settings.MIDDLEWARE
            if path != "touchtechnology.common.middleware.DatastarMiddleware"
        ]
        with override_settings(MIDDLEWARE=middleware):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "OpsSite needs "
                "'touchtechnology.common.middleware.DatastarMiddleware' "
                "in MIDDLEWARE.",
            ):
                OpsSite()
