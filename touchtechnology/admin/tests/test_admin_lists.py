from django.template import Context, Template
from example_app.tests.factories import RelativeFactory
from test_plus import TestCase

from touchtechnology.common.tests.factories import SuperUserFactory
from touchtechnology.news.tests.factories import ArticleFactory


class RelatedFilterTest(TestCase):
    def setUp(self):
        RelativeFactory.reset_sequence()
        self.template = Template(
            """
        {% load common admin_lists %}
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
        context = self._get_context(
            rel.link,
            ("relative_set",),
        )
        output = self.template.render(context).strip()
        self.assertEqual(
            output, "<dl>" "<dt>relative_set</dt>" "<dd>RelatedManager (1)</dd>" "</dl>"
        )


class PermissionNamesTest(TestCase):
    """
    The list code hands its templates the names of the model's permissions:
    ``admin_list`` for a related list on an object's page, ``generic_list``
    for a list page.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.article = ArticleFactory.create()

    def assertPermissionNames(self, model_name):
        for action in ("add", "view", "change", "delete"):
            with self.subTest(action=action):
                self.assertContext(f"{action}_perm", f"news.{action}_{model_name}")

    def test_admin_list(self):
        with self.login(self.make_user()):
            self.get_check_200("admin:news:article:edit", pk=self.article.pk)
        self.assertPermissionNames("translation")

    def test_generic_list(self):
        with self.login(self.make_user()):
            self.get_check_200("admin:news:article:list")
        self.assertPermissionNames("article")
