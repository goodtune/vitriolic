from unittest.mock import patch

from django.template import Context, Template
from django.test import RequestFactory
from test_plus import TestCase

from touchtechnology.common.context_processors import htmx_admin_tabs
from touchtechnology.common.tests import factories


class HtmxAdminTabsFeatureFlagTests(TestCase):
    """Tests for the HTMX admin tabs feature flag."""

    def test_default_flag_is_false(self):
        from touchtechnology.common.default_settings import HTMX_ADMIN_TABS

        self.assertFalse(HTMX_ADMIN_TABS)

    def test_context_processor_returns_flag(self):
        rf = RequestFactory()
        request = rf.get("/")
        result = htmx_admin_tabs(request)
        self.assertIn("htmx_admin_tabs", result)

    def test_context_processor_value_matches_setting(self):
        rf = RequestFactory()
        request = rf.get("/")
        result = htmx_admin_tabs(request)
        # By default, should be False
        self.assertFalse(result["htmx_admin_tabs"])


class HtmxTabTemplateRenderingTests(TestCase):
    """Tests for conditional template rendering based on the HTMX flag."""

    def test_traditional_mode_renders_data_toggle(self):
        template = Template(
            "{% load i18n %}"
            "{% if htmx_admin_tabs %}"
            '<a hx-get="?_htmx_tab=test">HTMX</a>'
            "{% else %}"
            '<a data-toggle="tab">Legacy</a>'
            "{% endif %}"
        )
        context = Context({"htmx_admin_tabs": False})
        output = template.render(context)
        self.assertIn('data-toggle="tab"', output)
        self.assertIn("Legacy", output)
        self.assertNotIn("hx-get", output)

    def test_htmx_mode_renders_hx_get(self):
        template = Template(
            "{% load i18n %}"
            "{% if htmx_admin_tabs %}"
            '<a hx-get="?_htmx_tab=test">HTMX</a>'
            "{% else %}"
            '<a data-toggle="tab">Legacy</a>'
            "{% endif %}"
        )
        context = Context({"htmx_admin_tabs": True})
        output = template.render(context)
        self.assertIn("hx-get", output)
        self.assertIn("HTMX", output)
        self.assertNotIn("Legacy", output)

    def test_htmx_mode_form_inside_tab_pane(self):
        template = Template(
            "{% if htmx_admin_tabs %}"
            '<div class="tab-pane">'
            '<form method="post">Tab form</form>'
            "</div>"
            "{% else %}"
            '<form method="post">'
            '<div class="tab-pane">Legacy form</div>'
            "</form>"
            "{% endif %}"
        )

        # HTMX mode: form is inside the tab pane
        context = Context({"htmx_admin_tabs": True})
        output = template.render(context)
        self.assertIn('<div class="tab-pane"><form method="post">', output)

        # Traditional mode: form wraps all tab panes
        context = Context({"htmx_admin_tabs": False})
        output = template.render(context)
        self.assertIn('<form method="post"><div class="tab-pane">', output)

    def test_htmx_mode_preload_trigger(self):
        template = Template(
            "{% if htmx_admin_tabs %}"
            '<div hx-trigger="load delay:100ms">Preload</div>'
            "{% else %}"
            "<div>Inline</div>"
            "{% endif %}"
        )
        context = Context({"htmx_admin_tabs": True})
        output = template.render(context)
        self.assertIn('hx-trigger="load delay:100ms"', output)


class HtmxTabViewTests(TestCase):
    """Tests for HTMX tab content loading via generic_edit."""

    def setUp(self):
        super().setUp()
        self.superuser = factories.UserFactory.create(
            is_staff=True, is_superuser=True
        )

    def test_edit_view_without_htmx_flag(self):
        """Edit view returns full page when HTMX flag is disabled."""
        with self.login(self.superuser):
            response = self.get("admin:auth:users:edit", pk=self.superuser.pk)
            self.response_200()
            self.assertTemplateUsed(response, "touchtechnology/admin/edit.html")

    @patch("touchtechnology.common.sites.HTMX_ADMIN_TABS", True)
    def test_edit_view_with_htmx_flag_no_htmx_header(self):
        """Edit view returns full page even with flag on if not HTMX request."""
        with self.login(self.superuser):
            response = self.client.get(
                self.reverse("admin:auth:users:edit", pk=self.superuser.pk),
                {"_htmx_tab": "groups"},
            )
            self.assertEqual(response.status_code, 200)
            # Without the HTMX header, it returns the full page
            self.assertTemplateUsed(
                response, "touchtechnology/admin/edit.html"
            )

    @patch("touchtechnology.common.sites.HTMX_ADMIN_TABS", True)
    def test_edit_view_htmx_tab_request_no_related(self):
        """HTMX tab request on view with no related objects returns empty."""
        with self.login(self.superuser):
            response = self.client.get(
                self.reverse("admin:auth:users:edit", pk=self.superuser.pk),
                {"_htmx_tab": "groups"},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 200)
            # The user edit view has no 'related' parameter, so the
            # HTMX tab handler returns the empty tab template
            template_names = [t.name for t in response.templates]
            self.assertIn(
                "touchtechnology/admin/_htmx_tab_empty.html", template_names
            )

    def test_edit_view_htmx_tab_ignored_when_flag_off(self):
        """HTMX tab parameter is ignored when feature flag is off."""
        with self.login(self.superuser):
            response = self.client.get(
                self.reverse("admin:auth:users:edit", pk=self.superuser.pk),
                {"_htmx_tab": "groups"},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(
                response, "touchtechnology/admin/edit.html"
            )
