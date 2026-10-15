import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from freezegun import freeze_time
from icalendar import Calendar
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.draw import schemas
from tournamentcontrol.competition.draw.builders import build
from tournamentcontrol.competition.models import Match, Team
from tournamentcontrol.competition.sites import competition as competition_site
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

    def test_venue(self):
        venue = factories.VenueFactory.create()
        factories.MatchFactory.create(
            play_at=venue, stage__division__season=venue.season
        )
        self.assertGoodView(
            "competition:venue",
            venue.season.competition.slug,
            venue.season.slug,
            venue.slug,
        )

    def test_venue_date(self):
        venue = factories.VenueFactory.create()
        factories.MatchFactory.create(
            play_at=venue,
            stage__division__season=venue.season,
            datetime=datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC")),
        )
        self.assertGoodView(
            "competition:venue",
            venue.season.competition.slug,
            venue.season.slug,
            venue.slug,
            "20250313",
        )

    def test_ground(self):
        ground = factories.GroundFactory.create()
        factories.MatchFactory.create(
            play_at=ground, stage__division__season=ground.venue.season
        )
        self.assertGoodView(
            "competition:ground",
            ground.venue.season.competition.slug,
            ground.venue.season.slug,
            ground.venue.slug,
            ground.slug,
        )

    def test_ground_date(self):
        ground = factories.GroundFactory.create()
        factories.MatchFactory.create(
            play_at=ground,
            stage__division__season=ground.venue.season,
            date=date(2025, 3, 13),
            time=time(10, 0),
            datetime=datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC")),
        )
        self.assertGoodView(
            "competition:ground",
            ground.venue.season.competition.slug,
            ground.venue.season.slug,
            ground.venue.slug,
            ground.slug,
            "20250313",
        )


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

    def setUp(self):
        # Archived feeds are stored in the cache, which outlives each test.
        cache.clear()
        # Fetch a feed no test looks at, so that the lookups made by
        # middleware are already cached and do not count against the tests.
        self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
            team=self.team_b.slug,
        )

    def test_team_calendar_query_count(self):
        # Middleware redirect check (1) + slug resolution (1) + last match (1)
        # + match query (1)
        with self.assertNumQueries(4):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
                division=self.division.slug,
                team=self.team_a.slug,
            )
        self.response_200(response)

    def test_division_calendar_query_count(self):
        # Middleware redirect check (1) + slug resolution (1) + last match (1)
        # + match query (1)
        with self.assertNumQueries(4):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
                division=self.division.slug,
            )
        self.response_200(response)

    def test_season_calendar_query_count(self):
        # Middleware redirect check (1) + slug resolution (1) + last match (1)
        # + match query (1)
        with self.assertNumQueries(4):
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
        # + last match (1) + match query (1)
        with self.assertNumQueries(7):
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
        self.assertNotIn("location", event)
        self.assertEqual(
            [str(c) for c in event["categories"].cats],
            [self.division.title, self.stage.title],
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
            str(event["url"]),
            "http://testserver{}".format(expected_path),
        )
        self.assertEqual(
            str(event["description"]),
            "{} ({})\n\nhttp://testserver{}".format(
                self.division.title, self.stage.title, expected_path
            ),
        )

    def _event_for_match_at(self, play_at):
        match = factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team_a,
            away_team=self.team_b,
            play_at=play_at,
        )
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
            team=self.team_a.slug,
        )
        self.response_200(response)
        _, events = self._parse_events(response)
        return next(e for e in events if e["uid"] == match.uuid.hex)

    def test_match_at_ground_location_names_ground_and_venue(self):
        ground = factories.GroundFactory.create(
            title="Field 3",
            venue__title="Sydney Olympic Park",
            venue__season=self.season,
            latlng="-33.8471,151.0685,15",
        )
        event = self._event_for_match_at(ground)

        self.assertEqual(str(event["location"]), "Field 3, Sydney Olympic Park")
        self.assertEqual(event["geo"].latitude, -33.8471)
        self.assertEqual(event["geo"].longitude, 151.0685)

    def test_match_at_ground_structured_location_for_apple_devices(self):
        ground = factories.GroundFactory.create(
            title="Field 3",
            venue__title="Sydney Olympic Park",
            venue__season=self.season,
            latlng="-33.8471,151.0685,15",
        )
        event = self._event_for_match_at(ground)

        prop = event["x-apple-structured-location"]
        self.assertEqual(str(prop), "geo:-33.8471,151.0685")
        self.assertEqual(prop.params["VALUE"], "URI")
        self.assertEqual(
            prop.params["X-TITLE"], "Field 3, Sydney Olympic Park"
        )

    def test_match_at_venue_location_names_venue(self):
        venue = factories.VenueFactory.create(
            title="Sydney Olympic Park",
            season=self.season,
            latlng="-33.8471,151.0685,15",
        )
        event = self._event_for_match_at(venue)

        self.assertEqual(str(event["location"]), "Sydney Olympic Park")
        self.assertEqual(event["geo"].latitude, -33.8471)

    def test_ground_without_coordinates_falls_back_to_venue(self):
        ground = factories.GroundFactory.create(
            title="Field 3",
            venue__title="Sydney Olympic Park",
            venue__season=self.season,
            venue__latlng="-33.8471,151.0685,15",
            latlng="",
        )
        event = self._event_for_match_at(ground)

        self.assertEqual(str(event["location"]), "Field 3, Sydney Olympic Park")
        self.assertEqual(event["geo"].latitude, -33.8471)
        self.assertEqual(event["geo"].longitude, 151.0685)

    def test_place_without_coordinates_omits_geo(self):
        ground = factories.GroundFactory.create(
            title="Field 3",
            venue__title="Sydney Olympic Park",
            venue__season=self.season,
            venue__latlng="",
            latlng="",
        )
        event = self._event_for_match_at(ground)

        self.assertEqual(str(event["location"]), "Field 3, Sydney Olympic Park")
        self.assertNotIn("geo", event)
        self.assertNotIn("x-apple-structured-location", event)

    def test_place_with_incomplete_coordinates_omits_geo(self):
        # LocationField stores "latitude,longitude,zoom"; a half-entered value
        # must not take the calendar down.
        venue = factories.VenueFactory.create(
            title="Sydney Olympic Park", season=self.season, latlng="-33.8471"
        )
        event = self._event_for_match_at(venue)

        self.assertEqual(str(event["location"]), "Sydney Olympic Park")
        self.assertNotIn("geo", event)

    def test_match_without_place_omits_location(self):
        event = self._event_for_match_at(None)

        self.assertNotIn("location", event)
        self.assertNotIn("geo", event)

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

    def _cache_control(self, response):
        return {
            directive.strip() for directive in response["Cache-Control"].split(",")
        }

    def _get_division_calendar(self):
        return self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=self.division.slug,
        )

    def _finish_all_matches(self):
        # The factory picks match times at random between 2008 and now, so
        # one could fall inside the grace period; make them all long past.
        Match.objects.filter(stage__division__season=self.season).update(
            datetime=timezone.now() - timedelta(days=30)
        )

    def _schedule_match_at(self, when, **kwargs):
        return factories.MatchFactory.create(
            stage=self.stage,
            home_team=self.team_a,
            away_team=self.team_b,
            datetime=when,
            date=when.date(),
            time=when.time(),
            **kwargs,
        )

    def test_calendar_cacheable_for_anonymous(self):
        self._schedule_match_at(timezone.now() + timedelta(days=1))
        response = self._get_division_calendar()
        self.response_200(response)
        self.assertEqual(
            self._cache_control(response),
            {"public", "max-age=600", "stale-while-revalidate=600"},
        )

    def test_calendar_with_all_matches_past_is_cacheable_for_a_week(self):
        self._finish_all_matches()
        self._schedule_match_at(timezone.now() - timedelta(days=4))
        response = self._get_division_calendar()
        self.response_200(response)
        self.assertEqual(
            self._cache_control(response),
            {"public", "max-age=604800", "stale-while-revalidate=604800"},
        )

    def test_calendar_is_live_until_the_grace_period_has_passed(self):
        self.division.matches.update(datetime=timezone.now() - timedelta(days=30))
        self._schedule_match_at(timezone.now() - timedelta(days=2))
        response = self._get_division_calendar()
        self.response_200(response)
        self.assertIn("max-age=600", self._cache_control(response))

    def test_calendar_without_matches_is_live(self):
        division = factories.DivisionFactory.create(season=self.season)
        response = self.get(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
            division=division.slug,
        )
        self.response_200(response)
        self.assertIn("max-age=600", self._cache_control(response))

    def test_archived_calendar_has_a_stable_dtstamp(self):
        last = self._schedule_match_at(timezone.now() - timedelta(days=10))
        self.division.matches.exclude(pk=last.pk).update(
            datetime=timezone.now() - timedelta(days=20)
        )
        last.refresh_from_db()

        first = self._get_division_calendar()
        with freeze_time(timezone.now() + timedelta(hours=5)):
            second = self._get_division_calendar()

        self.assertEqual(first.content, second.content)
        cal, events = self._parse_events(first)
        for event in events:
            self.assertEqual(event["dtstamp"].dt, last.datetime.replace(microsecond=0))

    def test_live_calendar_dtstamp_is_the_time_of_the_request(self):
        self._schedule_match_at(timezone.now() + timedelta(days=1))
        now = timezone.now()
        with freeze_time(now):
            response = self._get_division_calendar()
        cal, events = self._parse_events(response)
        for event in events:
            self.assertEqual(event["dtstamp"].dt, now.replace(microsecond=0))

    def test_calendar_private_for_superuser(self):
        superuser = factories.SuperUserFactory.create()
        with self.login(superuser):
            response = self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
                division=self.division.slug,
            )
        self.response_200(response)
        self.assertEqual(response["Cache-Control"], "private")

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        CACHE_MIDDLEWARE_SECONDS=0,
        MIDDLEWARE=[
            "django.middleware.cache.UpdateCacheMiddleware",
            *settings.MIDDLEWARE,
            "django.middleware.cache.FetchFromCacheMiddleware",
        ],
    )
    def test_calendar_cached_for_anonymous_not_served_to_superuser(self):
        draft_division = factories.DivisionFactory.create(
            season=self.season, draft=True
        )
        draft_stage = factories.StageFactory.create(division=draft_division)
        factories.MatchFactory.create_batch(stage=draft_stage, size=3)
        url = self.reverse(
            "competition:calendar",
            competition=self.competition.slug,
            season=self.season.slug,
        )

        # The anonymous feed is stored by the cache middleware...
        self.get(url)
        self.response_200()
        self.assertIn("Cookie", self.last_response["Vary"])
        cal, events = self._parse_events(self.last_response)
        self.assertEqual(len(events), 10)

        # ...but must not be what a superuser receives for the same URL.
        superuser = factories.SuperUserFactory.create()
        with self.login(superuser):
            self.get(url)
        self.response_200()
        cal, events = self._parse_events(self.last_response)
        self.assertEqual(len(events), 13)

    def test_archived_calendar_is_rendered_once(self):
        self._finish_all_matches()
        with CaptureQueriesContext(connection) as first_queries:
            first = self._get_division_calendar()
        with CaptureQueriesContext(connection) as second_queries:
            second = self._get_division_calendar()

        # The match query is not needed once the feed has been rendered.
        self.assertEqual(len(second_queries), len(first_queries) - 1)
        self.response_200(second)
        self.assertEqual(first.content, second.content)
        self.assertEqual(first["Cache-Control"], second["Cache-Control"])
        self.assertEqual(second["Content-Type"], "text/calendar")

    def test_live_calendar_is_never_rendered_from_the_cache(self):
        self._schedule_match_at(timezone.now() + timedelta(days=1))
        with CaptureQueriesContext(connection) as first_queries:
            self._get_division_calendar()
        with CaptureQueriesContext(connection) as second_queries:
            self._get_division_calendar()

        self.assertEqual(len(second_queries), len(first_queries))

    def test_archived_calendar_cache_follows_a_rescheduled_match(self):
        self._finish_all_matches()
        self._get_division_calendar()

        # A match moved into the future makes the feed live again at once.
        self._schedule_match_at(timezone.now() + timedelta(days=1))
        response = self._get_division_calendar()

        cal, events = self._parse_events(response)
        self.assertEqual(len(events), 11)
        self.assertIn("max-age=600", self._cache_control(response))

    def test_archived_calendar_cache_is_not_shared_with_superuser(self):
        draft_division = factories.DivisionFactory.create(
            season=self.season, draft=True
        )
        draft_stage = factories.StageFactory.create(division=draft_division)
        factories.MatchFactory.create_batch(stage=draft_stage, size=3)
        self._finish_all_matches()

        def get_season_calendar():
            return self.get(
                "competition:calendar",
                competition=self.competition.slug,
                season=self.season.slug,
            )

        get_season_calendar()
        cal, events = self._parse_events(self.last_response)
        self.assertEqual(len(events), 10)

        superuser = factories.SuperUserFactory.create()
        with self.login(superuser):
            get_season_calendar()
        self.response_200()
        cal, events = self._parse_events(self.last_response)
        self.assertEqual(len(events), 13)
        self.assertEqual(self.last_response["Cache-Control"], "private")

        # Nor does the superuser's feed replace the one stored for others.
        get_season_calendar()
        cal, events = self._parse_events(self.last_response)
        self.assertEqual(len(events), 10)

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
class DivisionFinalsQueryTests(TestCase):
    """
    Until a pool stage is over, its finals show placeholders such as
    "1st Pool A" in place of teams. Working one out used to look up the
    stage before, its pools and the stages after it, for every team of every
    final, which made the busiest public page of an event the slowest. The
    same query budget holds however many finals the division has.
    """

    @classmethod
    def _division(cls, title, finals):
        division = factories.DivisionFactory.create(season=cls.season, title=title)
        teams = factories.TeamFactory.create_batch(8, division=division)
        pools_stage = factories.StageFactory.create(
            division=division, title="Pools", order=1
        )
        kickoff = datetime(2026, 10, 6, 9, 0, tzinfo=ZoneInfo("UTC"))
        for number, members in enumerate((teams[:4], teams[4:]), start=1):
            pool = factories.StageGroupFactory.create(
                stage=pools_stage, title=f"Pool {number}"
            )
            for home, away in ((0, 1), (2, 3), (0, 2), (1, 3)):
                factories.MatchFactory.create(
                    stage=pools_stage,
                    stage_group=pool,
                    home_team=members[home],
                    away_team=members[away],
                    datetime=kickoff,
                    date=kickoff.date(),
                    time=kickoff.time(),
                )
        finals_stage = factories.StageFactory.create(
            division=division, title="Finals", order=2
        )
        finals_day = kickoff + timedelta(days=1)
        played = [
            factories.MatchFactory.create(
                stage=finals_stage,
                home_team=None,
                away_team=None,
                home_team_eval=f"G1P{number % 4 + 1}",
                away_team_eval=f"G2P{number % 4 + 1}",
                datetime=finals_day,
                date=finals_day.date(),
                time=kickoff.time(),
                label=f"Final {number + 1}",
            )
            for number in range(finals)
        ]
        # The winners of each pair of finals meet in a later round.
        later = finals_day + timedelta(hours=2)
        for number, (home, away) in enumerate(zip(played[::2], played[1::2]), 1):
            factories.MatchFactory.create(
                stage=finals_stage,
                home_team=None,
                away_team=None,
                home_team_eval="W",
                home_team_eval_related=home,
                away_team_eval="W",
                away_team_eval_related=away,
                datetime=later,
                date=later.date(),
                time=later.time(),
                label=f"Decider {number}",
            )
        # Playoffs between undecided teams: one named by a formula, one by
        # a label alone.
        for number in range(finals):
            factories.MatchFactory.create(
                stage=finals_stage,
                home_team=None,
                away_team=None,
                home_team_undecided=factories.UndecidedTeamFactory.create(
                    stage=finals_stage, formula=f"G1P{number % 4 + 1}", label=""
                ),
                away_team_undecided=factories.UndecidedTeamFactory.create(
                    stage=finals_stage, formula="", label="Host nation"
                ),
                datetime=later,
                date=later.date(),
                time=later.time(),
                label=f"Playoff {number + 1}",
            )
        return division

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create()
        cls.competition = cls.season.competition
        cls.few_finals = cls._division("Few Finals", finals=2)
        cls.many_finals = cls._division("Many Finals", finals=8)

    def test_placeholder_titles(self):
        final = self.few_finals.matches.get(label="Final 1")
        self.assertEqual(final.get_home_team(), {"title": "1st Pool 1"})
        self.assertEqual(final.get_away_team(), {"title": "1st Pool 2"})
        decider = self.few_finals.matches.get(label="Decider 1")
        self.assertEqual(decider.get_home_team(), {"title": "Winner Final 1"})
        self.assertEqual(decider.get_away_team(), {"title": "Winner Final 2"})
        playoff = self.few_finals.matches.get(label="Playoff 1")
        self.assertEqual(playoff.get_home_team(), {"title": "1st Pool 1"})
        self.assertEqual(playoff.get_away_team(), {"title": "Host nation"})

    def test_few_finals_query_count(self):
        self.assertGoodView(
            "competition:division",
            self.competition.slug,
            self.season.slug,
            self.few_finals.slug,
            test_query_count=17,
        )

    def test_many_finals_query_count(self):
        self.assertGoodView(
            "competition:division",
            self.competition.slug,
            self.season.slug,
            self.many_finals.slug,
            test_query_count=17,
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class SeasonThumbnailTests(TestCase):
    """
    A live-streamed season keeps the image it uploads to YouTube as its
    video thumbnail in the database. Every public page used to read it, for
    the season being viewed and for every season of every competition in
    the navigation, which slowed the whole site down. Only the thumbnail
    views need it.
    """

    THUMBNAIL = '"competition_season"."live_stream_thumbnail_image"'

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create(
            live_stream_thumbnail_image=b"\x89PNG" + b"\x00" * 1024
        )
        factories.SeasonFactory.create(
            competition=cls.season.competition,
            live_stream_thumbnail_image=b"\x89PNG" + b"\x00" * 1024,
        )
        cls.competition = cls.season.competition
        cls.division = factories.DivisionFactory.create(season=cls.season)
        cls.stage = factories.StageFactory.create(division=cls.division)
        cls.pool = factories.StageGroupFactory.create(stage=cls.stage)
        cls.team = factories.TeamFactory.create(division=cls.division)
        cls.match = factories.MatchFactory.create(
            stage=cls.stage, home_team=cls.team
        )

    def assertThumbnailNotRead(self, *args):
        with CaptureQueriesContext(connection) as queries:
            self.assertGoodView(*args)
        self.assertEqual(
            [q["sql"] for q in queries if self.THUMBNAIL in q["sql"]], []
        )

    def test_navigation(self):
        with CaptureQueriesContext(connection) as queries:
            seasons = [
                (season.short_title or season.title, season.slug)
                for competition in competition_site.competitions
                for season in competition.seasons.all()
            ]
        self.assertEqual(len(seasons), 2)
        # competitions, then their seasons
        self.assertEqual(len(queries), 2)
        self.assertEqual(
            [q["sql"] for q in queries if self.THUMBNAIL in q["sql"]], []
        )

    def test_navigation_carries_what_a_menu_needs(self):
        """
        A list of seasons links to each one, hides those that are disabled,
        shows when they run, and puts them in order, so none of that costs a
        query for every season. Everything else stays out.
        """
        navigation = {
            "competition_id",
            "title",
            "short_title",
            "slug",
            "enabled",
            "start_date",
            "order",
            "complete",
        }
        competition = competition_site.competitions.get(pk=self.competition.pk)
        seasons = list(competition.seasons.all())
        self.assertEqual(len(seasons), 2)
        with self.assertNumQueries(0):
            for season in seasons:
                for name in navigation:
                    getattr(season, name)
        for season in seasons:
            deferred = season.get_deferred_fields()
            self.assertEqual(deferred & navigation, set())
            self.assertIn("live_stream_thumbnail_image", deferred)
            self.assertIn("copy", deferred)

    def test_navigation_thumbnail_on_demand(self):
        competition = competition_site.competitions.get(pk=self.competition.pk)
        season = competition.seasons.get(pk=self.season.pk)
        self.assertEqual(
            bytes(season.live_stream_thumbnail_image), b"\x89PNG" + b"\x00" * 1024
        )

    def test_index(self):
        self.assertThumbnailNotRead("competition:index")

    def test_competition(self):
        self.assertThumbnailNotRead("competition:competition", self.competition.slug)

    def test_season(self):
        self.assertThumbnailNotRead(
            "competition:season", self.competition.slug, self.season.slug
        )

    def test_division(self):
        self.assertThumbnailNotRead(
            "competition:division",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
        )

    def test_stage(self):
        self.assertThumbnailNotRead(
            "competition:stage",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
            self.stage.slug,
        )

    def test_pool(self):
        self.assertThumbnailNotRead(
            "competition:pool",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
            self.stage.slug,
            self.pool.slug,
        )

    def test_team(self):
        self.assertThumbnailNotRead(
            "competition:team",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
            self.team.slug,
        )

    def test_match(self):
        self.assertThumbnailNotRead(
            "competition:match",
            self.competition.slug,
            self.season.slug,
            self.division.slug,
            self.match.pk,
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
@freeze_time("2026-10-08 03:00:00")
class ClubPageTests(TestCase):
    """
    A club's page lists its teams, each with its next match or, once it has
    played them all, its last one. Looking those up cost four queries per
    team, so the page slowed down with every team a nation entered. The same
    query budget now holds however many teams the club has.
    """

    @classmethod
    def _club(cls, title, teams):
        club = factories.ClubFactory.create(title=title)
        cls.competition.clubs.add(club)
        for number in range(teams):
            division = factories.DivisionFactory.create(season=cls.season)
            stage = factories.StageFactory.create(division=division)
            team = factories.TeamFactory.create(club=club, division=division)
            opponent = factories.TeamFactory.create(
                club=cls.opposition, division=division
            )
            days = (-2, -1, 1) if number else (-2, -1)  # the first has no more
            for day in days:
                when = datetime(2026, 10, 8, 9, 0, tzinfo=ZoneInfo("UTC"))
                when += timedelta(days=day)
                factories.MatchFactory.create(
                    stage=stage,
                    home_team=team,
                    away_team=opponent,
                    datetime=when,
                    date=when.date(),
                    time=when.time(),
                )
        return club

    @classmethod
    def setUpTestData(cls):
        cls.season = factories.SeasonFactory.create(timezone="UTC")
        cls.competition = cls.season.competition
        cls.opposition = factories.ClubFactory.create(title="Opposition")
        cls.competition.clubs.add(cls.opposition)
        cls.few = cls._club("Few", teams=2)
        cls.many = cls._club("Many", teams=6)

    def setUp(self):
        cache.clear()

    def assertNextOrLastMatch(self, teams):
        for team in teams:
            matches = team.matches.order_by("date", "time")
            if team.future().exists():
                expected = matches.filter(date=date(2026, 10, 9)).get()
            else:
                expected = matches.filter(date=date(2026, 10, 7)).get()
            self.assertEqual(team.next_match() or team.last_match(), expected)

    def test_next_or_last_match(self):
        self.assertGoodView(
            "competition:club",
            competition=self.competition.slug,
            season=self.season.slug,
            club=self.many.slug,
        )
        self.assertNextOrLastMatch(self.last_response.context["teams"])

    def test_prefetch_matches_the_lookup_per_team(self):
        teams = list(self.many.teams.all())
        prefetched = Team.prefetch_next_and_last_match(self.many.teams.all())
        self.assertEqual(
            [(t.next_match(), t.last_match()) for t in prefetched],
            [(t.next_match(), t.last_match()) for t in teams],
        )

    def test_few_teams_query_count(self):
        self.assertGoodView(
            "competition:club",
            competition=self.competition.slug,
            season=self.season.slug,
            club=self.few.slug,
            test_query_count=12,
        )

    def test_many_teams_query_count(self):
        self.assertGoodView(
            "competition:club",
            competition=self.competition.slug,
            season=self.season.slug,
            club=self.many.slug,
            test_query_count=12,
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class NextAndLastMatchTimeZoneTests(TestCase):
    """
    A team's next and last match are judged by kick-off instant, not by the
    venue's local date and time against the clock in UTC.

    On the finals day of an event in Japan (UTC+9), Australia played a semi
    final at 11:40 and the gold medal match at 16:20. At 19:05 in Japan,
    10:05 UTC, both still counted as to come, because 11:40 and 16:20 are
    later than 10:05, and the club page showed the semi final as the next
    match instead of the gold medal match as the last.
    """

    tokyo = ZoneInfo("Asia/Tokyo")

    @classmethod
    def _match(cls, stage, round, hour, minute, **kwargs):
        when = datetime(2026, 10, 10, hour, minute, tzinfo=cls.tokyo)
        return factories.MatchFactory.create(
            stage=stage,
            round=round,
            home_team=cls.team,
            away_team=cls.opponent,
            datetime=when,
            date=when.date(),
            time=when.time(),
            **kwargs,
        )

    @classmethod
    def setUpTestData(cls):
        season = factories.SeasonFactory.create(timezone="Asia/Tokyo")
        division = factories.DivisionFactory.create(season=season)
        stage = factories.StageFactory.create(division=division)
        cls.team = factories.TeamFactory.create(division=division)
        cls.opponent = factories.TeamFactory.create(division=division)
        cls.semi_final = cls._match(stage, 7, 11, 40)
        cls.final = cls._match(stage, 8, 16, 20)

    def assertNextAndLast(self, next_match, last_match):
        self.assertEqual(
            (self.team.next_match(), self.team.last_match()),
            (next_match, last_match),
        )
        (prefetched,) = Team.prefetch_next_and_last_match([self.team])
        self.assertEqual(
            (prefetched.next_match(), prefetched.last_match()),
            (next_match, last_match),
        )

    @freeze_time("2026-10-10 10:05:00")  # 19:05 in Japan
    def test_after_the_final(self):
        self.assertNextAndLast(None, self.final)

    @freeze_time("2026-10-10 05:00:00")  # 14:00 in Japan
    def test_between_the_semi_final_and_the_final(self):
        self.assertNextAndLast(self.final, self.semi_final)

    @freeze_time("2026-10-10 02:30:00")  # 11:30 in Japan
    def test_before_the_semi_final(self):
        self.assertNextAndLast(self.semi_final, None)

    @freeze_time("2026-10-10 02:50:00")  # 11:50 in Japan
    def test_still_next_until_fifteen_minutes_after_kick_off(self):
        self.assertNextAndLast(self.semi_final, None)

    @freeze_time("2026-10-10 10:05:00")  # 19:05 in Japan
    def test_kick_off_order_not_stage_order(self):
        # Match's default ordering puts stage ahead of time, so the earlier
        # semi final, in a stage ordered after the final's, would be taken
        # as the last match played.
        self.final.stage.order = 1
        self.final.stage.save()
        self.semi_final.stage = factories.StageFactory.create(
            division=self.team.division, order=2
        )
        self.semi_final.save()
        self.assertNextAndLast(None, self.final)


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


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class VenueViewTests(TestCase):
    """
    Public match listings for a venue and for each of its grounds.
    """

    def setUp(self):
        self.season = factories.SeasonFactory.create(timezone=ZoneInfo("UTC"))
        self.venue = factories.VenueFactory.create(
            season=self.season, title="Bill Hartley Fields"
        )
        self.ground_1 = factories.GroundFactory.create(
            venue=self.venue, title="Field 1"
        )
        self.ground_2 = factories.GroundFactory.create(
            venue=self.venue, title="Field 2"
        )
        self.division = factories.DivisionFactory.create(season=self.season)
        self.stage = factories.StageFactory.create(division=self.division)

    def _match(self, play_at, when, **kwargs):
        return factories.MatchFactory.create(
            stage=self.stage,
            play_at=play_at,
            datetime=when,
            **kwargs,
        )

    def _venue_args(self, *args):
        return (self.season.competition.slug, self.season.slug, self.venue.slug) + args

    def test_venue_lists_matches_on_every_ground(self):
        day_1 = datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC"))
        day_2 = datetime(2025, 3, 14, 11, tzinfo=ZoneInfo("UTC"))
        m1 = self._match(self.ground_1, day_1)
        m2 = self._match(self.ground_2, day_2)
        m3 = self._match(self.venue, day_2)
        self.assertGoodView("competition:venue", *self._venue_args())

        self.assertEqual(
            list(self.context["matches_by_date"].items()),
            [(date(2025, 3, 13), [m1]), (date(2025, 3, 14), [m2, m3])],
        )
        self.assertEqual(
            self.context["dates"], [date(2025, 3, 13), date(2025, 3, 14)]
        )
        self.assertIsNone(self.context["selected_date"])

        # grounds and days are linked from the venue page
        for ground in (self.ground_1, self.ground_2):
            self.assertResponseContains(
                'href="%s"'
                % self.reverse("competition:ground", *self._venue_args(ground.slug)),
                html=False,
            )
        day_url = self.reverse("competition:venue", *self._venue_args("20250314"))
        self.assertResponseContains('href="%s"' % day_url, html=False)
        # each match links to its detail page
        self.assertResponseContains(
            'href="%s"'
            % self.reverse(
                "competition:match",
                self.season.competition.slug,
                self.season.slug,
                self.division.slug,
                m1.pk,
            ),
            html=False,
        )

    def test_venue_single_day(self):
        m1 = self._match(
            self.ground_1, datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC"))
        )
        self._match(self.ground_2, datetime(2025, 3, 14, 10, tzinfo=ZoneInfo("UTC")))
        self.assertGoodView("competition:venue", *self._venue_args("20250313"))
        self.assertEqual(
            list(self.context["matches_by_date"].items()),
            [(date(2025, 3, 13), [m1])],
        )
        # the day navigation still offers every day at the venue
        self.assertEqual(
            self.context["dates"], [date(2025, 3, 13), date(2025, 3, 14)]
        )
        self.assertEqual(self.context["selected_date"], date(2025, 3, 13))

    def test_ground_lists_only_its_own_matches(self):
        when = datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC"))
        m1 = self._match(self.ground_1, when)
        self._match(self.ground_2, when)
        self._match(self.venue, when)
        self.assertGoodView(
            "competition:ground", *self._venue_args(self.ground_1.slug)
        )
        self.assertEqual(
            list(self.context["matches_by_date"].items()),
            [(date(2025, 3, 13), [m1])],
        )
        self.assertEqual(self.context["ground"], self.ground_1)
        self.assertResponseContains(
            'href="%s"' % self.reverse("competition:venue", *self._venue_args()),
            html=False,
        )

    def test_hidden_matches_excluded(self):
        when = datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC"))
        visible = self._match(self.ground_1, when)
        self._match(self.ground_1, when, is_bye=True)
        draft = factories.DivisionFactory.create(season=self.season, draft=True)
        factories.MatchFactory.create(
            stage__division=draft, play_at=self.ground_1, datetime=when
        )
        self.assertGoodView("competition:venue", *self._venue_args())
        self.assertEqual(
            list(self.context["matches_by_date"].items()),
            [(date(2025, 3, 13), [visible])],
        )

    def test_kick_off_in_local_time_of_ground(self):
        """
        A ground may keep its own timezone; its matches show local kick-off
        times even on the venue page, while other matches use the venue's.
        """
        self.venue.timezone = ZoneInfo("Europe/London")
        self.venue.save()
        self.ground_1.timezone = ZoneInfo("Asia/Tokyo")
        self.ground_1.save()
        self.ground_2.timezone = None
        self.ground_2.save()
        # 18:00 in Tokyo and 15:00 in London on the same day
        self._match(self.ground_1, datetime(2024, 1, 15, 9, tzinfo=ZoneInfo("UTC")))
        self._match(self.ground_2, datetime(2024, 1, 15, 15, tzinfo=ZoneInfo("UTC")))

        self.assertGoodView("competition:venue", *self._venue_args())
        self.assertResponseContains('<td class="time">6 p.m.</td>', html=False)
        self.assertResponseContains('<td class="time">3 p.m.</td>', html=False)

        self.assertGoodView(
            "competition:ground", *self._venue_args(self.ground_1.slug)
        )
        self.assertResponseContains('<td class="time">6 p.m.</td>', html=False)

    def test_season_links_to_venues(self):
        self.assertGoodView(
            "competition:season", self.season.competition.slug, self.season.slug
        )
        self.assertResponseContains(
            'href="%s"' % self.reverse("competition:venue", *self._venue_args()),
            html=False,
        )

    def test_empty_venue(self):
        self.assertGoodView("competition:venue", *self._venue_args())
        self.assertResponseContains("No matches have been scheduled here yet.")

    def test_day_without_matches_404(self):
        self._match(self.ground_1, datetime(2025, 3, 13, 10, tzinfo=ZoneInfo("UTC")))
        self.get("competition:venue", *self._venue_args("20250314"))
        self.response_404()
        self.get(
            "competition:ground", *self._venue_args(self.ground_2.slug, "20250313")
        )
        self.response_404()

    def test_invalid_date_404(self):
        self.get("competition:venue", *self._venue_args("20251399"))
        self.response_404()

    def test_venue_from_another_season_404(self):
        other = factories.VenueFactory.create()
        self.get(
            "competition:venue",
            self.season.competition.slug,
            self.season.slug,
            other.slug,
        )
        self.response_404()

    def test_ground_from_another_venue_404(self):
        other = factories.GroundFactory.create(venue__season=self.season)
        self.get("competition:ground", *self._venue_args(other.slug))
        self.response_404()
