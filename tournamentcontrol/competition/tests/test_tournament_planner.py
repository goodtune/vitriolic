from django.test import override_settings
from test_plus import TestCase

from tournamentcontrol.competition.draw.algorithms import seeded_tournament
from tournamentcontrol.competition.tests import factories

# Twelve teams over three days at up to three games a day needs two pools.
TEAMS = 12
DAYS = 3
MAX_PER_DAY = 3

# Serpent seeding of twelve teams into two pools, ordered by top seed.
EXPECTED_POOLS = [
    [1, 4, 5, 8, 9, 12],
    [2, 3, 6, 7, 10, 11],
]


class SeededTournamentTests(TestCase):
    def test_team_names(self):
        teams = [f"Team {n}" for n in range(1, TEAMS + 1)]
        res = seeded_tournament(teams, DAYS, MAX_PER_DAY)
        self.assertEqual(
            [[f"Team {n}" for n in pool] for pool in EXPECTED_POOLS],
            [[str(team) for team in pool] for pool in res["pools"]],
        )

    def test_team_instances(self):
        division = factories.DivisionFactory.create()
        teams = [
            factories.TeamFactory.create(division=division, order=n)
            for n in range(1, TEAMS + 1)
        ]
        res = seeded_tournament(division.teams.order_by("order"), DAYS, MAX_PER_DAY)
        self.assertEqual(
            [[teams[n - 1] for n in pool] for pool in EXPECTED_POOLS],
            res["pools"],
        )

    def test_odd_number_of_teams(self):
        teams = [f"Team {n}" for n in range(1, TEAMS)]
        res = seeded_tournament(teams, DAYS, MAX_PER_DAY)
        self.assertEqual(
            [
                ["Team 1", "Team 4", "Team 5", "Team 8", "Team 9"],
                ["Team 2", "Team 3", "Team 6", "Team 7", "Team 10", "Team 11"],
            ],
            [[str(team) for team in pool] for pool in res["pools"]],
        )


@override_settings(ROOT_URLCONF="tournamentcontrol.competition.tests.urls")
class TournamentPlannerViewTests(TestCase):
    def test_division_with_multiple_pools(self):
        division = factories.DivisionFactory.create()
        for n in range(1, TEAMS + 1):
            factories.TeamFactory.create(division=division, order=n, title=f"Seed {n}")
        self.get(
            "calculator:division",
            data={
                "team_hook": division.pk,
                "days_available": DAYS,
                "max_per_day": MAX_PER_DAY,
                "min_per_day": 1,
            },
        )
        self.response_200()
        self.assertResponseContains('<h4 class="list-group-item active">Pool 2</h4>')
        self.assertResponseContains(
            '<p class="list-group-item">Seed 1 <span class="badge">1</span></p>'
        )
