from test_plus import TestCase

from tournamentcontrol.competition.admin import next_related_factory
from tournamentcontrol.competition.forms import (
    DrawFormatForm,
    MatchEditForm,
    TeamBulkCreateForm,
    TeamBulkCreateFormSet,
    TeamForm,
)
from tournamentcontrol.competition.models import Team
from tournamentcontrol.competition.tests import factories


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


class TeamBulkCreateFormTests(TestCase):
    """Test cases for TeamBulkCreateForm and TeamBulkCreateFormSet."""

    @classmethod
    def setUpTestData(cls):
        cls.division = factories.DivisionFactory.create()

    def test_bulk_create_form_valid(self):
        """Valid title produces a valid form."""
        # Create an instance with division set to avoid validation errors
        instance = Team(division=self.division)
        form = TeamBulkCreateForm(data={"title": "Team Alpha", "order": 1}, instance=instance)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["title"], "Team Alpha")
        self.assertEqual(form.cleaned_data["order"], 1)

    def test_bulk_create_form_empty_title(self):
        """Empty title is invalid."""
        instance = Team(division=self.division)
        form = TeamBulkCreateForm(data={"title": "", "order": 1}, instance=instance)
        self.assertFormError(form, "title", ["This field is required."])

    def test_bulk_create_formset_assigns_division(self):
        """Formset assigns division to each created team."""
        from django.forms.models import modelformset_factory

        FormSet = modelformset_factory(
            Team,
            form=TeamBulkCreateForm,
            formset=TeamBulkCreateFormSet,
            extra=2,
            can_delete=False,
        )

        data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-title": "Team Alpha",
            "form-0-order": "1",
            "form-1-title": "Team Beta",
            "form-1-order": "2",
        }

        formset = FormSet(data, division=self.division)
        self.assertTrue(formset.is_valid(), formset.errors)

        teams = formset.save()
        self.assertEqual(len(teams), 2)
        self.assertEqual(teams[0].division, self.division)
        self.assertEqual(teams[0].title, "Team Alpha")
        self.assertEqual(teams[1].division, self.division)
        self.assertEqual(teams[1].title, "Team Beta")

    def test_bulk_create_formset_prepopulates_order(self):
        """Formset pre-populates order field with sequential values."""
        from django.forms.models import modelformset_factory

        # Create existing teams
        factories.TeamFactory.create(division=self.division, order=1)
        factories.TeamFactory.create(division=self.division, order=2)

        FormSet = modelformset_factory(
            Team,
            form=TeamBulkCreateForm,
            formset=TeamBulkCreateFormSet,
            extra=3,
            can_delete=False,
        )

        formset = FormSet(division=self.division)

        # Check that order values start from 3 (max existing + 1)
        self.assertEqual(formset.forms[0].initial["order"], 3)
        self.assertEqual(formset.forms[1].initial["order"], 4)
        self.assertEqual(formset.forms[2].initial["order"], 5)
