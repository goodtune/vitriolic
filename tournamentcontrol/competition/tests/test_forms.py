from test_plus import TestCase

from tournamentcontrol.competition.admin import next_related_factory
from tournamentcontrol.competition.forms import DrawFormatForm, PersonTransferForm, TeamForm
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


class PersonTransferFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.original_club = factories.ClubFactory.create(title="Original Club")
        cls.target_club = factories.ClubFactory.create(title="Target Club")
        cls.other_club = factories.ClubFactory.create(title="Other Club")
        cls.person = factories.PersonFactory.create(
            club=cls.original_club,
            first_name="John",
            last_name="Doe"
        )

    def test_form_excludes_current_club(self):
        """The form should exclude the person's current club from the choices."""
        form = PersonTransferForm(instance=self.person)
        club_choices = [choice[0] for choice in form.fields['club'].choices if choice[0]]
        
        self.assertNotIn(self.original_club.pk, club_choices)
        self.assertIn(self.target_club.pk, club_choices)
        self.assertIn(self.other_club.pk, club_choices)

    def test_transfer_to_different_club(self):
        """Test transferring a person to a different club."""
        form = PersonTransferForm(
            instance=self.person,
            data={"club": self.target_club.pk}
        )
        
        self.assertTrue(form.is_valid())
        saved_person = form.save()
        
        self.assertEqual(saved_person.club, self.target_club)
        self.assertEqual(saved_person.pk, self.person.pk)  # Same person
        
    def test_form_with_no_instance(self):
        """Test form behavior when no instance is provided."""
        form = PersonTransferForm()
        # Should show all clubs when no instance is provided
        club_choices = [choice[0] for choice in form.fields['club'].choices if choice[0]]
        
        self.assertIn(self.original_club.pk, club_choices)
        self.assertIn(self.target_club.pk, club_choices)
        self.assertIn(self.other_club.pk, club_choices)
