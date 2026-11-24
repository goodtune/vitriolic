"""
The names a person reads in the admin: in a row's menu, in the breadcrumbs, and
in the confirmation before something is deleted.

An object with no ``__str__`` of its own is named ``SeasonExclusionDate object
(4)``, and an object named by its key ``#4``. Neither tells a person which
object it is, so each of these is named by what the lists show of it.
"""

import datetime

from django.utils import translation
from test_plus import TestCase

from tournamentcontrol.competition.models import (
    DivisionExclusionDate,
    MatchScoreSheet,
    SeasonExclusionDate,
    SeasonMatchTime,
)
from tournamentcontrol.competition.tests import factories


class ExclusionDateNameTests(TestCase):
    def test_a_season_exclusion_date_is_named_by_its_date(self):
        exclusion = SeasonExclusionDate(date=datetime.date(2026, 12, 25))
        self.assertEqual(str(exclusion), "Friday 25 December 2026")

    def test_a_division_exclusion_date_is_named_by_its_date(self):
        exclusion = DivisionExclusionDate(date=datetime.date(2027, 1, 1))
        self.assertEqual(str(exclusion), "Friday 1 January 2027")

    def test_the_date_is_in_the_language_in_use(self):
        exclusion = SeasonExclusionDate(date=datetime.date(2026, 12, 25))
        with translation.override("fr"):
            self.assertEqual(str(exclusion), "vendredi 25 décembre 2026")

    def test_an_exclusion_date_not_yet_given_a_date_has_no_name(self):
        self.assertEqual(str(SeasonExclusionDate()), "")


class SeasonMatchTimeNameTests(TestCase):
    def test_a_time_slot_is_named_by_its_first_kick_off(self):
        time_slot = SeasonMatchTime(start=datetime.time(9, 5), interval=30, count=4)
        self.assertEqual(str(time_slot), "09:05")

    def test_a_time_slot_at_midnight_is_named(self):
        self.assertEqual(str(SeasonMatchTime(start=datetime.time(0, 0))), "00:00")

    def test_a_time_slot_not_yet_given_a_start_has_no_name(self):
        self.assertEqual(str(SeasonMatchTime()), "")


class MatchScoreSheetNameTests(TestCase):
    def test_a_score_sheet_is_named_by_its_match(self):
        match = factories.MatchFactory.create(
            home_team__title="Eagles", away_team__title="Hawks"
        )
        # What Cloudinary names an upload says nothing to a person.
        score_sheet = MatchScoreSheet.objects.create(
            match=match, image="s3gtb4jsjlafyynh7xzx"
        )
        self.assertEqual(str(score_sheet), "Score sheet for Eagles vs Hawks")
