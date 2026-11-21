"""
A shirt number of 0 is a number. It is legal in some sports, so only a
negative number, or none at all for someone who played, is refused.
"""

from django.core.exceptions import ValidationError
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import (
    SimpleScoreMatchStatistic,
    TeamAssociation,
)
from tournamentcontrol.competition.tests import factories


class StatisticNumberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.match = factories.MatchFactory.create()
        cls.person = factories.PersonFactory.create()

    def statistic(self, **kwargs):
        return SimpleScoreMatchStatistic(
            match=self.match, player=self.person, played=1, **kwargs
        )

    def test_person_who_played_in_number_zero_is_accepted(self):
        self.assertEqual(self.statistic(number=0, points=2).full_clean(), None)

    def test_person_who_played_with_no_number_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.statistic(number=None).full_clean()
        self.assertEqual(
            refused.exception.message_dict,
            {"number": ["A person who played must have a shirt number."]},
        )

    def test_negative_number_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.statistic(number=-1).full_clean()
        self.assertEqual(
            refused.exception.message_dict,
            {"number": ["Ensure this value is greater than or equal to 0."]},
        )


class TeamAssociationNumberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.team = factories.TeamFactory.create()
        cls.person = factories.PersonFactory.create(club=cls.team.club)

    def association(self, number):
        return TeamAssociation(team=self.team, person=self.person, number=number)

    def test_number_zero_is_accepted(self):
        self.assertEqual(self.association(0).full_clean(), None)

    def test_negative_number_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.association(-7).full_clean()
        self.assertEqual(
            refused.exception.message_dict,
            {"number": ["Ensure this value is greater than or equal to 0."]},
        )


@per_shell
class NumberZeroIsShownTests(TestCase):
    """Pages that show a shirt number show 0, not the mark of no number."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.team = factories.TeamFactory.create()
        self.season = self.team.division.season
        factories.TeamAssociationFactory.create(
            team=self.team,
            person=factories.PersonFactory.create(club=self.team.club),
            number=0,
            is_player=True,
        )

    def test_season_report(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:fixja:competition:season:report",
                self.season.competition_id,
                self.season.pk,
            )
        content = " ".join(self.last_response.content.decode().split())
        self.assertEqual((content.count("#0"), content.count("TBA")), (1, 0))
