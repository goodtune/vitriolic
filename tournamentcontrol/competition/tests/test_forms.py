from django import forms
from test_plus import TestCase

from tournamentcontrol.competition.admin import next_related_factory
from tournamentcontrol.competition.forms import (
    ClubEditForm,
    DivisionForm,
    DrawFormatForm,
    MatchEditForm,
    TeamForm,
)
from tournamentcontrol.competition.models import Club, Team
from tournamentcontrol.competition.tests import factories


class DivisionFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.division = factories.DivisionFactory.create()

    def _form(self, **data):
        defaults = {
            "title": self.division.title,
            "points_formula_0": "3",
            "points_formula_1": "2",
            "points_formula_2": "1",
            "points_formula_3": "",
            "points_formula_4": "",
            "points_formula_5": "",
            "bonus_points_formula": "",
            "forfeit_for_score": "5",
            "forfeit_against_score": "0",
            "include_forfeits_in_played": "1",
            "games_per_day": "2",
            "color": "#ffffff",
        }
        defaults.update(data)
        return DivisionForm(instance=self.division, data=defaults)

    def test_bonus_points_formula_margin(self):
        "A bonus formula may refer to the margin and diff of the match."
        form = self._form(
            bonus_points_formula="[win=1, score_against=0, forfeit_for=0: 1] "
            "+ [loss=1, margin<=2: 1] + [diff>=10: 1]"
        )
        self.assertFormError(form, "bonus_points_formula", [])
        self.assertEqual(
            "[win=1, score_against=0, forfeit_for=0: 1] "
            "+ [loss=1, margin<=2: 1] + [diff>=10: 1]",
            form.save().bonus_points_formula,
        )

    def test_bonus_points_formula_unknown_identifier(self):
        "A bonus formula must not refer to values a ladder entry does not have."
        form = self._form(bonus_points_formula="[tries>=4: 1] + [loss=1, margin<=7: 1]")
        self.assertFormError(
            form,
            "bonus_points_formula",
            ["Unknown identifier(s) in this points formula: tries."],
        )

    def test_points_formula_identifiers_limited_to_widget(self):
        """
        The points formula editor is a coefficient per identifier in
        ``valid_ladder_identifiers``; any other identifier would be dropped
        the next time the division is edited, so it must be rejected.
        """
        form = self._form()
        form.cleaned_data = {"points_formula": "3*win + 2*draw + 1*loss"}
        self.assertEqual(form.clean_points_formula(), "3*win + 2*draw + 1*loss")
        form.cleaned_data = {"points_formula": "3*win + diff"}
        with self.assertRaisesMessage(
            forms.ValidationError,
            "Unknown identifier(s) in this points formula: diff.",
        ):
            form.clean_points_formula()

    def test_bonus_points_formula_invalid_syntax(self):
        form = self._form(bonus_points_formula="loss=1: 1")
        self.assertFormError(
            form,
            "bonus_points_formula",
            ["Syntax of this points formula is invalid."],
        )


class ClubEditFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.club = factories.ClubFactory.create()
        cls.members = factories.PersonFactory.create_batch(3, club=cls.club)
        cls.outsider = factories.PersonFactory.create()

    def _data(self, **data):
        defaults = {
            "title": self.club.title,
            "slug": self.club.slug,
            "status": self.club.status,
        }
        defaults.update(data)
        return defaults

    def test_primary_offers_only_the_clubs_people(self):
        form = ClubEditForm(instance=self.club)
        self.assertCountEqual(form.fields["primary"].queryset, self.members)

    def test_primary_still_offers_the_current_primary(self):
        "A primary contact who has since moved on is not rejected."
        self.club.primary = self.outsider
        self.club.save()
        form = ClubEditForm(instance=self.club)
        self.assertCountEqual(
            form.fields["primary"].queryset, [*self.members, self.outsider]
        )

    def test_new_club_offers_nobody(self):
        form = ClubEditForm(instance=Club())
        self.assertQuerySetEqual(form.fields["primary"].queryset, [])

    def test_member_can_be_the_primary(self):
        form = ClubEditForm(
            instance=self.club, data=self._data(primary=self.members[0].pk)
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().primary, self.members[0])

    def test_outsider_cannot_be_the_primary(self):
        form = ClubEditForm(
            instance=self.club, data=self._data(primary=self.outsider.pk)
        )
        self.assertFormError(
            form,
            "primary",
            ["Select a valid choice. That choice is not one of the available choices."],
        )


class TeamFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.clubs = factories.ClubFactory.create_batch(5)
        cls.division = factories.DivisionFactory.create()
        cls.division.season.competition.clubs.set(cls.clubs)
        # Prepare a new team instance that we can use for tests related to creating new teams.
        cls.new_team = next_related_factory(Team, cls.division)

    def test_empty_club_requires_title(self):
        "When the club is empty, a title is required."
        form = TeamForm(division=self.division, instance=self.new_team, data={})
        self.assertFormError(form, "title", ["You must specify a name for this team."])

    def test_populated_club_defaults_title(self):
        "When the club is populated, a title is not required."
        form = TeamForm(
            division=self.division,
            instance=self.new_team,
            data={"club": self.clubs[0].pk},
        )
        self.assertFormError(form, "title", [])
        self.assertQuerySetEqual(Team.objects.all(), [form.save()])

    def test_drawformat_invalid(self):
        "When the draw format is invalid, an error is raised."
        form = DrawFormatForm(
            data={
                "name": "Test Draw Format",
                "text": "ROUND\n1: 1v2\n",
                "teams": 4,
                "is_final": "0",
            },
        )
        self.assertFormError(
            form,
            "text",
            ["Draw formula is invalid: line(s) '1' are not in the correct format."],
        )


class MatchEditFormTests(TestCase):
    """Test cases for MatchEditForm, particularly around BinaryField handling."""

    @classmethod
    def setUpTestData(cls):
        # Create stages with and without live streaming enabled
        cls.stage_with_live_stream = factories.StageFactory.create(
            division__season__live_stream=True
        )
        cls.stage_without_live_stream = factories.StageFactory.create(
            division__season__live_stream=False
        )

        cls.home_team_with_ls = factories.TeamFactory.create(
            division=cls.stage_with_live_stream.division
        )
        cls.away_team_with_ls = factories.TeamFactory.create(
            division=cls.stage_with_live_stream.division
        )

        cls.home_team_without_ls = factories.TeamFactory.create(
            division=cls.stage_without_live_stream.division
        )
        cls.away_team_without_ls = factories.TeamFactory.create(
            division=cls.stage_without_live_stream.division
        )

    def test_match_creation_with_empty_thumbnail_image(self):
        """Test that match can be created with empty string for thumbnail image."""
        instance = factories.MatchFactory.build(stage=self.stage_with_live_stream)

        # Simulate form submission with empty string for live_stream_thumbnail_image
        # This matches the POST data pattern from the error report in issue #240.
        form = MatchEditForm(
            instance=instance,
            data={
                "home_team": self.home_team_with_ls.pk,
                "away_team": self.away_team_with_ls.pk,
                "label": "",
                "round": "",
                "date": "",
                "include_in_ladder": "0",
                "videos_0": "",
                "videos_1": "",
                "videos_2": "",
                "videos_3": "",
                "videos_4": "",
                "live_stream_thumbnail_image": "",
            },
        )

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        match = form.save()
        self.assertIsNotNone(match.pk)
        self.assertIsNone(match.live_stream_thumbnail_image)

    def test_match_edit_preserves_existing_thumbnail(self):
        """Test that editing a match with existing thumbnail and empty string preserves it."""
        # Create a match with a thumbnail
        match = factories.MatchFactory.create(
            stage=self.stage_with_live_stream,
            home_team=self.home_team_with_ls,
            away_team=self.away_team_with_ls,
            live_stream_thumbnail_image=b"fake image data",
        )
        original_thumbnail = match.live_stream_thumbnail_image

        # Edit the match with empty string for thumbnail (simulating form submission)
        form = MatchEditForm(
            instance=match,
            data={
                "home_team": self.home_team_with_ls.pk,
                "away_team": self.away_team_with_ls.pk,
                "label": "Updated",
                "round": "",
                "date": "",
                "include_in_ladder": "1",
                "videos_0": "",
                "videos_1": "",
                "videos_2": "",
                "videos_3": "",
                "videos_4": "",
                "live_stream_thumbnail_image": "",
            },
        )

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        form.save()
        match.refresh_from_db()
        self.assertEqual(match.live_stream_thumbnail_image, original_thumbnail)
        self.assertEqual(match.label, "Updated")

    def test_thumbnail_field_removed_when_season_not_live_streamed(self):
        """Test that live_stream_thumbnail_image field is removed when season is not live streamed."""
        instance = factories.MatchFactory.build(stage=self.stage_without_live_stream)

        form = MatchEditForm(instance=instance)

        # Field should not be present in the form
        self.assertNotIn("live_stream_thumbnail_image", form.fields)

    def test_match_creation_without_live_stream_enabled(self):
        """Test that match can be created when season does not have live streaming enabled."""
        instance = factories.MatchFactory.build(stage=self.stage_without_live_stream)

        # Form should work without the live_stream_thumbnail_image field
        form = MatchEditForm(
            instance=instance,
            data={
                "home_team": self.home_team_without_ls.pk,
                "away_team": self.away_team_without_ls.pk,
                "label": "",
                "round": "",
                "date": "",
                "include_in_ladder": "0",
                "videos_0": "",
                "videos_1": "",
                "videos_2": "",
                "videos_3": "",
                "videos_4": "",
            },
        )

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        match = form.save()
        self.assertIsNotNone(match.pk)
        self.assertIsNone(match.live_stream_thumbnail_image)
