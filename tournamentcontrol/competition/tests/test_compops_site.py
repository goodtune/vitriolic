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
from tournamentcontrol.competition.compops import events, sites
from tournamentcontrol.competition.compops.fragments import render_counts
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

    def season_url(self, season):
        return reverse(
            "compops:season",
            kwargs={"competition": season.competition.slug, "season": season.slug},
        )

    def other_season(self, day, title):
        season = factories.SeasonFactory.create(
            title=title, timezone="Australia/Brisbane"
        )
        factories.MatchFactory.create(stage__division__season=season, date=day)
        return season

    def test_season_being_played_opens_at_today(self):
        with self.login(self.staff):
            self.get("compops:index")
        self.assert_http_200_ok()
        self.assertResponseContains("<h2>On now</h2>")
        today = self.reverse("compops:day", **self.day_kwargs)
        self.assertResponseContains(f'<a class="btn p" href="{today}">Open today</a>')
        self.assertResponseNotContains("<h2>Upcoming</h2>")
        self.assertResponseNotContains("<h2>Recent</h2>")

    def test_rest_day_offers_the_next_day_with_matches(self):
        self.match.date = datetime.date(2026, 10, 7)
        self.match.save()
        factories.MatchFactory.create(
            stage=self.stage, date=datetime.date(2026, 10, 10)
        )
        with self.login(self.staff):
            self.get("compops:index")
        url = reverse("compops:day", kwargs={**self.day_kwargs, "datestr": "20261010"})
        self.assertResponseContains(f'<a class="btn" href="{url}">Next: Sat 10 Oct</a>')

    def test_upcoming_and_recent_seasons_lead_to_their_days(self):
        soon = self.other_season(datetime.date(2026, 10, 9), "World Cup 2026")
        later = self.other_season(datetime.date(2026, 10, 20), "Euros 2026")
        ended = self.other_season(datetime.date(2026, 10, 7), "Atlantics 2026")
        older = self.other_season(datetime.date(2026, 9, 28), "Asia Cup 2026")
        with self.login(self.staff):
            self.get("compops:index")
        self.assertResponseContains("<h2>Upcoming</h2>")
        self.assertResponseContains("<h2>Recent</h2>")
        for season, note, when in (
            (soon, "tomorrow", "9 Oct 2026"),
            (later, "in 12 days", "20 Oct 2026"),
            (ended, "ended yesterday", "7 Oct 2026"),
            (older, "ended 10 days ago", "28 Sep 2026"),
        ):
            with self.subTest(season.title):
                self.assertResponseContains(
                    f'<a class="item" href="{self.season_url(season)}">'
                    f'<span class="title">{season.title}</span>'
                    f'<span class="comp">{season.competition.title}</span>'
                    f'<span class="note">{note}</span>'
                    f'<span class="when">{when}</span></a>'
                )

    def test_every_season_is_listed_even_with_no_matches(self):
        empty = factories.SeasonFactory.create(
            title="Draft 2027", timezone="Australia/Brisbane", enabled=False
        )
        with self.login(self.staff):
            self.get("compops:index")
        self.assertResponseContains("<h2>All events</h2>")
        self.assertResponseContains(f"<h3>{empty.competition.title}</h3>")
        self.assertResponseContains(
            f'<a class="item" href="{self.season_url(empty)}">'
            '<span class="title">Draft 2027</span>'
            '<span class="tag">Not public</span>'
            '<span class="when">No matches scheduled</span></a>'
        )


class EmptyIndexTests(TestCase):
    def test_no_seasons(self):
        with self.login(factories.UserFactory.create(is_staff=True)):
            self.get("compops:index")
        self.assert_http_200_ok()
        self.assertResponseContains('<p class="empty">There are no events yet.</p>')


@freeze_time("2026-10-08 00:00 +10:00")
class SeasonPageTests(CompOpsFixture):
    kwargs = {"competition": "pacific-cup", "season": "pc26"}

    def day_url(self, datestr):
        return reverse("compops:day", kwargs={**self.kwargs, "datestr": datestr})

    def test_login_required(self):
        self.assertLoginRequired("compops:season", **self.kwargs)

    def test_staff_required(self):
        with self.login(self.user):
            self.get("compops:season", **self.kwargs)
            self.assert_http_403_forbidden()

    def test_unknown_season(self):
        with self.login(self.staff):
            self.get("compops:season", competition="pacific-cup", season="pc99")
        self.assert_http_404_not_found()

    def test_days_are_listed_with_their_results(self):
        factories.MatchFactory.create(
            stage=self.stage,
            date=datetime.date(2026, 10, 6),
            home_team_score=1,
            away_team_score=0,
        )
        for _ in range(2):
            factories.MatchFactory.create(
                stage=self.stage, date=datetime.date(2026, 10, 7)
            )
        factories.MatchFactory.create(stage=self.stage, date=datetime.date(2026, 10, 9))
        factories.MatchFactory.create(stage=self.stage, date=None)
        with self.login(self.staff):
            self.get("compops:season", **self.kwargs)
        self.assert_http_200_ok()
        self.assertResponseContains(f"<h1>{self.season.title}</h1>")
        for datestr, day, tag, matches, state, text in (
            (
                "20261006",
                "Tuesday 6 October 2026",
                "",
                "1 match",
                "complete",
                "All results in",
            ),
            (
                "20261007",
                "Wednesday 7 October 2026",
                "",
                "2 matches",
                "overdue",
                "2 results missing",
            ),
            (
                "20261008",
                "Thursday 8 October 2026",
                '<span class="tag">Today</span>',
                "1 match",
                "today",
                "1 result to enter",
            ),
            (
                "20261009",
                "Friday 9 October 2026",
                "",
                "1 match",
                "upcoming",
                "Upcoming",
            ),
        ):
            with self.subTest(datestr):
                self.assertResponseContains(
                    f'<a class="item" href="{self.day_url(datestr)}">'
                    f'<span class="title">{day}</span>{tag}'
                    f'<span class="when">{matches}</span>'
                    f'<span class="state {state}">{text}</span></a>'
                )
        self.assertResponseContains('<p class="empty">1 match has no date yet.</p>')

    def test_today_is_the_date_where_the_season_is_played(self):
        # Midnight on the 8th in Brisbane is still the 7th in Perth.
        self.season.timezone = "Australia/Perth"
        self.season.save()
        with self.login(self.staff):
            self.get("compops:season", **self.kwargs)
        self.assertResponseContains(
            f'<a class="item" href="{self.day_url("20261008")}">'
            '<span class="title">Thursday 8 October 2026</span>'
            '<span class="when">1 match</span>'
            '<span class="state upcoming">Upcoming</span></a>'
        )

    def test_season_with_no_matches(self):
        self.match.delete()
        with self.login(self.staff):
            self.get("compops:season", **self.kwargs)
        self.assert_http_200_ok()
        self.assertResponseContains(
            '<p class="empty">No matches are scheduled for this event.</p>'
        )


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

    def test_topbar_leads_up_to_the_season_and_home(self):
        with self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        home = self.reverse("compops:index")
        season = self.reverse(
            "compops:season", competition="pacific-cup", season="pc26"
        )
        self.assertResponseContains(
            f'<a class="brand" href="{home}">TOURNAMENT OPS</a>'
        )
        self.assertResponseContains(
            f'<a class="season" href="{season}">{self.season}</a>'
        )

    def test_topbar_steps_to_the_nearest_days_with_matches(self):
        for day in (datetime.date(2026, 10, 5), datetime.date(2026, 10, 10)):
            factories.MatchFactory.create(stage=self.stage, date=day)
        with self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        before = reverse(
            "compops:day", kwargs={**self.day_kwargs, "datestr": "20261005"}
        )
        after = reverse(
            "compops:day", kwargs={**self.day_kwargs, "datestr": "20261010"}
        )
        self.assertResponseContains(
            '<nav class="days">'
            f'<a href="{before}" rel="prev" title="Monday 5 October">‹</a>'
            '<span class="day">Thursday 8 October</span>'
            f'<a href="{after}" rel="next" title="Saturday 10 October">›</a>'
            "</nav>"
        )

    def test_topbar_has_no_step_past_the_only_day(self):
        with self.login(self.staff):
            self.get("compops:day", **self.day_kwargs)
        self.assertResponseContains(
            '<nav class="days"><span class="step">‹</span>'
            '<span class="day">Thursday 8 October</span>'
            '<span class="step">›</span></nav>'
        )

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
