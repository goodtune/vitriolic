"""
Paths that only need to know whether rows exist ask with ``exists()``, never
with a ``COUNT(*)`` (#581).
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from test_plus import TestCase

from tournamentcontrol.competition.signals.ladders import (
    team_ladder_entry_aggregation,
)
from tournamentcontrol.competition.templatetags.competition import ladder
from tournamentcontrol.competition.tests.factories import (
    LadderEntryFactory,
    SeasonFactory,
    StageFactory,
    StageGroupFactory,
)
from tournamentcontrol.competition.wizards import DrawGenerationWizard, FilterForm


class ExistsNotCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stage = StageFactory.create(order=1)
        cls.pool = StageGroupFactory.create(stage=cls.stage)

    def assertNoCount(self, func, *args, **kwargs):
        with CaptureQueriesContext(connection) as queries:
            func(*args, **kwargs)
        self.assertEqual(
            [query["sql"] for query in queries if "COUNT(" in query["sql"]], []
        )

    def test_filter_form_clean(self):
        season = SeasonFactory.create()
        form = FilterForm(season, data={"template": "signon.html", "format": "pdf"})
        self.assertNoCount(form.is_valid)
        self.assertEqual(
            form.errors["__all__"], ["There are no matches that satisfy your criteria."]
        )

    def test_draw_generation_wizard_initial(self):
        wizard = DrawGenerationWizard()
        wizard.stage = self.stage
        self.assertNoCount(wizard.get_form_initial, "0")
        self.assertCountEqual(wizard.get_form_initial("0"), [self.pool])

    def test_stage_ladders(self):
        self.assertNoCount(self.stage.ladders)

    def test_ladder_tag(self):
        self.assertNoCount(ladder, {}, self.stage)

    def test_ladder_aggregation_carries_from_pools(self):
        stage = StageFactory.create(
            division=self.stage.division, order=2, carry_ladder=True
        )
        entry = LadderEntryFactory.create(match__stage=stage)
        self.assertNoCount(team_ladder_entry_aggregation, None, entry, created=False)
