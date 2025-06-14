from test_plus import TestCase

from tournamentcontrol.competition.tests.factories import SeasonFactory
from tournamentcontrol.highlights.constants import HighlightTemplateType
from tournamentcontrol.highlights.models import BaseTemplate, SeasonTemplate


class HighlightTemplateTests(TestCase):
    def test_base_template_render(self):
        tpl = BaseTemplate.objects.create(
            name="Score",
            slug="score",
            template_type=HighlightTemplateType.MATCH_SCORE,
            svg="<svg>{{ home }} {{ away }}</svg>",
        )
        result = tpl.render({"home": "A", "away": "B"})
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_season_template_render(self):
        season = SeasonFactory.create()
        base = BaseTemplate.objects.create(
            name="Score",
            slug="score-base",
            template_type=HighlightTemplateType.MATCH_SCORE,
            svg="<svg fill='{{ colour }}'>{{ team }}</svg>",
        )
        st = SeasonTemplate.objects.create(
            season=season,
            base=base,
            svg="",
            config={"colour": "red"},
        )
        result = st.render({"team": "Knights"})
        self.assertIn("red", result)
        self.assertIn("Knights", result)
