import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from django.test.utils import override_settings
from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.factories import SuperUserFactory


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
            datetime=datetime(2013, 11, 22, 10, tzinfo=timezone.utc),
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
class StreamInstructionsViewTests(TestCase):
    """Test the stream-instructions view for both markdown and HTML formats."""

    user_factory = SuperUserFactory

    def setUp(self):
        """Set up a superuser for permission-protected views."""
        self.user = self.make_user()

    def test_stream_instructions_md_endpoint(self):
        """Test that .md endpoint returns 200 and correct content-type."""
        season = factories.SeasonFactory.create()

        with self.login(self.user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "md",
            )
            self.response_200()
            self.assertEqual(self.last_response["Content-Type"], "text/markdown")
            self.assertResponseContains("# Live Streaming", html=False)
            self.assertResponseContains(season.competition.title, html=False)
            self.assertResponseContains(season.title, html=False)

    def test_stream_instructions_html_endpoint(self):
        """Test that .html endpoint returns 200 and correct content-type."""
        season = factories.SeasonFactory.create()

        with self.login(self.user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "html",
            )
            self.response_200()
            self.assertEqual(
                self.last_response["Content-Type"], "text/html; charset=utf-8"
            )
            self.assertResponseContains("<h1>Live Streaming</h1>")
            # Check for the section heading without the special dash characters
            self.assertResponseContains(
                "<h2>5. Operating the FIT Stream Controller</h2>"
            )

    def test_stream_instructions_internal_links_via_url_tags(self):
        """Test that internal links are rendered via {% url %} and are fully qualified URI."""
        season = factories.SeasonFactory.create()

        with self.login(self.user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "html",
            )
            self.response_200()

            # Check that internal links use {% url %} syntax and are fully qualified
            # The links now have the URL as the link text in markdown format [url](url)
            runsheet_url = self.reverse(
                "competition:runsheet", season.competition.slug, season.slug
            )
            results_url = self.reverse(
                "competition:results", season.competition.slug, season.slug
            )
            stream_url = self.reverse(
                "competition:stream", season.competition.slug, season.slug
            )
            
            self.assertResponseContains(f'<a href="{runsheet_url}">{runsheet_url}</a>')
            self.assertResponseContains(f'<a href="{results_url}">{results_url}</a>')
            self.assertResponseContains(f'<a href="{stream_url}">{stream_url}</a>')

    def test_stream_instructions_with_ground_stream_key(self):
        """Test that when ground has stream_key, it's displayed instead of placeholder."""
        season = factories.SeasonFactory.create()
        ground = factories.GroundFactory.create(
            venue__season=season, stream_key="test-stream-key-123"
        )

        with self.login(self.user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "md",
            )
            self.response_200()
            # Check for the real stream key from the ground
            self.assertResponseContains("test-stream-key-123", html=False)
            # Check that the ground title is included in the YouTube row (format changed)
            self.assertResponseContains(f"YouTube - {ground.title}", html=False)
            # Should not contain placeholder for YouTube key since we have a real one
            self.assertResponseNotContains(
                "| YouTube | rtmp://a.rtmp.youtube.com/live2 | ``PLACEHOLDER`` |"
            )

    def test_stream_instructions_missing_db_values_remain_placeholder(self):
        """Test that missing DB values remain as placeholders."""
        season = factories.SeasonFactory.create()
        # Don't create any ground with stream_key

        with self.login(self.user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "md",
            )
            self.response_200()
            # Should contain placeholders for static values in template
            self.assertResponseContains("INSERT STREAM KEY", html=False)
            # Should contain company name placeholder
            self.assertResponseContains("COMPANY NAME", html=False)
            # Should contain contact placeholders
            self.assertResponseContains("INSERT NAME", html=False)

    def test_stream_instructions_requires_login(self):
        """Test that unauthenticated users cannot access stream instructions."""
        season = factories.SeasonFactory.create()

        # Try accessing without login
        self.get(
            "competition:stream-instructions",
            season.competition.slug,
            season.slug,
            "md",
        )
        self.response_302()  # Should redirect to login

    def test_stream_instructions_requires_match_permissions(self):
        """Test that users without Match permissions cannot access stream instructions."""
        season = factories.SeasonFactory.create()
        regular_user = UserFactory.create()  # Regular user without Match permissions

        # Try accessing with regular user
        with self.login(regular_user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "md",
            )
            self.response_403()  # Should get 403 Forbidden

    def test_stream_instructions_html_requires_permissions(self):
        """Test that HTML endpoint also requires same permissions."""
        season = factories.SeasonFactory.create()
        regular_user = UserFactory.create()  # Regular user without Match permissions

        # Try accessing with regular user
        with self.login(regular_user):
            self.get(
                "competition:stream-instructions",
                season.competition.slug,
                season.slug,
                "html",
            )
            self.response_403()  # Should get 403 Forbidden
