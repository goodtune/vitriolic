"""Comprehensive test coverage for stage_group_position parser (Issues #182, #183).

Tests the fix for AttributeError crash on invalid input and ensures comprehensive
coverage of all stage_group_position parsing scenarios.
"""

from test_plus import TestCase

from tournamentcontrol.competition.tests.factories import (
    DivisionFactory,
    MatchFactory,
    StageFactory,
    StageGroupFactory,
    TeamFactory,
    UndecidedTeamFactory,
)
from tournamentcontrol.competition.utils import stage_group_position_re


class StageGroupPositionRegexTests(TestCase):
    """
    Direct tests for the stage_group_position regex patterns.
    Tests the core regex matching behavior.
    """

    def test_valid_regex_patterns(self):
        """Test that valid stage_group_position patterns match correctly."""
        valid_patterns = [
            ("P1", (None, None, "1")),
            ("P10", (None, None, "10")),
            ("G1P1", (None, "1", "1")),
            ("G2P5", (None, "2", "5")),
            ("S1G1P1", ("1", "1", "1")),
            ("S2G3P4", ("2", "3", "4")),
            ("S10G20P30", ("10", "20", "30")),
            # These zero-based patterns are actually valid according to the regex
            ("P0", (None, None, "0")),
            ("G0P1", (None, "0", "1")),
            ("S0G1P1", ("0", "1", "1")),
            ("S1P1", ("1", None, "1")),  # Stage without group is valid
        ]

        for pattern, expected_groups in valid_patterns:
            with self.subTest(pattern=pattern):
                match = stage_group_position_re.match(pattern)
                self.assertIsNotNone(match, f"Pattern '{pattern}' should match")

                stage, group, position = match.groups()
                expected_stage, expected_group, expected_position = expected_groups

                self.assertEqual(stage, expected_stage)
                self.assertEqual(group, expected_group)
                self.assertEqual(position, expected_position)

    def test_invalid_regex_patterns(self):
        """Test that invalid stage_group_position patterns do not match."""
        invalid_patterns = [
            "BAD1",  # Short version of original crash case
            "Team A",  # Shortened version
            "INVALID",
            "BadPat",  # Shortened to fit varchar constraints
            "P",  # Missing position number
            "G1",  # Missing position
            "S1G1",  # Missing position
            "1P1",  # Invalid format
            "GP1",  # Missing group number
            "SG1P1",  # Missing stage number
            "",  # Empty string
            "ABC123",
            "123",
        ]

        for pattern in invalid_patterns:
            with self.subTest(pattern=pattern):
                match = stage_group_position_re.match(pattern)
                self.assertIsNone(match, f"Pattern '{pattern}' should not match")

    def test_partial_matches_not_accepted(self):
        """Test that partial matches at start of string don't count as valid."""
        partial_patterns = [
            "P1Extra",  # Valid start but extra text
            "G1P1More",
            "S1G1P1AndMore",
            "P1 ",  # Trailing space
            " P1",  # Leading space
        ]

        for pattern in partial_patterns:
            with self.subTest(pattern=pattern):
                match = stage_group_position_re.match(pattern)
                # These might match but should not be considered complete/valid
                if match:
                    # If it matches, the full match should not equal the input
                    # indicating the pattern didn't consume the whole string
                    self.assertNotEqual(match.group(0), pattern)


class StageGroupPositionModelFixTests(TestCase):
    """
    Tests for the AttributeError fix in Match model methods.
    Tests the actual usage scenarios that were crashing.
    """

    def setUp(self):
        """Set up test fixtures for model testing."""
        self.division = DivisionFactory.create()
        self.stage1 = StageFactory.create(division=self.division, order=1)
        self.stage2 = StageFactory.create(
            division=self.division, order=2, follows=self.stage1
        )

        # Create actual teams for more realistic testing
        self.team1 = TeamFactory.create(division=self.division)
        self.team2 = TeamFactory.create(division=self.division)

        # Create pools for valid formula testing
        self.pool1 = StageGroupFactory.create(stage=self.stage1)
        self.pool2 = StageGroupFactory.create(stage=self.stage1)

    def test_no_crash_on_invalid_formulas_get_team_methods(self):
        """Test Match.get_home_team() and get_away_team() don't crash on invalid formulas."""
        invalid_formulas = [
            "BAD1",  # Short version of original crash case
            "Team A",  # Shortened version
            "INVALID",
            "BadForm",  # Shortened to fit varchar(10)
            "",
        ]

        for home_formula in invalid_formulas:
            for away_formula in invalid_formulas[
                :2
            ]:  # Limit combinations for performance
                with self.subTest(home=home_formula, away=away_formula):
                    match = MatchFactory.create(
                        stage=self.stage2,
                        home_team=None,
                        away_team=None,
                        home_team_eval=home_formula,
                        away_team_eval=away_formula,
                    )

                    # These should not raise AttributeError with 'groups' message
                    home_result = match.get_home_team()
                    away_result = match.get_away_team()

                    # An unreadable formula is shown as written, and no
                    # formula at all is "to be advised".
                    self.assertEqual(home_result, {"title": home_formula or "TBA"})
                    self.assertEqual(away_result, {"title": away_formula})

    def test_no_crash_on_invalid_formulas_eval_method(self):
        """Test Match.eval() method doesn't crash on invalid formulas."""
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="BAD1",  # Short version of original crash case
            away_team_eval="Team B",  # Shortened version
        )

        # This should not raise AttributeError
        home_team, away_team = match.eval()

        self.assertEqual(home_team, {"title": "BAD1"})
        self.assertEqual(away_team, {"title": "Team B"})

    def test_valid_formulas_still_work_correctly(self):
        """Test that valid formulas continue to work after the fix."""
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="P1",
            away_team_eval="P2",
        )

        home_result = match.get_home_team()
        away_result = match.get_away_team()

        # Should return proper ordinal positions
        self.assertEqual(home_result, {"title": "1st"})
        self.assertEqual(away_result, {"title": "2nd"})

    def test_complex_valid_formulas(self):
        """Test valid formulas with stage and group references."""
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="S1G1P1",  # Stage 1, Group 1, Position 1
            away_team_eval="G2P1",  # Group 2, Position 1
        )

        # These should work without crashing
        home_result = match.get_home_team()
        away_result = match.get_away_team()

        # Should return ordinal positions with pool info
        self.assertIn("1st", home_result["title"])
        self.assertIn("1st", away_result["title"])

    def test_edge_cases_dont_crash(self):
        """Test edge cases that might cause issues."""
        edge_cases = [
            None,  # Null values
            "",  # Empty strings
            "   ",  # Whitespace
            "0",  # Numbers that don't match pattern
            "P",  # Incomplete patterns
            "G1",  # Missing position
        ]

        for formula in edge_cases:
            with self.subTest(formula=repr(formula)):
                match = MatchFactory.create(
                    stage=self.stage2,
                    home_team=None,
                    away_team=None,
                    home_team_eval=formula,
                    away_team_eval="P1",  # Valid formula for comparison
                )

                # Should handle gracefully
                home_result = match.get_home_team()
                away_result = match.get_away_team()

                self.assertEqual(
                    home_result, {"title": (formula or "").strip() or "TBA"}
                )
                self.assertEqual(away_result, {"title": "1st"})


class ExplicitStageEvalTests(TestCase):
    """
    ``Match.eval`` resolves a positional reference with an explicit stage
    (``S1P1``) against that stage's ladder, not the ladder of the stage the
    match's own stage follows.
    """

    def test_explicit_stage_resolves_against_that_stage(self):
        division = DivisionFactory.create()
        teams = [TeamFactory.create(division=division) for _ in range(3)]
        stage1 = StageFactory.create(division=division, order=1)
        stage2 = StageFactory.create(division=division, order=2, follows=stage1)
        stage3 = StageFactory.create(division=division, order=3, follows=stage2)

        # Stage 1 ladder: teams[0] beats everyone, so leads.
        for home, away in ((teams[0], teams[1]), (teams[0], teams[2])):
            MatchFactory.create(
                stage=stage1,
                home_team=home,
                away_team=away,
                home_team_score=5,
                away_team_score=0,
            )
        # Stage 2 ladder: only teams[1] and teams[2] play, teams[1] leads.
        MatchFactory.create(
            stage=stage2,
            home_team=teams[1],
            away_team=teams[2],
            home_team_score=5,
            away_team_score=0,
        )

        final = MatchFactory.create(
            stage=stage3,
            home_team=None,
            away_team=None,
            home_team_eval="S1P1",
            away_team_eval="P1",
        )

        self.assertEqual(final.eval(), (teams[0], teams[1]))

    def test_zero_numbers_are_unresolved(self):
        """
        ``S0``, ``G0`` and ``P0`` pass the formula pattern but refer to
        nothing; they must fall back to the descriptive result rather than
        crash on a negative queryset index or pick a team from the end of a
        list.
        """
        division = DivisionFactory.create()
        teams = [TeamFactory.create(division=division) for _ in range(2)]
        stage1 = StageFactory.create(division=division, order=1)
        pool = StageGroupFactory.create(stage=stage1)
        pool.teams.set(teams)
        stage2 = StageFactory.create(division=division, order=2, follows=stage1)
        MatchFactory.create(
            stage=stage1,
            stage_group=pool,
            home_team=teams[0],
            away_team=teams[1],
            home_team_score=5,
            away_team_score=0,
        )

        for formula in ("S0P1", "G1P0", "G0P1"):
            with self.subTest(formula=formula):
                match = MatchFactory.create(
                    stage=stage2,
                    home_team=None,
                    away_team=None,
                    home_team_eval=formula,
                    away_team_eval="G1P1",
                )
                home, away = match.eval()
                self.assertNotIsInstance(home, type(teams[0]))
                self.assertEqual(away, teams[0])

    def test_winner_reference_without_related_match_is_unresolved(self):
        division = DivisionFactory.create()
        stage1 = StageFactory.create(division=division, order=1)
        stage2 = StageFactory.create(division=division, order=2, follows=stage1)
        match = MatchFactory.create(
            stage=stage2,
            home_team=None,
            away_team=None,
            home_team_eval="W",
            home_team_eval_related=None,
            away_team_eval="L",
            away_team_eval_related=None,
        )
        self.assertEqual(match.eval(), ({"title": "Winner"}, {"title": "Loser"}))


class FirstStageReferenceTests(TestCase):
    """
    A position with no stage in it (P1, G1P2) is a place on the ladder of the
    stage before. The first stage of a division has no stage before it, so
    the reference names nothing: it is shown as written, as a reference that
    cannot be read is, and never resolves to a team.
    """

    def setUp(self):
        self.stage = StageFactory.create(order=1)
        self.teams = TeamFactory.create_batch(2, division=self.stage.division)

    def test_reference_is_shown_as_written(self):
        match = MatchFactory.create(
            stage=self.stage,
            home_team=None,
            away_team=None,
            home_team_eval="P1",
            away_team_eval="G1P2",
        )
        self.assertEqual(match.get_home_team(), {"title": "P1"})
        self.assertEqual(match.get_away_team(), {"title": "G1P2"})
        self.assertEqual(match.get_home_team_plain(), "P1")
        self.assertEqual(match.get_away_team_plain(), "G1P2")
        self.assertEqual(str(match), "P1 vs G1P2")

    def test_undecided_team_is_shown_as_its_formula(self):
        home = UndecidedTeamFactory.create(stage=self.stage, formula="G1P2", label="")
        away = UndecidedTeamFactory.create(stage=self.stage, formula="P1", label="")
        match = MatchFactory.create(
            stage=self.stage,
            home_team=None,
            away_team=None,
            home_team_undecided=home,
            away_team_undecided=away,
        )
        self.assertEqual(str(home), "G1P2")
        self.assertEqual(match.get_home_team(), {"title": "G1P2"})
        self.assertEqual(match.get_away_team_plain(), "P1")
        self.assertEqual(str(match), "G1P2 vs P1")

    def test_undecided_team_may_be_any_team_of_the_division(self):
        undecided = UndecidedTeamFactory.create(
            stage=self.stage, formula="G1P2", label=""
        )
        self.assertCountEqual(undecided.choices.all(), self.teams)

    def test_eval_leaves_the_position_unresolved(self):
        """
        ``eval`` resolves the winner of a match in the same stage, but not a
        position: there is no stage before to take it from, and this stage's
        own ladder is not that stage.
        """
        semi = MatchFactory.create(
            stage=self.stage,
            home_team=self.teams[0],
            away_team=self.teams[1],
            home_team_score=5,
            away_team_score=2,
            label="Semi 1",
        )
        final = MatchFactory.create(
            stage=self.stage,
            home_team=None,
            away_team=None,
            home_team_eval="W",
            home_team_eval_related=semi,
            away_team_eval="P1",
        )
        self.assertEqual(final.eval(), (self.teams[0], {"title": "P1"}))


class ExplicitStageReferenceTests(TestCase):
    """
    A position may name its stage: ``S1G1P1`` is first place in pool 1 of the
    division's first stage, wherever the match is. Its title names that
    stage's places, the places ``eval`` fills it from, not those of the stage
    before the match's own.
    """

    @classmethod
    def setUpTestData(cls):
        cls.division = DivisionFactory.create()
        cls.teams = TeamFactory.create_batch(4, division=cls.division)
        cls.pools = StageFactory.create(division=cls.division, title="Pools", order=1)
        cls.pool = StageGroupFactory.create(stage=cls.pools, title="Pool 1")
        cls.pool.teams.set(cls.teams)
        cls.quarters = StageFactory.create(
            division=cls.division, title="Quarters", order=2, follows=cls.pools
        )
        # Quarters feeds two stages, so a place on its ladder names it.
        cls.semis = StageFactory.create(
            division=cls.division, title="Semis", order=3, follows=cls.quarters
        )
        StageFactory.create(
            division=cls.division, title="Plate", order=4, follows=cls.quarters
        )

    def play_pools(self):
        """Teams finish in pool 1 and on the ladder in the order they were made."""
        for home, away in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
            MatchFactory.create(
                stage=self.pools,
                stage_group=self.pool,
                home_team=self.teams[home],
                away_team=self.teams[away],
                home_team_score=5,
                away_team_score=0,
            )

    def test_title_names_the_stage_in_the_formula(self):
        match = MatchFactory.create(
            stage=self.semis,
            home_team=None,
            away_team=None,
            home_team_eval="S1G1P1",
            away_team_eval="S1P2",
        )
        self.assertEqual(match.get_home_team(), {"title": "1st Pool 1"})
        self.assertEqual(match.get_away_team(), {"title": "2nd"})
        self.assertEqual(match.get_home_team_plain(), "1st Pool 1")
        self.assertEqual(match.get_away_team_plain(), "2nd")
        self.assertEqual(str(match), "1st Pool 1 vs 2nd")

    def test_undecided_team_names_the_stage_in_its_formula(self):
        """``UndecidedTeam.title`` and the match's title agree."""
        undecided = UndecidedTeamFactory.create(
            stage=self.semis, formula="S1G1P1", label=""
        )
        match = MatchFactory.create(
            stage=self.semis,
            home_team=None,
            away_team=None,
            home_team_undecided=undecided,
            away_team_eval="S1P2",
        )
        self.assertEqual(str(undecided), "1st Pool 1")
        self.assertEqual(match.get_home_team(), {"title": "1st Pool 1"})
        self.assertEqual(str(match), "1st Pool 1 vs 2nd")

    def test_eval_agrees_with_the_title(self):
        match = MatchFactory.create(
            stage=self.semis,
            home_team=None,
            away_team=None,
            home_team_eval="S1G1P1",
            away_team_eval="S1P2",
        )
        self.assertEqual(match.eval(), ({"title": "1st Pool 1"}, {"title": "2nd"}))

        self.play_pools()
        # Quarters has a ladder of its own, led by the last team of the pool.
        MatchFactory.create(
            stage=self.quarters,
            home_team=self.teams[3],
            away_team=self.teams[2],
            home_team_score=5,
            away_team_score=0,
        )
        self.assertEqual(match.eval(), (self.teams[0], self.teams[1]))

    def test_stage_that_does_not_exist_is_shown_as_written(self):
        """
        The division has four stages: ``S9`` is past the last, and stages
        are numbered from one, so ``S0`` names none.
        """
        match = MatchFactory.create(
            stage=self.semis,
            home_team=None,
            away_team=None,
            home_team_eval="S9P1",
            away_team_eval="S0G1P1",
        )
        self.assertEqual(match.get_home_team(), {"title": "S9P1"})
        self.assertEqual(match.get_away_team(), {"title": "S0G1P1"})
        self.assertEqual(match.get_home_team_plain(), "S9P1")
        self.assertEqual(match.get_away_team_plain(), "S0G1P1")
        self.assertEqual(match.eval(), ({"title": "S9P1"}, {"title": "S0G1P1"}))

    def test_first_stage_names_its_own_ladder(self):
        """
        ``S1P1`` in the first stage is first place on that stage's ladder,
        where ``eval`` takes it from, unlike ``P1``, which names the stage
        before (see ``FirstStageReferenceTests``).
        """
        self.play_pools()
        played = self.pools.matches.get(
            home_team=self.teams[2], away_team=self.teams[3]
        )
        final = MatchFactory.create(
            stage=self.pools,
            home_team=None,
            away_team=None,
            home_team_eval="S1P1",
            away_team_eval="W",
            away_team_eval_related=played,
        )
        self.assertEqual(final.get_home_team(), {"title": "1st"})
        self.assertEqual(final.get_home_team_plain(), "1st")
        self.assertEqual(final.eval(), (self.teams[0], self.teams[2]))


class StageGroupPositionIntegrationTests(TestCase):
    """
    Integration tests that verify stage_group_position works correctly
    in realistic competition scenarios.
    """

    def setUp(self):
        """Set up a realistic two-stage competition."""
        self.division = DivisionFactory.create()

        # Stage 1: Round Robin with two groups
        self.stage1 = StageFactory.create(division=self.division, order=1)
        self.group1 = StageGroupFactory.create(stage=self.stage1)
        self.group2 = StageGroupFactory.create(stage=self.stage1)

        # Stage 2: Finals
        self.stage2 = StageFactory.create(
            division=self.division, order=2, follows=self.stage1
        )

        # Add teams to groups
        self.teams_g1 = [TeamFactory.create(division=self.division) for _ in range(4)]
        self.teams_g2 = [TeamFactory.create(division=self.division) for _ in range(4)]

        for team in self.teams_g1:
            self.group1.teams.add(team)
        for team in self.teams_g2:
            self.group2.teams.add(team)

    def test_realistic_finals_scenario(self):
        """Test a realistic finals match between group winners."""
        # Final match: Winner of Group 1 vs Winner of Group 2
        final_match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G1P1",  # Group 1, Position 1 (Winner)
            away_team_eval="G2P1",  # Group 2, Position 1 (Winner)
            label="Final",
        )

        home_result = final_match.get_home_team()
        away_result = final_match.get_away_team()

        # Should return ordinal positions with pool info
        self.assertIn("1st", home_result["title"])
        self.assertIn("1st", away_result["title"])

    def test_semifinal_scenario(self):
        """Test semifinal matches with valid formulas."""
        # Semi 1: G1P1 vs G2P2
        # Semi 2: G1P2 vs G2P1

        semi1 = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G1P1",
            away_team_eval="G2P2",
            label="Semifinal 1",
        )

        semi2 = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G1P2",
            away_team_eval="G2P1",
            label="Semifinal 2",
        )

        # Test both semifinals - check that ordinal positions are included
        home_semi1 = semi1.get_home_team()["title"]
        away_semi1 = semi1.get_away_team()["title"]
        home_semi2 = semi2.get_home_team()["title"]
        away_semi2 = semi2.get_away_team()["title"]

        self.assertIn("1st", home_semi1)
        self.assertIn("2nd", away_semi1)
        self.assertIn("2nd", home_semi2)
        self.assertIn("1st", away_semi2)

    def test_invalid_group_reference_handled_gracefully(self):
        """Test that invalid group references don't crash in realistic scenarios."""
        # Try to reference a group that doesn't exist
        match = MatchFactory.create(
            stage=self.stage2,
            home_team=None,
            away_team=None,
            home_team_eval="G5P1",  # Group 5 doesn't exist (only have groups 1 and 2)
            away_team_eval="G1P1",  # Valid reference
            label="Invalid Group Test",
        )

        # Should handle gracefully without crashing
        home_result = match.get_home_team()
        away_result = match.get_away_team()

        # Invalid group should return the formula as title (graceful fallback)
        self.assertEqual(home_result, {"title": "G5P1"})
        # Valid group should work normally
        self.assertIn("1st", away_result["title"])
