from django.template import Context, Template
from example_app.tests.factories import RelativeFactory
from test_plus import TestCase


class RelatedFilterTest(TestCase):
    def setUp(self):
        RelativeFactory.reset_sequence()
        self.template = Template(
            """
        {% load common mvp_tags %}
        {% spaceless %}
            <dl>
                {% for manager, name in object|related:related %}
                    <dt>{{ name }}</dt>
                    <dd>{{ manager|type }} ({{ manager.count }})</dd>
                {% endfor %}
            </dl>
        {% endspaceless %}
        """
        )

    def _get_context(self, obj, rel=None):
        if rel is None:
            rel = ()
        context = {"object": obj, "related": rel}
        return Context(context)

    def test_related_no_whitelist(self):
        rel = RelativeFactory()
        context = self._get_context(rel.link)
        output = self.template.render(context).strip()
        self.assertEqual(output, "<dl></dl>")

    def test_related_empty_whitelist(self):
        rel = RelativeFactory()
        context = self._get_context(rel.link, ())
        output = self.template.render(context).strip()
        self.assertEqual(output, "<dl></dl>")

    def test_related_specific_whitelist(self):
        rel = RelativeFactory()
        context = self._get_context(rel.link, ("relative_set",),)
        output = self.template.render(context).strip()
        self.assertEqual(
            output, "<dl>" "<dt>relative_set</dt>" "<dd>RelatedManager (1)</dd>" "</dl>"
        )
