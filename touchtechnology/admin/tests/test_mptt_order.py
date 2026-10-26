from django.urls import reverse
from test_plus import TestCase

from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests.factories import SitemapNodeFactory, SuperUserFactory


class SitemapMoveTest(TestCase):
    """
    A node of the sitemap moves past its neighbour when its arrow posts, and
    the move returns to the folder it is listed in. Following the address
    moves nothing.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        cls.root = SitemapNodeFactory.create()
        cls.children = SitemapNodeFactory.create_batch(parent=cls.root, size=4)

    def test_a_visitor_is_asked_to_sign_in(self):
        self.assertLoginRequired("admin:reorder", self.children[0].pk, "down")

    def test_moving_a_node_down_and_up_returns_to_its_folder(self):
        first, second, *rest = self.children
        folder = reverse("admin:content:index", query={"r": self.root.pk})
        with self.login(self.superuser):
            self.post("admin:reorder", first.pk, "down")
            self.assert_http_302_found(url=folder)
            self.assertEqual(list(self.root.get_children()), [second, first, *rest])
            self.post("admin:reorder", first.pk, "up")
            self.assert_http_302_found(url=folder)
            self.get_check_200(folder)
        self.assertEqual(list(self.root.get_children()), self.children)

    def test_moving_a_node_at_the_top_returns_to_the_top_of_the_sitemap(self):
        other = SitemapNodeFactory.create()
        with self.login(self.superuser):
            self.post("admin:reorder", self.root.pk, "down")
        self.assert_http_302_found(url=reverse("admin:content:index"))
        self.assertEqual(
            list(SitemapNode.objects.filter(pk__in=(self.root.pk, other.pk))),
            [other, self.root],
        )

    def test_following_the_address_moves_nothing(self):
        with self.login(self.superuser):
            self.get("admin:reorder", self.children[0].pk, "down")
        self.assert_http_405_method_not_allowed()
        self.assertEqual(list(self.root.get_children()), self.children)
