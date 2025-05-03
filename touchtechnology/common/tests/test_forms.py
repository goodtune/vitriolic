# coding=UTF-8

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from touchtechnology.common.forms.auth import permissionformset_factory
from touchtechnology.common.forms.fields import EmailField, HTMLField
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
