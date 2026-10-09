import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from tournamentcontrol.competition.ops import events
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_live_stream_transition import (
    YOUTUBE_SEASON,
    youtube_mock,
)

TZ = ZoneInfo("Australia/Brisbane")


@freeze_time("2026-10-08 10:50 +10:00")
class BoothFixture(TestCase):
    def setUp(self):
        events.reset_backend()
        self.season = factories.SeasonFactory.create(
            slug="pc26",
            slug_locked=True,
            competition__slug="pacific-cup",
            competition__slug_locked=True,
            timezone="Australia/Brisbane",
            statistics=True,
            **YOUTUBE_SEASON,
        )
        self.commentator = factories.UserFactory.create()
        assign_perm("competition.stream_season", self.commentator, self.season)
        self.outsider = factories.UserFactory.create()
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
        self.pool_a = factories.StageGroupFactory.create(
            stage=self.stage, title="Pool A"
        )
        self.pool_b = factories.StageGroupFactory.create(
            stage=self.stage, title="Pool B"
        )
        self.aus = factories.TeamFactory.create(
            division=self.division, title="Australia", stage_group=self.pool_a
        )
        self.nzl = factories.TeamFactory.create(
            division=self.division, title="New Zealand", stage_group=self.pool_a
        )
        self.fji = factories.TeamFactory.create(
            division=self.division, title="Fiji", stage_group=self.pool_b
        )
        self.previous = self.make(
            9,
            20,
            self.fji,
            self.aus,
            home_team_score=3,
            away_team_score=7,
            external_identifier="yt-prev",
            live_stream_status="complete",
        )
        self.current = self.make(
            10,
            40,
            self.aus,
            self.nzl,
            external_identifier="yt-now",
            live_stream_status="live",
        )
        self.following = self.make(
            11, 20, self.fji, self.nzl, external_identifier="yt-next"
        )
        self.kw = {"competition": "pacific-cup", "season": "pc26", "ground": "field-1"}

    def make(self, hour, minute, home, away, ground=None, **kwargs):
        when = timezone.make_aware(datetime.datetime(2026, 10, 8, hour, minute), TZ)
        return factories.MatchFactory.create(
            stage=self.stage,
            stage_group=self.pool_a,
            home_team=home,
            away_team=away,
            datetime=when,
            date=when.date(),
            time=when.time(),
            play_at=ground or self.field1,
            **kwargs,
        )

    def url(self, name, **extra):
        return reverse(f"ops:{name}", kwargs={**self.kw, **extra})


class BoothAccessTests(BoothFixture):
    def test_login_required(self):
        self.assertLoginRequired("ops:booth", **self.kw)

    def test_stream_permission_required(self):
        with self.login(self.outsider):
            self.get("ops:booth", **self.kw)
            self.response_403()

    def test_commentator_without_staff_flag_can_open_the_booth(self):
        with self.login(self.commentator):
            self.get("ops:booth", **self.kw)
        self.response_200()
        self.assertResponseContains('<div id="lamp" class="lamp live">ON AIR</div>')

    def test_index_lists_streamed_grounds(self):
        with self.login(self.commentator):
            self.get("ops:booth-index", competition="pacific-cup", season="pc26")
        self.assertResponseContains('<a href="%s">Field 1</a>' % self.url("booth"))

    def test_unknown_ground_is_404(self):
        with self.login(self.commentator):
            self.get(
                "ops:booth", competition="pacific-cup", season="pc26", ground="field-9"
            )
            self.response_404()


class StripAndLampTests(BoothFixture):
    def test_strip_shows_previous_current_next(self):
        with self.login(self.commentator):
            self.get("ops:booth-strip", **self.kw)
        self.assertResponseContains('<div class="res">3 – 7</div>')
        self.assertResponseContains(
            '<div class="teams">Australia <small>v</small> New Zealand</div>'
        )
        self.assertResponseContains(
            '<div class="teams">Fiji <small>v</small> New Zealand</div>'
        )

    def test_lamp_offers_end_while_live(self):
        with self.login(self.commentator):
            self.get("ops:booth-lamp", **self.kw)
        self.assertResponseContains(
            '<button class="bigbtn end" type="submit" data-hold="1500">HOLD TO END BROADCAST</button>'
        )


class OnAirTests(BoothFixture):
    @mock.patch("tournamentcontrol.competition.models.build")
    def test_end_broadcast(self, build):
        build.return_value = youtube_mock("live")
        with self.login(self.commentator), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url("booth-onair", status="complete"),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: elements <section id="onair" class="onair">', body)
        self.assertIn('<div id="lamp" class="lamp">OFF AIR</div>', body)
        self.current.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "complete")
        (event,) = events.recent(self.season.pk)
        self.assertEqual(event["status"], "complete")

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_lamp_follows_the_live_match_when_it_overruns(self, build):
        build.return_value = youtube_mock("live")
        untouched = self.following.live_stream_status
        with freeze_time("2026-10-08 11:30 +10:00"):
            with self.login(self.commentator):
                self.get("ops:booth-lamp", **self.kw)
                self.response_200()
                self.assertResponseContains(
                    '<div id="lamp" class="lamp live">ON AIR</div>'
                )
                end_url = self.url("booth-onair", status="complete")
                self.assertIn(
                    'action="%s"' % end_url, self.last_response.content.decode()
                )
                self.assertResponseContains(
                    '<button class="bigbtn end" type="submit" data-hold="1500">HOLD TO END BROADCAST</button>'
                )
            with (
                self.login(self.commentator),
                self.captureOnCommitCallbacks(execute=True),
            ):
                self.client.post(end_url, headers={"Datastar-Request": "true"})
        self.current.refresh_from_db()
        self.following.refresh_from_db()
        self.assertEqual(self.current.live_stream_status, "complete")
        self.assertEqual(self.following.live_stream_status, untouched)

    def test_nothing_on_the_ground_is_a_refusal_not_an_error(self):
        self.current.delete()
        self.previous.delete()
        with self.login(self.commentator):
            response = self.client.post(
                self.url("booth-onair", status="complete"),
                headers={"Datastar-Request": "true"},
            )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn("Nothing is on this ground right now.", body)

    def test_times_follow_the_ground_zone(self):
        auckland = factories.GroundFactory.create(
            venue=self.field1.venue,
            title="Field 3",
            slug="field-3",
            slug_locked=True,
            live_stream=True,
            timezone="Pacific/Auckland",
        )
        self.make(
            10,
            40,
            self.aus,
            self.nzl,
            ground=auckland,
            external_identifier="yt-akl",
            live_stream_status="live",
            live_stream_status_at=datetime.datetime(
                2026, 10, 8, 0, 30, tzinfo=datetime.timezone.utc
            ),
        )
        with self.login(self.commentator):
            self.get("ops:booth-lamp", **{**self.kw, "ground": "field-3"})
        body = self.last_response.content.decode()
        self.assertIn("live since 13:30", body)
        self.assertNotIn("live since 10:30", body)

    def test_only_live_and_complete_are_accepted(self):
        with self.login(self.commentator):
            response = self.client.post(self.url("booth-onair", status="testing"))
        self.assertEqual(response.status_code, 404)

    def test_outsider_is_403(self):
        with self.login(self.outsider):
            response = self.client.post(self.url("booth-onair", status="complete"))
        self.assertEqual(response.status_code, 403)


class ArmTests(BoothFixture):
    def test_cannot_arm_while_live(self):
        with self.login(self.commentator):
            response = self.client.post(
                self.url("booth-arm"), headers={"Datastar-Request": "true"}
            )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn("End the current broadcast first", body)

    @mock.patch("tournamentcontrol.competition.models.build")
    def test_arm_moves_next_to_testing(self, build):
        build.return_value = youtube_mock("ready")
        self.current.live_stream_status = "complete"
        self.current.save()
        with self.login(self.commentator), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url("booth-arm"), headers={"Datastar-Request": "true"}
            )
        self.assertEqual(response.status_code, 200)
        self.following.refresh_from_db()
        self.assertEqual(self.following.live_stream_status, "testing")

    def test_arm_without_broadcast_is_a_refusal_not_an_error(self):
        self.current.live_stream_status = "complete"
        self.current.save()
        self.following.external_identifier = None
        self.following.save()
        with self.login(self.commentator):
            response = self.client.post(
                self.url("booth-arm"), headers={"Datastar-Request": "true"}
            )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn("has no YouTube broadcast", body)

    def test_no_next_match_today_is_a_refusal(self):
        self.current.live_stream_status = "complete"
        self.current.save()
        self.following.delete()
        with self.login(self.commentator):
            response = self.client.post(
                self.url("booth-arm"), headers={"Datastar-Request": "true"}
            )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode()
        self.assertIn("No more broadcasts on Field 1 today", body)


class PaneTests(BoothFixture):
    def setUp(self):
        super().setUp()
        self.player = factories.PersonFactory.create(
            first_name="Liam", last_name="Thompson"
        )
        factories.TeamAssociationFactory.create(
            team=self.aus, person=self.player, number=1
        )
        factories.SimpleScoreMatchStatisticFactory.create(
            match=self.previous, player=self.player, number=1, played=1, points=4, mvp=3
        )

    def test_sheets(self):
        with self.login(self.commentator):
            response = self.client.get(
                self.url("booth-pane", match_pk=self.current.pk, pane="sheets"),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: elements <div id="pane" class="pane sheets">', body)
        self.assertIn("Liam Thompson", body)
        self.assertIn(
            'data: signals {"pane":"sheets","match":%d}' % self.current.pk, body
        )

    def test_results_pane_lists_each_team_this_season(self):
        with self.login(self.commentator):
            self.get(
                "ops:booth-pane", match_pk=self.current.pk, pane="results", **self.kw
            )
        # Australia were the away team in the 3 – 7 match, so their row reads 7 – 3.
        self.assertResponseContains('<td class="num">7 – 3</td>')

    def test_ladder_pane_uses_the_pool(self):
        # The result already entered for Australia has produced their row (and
        # Fiji's); New Zealand have no row yet.
        factories.LadderSummaryFactory.create(
            stage=self.stage, stage_group=self.pool_a, team=self.nzl, points=6
        )
        with self.login(self.commentator):
            self.get(
                "ops:booth-pane", match_pk=self.current.pk, pane="ladder", **self.kw
            )
        self.assertResponseContains("<h4>Men's Open · Pool A</h4>")

    def test_leaders(self):
        with self.login(self.commentator):
            self.get(
                "ops:booth-pane", match_pk=self.current.pk, pane="leaders", **self.kw
            )
        self.assertResponseContains('<td class="num">4</td>')

    def test_unknown_pane_is_404(self):
        with self.login(self.commentator):
            self.get(
                "ops:booth-pane", match_pk=self.current.pk, pane="weather", **self.kw
            )
            self.response_404()

    def test_match_from_another_ground_is_404(self):
        other = factories.GroundFactory.create(
            venue=self.field1.venue, live_stream=True
        )
        elsewhere = self.make(12, 0, self.aus, self.fji, ground=other)
        with self.login(self.commentator):
            self.get("ops:booth-pane", match_pk=elsewhere.pk, pane="sheets", **self.kw)
            self.response_404()

    def test_runsheet(self):
        with self.login(self.commentator):
            self.get("ops:booth-runsheet", **self.kw)
        self.assertResponseContains('<td class="onair">ON AIR</td>')


class TeamPickerTests(BoothFixture):
    def test_picker_groups_the_division_by_pool(self):
        with self.login(self.commentator):
            response = self.client.get(
                self.url("booth-teams", match_pk=self.current.pk),
                headers={"Datastar-Request": "true"},
            )
        body = b"".join(response.streaming_content).decode()
        self.assertIn('data: elements <div id="modal-body" class="sheet">', body)
        self.assertIn("Pool A", body)
        self.assertIn("Pool B", body)
        self.assertIn('data: signals {"modal":true}', body)

    def test_team_modal_shows_squad_and_results(self):
        with self.login(self.commentator):
            self.get("ops:booth-team", team_pk=self.fji.pk, **self.kw)
        self.assertResponseContains("<h3>Fiji</h3>")
        self.assertResponseContains('<td class="num">3 – 7</td>')

    def test_team_from_another_season_is_404(self):
        stranger = factories.TeamFactory.create()
        with self.login(self.commentator):
            self.get("ops:booth-team", team_pk=stranger.pk, **self.kw)
            self.response_404()
