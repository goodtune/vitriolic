from django.test import override_settings
from test_plus import TestCase

from touchtechnology.admin.tests.shells import IconMixin, per_shell
from touchtechnology.common.tests.factories import SuperUserFactory
from tournamentcontrol.competition.tests import factories


@per_shell
class EmptyRelatedTabTests(IconMixin, TestCase):
    """
    A tab of a stage's page draws its heading and the link that adds another
    object whether or not the relation has rows: the Matches tab, whose list
    is narrowed by the stage's ``_list_select_related``, as much as the Pools
    tab, which lists the plain relation.
    """

    user_factory = SuperUserFactory
    edit = "admin:fixja:competition:season:division:stage:edit"

    @classmethod
    def setUpTestData(cls):
        cls.stage = factories.StageFactory.create()

    def add_link(self, scope, label):
        url = self.reverse(
            f"admin:fixja:competition:season:division:stage:{scope}:add",
            *self.stage._get_url_args(),
        )
        icon = self.icon("plus")
        return self.by_shell(
            workbook=(
                f'<a class="wb-button wb-button-primary wb-button-small" '
                f'href="{url}">{icon}{label}</a>'
            ),
            explorer=(
                f'<a class="button primary compact" href="{url}">'
                f"{icon}<span>{label}</span></a>"
            ),
        )

    def test_empty_matches(self):
        with self.login(self.make_user()):
            self.get_check_200(self.edit, *self.stage._get_url_args())
        self.assertResponseContains(self.add_link("match", "Add match"))

    def test_empty_pools(self):
        with self.login(self.make_user()):
            self.get_check_200(self.edit, *self.stage._get_url_args())
        self.assertResponseContains(self.add_link("stagegroup", "Add pool"))

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_empty_matches_htmx_tab(self):
        with self.login(self.make_user()):
            self.get(
                self.edit,
                *self.stage._get_url_args(),
                data={"_htmx_tab": "matches"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()
        self.assertResponseContains(self.add_link("match", "Add match"))

    @override_settings(TOUCHTECHNOLOGY_HTMX_ADMIN_TABS=True)
    def test_empty_pools_htmx_tab(self):
        with self.login(self.make_user()):
            self.get(
                self.edit,
                *self.stage._get_url_args(),
                data={"_htmx_tab": "pools"},
                extra={"HTTP_HX_REQUEST": "true"},
            )
        self.assert_http_200_ok()
        self.assertResponseContains(self.add_link("stagegroup", "Add pool"))
