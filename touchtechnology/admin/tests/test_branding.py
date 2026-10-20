from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from test_plus import TestCase

from touchtechnology.admin.branding import brand_check, brand_from, get_brand


def brand_for(request):
    return {"name": "From callable " + request.path}


class BrandTests(TestCase):
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
