from urllib.parse import urlparse, urlunparse

from django.template import Context, Template
from django.test.utils import override_settings
from django.utils.http import urlencode
from test_plus import TestCase

from touchtechnology.common.models import SitemapNode

CSSIFY_TEMPLATE = Template("{% load common %}{{ value|cssify }}")
TWITTIFY_TEMPLATE = Template("{% load common %}{{ value|twittify }}")


class CssifyTest(TestCase):
    def test_cssify_str(self):
        context = Context({"value": "some-normal-slug"})
        value = CSSIFY_TEMPLATE.render(context)
        self.assertEqual("some_normal_slug", value)

    def test_cssify_unicode(self):
        context = Context({"value": "some-normal-slug"})
        value = CSSIFY_TEMPLATE.render(context)
        self.assertEqual("some_normal_slug", value)

    def test_cssify_none(self):
        context = Context({"value": None})
        value = CSSIFY_TEMPLATE.render(context)
        self.assertEqual("", value)


class NavigationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = SitemapNode.objects.create(title="Home Page", slug="home")
        cls.about = SitemapNode.objects.create(title="About Us", slug="about")
        cls.about_people = SitemapNode.objects.create(
            title="Our People", slug="people", parent=cls.about
        )
        cls.about_work = SitemapNode.objects.create(
            title="Our Work", slug="work", parent=cls.about
        )
        cls.contact = SitemapNode.objects.create(title="Contact Us", slug="contact")
        cls.about_people_gary = SitemapNode.objects.create(
            title="Gary Reynolds", slug="goodtune", parent=cls.about_people
        )
        cls.about_people_fred = SitemapNode.objects.create(
            title="Fred Nurks",
            slug="freddy",
            parent=cls.about_people,
            hidden_from_navigation=True,
        )

    @classmethod
    def tearDownClass(cls):
        pass

    def test_basic(self):
        template = Template("{% load common %}{% navigation %}")
        value = template.render(Context())
        self.assertHTMLEqual(
            value,
            """
            <ul class="navigation">
                <li class="root first NoneType" id="node{}">
                    <a href="/">Home Page</a>
                </li>
                <li class=" has_children NoneType" id="node{}">
                    <a href="/about/">About Us</a>
                </li>
                <li class=" last NoneType" id="node{}">
                    <a href="/contact/">Contact Us</a>
                </li>
            </ul>
            """.format(
                self.home.pk, self.about.pk, self.contact.pk
            ),
        )

    def test_current_node(self):
        template = Template("{% load common %}{% navigation current_node=node %}")
        context = Context({"node": self.contact})
        value = template.render(context)
        self.assertHTMLEqual(
            value,
            """
            <ul class="navigation">
                <li class="root first NoneType" id="node{}">
                    <a href="/">Home Page</a>
                </li>
                <li class=" has_children NoneType" id="node{}">
                    <a href="/about/">About Us</a>
                </li>
                <li class=" current last NoneType" id="node{}">
                    <a href="/contact/">Contact Us</a>
                </li>
            </ul>
            """.format(
                self.home.pk, self.about.pk, self.contact.pk
            ),
        )

    def test_start_stop(self):
        template = Template("{% load common %}{% navigation start_at=0 stop_at=1 %}")
        value = template.render(Context())
        self.assertHTMLEqual(
            value,
            """
            <ul class="navigation">
                <li class="root first NoneType" id="node{}">
                    <a href="/">Home Page</a>
                </li>
                <li class=" has_children NoneType" id="node{}">
                    <a href="/about/">About Us</a>
                    <ul class="navigation">
                        <li class=" has_children first NoneType" id="node{}">
                            <a href="/about/people/">Our People</a>
                        </li>
                        <li class=" last NoneType" id="node{}">
                            <a href="/about/work/">Our Work</a>
                        </li>
                    </ul>
                </li>
                <li class=" NoneType last" id="node{}">
                    <a href="/contact/">Contact Us</a>
                </li>
            </ul>
            """.format(
                self.home.pk,
                self.about.pk,
                self.about_people.pk,
                self.about_work.pk,
                self.contact.pk,
            ),
        )


class NavigationQueryPerformanceTest(TestCase):
    """Test that navigation query count stays bounded regardless of tree depth."""

    @classmethod
    def setUpTestData(cls):
        # Build a tree with depth 5 and siblings at each level to exercise
        # the full navigation code path.
        #
        # Level 0 (roots)
        cls.home = SitemapNode.objects.create(title="Home", slug="home")
        cls.about = SitemapNode.objects.create(title="About", slug="about")
        cls.contact = SitemapNode.objects.create(title="Contact", slug="contact")
        cls.news = SitemapNode.objects.create(title="News", slug="news")
        # Level 1
        cls.team = SitemapNode.objects.create(
            title="Team", slug="team", parent=cls.about
        )
        cls.history = SitemapNode.objects.create(
            title="History", slug="history", parent=cls.about
        )
        cls.values = SitemapNode.objects.create(
            title="Values", slug="values", parent=cls.about
        )
        # Level 2
        cls.engineering = SitemapNode.objects.create(
            title="Engineering", slug="engineering", parent=cls.team
        )
        cls.design = SitemapNode.objects.create(
            title="Design", slug="design", parent=cls.team
        )
        # Level 3
        cls.frontend = SitemapNode.objects.create(
            title="Frontend", slug="frontend", parent=cls.engineering
        )
        cls.backend = SitemapNode.objects.create(
            title="Backend", slug="backend", parent=cls.engineering
        )
        # Level 4 (deepest)
        cls.react = SitemapNode.objects.create(
            title="React Team", slug="react", parent=cls.frontend
        )
        cls.vue = SitemapNode.objects.create(
            title="Vue Team", slug="vue", parent=cls.frontend
        )

    def test_deep_node_query_count(self):
        """Navigation for a deeply nested node should use a bounded number of queries."""
        template = Template("{% load common %}{% navigation current_node=node %}")
        context = Context({"node": self.react})
        with self.assertNumQueriesLessThan(15):
            template.render(context)

    def test_shallow_node_query_count(self):
        """Navigation for a shallow node should not use more queries than a deep node."""
        template = Template("{% load common %}{% navigation current_node=node %}")
        context = Context({"node": self.about})
        with self.assertNumQueriesLessThan(15):
            template.render(context)

    def test_deep_node_renders_expected_structure(self):
        """Navigation for a deep node should include ancestors, siblings, and children."""
        template = Template("{% load common %}{% navigation current_node=node %}")
        context = Context({"node": self.react})
        value = template.render(context)
        self.assertHTMLEqual(
            value,
            f"""
            <ul class="navigation">
                <li id="node{self.home.pk}" class="NoneType first root">
                    <a href="/">Home</a>
                </li>
                <li id="node{self.about.pk}" class="NoneType has_children parent ">
                    <a href="/about/">About</a>
                    <ul class="navigation">
                        <li id="node{self.team.pk}" class="NoneType first has_children parent ">
                            <a href="/about/team/">Team</a>
                            <ul class="navigation">
                                <li id="node{self.engineering.pk}" class="NoneType first has_children parent ">
                                    <a href="/about/team/engineering/">Engineering</a>
                                    <ul class="navigation">
                                        <li id="node{self.frontend.pk}" class="NoneType first has_children parent ">
                                            <a href="/about/team/engineering/frontend/">Frontend</a>
                                            <ul class="navigation">
                                                <li id="node{self.react.pk}" class="NoneType first current ">
                                                    <a href="/about/team/engineering/frontend/react/">React Team</a>
                                                </li>
                                                <li id="node{self.vue.pk}" class="NoneType last ">
                                                    <a href="/about/team/engineering/frontend/vue/">Vue Team</a>
                                                </li>
                                            </ul>
                                        </li>
                                        <li id="node{self.backend.pk}" class="NoneType last ">
                                            <a href="/about/team/engineering/backend/">Backend</a>
                                        </li>
                                    </ul>
                                </li>
                                <li id="node{self.design.pk}" class="NoneType last ">
                                    <a href="/about/team/design/">Design</a>
                                </li>
                            </ul>
                        </li>
                        <li id="node{self.history.pk}" class="NoneType ">
                            <a href="/about/history/">History</a>
                        </li>
                        <li id="node{self.values.pk}" class="NoneType last ">
                            <a href="/about/values/">Values</a>
                        </li>
                    </ul>
                </li>
                <li id="node{self.contact.pk}" class="NoneType ">
                    <a href="/contact/">Contact</a>
                </li>
                <li id="node{self.news.pk}" class="NoneType last ">
                    <a href="/news/">News</a>
                </li>
            </ul>
            """,
        )


class TwittifyTest(TestCase):
    def test_twittify(self):
        context = Context({"value": "@goodtune"})
        value = TWITTIFY_TEMPLATE.render(context)
        expected = """
        @<a class="twitter user" target="_blank"
            href="http://twitter.com/goodtune">goodtune</a>
        """
        self.assertHTMLEqual(expected, value)

    def test_twittify_invalid(self):
        context = Context({"value": "goodtune"})
        value = TWITTIFY_TEMPLATE.render(context)
        expected = "goodtune"
        self.assertHTMLEqual(expected, value)


@override_settings(ROOT_URLCONF="example_app.urls")
class QueryStringTest(TestCase):

    fixtures = ["query_string"]

    def setUp(self):
        self.query = dict(year=2013)
        self.url = urlparse(self.reverse("querystring:index"))

    def test_no_filter_no_page(self):
        self.get("querystring:index")

        self.assertResponseContains('<a href="?page=3">3</a>')
        self.assertResponseNotContains('<a href="?page=4">4</a>')

        self.assertResponseContains('<span id="5">5</span>')
        self.assertResponseNotContains('<span id="9">9</span>')

    def test_no_filter_page(self):
        query = dict(page=2)
        url = self.url._replace(query=urlencode(query, True))
        self.get(urlunparse(url))

        self.assertResponseContains('<a href="?page=3">3</a>')
        self.assertResponseNotContains('<a href="?page=4">4</a>')

        self.assertResponseNotContains('<span id="5">5</span>')
        self.assertResponseContains('<span id="9">9</span>')

    def test_filter_no_page(self):
        url = self.url._replace(query=urlencode(self.query, True))
        self.get(urlunparse(url))

        link = '<a href="?year={year}&amp;page={page}">{page}</a>'
        self.assertResponseContains(link.format(page=2, **self.query))
        self.assertResponseNotContains(link.format(page=3, **self.query))

        self.assertResponseContains('<span id="5">5</span>')
        self.assertResponseNotContains('<span id="9">9</span>')

    def test_filter_page(self):
        query = dict(page=2, **self.query)
        url = self.url._replace(query=urlencode(query, True))
        self.get(urlunparse(url))

        link = '<a href="?year={year}&amp;page={page}">{page}</a>'
        self.assertResponseContains(link.format(page=2, **self.query))
        self.assertResponseNotContains(link.format(page=3, **self.query))

        self.assertResponseNotContains('<span id="5">5</span>')
        self.assertResponseContains('<span id="9">9</span>')


@override_settings(ROOT_URLCONF="example_app.urls")
class ContextTest(TestCase):
    def test_env(self):
        self.get("context:env")
        self.assertResponseContains("dev", html=False)

    def test_tz(self):
        self.get("context:tz")
        self.assertResponseContains("UTC", html=False)


class VersionTest(TestCase):
    def test_version_python(self):
        """Test version tag for Python returns expected structure."""
        template = Template("{% load common %}{% version 'python' %}")
        output = template.render(Context()).strip()
        # Should contain a version div with Python info
        self.assertIn('class="version"', output)
        self.assertIn('id="pkg_Python"', output)  # name is "Python" for python package
        self.assertIn("Python", output)
        # Should contain a version number (e.g., 3.12.x)
        self.assertRegex(output, r"\d+\.\d+")

    def test_version_django(self):
        """Test version tag for Django package."""
        template = Template("{% load common %}{% version 'django' %}")
        output = template.render(Context()).strip()
        # Should contain a version div with Django info
        self.assertIn('class="version"', output)
        self.assertIn(
            'id="pkg_django"', output
        )  # name is lowercase for regular packages
        self.assertIn("Django", output)
        # Should contain a version number
        self.assertRegex(output, r"\d+\.\d+")

    def test_version_nonexistent_package(self):
        """Test version tag for non-existent package."""
        template = Template("{% load common %}{% version 'nonexistentpackage123' %}")
        output = template.render(Context()).strip()
        # Should contain unversioned div when package not found
        self.assertIn('class="version"', output)
        self.assertIn('id="unknown"', output)
        self.assertIn("Unversioned", output)
