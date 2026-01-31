from django.utils.encoding import smart_str
from test_plus import TestCase

from touchtechnology.common.tests import factories


class SitemapNodeTests(TestCase):

    def setUp(self):
        self.object = factories.SitemapNodeFactory.create()

    def test_string_representation(self):
        self.assertEqual(self.object.title, smart_str(self.object))

    def test_repr_with_unicode_smart_quotes(self):
        """Test that __repr__ handles Unicode smart quotes without error."""
        # Create a SitemapNode with smart quotes in the title
        # Using Unicode character codes for smart quotes
        node = factories.SitemapNodeFactory.create(
            title='Test \u201csmart quotes\u201d and \u2018apostrophes\u2019'
        )
        # This should not raise UnicodeDecodeError
        repr_str = repr(node)
        # Verify the repr string is valid and contains the class name
        self.assertIn("SitemapNode", repr_str)
        self.assertIn("Test", repr_str)
        # Verify that the repr is ASCII-safe (contains escaped Unicode)
        # The smart quotes should be escaped as \u201c, \u201d, \u2018, \u2019
        self.assertIn(r"\u201c", repr_str)
        self.assertIn(r"\u201d", repr_str)
        # Verify it's a valid ASCII string
        repr_str.encode('ascii')

    def test_disable_with_unicode_title(self):
        """Test that disabling a node with Unicode title doesn't crash logging."""
        import logging
        # Create a SitemapNode with Unicode characters
        node = factories.SitemapNodeFactory.create(
            title='Test \u201csmart quotes\u201d'
        )
        # This should not raise UnicodeDecodeError when logging with %r
        with self.assertLogs('touchtechnology.common.models', level='DEBUG') as cm:
            node.disable()
        # Verify the log message was created
        self.assertEqual(len(cm.output), 1)
        self.assertIn('Disabling node', cm.output[0])

