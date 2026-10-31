from django.utils.encoding import smart_str
from test_plus import TestCase

from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests import factories


class SitemapNodeTests(TestCase):
    def setUp(self):
        super().setUp()
        self.object = factories.SitemapNodeFactory.create()

    def test_string_representation(self):
        self.assertEqual(self.object.title, smart_str(self.object))

    def test_repr_with_unicode_smart_quotes(self):
        """Test that __repr__ handles Unicode smart quotes without error."""
        # Create a SitemapNode with smart quotes in the title
        # Using Unicode character codes for smart quotes
        node = factories.SitemapNodeFactory.create(
            title="Test \u201csmart quotes\u201d and \u2018apostrophes\u2019"
        )
        # Verify the repr matches the expected ASCII-safe format
        expected = f'<SitemapNode: "Test \\u201csmart quotes\\u201d and \\u2018apostrophes\\u2019" ({node.level}:{node.lft},{node.rght})>'
        self.assertEqual(repr(node), expected)

    def test_logging_with_unicode_title_in_repr(self):
        """Test that logging with %r and Unicode title doesn't crash."""
        # Create a SitemapNode with Unicode characters
        node = factories.SitemapNodeFactory.create(
            title="Test \u201csmart quotes\u201d"
        )
        # This should not raise UnicodeDecodeError when logging with %r
        with self.assertLogs("touchtechnology.common.models", level="DEBUG") as cm:
            node.disable()
        # Verify the exact log message was created
        expected_log = (
            f"DEBUG:touchtechnology.common.models:Disabling node {repr(node)}"
        )
        self.assertCountEqual(cm.output, [expected_log])


class SitemapNodeAddressTests(TestCase):
    """
    A node's address is the slugs of its line, the home page's left out,
    however the node was loaded.
    """

    def setUp(self):
        super().setUp()
        self.home = SitemapNode.objects.create(title="Home", slug="home")
        self.press = SitemapNode.objects.create(title="Press", slug="press")
        self.archive = SitemapNode.objects.create(
            title="Archive", slug="archive", parent=self.press
        )
        self.minutes = SitemapNode.objects.create(
            title="Minutes", slug="minutes", parent=self.archive
        )

    def test_a_node_loaded_alone(self):
        node = SitemapNode.objects.get(pk=self.minutes.pk)
        self.assertEqual(node.get_absolute_url(), "/press/archive/minutes/")

    def test_a_node_at_the_top_needs_no_query(self):
        press, home = SitemapNode.objects.filter(level=0).order_by("-slug")
        with self.assertNumQueries(0):
            self.assertEqual(
                (press.get_absolute_url(), home.get_absolute_url()), ("/press/", "/")
            )

    def test_a_node_loaded_through_its_parents_needs_no_query(self):
        press = SitemapNode.objects.get(pk=self.press.pk)
        (archive,) = press.children.all()
        (minutes,) = archive.children.all()
        with self.assertNumQueries(0):
            self.assertEqual(minutes.get_absolute_url(), "/press/archive/minutes/")
