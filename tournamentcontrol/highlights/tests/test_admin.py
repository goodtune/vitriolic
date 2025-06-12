from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.highlights.models import BaseTemplate, SeasonTemplate
from tournamentcontrol.highlights.constants import HighlightTemplateType
from tournamentcontrol.competition.tests.factories import SeasonFactory


class HighlightsAdminTests(TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_manage_base_template(self):
        with self.login(self.superuser):
            self.assertGoodView("admin:highlights:base:list")
            self.post(
                "admin:highlights:base:add",
                data={
                    "name": "Score",
                    "slug": "score",
                    "template_type": HighlightTemplateType.MATCH_SCORE,
                    "svg": "<svg></svg>",
                },
            )
            self.response_302()
            self.assertEqual(1, BaseTemplate.objects.count())

    def test_manage_season_template(self):
        season = SeasonFactory.create()
        base = BaseTemplate.objects.create(
            name="Base",
            slug="base",
            template_type=HighlightTemplateType.MATCH_SCORE,
            svg="<svg></svg>",
        )
        with self.login(self.superuser):
            self.assertGoodView("admin:highlights:season:list")
            self.post(
                "admin:highlights:season:add",
                data={
                    "season": season.pk,
                    "base": base.pk,
                    "name": "",
                    "svg": "",
                    "config": "{}",
                },
            )
            self.response_302()
            self.assertEqual(1, SeasonTemplate.objects.count())
