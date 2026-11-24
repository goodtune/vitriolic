"""
Follow the links of an admin page, to find the ones that lead nowhere.

A link in the admin is easy to get wrong without a page showing it: a Cancel
button that climbs two levels of the address (``../..``) lands on whatever sits
there, and where the objects nest under another there may be no page at all.
Add ``LinksMixin`` to a test case and call ``follow_links`` with the page::

    @per_shell
    class SeasonLinksTests(LinksMixin, TestCase):
        def test_the_season_page(self):
            with self.login(self.superuser):
                self.follow_links("admin:fixja:competition:season:edit", 1, 2)

No link of the admin acts when it is followed: whatever changes something (a
Delete, an arrow that moves a row) is a form that posts.
"""

from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


class LinksMixin:
    """For a ``test_plus`` test case: ``follow_links``."""

    def setUp(self):
        super().setUp()
        self.followed_links = set()

    def follow_links(self, url_name, *args, selector="a"):
        """
        Get the page ``url_name`` names, then every link of it (the elements
        ``selector`` finds) that stays in the admin, and check each answers
        (once any redirect has been followed). A link is followed once for the
        test, whichever page holds it; one that is relative is taken from the
        page, as a browser does.
        """
        self.get(self.reverse(url_name, *args))
        self.assert_http_200_ok()
        page = self.last_response.wsgi_request.get_full_path()
        admin = self.reverse("admin:index")
        anchors = BeautifulSoup(self.last_response.content, "html.parser").select(
            selector
        )
        for href in dict.fromkeys(a["href"] for a in anchors if a.has_attr("href")):
            link = urlsplit(urljoin(page, href))._replace(fragment="").geturl()
            if (
                not link.startswith(admin)
                or link in self.followed_links
                or link == page
            ):
                continue
            self.followed_links.add(link)
            with self.subTest(page=page, link=link):
                self.get(link, follow=True)
                self.assert_http_200_ok()
