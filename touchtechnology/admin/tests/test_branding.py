import copy

from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.template import Context, Template
from django.test import RequestFactory, override_settings
from test_plus import TestCase
from vitriolic.brands import BRANDS

from touchtechnology.admin.branding import (
    COLOUR_KEYS,
    DEFAULT_LOGO,
    Brand,
    brand_check,
    brand_from,
    get_brand,
)
from touchtechnology.common.tests import factories


def brand_for(request):
    return {"name": "From callable " + request.path}


CALLS = []


def counted_brand(request):
    CALLS.append(request.path)
    return {"name": "Counted"}


class BrandTests(TestCase):
    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_default_brand(self):
        brand = get_brand()
        self.assertEqual(brand.name, "Administration")
        self.assertEqual(brand.colours["primary"], "#275d8b")
        self.assertEqual(brand.logo, DEFAULT_LOGO)

    def test_logo_defaults_to_the_static_logo_the_shell_always_showed(self):
        self.assertEqual(DEFAULT_LOGO, "img/logo.png")
        self.assertEqual(brand_from({"name": "Harbour"}).logo, "img/logo.png")
        self.assertEqual(Brand().logo, "img/logo.png")

    def test_explicit_none_logo_is_the_text_mark(self):
        self.assertIsNone(brand_from({"logo": None}).logo)

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

    def test_unknown_colour_key_is_refused(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TOUCHTECHNOLOGY_ADMIN_BRAND colour 'primay' is not one of "
            "primary, secondary, success, warning, danger",
        ):
            brand_from({"colours": {"primay": "#275d8b"}})

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"colours": {"primay": "#275d8b"}})
    def test_unknown_colour_key_is_a_check_error(self):
        errors = brand_check(None)
        self.assertEqual([e.id for e in errors], ["touchtechnology_admin.E001"])
        self.assertIn("'primay'", errors[0].msg)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND="touchtechnology.admin.nowhere")
    def test_misspelt_dotted_path_is_a_check_error(self):
        errors = brand_check(None)
        self.assertEqual([e.id for e in errors], ["touchtechnology_admin.E001"])
        self.assertIn("'touchtechnology.admin.nowhere'", errors[0].msg)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND="touchtechnology.admin.nowhere")
    def test_misspelt_dotted_path_is_improperly_configured(self):
        with self.assertRaisesMessage(
            ImproperlyConfigured,
            "TOUCHTECHNOLOGY_ADMIN_BRAND cannot import "
            "'touchtechnology.admin.nowhere'",
        ):
            get_brand(RequestFactory().get("/"))

    @override_settings(
        TOUCHTECHNOLOGY_ADMIN_BRAND="touchtechnology.admin.branding.DEFAULT_COLOURS"
    )
    def test_dotted_path_must_name_a_callable(self):
        errors = brand_check(None)
        self.assertEqual([e.id for e in errors], ["touchtechnology_admin.E001"])
        self.assertIn("must name a callable", errors[0].msg)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=42)
    def test_unsupported_type_is_a_check_error_naming_the_type(self):
        errors = brand_check(None)
        self.assertEqual([e.id for e in errors], ["touchtechnology_admin.E001"])
        self.assertIn("got int", errors[0].msg)

    @override_settings(
        TOUCHTECHNOLOGY_ADMIN_BRAND="touchtechnology.admin.tests.test_branding.brand_for"
    )
    def test_importable_dotted_callable_passes_the_check(self):
        self.assertEqual(brand_check(None), [])

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"name": "Valid"})
    def test_valid_mapping_passes_the_check(self):
        self.assertEqual(brand_check(None), [])

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_a_string_on_the_request_is_an_error_and_is_not_imported(self):
        request = RequestFactory().get("/")
        request.admin_brand = "touchtechnology.admin.tests.test_branding.brand_for"
        with self.assertRaisesMessage(
            ImproperlyConfigured, "request.admin_brand must be a mapping"
        ):
            get_brand(request)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=counted_brand)
    def test_brand_is_resolved_once_per_request(self):
        CALLS.clear()
        request = RequestFactory().get("/")
        first = get_brand(request)
        self.assertIs(get_brand(request), first)
        self.assertEqual(CALLS, ["/"])

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
                '<img src="/static/img/logo.png" alt="Administration">', html=True
            )

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND={"logo": None})
    def test_no_logo_shows_the_name_as_a_text_mark(self):
        with self.login(self.superuser):
            self.get_check_200("admin:index")
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
                '<img src="/static/img/logo.png" alt="Administration">', html=True
            )

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=None)
    def test_title_is_the_brand_name(self):
        with self.login(self.superuser):
            self.get_check_200("admin:index")
            self.assertResponseContains("<title>Administration</title>", html=True)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=counted_brand)
    def test_callable_brand_is_called_once_across_render_and_processor(self):
        CALLS.clear()
        with self.login(self.superuser):
            self.get_check_200("admin:news:article:list")
        self.assertEqual(len(CALLS), 1)

    @override_settings(TOUCHTECHNOLOGY_ADMIN_BRAND=counted_brand)
    def test_callable_brand_is_called_once_for_the_index(self):
        CALLS.clear()
        with self.login(self.superuser):
            self.get_check_200("admin:index")
        self.assertEqual(len(CALLS), 1)


class LogoUrlTests(TestCase):
    def test_static_path_goes_through_static(self):
        self.assertEqual(
            Template("{% load admin %}{{ logo|brand_logo_url }}").render(
                Context({"logo": "img/logo.png"})
            ),
            "/static/img/logo.png",
        )

    def test_absolute_and_root_relative_logos_are_used_as_given(self):
        for logo in ("https://cdn.example.com/logo.png", "/media/logo.png"):
            with self.subTest(logo=logo):
                self.assertEqual(
                    Template("{% load admin %}{{ logo|brand_logo_url }}").render(
                        Context({"logo": logo})
                    ),
                    logo,
                )
