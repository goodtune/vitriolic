# -*- coding: utf-8 -*-

"""
Test fixtures for AI-generated draw formats.

This module contains comprehensive test cases for various tournament scenarios
that AI models should be able to generate. Each fixture includes:
- Tournament constraints and requirements
- Expected draw format strings (compatible with DrawGenerator)
- Human-readable descriptions
- Validation criteria
"""

import itertools
import textwrap

from test_plus import TestCase

from tournamentcontrol.competition.draw.builders import build
from tournamentcontrol.competition.draw.schemas import (
    DivisionStructure,
    PoolFixture,
    StageFixture,
)
from tournamentcontrol.competition.models import Match, StageGroup
from tournamentcontrol.competition.tests.factories import SeasonFactory
from tournamentcontrol.competition.utils import (
    round_robin,
    round_robin_format,
    single_elimination_final_format,
)


class DrawFormatFixturesTestCase(TestCase):
    """Test cases for tournament draw format fixtures."""

    maxDiff = None

    def setUp(self):
        """Set up test data."""
        self.season = SeasonFactory.create()

    def test_simple_4_team_knockout(self):
        """Test case for a simple 4-team knockout tournament."""
        fixture = DivisionStructure(
            title="It's a Knockout!",
            teams=["NSW", "QLD", "WA", "VIC"],
            draw_formats={
                "Knockout": textwrap.dedent(
                    """\
                        ROUND
                        1: 1 vs 2 Semi 1
                        2: 3 vs 4 Semi 2
                        ROUND
                        3: L1 vs L2 Bronze
                        ROUND
                        4: W1 vs W2 Final"""
                )
            },
            stages=[
                StageFixture(
                    title="Knockout Finals",
                    draw_format_ref="Knockout",
                )
            ],
        )

        # Validate that no matches exist before building the tournament
        self.assertCountEqual(Match.objects.all(), [])

        # Build the tournament structure
        build(self.season, fixture)

        # Validate the structure
        expected_matches = [
            ("Knockout Finals", {"NSW", "QLD"}),
            ("Knockout Finals", {"WA", "VIC"}),
            ("Knockout Finals", {"Loser Semi 1", "Loser Semi 2"}),
            ("Knockout Finals", {"Winner Semi 1", "Winner Semi 2"}),
        ]
        actual_matches = [
            (m.stage.title, {m.home_team_title, m.away_team_title})
            for m in Match.objects.all()
        ]
        self.assertCountEqual(actual_matches, expected_matches)

    def test_two_pools_with_finals(self):
        """Test case for a simple two-pool format with finals."""
        fixture = DivisionStructure(
            title="Simple Two Pools with Finals",
            teams=[f"Team {i + 1}" for i in range(8)],
            draw_formats={
                "Pool Play": round_robin_format(4),
                "Finals": "\n".join(str(r) for r in single_elimination_final_format(2)),
            },
            stages=[
                StageFixture(
                    title="Pool Play",
                    draw_format=None,
                    pools=[
                        PoolFixture(
                            title="Pool A",
                            draw_format_ref="Pool Play",
                            teams=[0, 1, 2, 3],
                        ),
                        PoolFixture(
                            title="Pool B",
                            draw_format_ref="Pool Play",
                            teams=[4, 5, 6, 7],
                        ),
                    ],
                ),
                StageFixture(
                    title="Finals",
                    draw_format_ref="Finals",
                ),
            ],
        )

        # Validate that no matches exist before building the tournament
        self.assertCountEqual(Match.objects.all(), [])

        # Build the tournament structure
        build(self.season, fixture)

        expected_matches = [
            # Pool A
            ("Pool Play", {"Team 1", "Team 2"}),
            ("Pool Play", {"Team 3", "Team 4"}),
            ("Pool Play", {"Team 1", "Team 3"}),
            ("Pool Play", {"Team 2", "Team 4"}),
            ("Pool Play", {"Team 1", "Team 4"}),
            ("Pool Play", {"Team 2", "Team 3"}),
            # Pool B
            ("Pool Play", {"Team 5", "Team 6"}),
            ("Pool Play", {"Team 7", "Team 8"}),
            ("Pool Play", {"Team 5", "Team 7"}),
            ("Pool Play", {"Team 6", "Team 8"}),
            ("Pool Play", {"Team 5", "Team 8"}),
            ("Pool Play", {"Team 6", "Team 7"}),
            # Finals
            ("Finals", {"1st Group 1", "2nd Group 2"}),
            ("Finals", {"1st Group 2", "2nd Group 1"}),
            ("Finals", {"Winner Semi Final 1", "Winner Semi Final 2"}),
        ]

        # Validate the structure
        actual_matches = [
            (m.stage.title, {m.home_team_title, m.away_team_title})
            for m in Match.objects.all()
        ]
        self.assertCountEqual(actual_matches, expected_matches)

    def _regrouped_pool_format(self, teams):
        """Generate draw format for regrouped pool, excluding matches between teams from same original pool."""
        # Generate all round-robin matches - returns list of rounds, each round is list of pairings
        schedule = round_robin(teams)

        # Flatten to get all matches and filter out matches between teams from same original group
        valid_matches = []
        for round_pairings in schedule:
            for team1, team2 in round_pairings:
                # Skip bye matches (team = 0)
                if team1 == 0 or team2 == 0:
                    continue

                # Extract group number from team reference (e.g., "G1P1" -> "G1", "G5P3" -> "G5")
                group1 = team1[:2]  # "G1", "G2", etc.
                group2 = team2[:2]

                # Only include matches between teams from different original groups
                if group1 != group2:
                    valid_matches.append((team1, team2))

        # Convert to draw format string
        format_lines = []
        match_id = 1
        for i in range(0, len(valid_matches), 3):  # Group into rounds of 3 matches
            format_lines.append("ROUND")
            for j in range(3):
                if i + j < len(valid_matches):
                    home, away = valid_matches[i + j]
                    format_lines.append(f"{match_id}: {home} vs {away}")
                    match_id += 1

        return "\n".join(format_lines)

    def test_eccentric_24_team_format(self):
        """Test case for an eccentric 24-team format with multiple stages."""
        fixture = DivisionStructure(
            title="Eccentric 24-Team Format",
            teams=[f"Team {i}" for i in range(1, 25)],
            draw_formats={
                "Initial Pools": round_robin_format(4),
                # Pool G: 1st from groups 1&5, 2nd from group 3, 3rd from groups 1&5, 4th from group 3
                "Pool G": self._regrouped_pool_format(
                    ["G1P1", "G5P1", "G3P2", "G1P3", "G5P3", "G3P4"]
                ),
                # Pool H: 1st from groups 2&6, 2nd from group 4, 3rd from groups 2&6, 4th from group 4
                "Pool H": self._regrouped_pool_format(
                    ["G2P1", "G6P1", "G4P2", "G2P3", "G6P3", "G4P4"]
                ),
                # Pool I: 1st from group 3, 2nd from groups 1&5, 3rd from group 3, 4th from groups 1&5
                "Pool I": self._regrouped_pool_format(
                    ["G3P1", "G1P2", "G5P2", "G3P3", "G1P4", "G5P4"]
                ),
                # Pool J: 1st from group 4, 2nd from groups 2&6, 3rd from group 4, 4th from groups 2&6
                "Pool J": self._regrouped_pool_format(
                    ["G4P1", "G2P2", "G6P2", "G4P3", "G2P4", "G6P4"]
                ),
                "Championship Finals": "\n".join(
                    str(r) for r in single_elimination_final_format(4)
                ),
            },
            stages=[
                StageFixture(
                    title="Initial Pools",
                    pools=[
                        PoolFixture(
                            title=f"Pool {chr(ord('A') + i)}",  # A, B, C, D, E, F
                            draw_format_ref="Initial Pools",
                            teams=[j for j in range(i * 4, (i + 1) * 4)],
                        )
                        for i in range(6)  # 6 pools of 4
                    ],
                ),
                StageFixture(
                    title="Regrouped Pools",
                    pools=[
                        PoolFixture(
                            title=f"Pool {chr(ord('G') + p)}",  # G, H, I, J
                            draw_format_ref=f"Pool {chr(ord('G') + p)}",
                        )
                        for p in range(4)
                    ],
                ),
                StageFixture(
                    title="Championship Finals",
                    draw_format_ref="Championship Finals",
                ),
            ],
        )

        # Validate that no matches exist before building the tournament
        self.assertCountEqual(Match.objects.all(), [])

        # Build the tournament structure
        build(self.season, fixture)

        # Validate the pool structure
        expected_pools = [
            ("Initial Pools", "Pool A"),
            ("Initial Pools", "Pool B"),
            ("Initial Pools", "Pool C"),
            ("Initial Pools", "Pool D"),
            ("Initial Pools", "Pool E"),
            ("Initial Pools", "Pool F"),
            ("Regrouped Pools", "Pool G"),
            ("Regrouped Pools", "Pool H"),
            ("Regrouped Pools", "Pool I"),
            ("Regrouped Pools", "Pool J"),
        ]
        actual_pools = [
            (pool.stage.title, pool.title) for pool in StageGroup.objects.all()
        ]
        self.assertCountEqual(actual_pools, expected_pools)

        # Validate the match structure
        expected_matches = [
            # Pool A: Team 1, 2, 3, 4
            ("Initial Pools", {"Team 1", "Team 2"}),
            ("Initial Pools", {"Team 1", "Team 3"}),
            ("Initial Pools", {"Team 1", "Team 4"}),
            ("Initial Pools", {"Team 2", "Team 3"}),
            ("Initial Pools", {"Team 2", "Team 4"}),
            ("Initial Pools", {"Team 3", "Team 4"}),
            # Pool B: Team 5, 6, 7, 8
            ("Initial Pools", {"Team 5", "Team 6"}),
            ("Initial Pools", {"Team 5", "Team 7"}),
            ("Initial Pools", {"Team 5", "Team 8"}),
            ("Initial Pools", {"Team 6", "Team 7"}),
            ("Initial Pools", {"Team 6", "Team 8"}),
            ("Initial Pools", {"Team 7", "Team 8"}),
            # Pool C: Team 9, 10, 11, 12
            ("Initial Pools", {"Team 9", "Team 10"}),
            ("Initial Pools", {"Team 9", "Team 11"}),
            ("Initial Pools", {"Team 9", "Team 12"}),
            ("Initial Pools", {"Team 10", "Team 11"}),
            ("Initial Pools", {"Team 10", "Team 12"}),
            ("Initial Pools", {"Team 11", "Team 12"}),
            # Pool D: Team 13, 14, 15, 16
            ("Initial Pools", {"Team 13", "Team 14"}),
            ("Initial Pools", {"Team 13", "Team 15"}),
            ("Initial Pools", {"Team 13", "Team 16"}),
            ("Initial Pools", {"Team 14", "Team 15"}),
            ("Initial Pools", {"Team 14", "Team 16"}),
            ("Initial Pools", {"Team 15", "Team 16"}),
            # Pool E: Team 17, 18, 19, 20
            ("Initial Pools", {"Team 17", "Team 18"}),
            ("Initial Pools", {"Team 17", "Team 19"}),
            ("Initial Pools", {"Team 17", "Team 20"}),
            ("Initial Pools", {"Team 18", "Team 19"}),
            ("Initial Pools", {"Team 18", "Team 20"}),
            ("Initial Pools", {"Team 19", "Team 20"}),
            # Pool F: Team 21, 22, 23, 24
            ("Initial Pools", {"Team 21", "Team 22"}),
            ("Initial Pools", {"Team 21", "Team 23"}),
            ("Initial Pools", {"Team 21", "Team 24"}),
            ("Initial Pools", {"Team 22", "Team 23"}),
            ("Initial Pools", {"Team 22", "Team 24"}),
            ("Initial Pools", {"Team 23", "Team 24"}),
            # Pool G - Round 1
            ("Regrouped Pools", {"1st Group 1", "1st Group 5"}),
            ("Regrouped Pools", {"2nd Group 3", "3rd Group 1"}),
            ("Regrouped Pools", {"3rd Group 5", "4th Group 3"}),
            # Pool G - Round 2
            ("Regrouped Pools", {"1st Group 1", "2nd Group 3"}),
            # ("Regrouped Pools", {"3rd Group 5", "1st Group 5"}),
            ("Regrouped Pools", {"4th Group 3", "3rd Group 1"}),
            # Pool G - Round 3
            ("Regrouped Pools", {"1st Group 1", "3rd Group 5"}),
            # ("Regrouped Pools", {"4th Group 3", "2nd Group 3"}),
            ("Regrouped Pools", {"3rd Group 1", "1st Group 5"}),
            # Pool G - Round 4
            ("Regrouped Pools", {"1st Group 1", "4th Group 3"}),
            ("Regrouped Pools", {"3rd Group 1", "3rd Group 5"}),
            ("Regrouped Pools", {"1st Group 5", "2nd Group 3"}),
            # Pool G - Round 5
            # ("Regrouped Pools", {"1st Group 1", "3rd Group 1"}),
            ("Regrouped Pools", {"1st Group 5", "4th Group 3"}),
            ("Regrouped Pools", {"2nd Group 3", "3rd Group 5"}),
            # Pool H - Round 1
            ("Regrouped Pools", {"1st Group 2", "1st Group 6"}),
            ("Regrouped Pools", {"2nd Group 4", "3rd Group 2"}),
            ("Regrouped Pools", {"3rd Group 6", "4th Group 4"}),
            # Pool H - Round 2
            ("Regrouped Pools", {"1st Group 2", "2nd Group 4"}),
            # ("Regrouped Pools", {"3rd Group 6", "1st Group 6"}),
            ("Regrouped Pools", {"4th Group 4", "3rd Group 2"}),
            # Pool H - Round 3
            ("Regrouped Pools", {"1st Group 2", "3rd Group 6"}),
            # ("Regrouped Pools", {"4th Group 4", "2nd Group 4"}),
            ("Regrouped Pools", {"3rd Group 2", "1st Group 6"}),
            # Pool H - Round 4
            ("Regrouped Pools", {"1st Group 2", "4th Group 4"}),
            ("Regrouped Pools", {"3rd Group 2", "3rd Group 6"}),
            ("Regrouped Pools", {"1st Group 6", "2nd Group 4"}),
            # Pool H - Round 5
            # ("Regrouped Pools", {"1st Group 2", "3rd Group 2"}),
            ("Regrouped Pools", {"1st Group 6", "4th Group 4"}),
            ("Regrouped Pools", {"2nd Group 4", "3rd Group 6"}),
            # Pool I - Round 1
            ("Regrouped Pools", {"1st Group 3", "2nd Group 1"}),
            ("Regrouped Pools", {"2nd Group 5", "3rd Group 3"}),
            ("Regrouped Pools", {"4th Group 1", "4th Group 5"}),
            # Pool I - Round 2
            ("Regrouped Pools", {"1st Group 3", "2nd Group 5"}),
            # ("Regrouped Pools", {"4th Group 1", "2nd Group 1"}),
            ("Regrouped Pools", {"4th Group 5", "3rd Group 3"}),
            # Pool I - Round 3
            ("Regrouped Pools", {"1st Group 3", "4th Group 1"}),
            # ("Regrouped Pools", {"4th Group 5", "2nd Group 5"}),
            ("Regrouped Pools", {"3rd Group 3", "2nd Group 1"}),
            # Pool I - Round 4
            ("Regrouped Pools", {"1st Group 3", "4th Group 5"}),
            ("Regrouped Pools", {"3rd Group 3", "4th Group 1"}),
            ("Regrouped Pools", {"2nd Group 1", "2nd Group 5"}),
            # Pool I - Round 5
            # ("Regrouped Pools", {"1st Group 3", "3rd Group 3"}),
            ("Regrouped Pools", {"2nd Group 1", "4th Group 5"}),
            ("Regrouped Pools", {"2nd Group 5", "4th Group 1"}),
            # Pool J - Round 1
            ("Regrouped Pools", {"1st Group 4", "2nd Group 2"}),
            ("Regrouped Pools", {"2nd Group 6", "3rd Group 4"}),
            ("Regrouped Pools", {"4th Group 2", "4th Group 6"}),
            # Pool J - Round 2
            ("Regrouped Pools", {"1st Group 4", "2nd Group 6"}),
            # ("Regrouped Pools", {"4th Group 2", "2nd Group 2"}),
            ("Regrouped Pools", {"4th Group 6", "3rd Group 4"}),
            # Pool J - Round 3
            ("Regrouped Pools", {"1st Group 4", "4th Group 2"}),
            # ("Regrouped Pools", {"4th Group 6", "2nd Group 6"}),
            ("Regrouped Pools", {"3rd Group 4", "2nd Group 2"}),
            # Pool J - Round 4
            ("Regrouped Pools", {"1st Group 4", "4th Group 6"}),
            ("Regrouped Pools", {"3rd Group 4", "4th Group 2"}),
            ("Regrouped Pools", {"2nd Group 2", "2nd Group 6"}),
            # Pool J - Round 5
            # ("Regrouped Pools", {"1st Group 4", "3rd Group 4"}),
            ("Regrouped Pools", {"2nd Group 2", "4th Group 6"}),
            ("Regrouped Pools", {"2nd Group 6", "4th Group 2"}),
            # Championship Finals
            ("Championship Finals", {"1st Group 1", "2nd Group 4"}),
            ("Championship Finals", {"2nd Group 3", "1st Group 2"}),
            ("Championship Finals", {"1st Group 3", "2nd Group 2"}),
            ("Championship Finals", {"2nd Group 1", "1st Group 4"}),
            (
                "Championship Finals",
                {"Winner Quarter Final 4", "Winner Quarter Final 1"},
            ),
            (
                "Championship Finals",
                {"Winner Quarter Final 2", "Winner Quarter Final 3"},
            ),
            ("Championship Finals", {"Winner Semi Final 1", "Winner Semi Final 2"}),
        ]
        actual_matches = [
            (m.stage.title, {m.home_team_title, m.away_team_title})
            for m in Match.objects.all()
        ]
        self.assertCountEqual(actual_matches, expected_matches)

    def test_simple_redraw_format(self):
        fixure = DivisionStructure(
            title="Simple Redraw Format",
            teams=[f"Team {i + 1}" for i in range(4)],
            draw_formats={
                "Round Robin": round_robin_format(4),
                "Seeded Round Robin": round_robin_format(["P1", "P2", "P3", "P4"]),
            },
            stages=[
                StageFixture(
                    title="Seeding Stage",
                    draw_format_ref="Round Robin",
                ),
                StageFixture(
                    title="Finals Stage",
                    draw_format_ref="Seeded Round Robin",
                ),
            ],
        )

        # Validate that no matches exist before building the tournament
        self.assertCountEqual(Match.objects.all(), [])

        # Build the tournament structure
        build(self.season, fixure)

        # Validate the structure
        expected_matches = [
            ("Seeding Stage", {"Team 1", "Team 2"}),
            ("Seeding Stage", {"Team 1", "Team 3"}),
            ("Seeding Stage", {"Team 1", "Team 4"}),
            ("Seeding Stage", {"Team 2", "Team 3"}),
            ("Seeding Stage", {"Team 2", "Team 4"}),
            ("Seeding Stage", {"Team 3", "Team 4"}),
            ("Finals Stage", {"1st", "2nd"}),
            ("Finals Stage", {"1st", "3rd"}),
            ("Finals Stage", {"1st", "4th"}),
            ("Finals Stage", {"2nd", "3rd"}),
            ("Finals Stage", {"2nd", "4th"}),
            ("Finals Stage", {"3rd", "4th"}),
        ]
        actual_matches = [
            (m.stage.title, {m.home_team_title, m.away_team_title})
            for m in Match.objects.all()
        ]
        self.assertCountEqual(actual_matches, expected_matches)

    def test_deserialization(self):
        """Test case for deserializing a complex tournament structure."""
        fixture = DivisionStructure.model_validate(
            {
                "title": "Test Series",
                "teams": ["Australia", "New Zealand"],
                "draw_formats": {
                    "Best of Three": "ROUND\n1: 1 vs 2 1st Test\nROUND\n2: 1 vs 2 2nd Test\nROUND\n3: 1 vs 2 3rd Test"
                },
                "stages": [
                    {
                        "title": "Best of Three",
                        "draw_format_ref": "Best of Three",
                    },
                ],
            }
        )

        # Validate that no matches exist before building the tournament
        self.assertCountEqual(Match.objects.all(), [])

        # Build the tournament structure
        build(self.season, fixture)

        # Validate the structure
        expected_matches = [
            ("Best of Three", "1st Test", {"Australia", "New Zealand"}),
            ("Best of Three", "2nd Test", {"Australia", "New Zealand"}),
            ("Best of Three", "3rd Test", {"Australia", "New Zealand"}),
        ]
        actual_matches = [
            (m.stage.title, m.label, {m.home_team_title, m.away_team_title})
            for m in Match.objects.all()
        ]
        self.assertCountEqual(actual_matches, expected_matches)
