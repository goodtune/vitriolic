# coding=UTF-8

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from touchtechnology.common.forms.auth import permissionformset_factory
from touchtechnology.common.forms.fields import (
    EmailField,
    GoogleMapsField,
    HTMLField,
)
from touchtechnology.common.models import SitemapNode
from touchtechnology.common.tests import factories


class CustomFormField(TestCase):
    def test_email_field(self):
        self.assertFieldOutput(
            EmailField,
            {"a@a.com": "a@a.com", "B@B.COM": "b@b.com"},
            {"aaa": ["Enter a valid email address."]},
        )
        self.assertFieldOutput(
            EmailField,
            {"a@a.com": "a@a.com", "B@B.COM": "B@B.COM"},
            {"aaa": ["Enter a valid email address."]},
            (),
            {"lowercase": False},
        )

    def test_html_field(self):
        valid = {
            '<a href="http://www.example.com/">Example</a>': '<a href="http://www.example.com/">Example</a>',
            "Penn\u00a0& Teller": "Penn&nbsp;& Teller",
            "sauté": "saut&eacute;",
        }
        self.assertFieldOutput(HTMLField, valid, {})

    maxDiff = None


class LocationWidgetTest(TestCase):
    def test_render(self):
        field = GoogleMapsField(max_length=100)
        self.assertHTMLEqual(
            field.widget.render("latlng", "-33.8471,151.0685,15"),
            '<div class="location-widget">'
            '<div class="location-widget-inputs">'
            '<input type="text" name="latlng_0" value="-33.8471" placeholder="Latitude">'
            '<input type="text" name="latlng_1" value="151.0685" placeholder="Longitude">'
            '<input type="text" name="latlng_2" value="15" placeholder="Zoom">'
            "</div>"
            '<div class="location-widget-map" data-zoom="8" '
            'style="height: 200px; max-width: 300px; margin-top: 5px;"></div>'
            "</div>",
        )

    def test_media(self):
        field = GoogleMapsField(max_length=100)
        self.assertHTMLEqual(
            str(field.widget.media),
            '<link href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" '
            'media="all" rel="stylesheet">'
            '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
            '<script src="/static/touchtechnology/common/js/location-widget.js">'
            "</script>",
        )

    def test_clean(self):
        field = GoogleMapsField(max_length=100)
        self.assertEqual(
            field.clean(["-33.8471", "151.0685", "15"]), "-33.8471,151.0685,15"
        )


class TestPermissionFormSet(TestCase):
    def setUp(self):
        self.UserModel = get_user_model()
        self.queryset = Permission.objects.filter(
            content_type=ContentType.objects.get_for_model(SitemapNode)
        ).exclude(codename__startswith="add_")
        self.instance = SitemapNode.objects.create(title="permissions")
        self.staff = factories.UserFactory.create(is_staff=True, is_superuser=True)
        self.regular = factories.UserFactory.create()

    def test_staff_only(self):
        formset_class = permissionformset_factory(SitemapNode, staff_only=True)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertQuerySetEqual(
            formset.forms[0].fields["users"].queryset,
            (repr(o) for o in self.UserModel.objects.filter(is_staff=True)),
            transform=repr,
        )

    def test_all_users(self):
        formset_class = permissionformset_factory(SitemapNode, staff_only=False)
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertQuerySetEqual(
            formset.forms[0].fields["users"].queryset.order_by("pk"),
            (repr(o) for o in self.UserModel.objects.order_by("pk")),
            transform=repr,
        )

    def test_user_widget_checkbox_lte(self):
        "Less than equal to 5 users, should be iCheckboxSelectMultiple widget"
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False, max_checkboxes=5
        )
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertEqual(
            formset.forms[0].fields["users"].queryset.count(),
            3,  # need to account for the AnonymousUser that guardian creates
        )

    def test_user_widget_checkbox_eq(self):
        "Equal to 3 users, should be iCheckboxSelectMultiple widget"
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False, max_checkboxes=3
        )
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertEqual(
            formset.forms[0].fields["users"].queryset.count(),
            3,  # need to account for the AnonymousUser that guardian creates
        )

    def test_user_widget_select2(self):
        "More than 1 user, should not be iCheckboxSelectMultiple widget"
        formset_class = permissionformset_factory(
            SitemapNode, staff_only=False, max_checkboxes=1
        )
        formset = formset_class(queryset=self.queryset, instance=self.instance)
        self.assertEqual(
            formset.forms[0].fields["users"].queryset.count(),
            3,  # need to account for the AnonymousUser that guardian creates
        )
