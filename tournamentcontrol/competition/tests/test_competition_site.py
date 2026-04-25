import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import override_settings
from freezegun import freeze_time
from icalendar import Calendar
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.draw import schemas
from tournamentcontrol.competition.draw.builders import build
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin_format


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
    The division view follows ``parent.ladders`` and
    ``parent.matches_by_date``, both of which used to issue at least
    one extra query per stage. Pin the view's query count so the
    Sentry N+1 explosion (600+ model instantiations on a single
    request) cannot silently regress: the same ``test_query_count``
    upper bound is used for a small and a large division, so any
    per-stage scaling trips the large case.
    """

    @classmethod
    def _build_scored_division(cls, spec):
        """
        Build a division from a ``DivisionStructure`` spec and score
        every match so the ladder signals populate ``LadderEntry`` and
        ``LadderSummary`` rows — matching the shape of production data
        the division view has to render.
        """
        division = build(cls.season, spec)
        # DivisionStructure does not carry a points formula, so set one
        # here to match what ``DivisionFactory`` would normally give us
        # and let the ladder signals produce ladder rows.
        division.points_formula = "3*win + 2*draw + 1*loss"
        division.save()
        # ``build`` uses a no-date generator, so matches come back with
        # ``datetime=None``. Scheduling them here both gives the scoring
        # signals realistic data and avoids ``Match.get_datetime``
        # issuing a per-match sibling lookup during template render.
        match_dt = datetime(2025, 8, 22, 9, 0, tzinfo=ZoneInfo("UTC"))
        for i, match in enumerate(division.matches.all()):
            match.date = match_dt.date()
            match.time = match_dt.time()
            match.datetime = match_dt
            match.home_team_score = 10 + (i % 4)
            match.away_team_score = 5 + (i % 3)
            match.save()
        return division

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()
        cls.competition = cls.season.competition

        # Small: one stage, four teams, six round-robin matches.
        cls.small_division = cls._build_scored_division(
            schemas.DivisionStructure(
                title="Small Division",
                teams=["Alpha", "Beta", "Gamma", "Delta"],
                draw_formats={"rr4": round_robin_format(4)},
                stages=[
                    schemas.StageFixture(
                        title="Round Robin", draw_format_ref="rr4"
                    ),
                ],
            )
        )

        # Large: three stages, eight teams, 28 round-robin matches per
        # stage. Enough to make any per-stage N+1 visible against the
        # same query-count bound used by the small case.
        cls.large_division = cls._build_scored_division(
            schemas.DivisionStructure(
                title="Large Division",
                teams=[f"Team {i}" for i in range(1, 9)],
                draw_formats={"rr8": round_robin_format(8)},
                stages=[
                    schemas.StageFixture(
                        title=f"Stage {i}", draw_format_ref="rr8"
                    )
                    for i in range(1, 4)
                ],
            )
        )

    def test_small_division_query_count(self):
        self.assertGoodView(
            "competition:division",
            self.competition.slug,
            self.season.slug,
            self.small_division.slug,
            test_query_count=14,
        )

    def test_large_division_query_count(self):
        self.assertGoodView(
            "competition:division",
            self.competition.slug,
            self.season.slug,
            self.large_division.slug,
            test_query_count=14,
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class MatchDetailViewQueryTests(TestCase):
    """
    The public match detail page renders the ``preview`` template tag,
    which iterates ``TeamAssociation`` rows for both teams and
    dereferences ``person`` on each one. Without prefetching, that
    produces one ``competition_person`` query per associated player.
    Pin the view's query count so the same upper bound holds whether
    the teams are empty or fully squadded - any per-player scaling
    trips the large case.
    """

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()
        cls.competition = cls.season.competition
        cls.division = factories.DivisionFactory.create(season=cls.season)
        cls.stage = factories.StageFactory.create(division=cls.division)

        # Small: a match with no team associations.
        cls.small_match = factories.MatchFactory.create(stage=cls.stage)

        # Large: a match where each team has 12 associated players.
        cls.large_match = factories.MatchFactory.create(stage=cls.stage)
        for _ in range(12):
            factories.TeamAssociationFactory.create(
                team=cls.large_match.home_team,
                person=factories.PersonFactory.create(
                    club=cls.large_match.home_team.club,
                ),
            )
            factories.TeamAssociationFactory.create(
                team=cls.large_match.away_team,
                person=factories.PersonFactory.create(
                    club=cls.large_match.away_team.club,
                ),
            )

    def test_small_match_query_count(self):
        self.assertGoodView(
            "competition:match",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
            self.small_match.pk,
            test_query_count=18,
        )

    def test_large_match_query_count(self):
        self.assertGoodView(
            "competition:match",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
            self.large_match.pk,
            test_query_count=18,
        )
