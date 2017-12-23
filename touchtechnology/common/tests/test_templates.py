from __future__ import unicode_literals

from django.template import Context, Template
from django.test.utils import override_settings
from django.utils.http import urlencode
from django.utils.six.moves.urllib.parse import urlparse, urlunparse
from test_plus import TestCase

CSSIFY_TEMPLATE = Template("{% load common %}{{ value|cssify }}")
TWITTIFY_TEMPLATE = Template("{% load common %}{{ value|twittify }}")


class CssifyTest(TestCase):

    def test_cssify_str(self):
        context = Context({'value': 'some-normal-slug'})
        value = CSSIFY_TEMPLATE.render(context)
        self.assertEqual('some_normal_slug', value)

    def test_cssify_unicode(self):
        context = Context({'value': 'some-normal-slug'})
        value = CSSIFY_TEMPLATE.render(context)
        self.assertEqual('some_normal_slug', value)

    def test_cssify_none(self):
        context = Context({'value': None})
        value = CSSIFY_TEMPLATE.render(context)
        self.assertEqual('', value)


class TwittifyTest(TestCase):

    def test_twittify(self):
        context = Context({'value': "@goodtune"})
        value = TWITTIFY_TEMPLATE.render(context)
        expected = """
        @<a class="twitter user" target="_blank"
            href="http://twitter.com/goodtune">goodtune</a>
        """
        self.assertHTMLEqual(expected, value)

    def test_twittify_invalid(self):
        context = Context({'value': "goodtune"})
        value = TWITTIFY_TEMPLATE.render(context)
        expected = "goodtune"
        self.assertHTMLEqual(expected, value)


@override_settings(ROOT_URLCONF='example_app.urls')
class QueryStringTest(TestCase):

    fixtures = ['query_string']

    def setUp(self):
        self.query = dict(year=2013)
        self.url = urlparse(self.reverse('querystring:index'))

    def test_no_filter_no_page(self):
        self.get('querystring:index')

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


@override_settings(ROOT_URLCONF='example_app.urls')
class ContextTest(TestCase):

    def test_env(self):
        self.get('context:env')
        self.assertResponseContains('dev', html=False)

    def test_tz(self):
        self.get('context:tz')
        self.assertResponseContains('UTC', html=False)
