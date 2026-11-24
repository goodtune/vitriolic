from test_plus import TestCase

from touchtechnology.content.models import Content, Page, PageContent


class ReprTests(TestCase):
    """An object can be shown before it is saved, as Django's own reprs can."""

    def test_unsaved_content(self):
        self.assertEqual(repr(Content()), "<Content: #None>")

    def test_saved_content(self):
        content = Content.objects.create(copy="<p>Copy</p>")

        self.assertEqual(repr(content), f"<Content: #{content.pk}>")

    def test_unsaved_page_content(self):
        self.assertEqual(repr(PageContent()), "<PageContent: #None, page=None>")

    def test_saved_page_content(self):
        page = Page.objects.create()
        content = PageContent.objects.create(page=page, sequence=1, copy="<p>Copy</p>")

        self.assertEqual(repr(content), f"<PageContent: #{content.pk}, page={page.pk}>")
