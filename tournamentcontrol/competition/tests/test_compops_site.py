import datetime
import re
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.admin.tests.tenancy import schema_context
from tournamentcontrol.competition.compops import events
from tournamentcontrol.competition.compops.fragments import render_counts
from tournamentcontrol.competition.compops import sites
from tournamentcontrol.competition.compops.sites import CompOpsSite
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")


class CompOpsFixture(TestCase):
    def setUp(self):
        super().setUp()
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
class IndexTests(CompOpsFixture):
    def test_login_required(self):
        self.assertLoginRequired("compops:index")

    def test_staff_required(self):
        with self.login(self.user):
            self.get("compops:index")
            self.assert_http_403_forbidden()

    def test_single_active_season_redirects_to_today(self):
        with self.login(self.staff):
            self.get("compops:index")
        self.assert_http_302_found(url=self.reverse("compops:day", **self.day_kwargs))

    def test_two_active_seasons_are_listed(self):
        other = factories.SeasonFactory.create(timezone="Australia/Brisbane")
        factories.MatchFactory.create(
            stage__division__season=other, date=datetime.date(2026, 10, 8)
        )
        with self.login(self.staff):
            self.get("compops:index")
        self.assert_http_200_ok()
        url = reverse(
            "compops:season", kwargs={"competition": "pacific-cup", "season": "pc26"}
        )
        self.assertResponseContains(f'<a href="{url}">{self.season}</a>')


@freeze_time("2026-10-08 00:00 +10:00")
class DayPageTests(CompOpsFixture):
    def test_pending_forms_share_no_ids(self):
        # Datastar morphs by id, so two forms must not both claim one.
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 8, 0), TZ)
        other = factories.MatchFactory.create(
            stage=self.stage, datetime=when, date=when.date(), time=when.time()
        )
        self.staff.user_permissions.add(Permission.objects.get(codename="change_match"))
        with self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        body = self.last_response.content.decode()
        ids = re.findall(r'\bid="([^"]*)"', body)
        self.assertIn(f"m{self.match.pk}_home_team_score", ids)
        self.assertIn(f"m{other.pk}_home_team_score", ids)
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_season_redirects_to_today_in_season_time_zone(self):
        with self.login(self.staff):
            self.get("compops:season", competition="pacific-cup", season="pc26")
        self.assert_http_302_found(url=self.reverse("compops:day", **self.day_kwargs))

    def test_day_page_renders_every_panel(self):
        with self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        self.assert_http_200_ok()
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
                "compops:day",
                competition="pacific-cup",
                season="pc26",
                datestr="20261399",
            )
        self.assert_http_404_not_found()

    def test_fragment_plain_and_datastar(self):
        with self.login(self.staff):
            self.get("compops:activity", **self.day_kwargs)
            self.assertResponseHeaders({"Content-Type": "text/html; charset=utf-8"})
            self.assertResponseContains(
                '<li id="activity-empty" class="empty">Nothing has happened yet today.</li>'
            )
            self.get(
                "compops:activity",
                extra={"headers": {"Datastar-Request": "true"}},
                **self.day_kwargs,
            )
        self.assertResponseHeaders({"Content-Type": "text/event-stream"})
        body = b"".join(self.last_response.streaming_content).decode()
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
            self.get("compops:activity", **self.day_kwargs)
        self.assertResponseContains(
            '<li class="score-entered"><time>09:15:30</time>'
            "<span>Score · x · priya</span></li>"
        )

    def test_activity_is_kept_to_its_tenant(self):
        events.reset_backend()
        self.addCleanup(events.reset_backend)
        with (
            freeze_time("2026-10-07 23:15:30+00:00"),
            schema_context("alpha"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            events.publish(
                self.season.pk, "score-entered", actor="priya", summary="Score · x"
            )
        with self.login(self.staff):
            with schema_context("bravo"):
                self.get("compops:activity", **self.day_kwargs)
            self.assertResponseContains(
                '<li id="activity-empty" class="empty">Nothing has happened yet today.</li>'
            )
            with schema_context("alpha"):
                self.get("compops:activity", **self.day_kwargs)
            self.assertResponseContains(
                '<li class="score-entered"><time>09:15:30</time>'
                "<span>Score · x · priya</span></li>"
            )

    def test_count_ids_are_unique_on_the_page(self):
        with self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        self.assert_http_200_ok()
        content = self.last_response.content.decode()
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


@freeze_time("2026-10-08 00:00 +13:00")
class SeasonWithoutTimeZoneTests(CompOpsFixture):
    """
    A season without a time zone shows times in the current one, as its
    models do, rather than in the server default.
    """

    def setUp(self):
        super().setUp()
        self.season.timezone = None
        self.season.statistics = True
        self.season.save()
        events.reset_backend()
        self.addCleanup(events.reset_backend)

    def test_day_page_shows_activity_in_the_current_time_zone(self):
        with (
            freeze_time("2026-10-07 23:15:30+00:00"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            events.publish(
                self.season.pk, "score-entered", actor="priya", summary="Score · x"
            )
        with timezone.override("Pacific/Auckland"), self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        self.assert_http_200_ok()
        self.assertResponseContains(
            '<li class="score-entered"><time>12:15:30</time>'
            "<span>Score · x · priya</span></li>"
        )

    def test_scorers_page_renders_the_day(self):
        self.staff.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "add_simplescorematchstatistic",
                    "change_simplescorematchstatistic",
                ]
            )
        )
        self.match.home_team_score = 2
        self.match.away_team_score = 1
        self.match.save()
        with timezone.override("Pacific/Auckland"), self.login(self.staff):
            self.get("compops:match-scorers", match_pk=self.match.pk, **self.day_kwargs)
        self.assert_http_200_ok()
        self.assertResponseContains(
            f'<span class="season">{self.season} · Thursday 8 October</span>'
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
class LayoutTests(CompOpsFixture):
    def test_toggle_collapses_then_expands(self):
        with self.login(self.staff):
            self.post(
                "compops:layout",
                extra={"headers": {"Datastar-Request": "true"}},
                **self.day_kwargs,
            )
            body = b"".join(self.last_response.streaming_content).decode()
            self.assertIn('data: elements <main id="main" class="collapsed">', body)
            self.assertEqual(self.client.session["compops_collapsed"], True)
            self.post("compops:layout", **self.day_kwargs)
            self.assert_http_302_found(
                url=self.reverse("compops:day", **self.day_kwargs)
            )
            self.assertEqual(self.client.session["compops_collapsed"], False)

    def test_day_page_honours_the_session(self):
        with self.login(self.staff):
            session = self.client.session
            session["compops_collapsed"] = True
            session.save()
            self.get("compops:day", **self.day_kwargs)
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
                "CompOpsSite needs "
                "'touchtechnology.common.middleware.DatastarMiddleware' "
                "in MIDDLEWARE.",
            ):
                CompOpsSite()

    def test_site_without_template_partials_before_django_6_is_refused(self):
        with mock.patch.object(sites.django, "VERSION", (5, 2, 0)):
            with mock.patch.object(sites.apps, "is_installed", return_value=False):
                with self.assertRaisesMessage(
                    ImproperlyConfigured,
                    "CompOpsSite needs django-template-partials and "
                    "'template_partials' in INSTALLED_APPS before Django 6.0.",
                ):
                    CompOpsSite()

    def test_site_without_template_partials_on_django_6_mounts(self):
        with mock.patch.object(sites.django, "VERSION", (6, 0, 0)):
            with mock.patch.object(sites.apps, "is_installed", return_value=False):
                self.assertIsInstance(CompOpsSite(), CompOpsSite)
