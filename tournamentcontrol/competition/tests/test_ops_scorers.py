import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from tournamentcontrol.competition.models import SimpleScoreMatchStatistic
from tournamentcontrol.competition.ops import events
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Australia/Brisbane")


@freeze_time("2026-10-08 00:00 +10:00")
class ScorersFixture(TestCase):
    def setUp(self):
        events.reset_backend()
        self.staff = factories.UserFactory.create(is_staff=True)
        self.staff.user_permissions.add(
            *Permission.objects.filter(
                codename__in=[
                    "add_simplescorematchstatistic",
                    "change_simplescorematchstatistic",
                ]
            )
        )
        self.nostats = factories.UserFactory.create(is_staff=True)
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
            statistics=True,
        )
        stage = factories.StageFactory.create(division__season=self.season)
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, 8), TZ)
        self.match = factories.MatchFactory.create(
            stage=stage,
            datetime=when,
            date=when.date(),
            time=when.time(),
            home_team_score=2,
            away_team_score=1,
        )
        self.home = [self.player(self.match.home_team, n) for n in (1, 2)]
        self.away = [self.player(self.match.away_team, n) for n in (3,)]
        self.kw = {
            "competition": "pacific-cup",
            "season": "pc26",
            "datestr": "20261008",
        }
        self.url = reverse(
            "ops:match-scorers", kwargs={**self.kw, "match_pk": self.match.pk}
        )

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
            for i, (person, pts) in enumerate(zip(people, points)):
                data.update(
                    {
                        f"{prefix}-{i}-played": "1",
                        f"{prefix}-{i}-number": str(i + 1),
                        f"{prefix}-{i}-points": str(pts),
                        f"{prefix}-{i}-mvp": "",
                    }
                )
        return data


class ScorersListTests(ScorersFixture):
    def test_list_shows_match_awaiting_scorers(self):
        with self.login(self.staff):
            self.get("ops:scorers", **self.kw)
        self.assertResponseContains('<span class="score">2 – 1</span>')
        self.assertResponseContains(
            f'<a class="btn" href="{self.url}" '
            f"data-on:click__prevent=\"@get('{self.url}')\">Enter scorers</a>"
        )

    def test_unbalanced_match_is_marked(self):
        SimpleScoreMatchStatistic.objects.create(
            match=self.match, player=self.home[0], number=1, played=1, points=1
        )
        with self.login(self.staff):
            self.get("ops:scorers", **self.kw)
        self.assertResponseContains('<span class="pill warn">out of balance</span>')

    def test_user_without_statistics_permission_sees_no_button(self):
        with self.login(self.nostats):
            self.get("ops:scorers", **self.kw)
        self.assertResponseNotContains("Enter scorers")


class ScorersModalTests(ScorersFixture):
    def test_modal_renders_both_rosters(self):
        with self.login(self.staff):
            response = self.client.get(self.url, headers={"Datastar-Request": "true"})
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: elements <div id="modal-body" class="modal"', body)
        self.assertIn('name="home-TOTAL_FORMS" value="2"', body)
        self.assertIn('name="away-TOTAL_FORMS" value="1"', body)
        self.assertIn("event: datastar-patch-signals", body)
        self.assertIn('data: signals {"modal":true}', body)
        self.assertIn('data-signals="{home_total: 0, away_total: 0}"', body)
        self.assertIn('<span data-text="$home_total">0</span>', body)
        self.assertIn('<span data-text="$away_total">0</span>', body)

    def test_valid_post_saves_and_closes(self):
        with self.login(self.staff), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                self.payload([1, 1], [1]),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: signals {"modal":false}', body)
        self.assertIn('data: elements <div id="scorers"', body)
        self.assertIn('<span id="scorers-count" class="count zero">0</span>', body)
        self.assertIn('<span id="scorers-count-tab" class="count zero">0</span>', body)
        self.assertEqual(
            SimpleScoreMatchStatistic.objects.filter(match=self.match).count(), 3
        )
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "statistics-entered")
        self.assertEqual(event["actor"], self.staff.get_username())

    def test_one_event_is_published_after_both_sides_are_saved(self):
        seen = []
        publish = events.publish

        def record(*args, **kwargs):
            # Runs where the receiver calls it, at signal time.
            seen.append(
                SimpleScoreMatchStatistic.objects.filter(
                    match=self.match, player=self.away[0]
                ).exists()
            )
            return publish(*args, **kwargs)

        with (
            mock.patch.object(events, "publish", side_effect=record) as patched,
            self.login(self.staff),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(
                self.url,
                self.payload([1, 1], [1]),
                headers={"Datastar-Request": "true"},
            )
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(seen, [True])
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["type"], "statistics-entered")

    def test_points_that_do_not_sum_re_render_the_modal(self):
        with self.login(self.staff):
            response = self.client.post(
                self.url,
                self.payload([1, 0], [1]),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: elements <div id="modal-body" class="modal"', body)
        self.assertIn("does not equal", body.lower())
        self.assertIn('data-signals="{home_total: 1, away_total: 1}"', body)
        self.assertIn('<span data-text="$home_total">1</span>', body)
        self.assertEqual(
            SimpleScoreMatchStatistic.objects.filter(match=self.match).count(), 0
        )

    def test_plain_post_redirects_to_day(self):
        with self.login(self.staff):
            response = self.client.post(self.url, self.payload([1, 1], [1]))
        self.assertRedirects(
            response, reverse("ops:day", kwargs=self.kw), fetch_redirect_response=False
        )

    def test_without_permission_is_403(self):
        with self.login(self.nostats):
            response = self.client.post(self.url, self.payload([1, 1], [1]))
        self.assertEqual(response.status_code, 403)

    def test_match_without_score_is_404(self):
        self.match.home_team_score = None
        self.match.away_team_score = None
        self.match.save()
        with self.login(self.staff):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
