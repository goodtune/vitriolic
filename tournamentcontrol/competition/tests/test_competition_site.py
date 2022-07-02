import unittest
from datetime import datetime

from django.test.utils import override_settings
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase
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
        matches = factories.MatchFactory.create_batch(
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
