from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tests.factories import SeasonFactory
from tournamentcontrol.highlights.constants import HighlightTemplateType
from tournamentcontrol.highlights.models import BaseTemplate, SeasonTemplate


class HighlightsAdminTests(TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_manage_base_template(self):
        with self.login(self.superuser):
            self.assertGoodView("admin:highlights:basetemplate:list")
            self.post(
                "admin:highlights:basetemplate:add",
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
        base_template = BaseTemplate.objects.create(
            name="Base",
            slug="base",
            template_type=HighlightTemplateType.MATCH_SCORE,
            svg="<svg></svg>",
        )
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:highlights:basetemplate:seasontemplate:list", base_template.pk
            )
            self.post(
                "admin:highlights:basetemplate:seasontemplate:add",
                base_template.pk,
                data={"season": season.pk, "name": "", "config": "{}"},
            )
            self.response_302()
            self.assertEqual(1, SeasonTemplate.objects.count())
