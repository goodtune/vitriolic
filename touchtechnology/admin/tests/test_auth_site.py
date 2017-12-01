from django.contrib.auth.models import Group
from test_plus import TestCase as PlusTestCase
from touchtechnology.common.tests import factories


class TestCase(PlusTestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.staff = factories.UserFactory.create(is_staff=True)
        self.superuser = factories.UserFactory.create(
            is_staff=True, is_superuser=True)

    def get_generic_200(self, url_name, user, in_context, template, **kw):
        self.assertLoginRequired(url_name, **kw)
        with self.login(user):
            res = self.get(url_name, **kw)
            self.response_200()
            for key in in_context:
                self.assertInContext(key)
            self.assertTemplateUsed(res, template)


class AuthSiteUserTests(TestCase):

    def test_index(self):
        url_name = 'admin:auth:index'

        self.assertLoginRequired(url_name)

        with self.login(self.superuser):
            self.get(url_name)
            self.response_302()

    def test_user_list(self):
        self.get_generic_200(
            'admin:auth:users:list',
            self.superuser,
            ['model', 'object_list'],
            'touchtechnology/admin/list.html',
        )

    def test_user_create(self):
        self.get_generic_200(
            'admin:auth:users:add',
            self.superuser,
            ['model', 'form'],
            'touchtechnology/admin/edit.html',
        )

    def test_user_edit(self):
        self.get_generic_200(
            'admin:auth:users:edit',
            self.superuser,
            ['model', 'form', 'object'],
            'touchtechnology/admin/edit.html',
            pk=1,
        )

    def test_user_perms(self):
        self.get_generic_200(
            'admin:auth:users:perms',
            self.superuser,
            ['model', 'formset'],
            'touchtechnology/admin/permissions.html',
            pk=1,
        )

    def test_user_delete(self):
        url_name = 'admin:auth:users:delete'

        with self.login(self.superuser):
            self.get(url_name, pk=1)
            self.response_405()

            self.post(url_name, pk=1)
            self.response_302()


class AuthSiteGroupTests(TestCase):

    def setUp(self):
        super(AuthSiteGroupTests, self).setUp()
        self.group_instance = Group.objects.create(name='Group')

    def test_group_list(self):
        self.get_generic_200(
            'admin:auth:groups:list',
            self.superuser,
            ['model', 'object_list'],
            'touchtechnology/admin/list.html',
        )

    def test_group_create(self):
        self.get_generic_200(
            'admin:auth:groups:add',
            self.superuser,
            ['model', 'form'],
            'touchtechnology/admin/edit.html',
        )

    def test_group_edit(self):
        self.get_generic_200(
            'admin:auth:groups:edit',
            self.superuser,
            ['model', 'form', 'object'],
            'touchtechnology/admin/edit.html',
            pk=self.group_instance.pk,
        )

    def test_group_perms(self):
        self.get_generic_200(
            'admin:auth:groups:perms',
            self.superuser,
            ['model', 'formset'],
            'touchtechnology/admin/permissions.html',
            pk=self.group_instance.pk,
        )

    def test_group_delete(self):
        url_name = 'admin:auth:groups:delete'

        with self.login(self.superuser):
            self.get(url_name, pk=self.group_instance.pk)
            self.response_405()

            self.post(url_name, pk=self.group_instance.pk)
            self.response_302()
