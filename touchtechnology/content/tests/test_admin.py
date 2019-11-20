from os.path import dirname, join

from django.contrib.auth.models import Permission
from test_plus.test import TestCase
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests.factories import UserFactory
from touchtechnology.content.models import Placeholder
from touchtechnology.content.tests import factories


class AdminTests(TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.staff = UserFactory.create(is_staff=True)
        self.staff.user_permissions.set(
            Permission.objects.filter(codename__endswith="_sitemapnode")
        )

        placeholder = Placeholder.objects.get(namespace="context")
        self.root_node = SitemapNode.objects.create(
            title="Simple Test",
            slug="home",
            object=placeholder,
            kwargs={"key": "value"},
        )

    def get_text(self, filename):
        with open(join(dirname(__file__), filename)) as fp:
            text = fp.read()
        return text

    def test_sitemap_index_superuser(self):
        self.assertLoginRequired("admin:content:index")
        with self.login(self.superuser):
            self.get("admin:content:index")
            html = """
                <a role="button" href="/admin/content/application/{}/">
                    <i class="fa fa-pencil fa-fw"></i>
                    Edit
                </a>
            """.format(
                self.root_node.pk
            )
            self.assertResponseContains(html)

    def test_sitemap_index_staff_user(self):
        self.assertLoginRequired("admin:content:index")
        with self.login(self.staff):
            self.get("admin:content:index")
            html = "<span>Simple Test</span>"
            self.assertResponseContains(html)

    def test_edit_page(self):
        with self.login(self.superuser):
            self.assertGoodView("admin:content:page:add")

            copy = """<p>Sample page data.</p>"""
            data = {
                "parent-form-parent": "",
                "parent-form-title": "Sample",
                "parent-form-short_title": "",
                "parent-form-enabled": "1",
                "parent-form-hidden_from_navigation": "0",
                "parent-form-hidden_from_sitemap": "0",
                "parent-form-slug": "",
                "parent-form-slug_locked": "0",
                "form-template": "",
                "form-keywords": "",
                "form-description": "",
                "formset-TOTAL_FORMS": "1",
                "formset-INITIAL_FORMS": "0",
                "formset-MIN_NUM_FORMS": "0",
                "formset-MAX_NUM_FORMS": "1000",
                "formset-0-copy": copy,
                "formset-0-label": "copy",
                "formset-0-sequence": "1",
                "formset-0-id": "",
                "formset-0-page": "",
            }
            self.post("admin:content:page:add", data=data)
            self.response_302()

            node = SitemapNode.objects.latest("pk")
            self.assertEqual(node.get_absolute_url(), "/sample/")

            self.assertEqual(node.object.content.latest("pk").copy, copy)

            # Unfortunately the SitemapNodeMiddleware does not appear to be
            # having an effect?
            # self.get(node.get_absolute_url())
            # self.response_200()


class GoodViewTests(TestCase):
    def setUp(self):
        self.staff = UserFactory.create(is_staff=True, is_superuser=True)
        self.regular = UserFactory.create()

    def test_redirect_list(self):
        factories.RedirectFactory.create()

        with self.login(self.staff):
            self.assertGoodView("admin:content:redirect:list")
            self.response_200()
