from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from test_plus import TestCase

from tournamentcontrol.competition.models import (
    SimpleScoreMatchStatistic,
    TeamAssociation,
)
from tournamentcontrol.competition.tests import factories


def add_roster(team, size):
    """People on ``team``, each with a statistic for every match it plays."""
    links = []
    for number in range(1, size + 1):
        person = factories.PersonFactory.create(club=team.club)
        links.append(
            factories.TeamAssociationFactory.create(
                team=team, person=person, number=number, is_player=True
            )
        )
    return links


def score(match, links, played=1, points=2, mvp=1):
    for link in links:
        SimpleScoreMatchStatistic.objects.create(
            match=match,
            player=link.person,
            number=link.number,
            played=played,
            points=points,
            mvp=mvp,
        )


class TeamAssociationStatisticsTests(TestCase):
    def setUp(self):
        self.stage = factories.StageFactory.create()
        self.team = factories.TeamFactory.create(division=self.stage.division)
        self.other = factories.TeamFactory.create(division=self.stage.division)
        self.third = factories.TeamFactory.create(division=self.stage.division)

    def test_annotated_totals_are_those_statistics_would_compute(self):
        links = add_roster(self.team, 3)
        for _ in range(2):
            match = factories.MatchFactory.create(
                stage=self.stage, home_team=self.team, away_team=self.other
            )
            score(match, links[:2], points=3, mvp=0)
        # played for another team: not part of this team's totals
        elsewhere = factories.MatchFactory.create(
            stage=self.stage, home_team=self.other, away_team=self.third
        )
        score(elsewhere, links[:1], points=9, mvp=9)

        annotated = {
            link.pk: link.statistics()
            for link in self.team.people.with_statistics(self.team)
        }

        for link in links:
            with self.subTest(number=link.number):
                self.assertEqual(annotated[link.pk], link.statistics())
        self.assertEqual(annotated[links[0].pk], {"played": 2, "points": 6, "mvp": 0})
        self.assertEqual(
            annotated[links[2].pk], {"played": None, "points": None, "mvp": None}
        )

    def test_annotated_statistics_make_no_further_queries(self):
        links = add_roster(self.team, 4)
        match = factories.MatchFactory.create(
            stage=self.stage, home_team=self.team, away_team=self.other
        )
        score(match, links)
        roster = list(self.team.people.with_statistics(self.team))

        with self.assertNumQueries(0):
            totals = [link.statistics() for link in roster]

        self.assertEqual(totals, [{"played": 1, "points": 2, "mvp": 1}] * 4)

    def test_unannotated_associations_still_compute_their_own(self):
        links = add_roster(self.team, 1)
        match = factories.MatchFactory.create(
            stage=self.stage, home_team=self.team, away_team=self.other
        )
        score(match, links)

        self.assertEqual(
            TeamAssociation.objects.get(pk=links[0].pk).statistics(),
            {"played": 1, "points": 2, "mvp": 1},
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class TeamPageQueryTests(TestCase):
    def queries(self, team):
        def get():
            self.assertGoodView(
                "competition:team",
                team.division.season.competition.slug,
                team.division.season.slug,
                team.division.slug,
                team.slug,
            )

        get()  # the first request of all fills caches the later ones use
        with CaptureQueriesContext(connection) as queries:
            get()
        return len(queries)

    def test_queries_do_not_grow_with_the_size_of_the_roster(self):
        stage = factories.StageFactory.create()
        small = factories.TeamFactory.create(division=stage.division)
        large = factories.TeamFactory.create(division=stage.division)
        opponent = factories.TeamFactory.create(division=stage.division)
        for team, size in ((small, 2), (large, 14)):
            links = add_roster(team, size)
            match = factories.MatchFactory.create(
                stage=stage, home_team=team, away_team=opponent
            )
            score(match, links)

        self.assertEqual(self.queries(large), self.queries(small))

    def test_totals_are_shown_for_each_player(self):
        stage = factories.StageFactory.create()
        team = factories.TeamFactory.create(division=stage.division)
        opponent = factories.TeamFactory.create(division=stage.division)
        links = add_roster(team, 2)
        match = factories.MatchFactory.create(
            stage=stage, home_team=team, away_team=opponent
        )
        score(match, links[:1], played=1, points=5, mvp=3)

        self.assertGoodView(
            "competition:team",
            stage.division.season.competition.slug,
            stage.division.season.slug,
            stage.division.slug,
            team.slug,
        )

        self.assertResponseContains(
            '<td class="statistic played">1</td>', html=True
        )
        self.assertResponseContains(
            '<td class="statistic touchdowns">5</td>', html=True
        )
