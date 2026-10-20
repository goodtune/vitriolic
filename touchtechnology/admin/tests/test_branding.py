import copy

from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from test_plus import TestCase

from touchtechnology.admin.branding import (
    COLOUR_KEYS,
    brand_check,
    brand_from,
    get_brand,
)
from touchtechnology.common.tests import factories
from vitriolic.brands import BRANDS


def brand_for(request):
    return {"name": "From callable " + request.path}


class BrandTests(TestCase):
    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_default_brand(self):
        brand = get_brand()
        self.assertEqual(brand.name, "Administration")
        self.assertEqual(brand.colours["primary"], "#275d8b")

    @override_settings(
        TOUCHTECHNOLOGY_ADMIN_BRAND={
            "name": "Harbour Touch",
            "colours": {"primary": "#1e3d2f"},
        }
    )
    def test_setting_mapping_fills_missing_colours(self):
        brand = get_brand()
        self.assertEqual(brand.name, "Harbour Touch")
        self.assertEqual(brand.colours["primary"], "#1e3d2f")
        self.assertEqual(brand.colours["danger"], "#b8322f")

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"colours": {"primary": "blue"}})
    def test_invalid_colour_is_a_check_error(self):
        errors = brand_check(None)
        self.assertEqual([e.id for e in errors], ["touchtechnology_admin.E001"])
        self.assertIn("'primary'", errors[0].msg)

    @override_settings(
        TOUCHTECHNOLOGY_ADMIN_BRAND="touchtechnology.admin.tests.test_branding.brand_for"
    )
    def test_dotted_callable_receives_request(self):
        request = RequestFactory().get("/")
        self.assertEqual(get_brand(request).name, "From callable /")

    def test_request_attribute_wins(self):
        request = RequestFactory().get("/")
        request.admin_brand = {"name": "Per request"}
        with override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"name": "From settings"}):
            self.assertEqual(get_brand(request).name, "Per request")

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"colours": {"primary": "blue"}})
    def test_check_is_registered(self):
        ids = [message.id for message in checks.run_checks()]
        self.assertIn("touchtechnology_admin.E001", ids)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"colours": {"primary": "blue"}})
    def test_invalid_colour_message(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TOUCHTECHNOLOGY_ADMIN_BRAND colour 'primary' must be #rrggbb, got 'blue'",
        ):
            get_brand()

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=brand_for)
    def test_callable_is_not_called_by_check(self):
        self.assertEqual(brand_check(None), [])

    def test_trailing_newline_is_refused(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TOUCHTECHNOLOGY_ADMIN_BRAND colour 'primary' must be #rrggbb, "
            "got '#275d8b\\n'",
        ):
            brand_from({"colours": {"primary": "#275d8b\n"}})


class DemoBrandTests(TestCase):
    def test_demo_brands_are_valid(self):
        for name, value in BRANDS.items():
            with self.subTest(name=name):
                brand = brand_from(value)
                self.assertEqual(set(brand.colours), set(COLOUR_KEYS))


class ShellTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(is_staff=True, is_superuser=True)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_admin_index_emits_brand_properties(self):
        with self.login(self.superuser):
            self.get_check_200("admin:index")
            self.assertResponseContains(
                "<style>:root{--brand-primary:#275d8b;--brand-secondary:#e8862a;"
                "--brand-success:#2a8a5c;--brand-warning:#d9a21b;"
                "--brand-danger:#b8322f;}</style>",
                html=True,
            )
            self.assertResponseContains(
                '<span class="navbar-brand-text">Administration</span>', html=True
            )

    @override_settings(
        TOUCHTECHNOLOGY_ADMIN_BRAND={
            "name": "Harbour Touch",
            "logo": "img/harbour.png",
        }
    )
    def test_logo_is_resolved_through_static(self):
        with self.login(self.superuser):
            self.get_check_200("admin:index")
            self.assertResponseContains(
                '<img src="/static/img/harbour.png" alt="Harbour Touch">', html=True
            )

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_shell_resolves_brand_without_the_context_processor(self):
        templates = copy.deepcopy(settings.TEMPLATES)
        processors = templates[0]["OPTIONS"]["context_processors"]
        processors.remove("touchtechnology.admin.context_processors.brand")
        with self.settings(TEMPLATES=templates), self.login(self.superuser):
            self.get_check_200("admin:index")
            self.assertResponseContains(
                '<span class="navbar-brand-text">Administration</span>', html=True
            )
