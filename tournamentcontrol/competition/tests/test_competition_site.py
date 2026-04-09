import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from freezegun import freeze_time
from icalendar import Calendar
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests import factories


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class GoodViewTests(TestCase):
    def test_index(self):
        self.assertGoodView("competition:index")

    def test_competition(self):
        competition = factories.CompetitionFactory.create()
        self.assertGoodView("competition:competition", competition.slug)

    def test_season(self):
        season = factories.SeasonFactory.create()
        self.assertGoodView("competition:season", season.competition.slug, season.slug)

    def test_season_calendar(self):
        # TODO load matches to see if the query count is scaled properly
        stage = factories.StageFactory.create()
        factories.MatchFactory.create_batch(
            5, stage=stage, date="2022-07-02", time="09:00", datetime="2022-07-02 09:00"
        )
        self.assertGoodView(
            "competition:calendar",
            stage.division.season.competition.slug,
            stage.division.season.slug,
        )

    def test_season_videos(self):
        season = factories.SeasonFactory.create()
        self.assertGoodView(
            "competition:season-videos", season.competition.slug, season.slug
        )

    def test_stream(self):
        # Create a superuser to access the login-required stream view
        superuser = UserFactory.create(is_staff=True, is_superuser=True)

        # Create a season with timezone to test the ZoneInfo fix
        season = factories.SeasonFactory.create(timezone=ZoneInfo("Australia/Sydney"))

        # Create a ground with live streaming enabled as would happen via edit_match
        ground = factories.GroundFactory.create(
            venue__season=season,
            live_stream=True,
            external_identifier="ground-stream-123",
            stream_key="stream-key-456",
        )

        # Create a single match with proper structure as would be created via edit_match
        external_id = "test-match-123"
        factories.MatchFactory.create(
            stage__division__season=season,
            external_identifier=external_id,
            play_at=ground,
            videos=[f"http://youtu.be/{external_id}"],
            live_stream_bind=ground.external_identifier,
        )

        with self.login(superuser):
            self.assertGoodView(
                "competition:stream", season.competition.slug, season.slug
            )

    def test_club(self):
        club = factories.ClubFactory.create()
        stage = factories.StageFactory.create()
        stage.division.season.competition.clubs.add(club)
        team = factories.TeamFactory.create(club=club, division=stage.division)
        factories.MatchFactory.create_batch(stage=stage, home_team=team, size=10)
        self.assertGoodView(
            "competition:club",
            competition=stage.division.season.competition.slug,
            season=stage.division.season.slug,
            club=club.slug,
        )

    def test_club_calendar(self):
        club = factories.ClubFactory.create()
        stage = factories.StageFactory.create(division__season__disable_calendar=True)
        stage.division.season.competition.clubs.add(club)
        team = factories.TeamFactory.create(club=club, division=stage.division)
        factories.MatchFactory.create_batch(stage=stage, home_team=team, size=10)
        self.get(
            "competition:calendar",
            competition=stage.division.season.competition.slug,
            season=stage.division.season.slug,
            club=club.slug,
        )
        self.response_410()

    def test_division(self):
        division = factories.DivisionFactory.create()
        self.assertGoodView(
            "competition:division",
            division.season.competition.slug,
            division.season.slug,
            division.slug,
        )

    def test_division_calendar(self):
        division = factories.DivisionFactory.create()
        self.assertGoodView(
            "competition:calendar",
            competition=division.season.competition.slug,
            season=division.season.slug,
            division=division.slug,
        )

    def test_stage(self):
        stage = factories.StageFactory.create()
        self.assertGoodView(
            "competition:stage",
            stage.division.season.competition.slug,
            stage.division.season.slug,
            stage.division.slug,
            stage.slug,
        )

    def test_stage_group(self):
        pool = factories.StageGroupFactory.create()
        self.assertGoodView(
            "competition:pool",
            pool.stage.division.season.competition.slug,
            pool.stage.division.season.slug,
            pool.stage.division.slug,
            pool.stage.slug,
            pool.slug,
        )

    def test_match(self):
        match = factories.MatchFactory.create()
        self.assertGoodView(
            "competition:match",
            match.stage.division.season.competition.slug,
            match.stage.division.season.slug,
            match.stage.division.slug,
            match.pk,
        )

    def test_match_gone(self):
        opts = [
            {"is_bye": True},
            {"home_team": None},
            {"away_team": None},
        ]
        for kw in opts:
            match = factories.MatchFactory.create(**kw)
            self.get(
                "competition:match",
                match.stage.division.season.competition.slug,
                match.stage.division.season.slug,
                match.stage.division.slug,
                match.pk,
            )
            self.response_410()

    def test_match_video(self):
        match = factories.MatchFactory.create(videos=["https://youtu.be/jNQXAC9IVRw"])
        self.assertGoodView(
            "competition:match-video",
            match.stage.division.season.competition.slug,
            match.stage.division.season.slug,
            match.stage.division.slug,
            match.pk,
        )
        self.assertResponseContains(
            '<iframe width="480" height="360" '
            'src="http://www.youtube.com/embed/jNQXAC9IVRw?wmode=opaque" '
            'loading="lazy" frameborder="0" allowfullscreen>'
            "</iframe>"
        )

    def test_match_video_gone(self):
        opts = [
            {"is_bye": True},
            {"home_team": None},
            {"away_team": None},
        ]
        for kw in opts:
            match = factories.MatchFactory.create(**kw)
            self.get(
                "competition:match-video",
                match.stage.division.season.competition.slug,
                match.stage.division.season.slug,
                match.stage.division.slug,
                match.pk,
            )
            self.response_410()


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class FrontEndTests(TestCase):
    def test_competition_list(self):
        comp_1 = factories.CompetitionFactory.create()
        comp_2 = factories.CompetitionFactory.create(enabled=False)
        self.get("competition:index")
        self.assertResponseContains(comp_1.title, html=False)
        self.assertResponseNotContains(comp_2.title, html=False)

    def test_season_list(self):
        season = factories.SeasonFactory.create()
        self.assertGoodView("competition:season", season.competition.slug, season.slug)
        self.assertResponseContains(season.title, html=False)

        season = factories.SeasonFactory.create(competition__enabled=False)
        self.get("competition:competition", season.competition.slug)
        self.response_404()

    def test_division_list(self):
        division = factories.DivisionFactory.create()
        self.assertGoodView(
            "competition:season", division.season.competition.slug, division.season.slug
        )
        self.assertResponseContains(division.title, html=False)

    def test_division_view(self):
        division = factories.DivisionFactory.create()
        self.assertGoodView(
            "competition:division",
            division.season.competition.slug,
            division.season.slug,
            division.slug,
        )
        self.assertResponseContains(division.title, html=False)

    @freeze_time("2013-11-01")
    def test_upcoming_matches(self):
        division = factories.DivisionFactory.create()
        factories.MatchFactory.create_batch(
            stage__division=division,
            datetime=datetime(2013, 11, 22, 10, tzinfo=ZoneInfo("UTC")),
            size=10,
        )
        self.assertGoodView(
            "competition:season", division.season.competition.slug, division.season.slug
        )
        self.assertResponseContains("Nov. 22, 2013", html=False)

    def test_division_match_list(self):
        division = factories.DivisionFactory.create()
        factories.MatchFactory.create_batch(stage__division=division, size=10)
        self.assertGoodView(
            "competition:division",
            division.season.competition.slug,
            division.season.slug,
            division.slug,
        )
        for team in division.teams.all():
            href = self.reverse(
                "competition:team",
                division.season.competition.slug,
                division.season.slug,
                division.slug,
                team.slug,
            )
            self.assertResponseContains(
                '<a href="{0}">{1}</a>'.format(href, team.title)
            )

    def test_team_calendar(self):
        team = factories.TeamFactory.create()
        factories.MatchFactory.create_batch(
            stage__division=team.division, home_team=team, size=5
        )
        self.assertGoodView(
            "competition:calendar",
            team.division.season.competition.slug,
            team.division.season.slug,
            team.division.slug,
            team.slug,
        )
        for opponent in team.division.teams.exclude(pk=team.pk):
            subject = "{} vs {}".format(team.title, opponent.title)
            self.assertResponseContains(subject, html=False)

    @unittest.expectedFailure
    def test_team_calendar_disabled(self):
        season = factories.SeasonFactory.create(disable_calendar=True)
        team = factories.TeamFactory.create(division__season=season)
        factories.MatchFactory.create_batch(
            stage__division=team.division, home_team=team, size=5
        )
        self.assertGoodView(
            "competition:calendar",
            team.division.season.competition.slug,
            team.division.season.slug,
            team.division.slug,
            team.slug,
        )

    def test_division_calendar(self):
        team = factories.TeamFactory.create()
        factories.MatchFactory.create_batch(
            stage__division=team.division, home_team=team, size=5
        )
        self.assertGoodView(
            "competition:calendar",
            team.division.season.competition.slug,
            team.division.season.slug,
            team.division.slug,
        )
        for opponent in team.division.teams.exclude(pk=team.pk):
            subject = "{} vs {}".format(team.title, opponent.title)
            self.assertResponseContains(subject, html=False)

    @unittest.expectedFailure
    def test_division_calendar_disabled(self):
        season = factories.SeasonFactory.create(disable_calendar=True)
        team = factories.TeamFactory.create(division__season=season)
        factories.MatchFactory.create_batch(
            stage__division=team.division, home_team=team, size=5
        )
        self.assertGoodView(
            "competition:calendar",
            team.division.season.competition.slug,
            team.division.season.slug,
            team.division.slug,
        )

    def test_season_calendar(self):
        team = factories.TeamFactory.create()
        factories.MatchFactory.create_batch(
            stage__division=team.division, home_team=team, size=5
        )
        self.assertGoodView(
            "competition:calendar",
            team.division.season.competition.slug,
            team.division.season.slug,
        )
        for opponent in team.division.teams.exclude(pk=team.pk):
            subject = "{} vs {}".format(team.title, opponent.title)
            self.assertResponseContains(subject, html=False)

    @unittest.expectedFailure
    def test_season_calendar_disabled(self):
        season = factories.SeasonFactory.create(disable_calendar=True)
        team = factories.TeamFactory.create(division__season=season)
        factories.MatchFactory.create_batch(
            stage__division=team.division, home_team=team, size=5
        )
        self.assertGoodView(
            "competition:calendar",
            team.division.season.competition.slug,
            team.division.season.slug,
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class CalendarQueryTests(TestCase):
    """Test that calendar views use an efficient number of database queries."""

    @classmethod
    def setUpTestData(cls):
        cls.stage = factories.StageFactory.create()
        cls.division = cls.stage.division
        cls.season = cls.division.season
        cls.competition = cls.season.competition

        cls.team_a = factories.TeamFactory.create(division=cls.division)
        cls.team_b = factories.TeamFactory.create(division=cls.division)

        factories.MatchFactory.create_batch(
            stage=cls.stage,
            home_team=cls.team_a,
            away_team=cls.team_b,
            size=10,
        )

    def test_team_calendar_query_count(self):
        # Middleware redirect check (1) + slug resolution (1) + match query (1)
        with self.assertNumQueries(3):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
                division=self.division.slug,
                team=self.team_a.slug,
            )
        self.response_200(response)

    def test_division_calendar_query_count(self):
        # Middleware redirect check (1) + slug resolution (1) + match query (1)
        with self.assertNumQueries(3):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
                division=self.division.slug,
            )
        self.response_200(response)

    def test_season_calendar_query_count(self):
        # Middleware redirect check (1) + slug resolution (1) + match query (1)
        with self.assertNumQueries(3):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
            )
        self.response_200(response)

    def test_club_calendar_query_count(self):
        club = factories.ClubFactory.create()
        self.team_a.club = club
        self.team_a.save()
        # Middleware (3) + season resolution (1) + club resolution (1)
        # + match query (1)
        with self.assertNumQueries(6):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
                club=club.slug,
            )
        self.response_200(response)

    def _parse_events(self, response):
        cal = Calendar.from_ical(response.content)
        return cal, [c for c in cal.walk() if c.name == "VEVENT"]

    @freeze_time("2025-06-01 10:00:00")
    def test_team_calendar_event_properties(self):
        match_dt = datetime(2025, 7, 5, 14, 30, tzinfo=ZoneInfo("UTC"))
        match = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team_a,
            away_team=self.team_b,
            datetime=match_dt,
            date=match_dt.date(),
            time=match_dt.time(),
        )

        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
            team=self.team_a.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)

        # VCALENDAR properties
        self.assertEqual(
            str(cal["prodid"]),
            "-//Tournament Control//testserver//",
        )
        self.assertEqual(str(cal["version"]), "2.0")

        # 10 from setUpTestData + 1 created above
        self.assertEqual(len(events), 11)

        # Find the specific match by UID
        event = next(e for e in events if e["uid"] == match.uuid.hex)

        self.assertEqual(
            str(event["summary"]),
            "{} vs {}".format(self.team_a.title, self.team_b.title),
        )
        self.assertEqual(
            str(event["location"]),
            "{} ({})".format(self.division.title, self.stage.title),
        )
        self.assertEqual(event["dtstart"].dt, match_dt)
        self.assertEqual(
            event["dtend"].dt, match_dt + timedelta(minutes=45)
        )
        self.assertEqual(
            event["dtstamp"].dt,
            datetime(2025, 6, 1, 10, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

        expected_path = self.reverse(
            "competition:match",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
            match=match.pk,
        )
        self.assertEqual(
            str(event["description"]),
            "http://testserver{}".format(expected_path),
        )

    def test_division_calendar_contains_all_division_matches(self):
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        self.assertEqual(len(events), 10)

        uids = {e["uid"] for e in events}
        expected_uids = set(
            self.division.matches.values_list("uuid", flat=True)
        )
        self.assertCountEqual(
            uids, {u.hex for u in expected_uids}
        )

    def test_disabled_calendar_returns_410(self):
        season = factories.SeasonFactory.create(disable_calendar=True)
        division = factories.DivisionFactory.create(season=season)
        team = factories.TeamFactory.create(division=division)
        stage = factories.StageFactory.create(division=division)
        factories.MatchFactory.create_batch(
            stage=stage, home_team=team, size=3
        )
        self.get(
            "competition:calendar",
            competition=season.competition.slug,
            season=season.slug,
            division=division.slug,
            team=team.slug,
        )
        self.response_410()

    def test_draft_division_excluded_for_anonymous(self):
        draft_division = factories.DivisionFactory.create(
            season=self.season, draft=True
        )
        draft_stage = factories.StageFactory.create(division=draft_division)
        factories.MatchFactory.create_batch(
            stage=draft_stage, size=3
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        # Only the 10 non-draft matches, not the 3 draft matches
        self.assertEqual(len(events), 10)

    def test_draft_division_included_for_superuser(self):
        superuser = factories.SuperUserFactory.create()
        draft_division = factories.DivisionFactory.create(
            season=self.season, draft=True
        )
        draft_stage = factories.StageFactory.create(division=draft_division)
        factories.MatchFactory.create_batch(
            stage=draft_stage, size=3
        )
        with self.login(superuser):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
            )
        self.response_200(response)

        cal, events = self._parse_events(response)
        # Superuser sees all matches: 10 regular + 3 draft
        self.assertEqual(len(events), 13)

    def test_calendar_excludes_unscheduled_matches(self):
        unscheduled = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team_a,
            away_team=self.team_b,
            datetime=None,
            date=None,
            time=None,
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
            team=self.team_a.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        # Only the 10 scheduled matches, not the unscheduled one
        self.assertEqual(len(events), 10)
        uids = {e["uid"] for e in events}
        self.assertNotIn(unscheduled.uuid.hex, uids)

    def test_nonexistent_team_returns_404(self):
        self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
            team="nonexistent-team",
        )
        self.response_404()

    def test_season_calendar_contains_all_season_matches(self):
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        self.assertEqual(len(events), 10)

        uids = {e["uid"] for e in events}
        expected_uids = set(
            self.season.matches.values_list("uuid", flat=True)
        )
        self.assertCountEqual(
            uids, {u.hex for u in expected_uids}
        )

    def test_calendar_with_bye_match(self):
        """Bye matches with a datetime should appear in the calendar."""
        match = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team_a,
            away_team=None,
            is_bye=True,
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        event = next(e for e in events if e["uid"] == match.uuid.hex)
        summary = str(event["summary"])
        self.assertIn(self.team_a.title, summary)
        self.assertIn("Bye", summary)

    def test_calendar_with_undecided_team(self):
        """Matches with undecided teams should appear in the calendar."""
        undecided = factories.UndecidedTeamFactory.create(
            stage=self.stage,
            label="Winner Pool A",
        )
        match = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team_a,
            away_team=None,
            away_team_undecided=undecided,
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        event = next(e for e in events if e["uid"] == match.uuid.hex)
        summary = str(event["summary"])
        self.assertIn(self.team_a.title, summary)
        self.assertIn("Winner Pool A", summary)

    def test_calendar_with_both_teams_undecided(self):
        """Matches where both teams are undecided should appear."""
        home_undecided = factories.UndecidedTeamFactory.create(
            stage=self.stage,
            label="1st Pool A",
        )
        away_undecided = factories.UndecidedTeamFactory.create(
            stage=self.stage,
            label="2nd Pool B",
        )
        match = factories.MatchFactory.create(
            stage=self.stage,
            home_team=None,
            away_team=None,
            home_team_undecided=home_undecided,
            away_team_undecided=away_undecided,
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        event = next(e for e in events if e["uid"] == match.uuid.hex)
        summary = str(event["summary"])
        self.assertIn("1st Pool A", summary)
        self.assertIn("2nd Pool B", summary)

    def test_calendar_with_no_teams(self):
        """Matches with no teams assigned should not crash."""
        match = factories.MatchFactory.create(
            stage=self.stage,
            home_team=None,
            away_team=None,
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )
        self.response_200(response)

        cal, events = self._parse_events(response)
        event = next(e for e in events if e["uid"] == match.uuid.hex)
        self.assertEqual(str(event["summary"]), "TBD")


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class DivisionViewQueryTests(TestCase):
    """
    The division view renders a whole division's draw and ladder,
    following FKs such as ``match.home_team.club``. Its query count must
    be bounded — it must NOT grow with the number of teams, matches or
    stages — otherwise we re-introduce the N+1 explosion seen in Sentry
    (600+ model instantiations on a single request).
    """

    @staticmethod
    def _populate_division(team_count, stage_count=2, match_count=10):
        """
        Create a division with ``stage_count`` stages, ``team_count`` teams
        (each in their own club) and ``match_count`` matches spread across
        the stages. Returns the division.
        """
        division = factories.DivisionFactory.create()
        for _ in range(stage_count):
            factories.StageFactory.create(division=division)
        teams = []
        for _ in range(team_count):
            club = factories.ClubFactory.create()
            division.season.competition.clubs.add(club)
            team = factories.TeamFactory.create(club=club, division=division)
            teams.append(team)
        stages = list(division.stages.order_by("order"))
        for i in range(match_count):
            home = teams[(2 * i) % team_count]
            away = teams[(2 * i + 1) % team_count]
            factories.MatchFactory.create(
                stage=stages[i % stage_count],
                home_team=home,
                away_team=away,
            )
        return division

    def _get_division(self, division):
        return self.get(
            "competition:division",
            competition=division.season.competition.slug,
            season=division.season.slug,
            division=division.slug,
        )

    def _assert_bounded_by_division_size(self, small, large):
        # Warm any lazy import/template caches so the measurement is
        # stable.
        self._get_division(small)

        with CaptureQueriesContext(connection) as small_ctx:
            self.response_200(self._get_division(small))
        with CaptureQueriesContext(connection) as large_ctx:
            self.response_200(self._get_division(large))

        small_count = len(small_ctx.captured_queries)
        large_count = len(large_ctx.captured_queries)
        self.assertEqual(
            small_count,
            large_count,
            msg=(
                f"Division view query count scales with division size: "
                f"{small_count} queries for the small division vs "
                f"{large_count} for the large one. Executed queries on "
                f"the large division were:\n"
                + "\n".join(
                    f"  {i}. {q['sql'][:240]}"
                    for i, q in enumerate(large_ctx.captured_queries, 1)
                )
            ),
        )

    def test_division_view_query_count_does_not_scale(self):
        """Doubling the number of teams, clubs, stages and matches in
        the division must not increase the number of DB queries."""
        small = self._populate_division(
            team_count=4, stage_count=2, match_count=6
        )
        large = self._populate_division(
            team_count=20, stage_count=4, match_count=40
        )
        self._assert_bounded_by_division_size(small, large)

    def test_division_view_query_count_does_not_scale_with_pools(self):
        """
        The division view must also be bounded when stages have pools
        (``StageGroup``). This exercises the pools branch of
        ``Division.ladders``, which has to prefetch both the pools and
        each pool's ladder summary.
        """
        def build(stage_pools):
            division = factories.DivisionFactory.create()
            for n_pools in stage_pools:
                stage = factories.StageFactory.create(division=division)
                for _ in range(n_pools):
                    factories.StageGroupFactory.create(stage=stage)
            return division

        small = build([2, 2])
        large = build([4, 4, 4, 4])
        self._assert_bounded_by_division_size(small, large)
