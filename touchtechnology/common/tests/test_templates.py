from __future__ import unicode_literals

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
    maxDiff = None

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
