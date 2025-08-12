from test_plus import TestCase

from tournamentcontrol.competition.admin import next_related_factory
from tournamentcontrol.competition.forms import DrawFormatForm, TeamForm
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
