"""
Registering components with an ``AdminSite``: the messages it logs and the
errors it raises, which are translated.
"""

from django.contrib.admin.sites import AlreadyRegistered, NotRegistered
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import translation

from touchtechnology.admin.sites import AdminSite, site
from touchtechnology.news.admin import NewsAdminComponent


class RegisterTest(SimpleTestCase):
    def setUp(self):
        self.site = AdminSite(name="registry")

    def test_register_logs_the_component(self):
        with self.assertLogs("touchtechnology.admin.sites.admin", "DEBUG") as logs:
            self.site.register(NewsAdminComponent)
        self.assertEqual(
            logs.output,
            [
                "DEBUG:touchtechnology.admin.sites.admin:"
                "Registering admin component... NewsAdminComponent"
            ],
        )

    @override_settings(TESTING=False)
    def test_register_twice(self):
        self.site.register(NewsAdminComponent)
        with self.assertRaisesMessage(
            AlreadyRegistered,
            "The component NewsAdminComponent is already registered",
        ):
            self.site.register(NewsAdminComponent)

    @override_settings(TESTING=False)
    def test_register_twice_is_translated(self):
        # The catalogue holds the literal with its placeholder, so the
        # message is found and the name is filled in after translation.
        self.site.register(NewsAdminComponent)
        with translation.override("fr"):
            with self.assertRaisesMessage(
                AlreadyRegistered,
                "Le composant NewsAdminComponent est déjà enregistré",
            ):
                self.site.register(NewsAdminComponent)

    def test_register_twice_while_testing_logs_and_skips(self):
        self.site.register(NewsAdminComponent)
        with self.assertLogs("touchtechnology.admin.sites.admin", "DEBUG") as logs:
            self.site.register(NewsAdminComponent)
        self.assertEqual(
            logs.output,
            [
                "DEBUG:touchtechnology.admin.sites.admin:"
                "Registering admin component... NewsAdminComponent",
                "DEBUG:touchtechnology.admin.sites.admin:"
                "Component NewsAdminComponent already registered, "
                "skipping during test",
            ],
        )

    def test_unregister_unknown(self):
        with self.assertRaisesMessage(
            NotRegistered, "The component NewsAdminComponent is not registered"
        ):
            self.site.unregister(NewsAdminComponent)

    def test_reverse_names_the_site(self):
        self.assertEqual(str(site.reverse("index")), reverse("admin:index"))
        self.assertEqual(str(site.get_absolute_url()), reverse("admin:index"))
