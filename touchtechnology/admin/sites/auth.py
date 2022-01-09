import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.forms.models import modelform_factory
from django.urls import include, path
from django.utils.translation import gettext_lazy as _

from touchtechnology.admin.base import AdminComponent
from touchtechnology.admin.forms import GroupEditForm, UserEditForm
from touchtechnology.common.decorators import staff_login_required_m

ANONYMOUS_USER_ID = getattr(settings, "ANONYMOUS_USER_ID", None)


class UsersGroups(AdminComponent):
    verbose_name = _("Users & Groups")

    user_order_by = ("last_name", "first_name")

    group_class = Group
    group_order_by = ("name",)

    unprotected = False

    def __init__(self, app, name="auth", app_name="auth"):
        super(UsersGroups, self).__init__(app, name, app_name)
        self.user_class = get_user_model()

    @property
    def template_base(self):
        return "touchtechnology/admin"

    def get_urls(self):
        user_patterns = (
            [
                path("", self.list_users, name="list"),
                path("add/", self.edit_user, name="add"),
                path("<int:pk>/", self.edit_user, name="edit"),
                path("<int:pk>/delete/", self.delete_user, name="delete"),
                path("<int:pk>/permission/", self.perms_user, name="perms"),
            ],
            self.app_name,
        )

        group_patterns = (
            [
                path("", self.list_groups, name="list"),
                path("add/", self.edit_group, name="add"),
                path("<int:pk>/", self.edit_group, name="edit"),
                path("<int:pk>/delete/", self.delete_group, name="delete"),
                path("<int:pk>/permission/", self.perms_group, name="perms"),
            ],
            self.app_name,
        )

        urlpatterns = [
            path("", self.index, name="index"),
            path("user/", include(user_patterns, namespace="users")),
            path("group/", include(group_patterns, namespace="groups")),
        ]
        return urlpatterns

    def dropdowns(self):
        dl = (
            (_("Users"), self.reverse("users:list"), "user"),
            (_("Groups"), self.reverse("groups:list"), "users"),
        )
        return dl

    @staff_login_required_m
    def index(self, request, *args, **kwargs):
        return self.redirect(self.reverse("users:list"))

    @staff_login_required_m
    def list_users(self, request, **extra_context):
        queryset = self.user_class.objects.exclude(pk=ANONYMOUS_USER_ID).order_by(
            *self.user_order_by
        )
        return self.generic_list(
            request,
            queryset,
            paginate_by=25,
            permission_required=True,
            search=("first_name", "last_name", "email"),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def edit_user(self, request, pk=None, **extra_context):
        # when performing a creation we need to pass an instance with a random
        # password already set so that the user can initiate a password reset.
        instance = None

        if pk is None:
            instance = self.user_class()
            # generate a password that we will never retain in the clear and
            # would be very hard to brute force attack due to it's length.
            password = uuid.uuid4().hex

            # set the random password so that it's not possible to sign-in to
            # this account without first performing a password reset cycle.
            instance.set_password(password)

        # create a ModelForm using our base UserEditForm, but overload the
        # Meta.fields with value from custom UserModel.USER_EDIT_FORM_FIELDS
        # if it is present. Always exclude certain fields.
        fields = getattr(self.user_class, "USER_EDIT_FORM_FIELDS", "__all__")
        exclude = ("password", "last_login", "date_joined")
        form_class = modelform_factory(
            self.user_class, form=UserEditForm, fields=fields, exclude=exclude
        )

        return self.generic_edit(
            request,
            self.user_class,
            pk=pk,
            instance=instance,
            form_class=form_class,
            related=(),
            permission_required=True,
            post_save_redirect=self.redirect(self.reverse("users:list")),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_user(self, request, pk, **extra_context):
        return self.generic_delete(
            request, self.user_class, pk=pk, permission_required=True
        )

    @staff_login_required_m
    def perms_user(self, request, pk, **extra_context):
        return self.generic_permissions(
            request, self.user_class, pk=pk, **extra_context
        )

    @staff_login_required_m
    def list_groups(self, request, **extra_context):
        queryset = self.group_class.objects.order_by(*self.group_order_by)
        return self.generic_list(
            request,
            queryset,
            paginate_by=25,
            permission_required=True,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def edit_group(self, request, pk=None, **extra_context):
        return self.generic_edit(
            request,
            self.group_class,
            pk=pk,
            form_class=GroupEditForm,
            related=(),
            permission_required=True,
            post_save_redirect=self.redirect(self.reverse("groups:list")),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_group(self, request, pk, **extra_context):
        return self.generic_delete(
            request, self.group_class, pk=pk, permission_required=True
        )

    @staff_login_required_m
    def perms_group(self, request, pk, **extra_context):
        return self.generic_permissions(
            request, self.group_class, pk=pk, **extra_context
        )
