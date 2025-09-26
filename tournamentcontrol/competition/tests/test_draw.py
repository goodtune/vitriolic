import itertools
from datetime import date, datetime
from zoneinfo import ZoneInfo

from test_plus import TestCase

from tournamentcontrol.competition.draw.generators import (
    tournament_date_generator,
    weekly_date_generator,
)
from tournamentcontrol.competition.tests.factories import StageFactory


class DrawGenerationUtilities(TestCase):
    def setUp(self):
        super().setUp()
        self.stage = StageFactory.create(
            division__games_per_day=3,
            division__season__start_date=date(2022, 8, 2),
        )

    def test_tournament_date_generator(self):
        with self.assertLogs("tournamentcontrol.competition.draw", "DEBUG") as cm:
            res = tournament_date_generator(self.stage)
            self.assertCountEqual(
                itertools.islice(res, 10),
                [
                    date(2022, 8, 2),
                    date(2022, 8, 2),
                    date(2022, 8, 2),
                    date(2022, 8, 3),
                    date(2022, 8, 3),
                    date(2022, 8, 3),
                    date(2022, 8, 4),
                    date(2022, 8, 4),
                    date(2022, 8, 4),
                    date(2022, 8, 5),
                ],
            )

        self.assertCountEqual(
            cm.output,
            [
                f"DEBUG:tournamentcontrol.competition.draw.generators:"
                f"Tournament date generator: '{self.stage.title}' (2022-08-02 00:00:00+00:00:3)",
            ],
        )

    def test_weekly_date_generator(self):
        with self.assertLogs("tournamentcontrol.competition.draw", "DEBUG") as cm:
            res = weekly_date_generator(self.stage)
            self.assertCountEqual(
                itertools.islice(res, 5),
                [
                    datetime(2022, 8, 2, tzinfo=ZoneInfo("UTC")),
                    datetime(2022, 8, 9, tzinfo=ZoneInfo("UTC")),
                    datetime(2022, 8, 16, tzinfo=ZoneInfo("UTC")),
                    datetime(2022, 8, 23, tzinfo=ZoneInfo("UTC")),
                    datetime(2022, 8, 30, tzinfo=ZoneInfo("UTC")),
                ],
            )

        self.assertCountEqual(
            cm.output,
            [
                f"DEBUG:tournamentcontrol.competition.draw.generators:"
                f"Weekly date generator: '{self.stage.title}' (2022-08-02 00:00:00+00:00)",
            ],
        )
