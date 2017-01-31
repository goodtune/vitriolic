import unittest

from django.test.utils import override_settings
from example_app.models import TestDateTimeField
from example_app.tests.factories import TestDateTimeFieldFactory
from test_plus import TestCase as BTC
from touchtechnology.common.tests import factories


@override_settings(ROOT_URLCONF='example_app.urls')
class TestCase(BTC):

    def setUp(self):
        self.staff = factories.UserFactory.create(
            is_staff=True, is_superuser=True)
        self.regular = factories.UserFactory.create()


class GenericListTests(TestCase):

    def test_vanilla(self):
        self.assertGoodView('generic:vanilla:list')
        self.assertResponseContains('<title>test date time field</title>')
        self.assertResponseContains('<h1>test date time fields</h1>')

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view"
        self.assertLoginRequired('generic:permissions:list')

        with self.login(self.regular):
            self.get('generic:permissions:list')
            self.response_403()

        with self.login(self.staff):
            self.assertGoodView('generic:permissions:list')


class GenericDetailTests(TestCase):

    def setUp(self):
        super(GenericDetailTests, self).setUp()
        TestDateTimeFieldFactory.reset_sequence()
        TestDateTimeFieldFactory.create_batch(20)
        self.instance = TestDateTimeField.objects.earliest('pk')

    def test_vanilla(self):
        self.assertGoodView('generic:vanilla:detail', self.instance.pk)
        self.assertResponseContains('<title>test date time field</title>')
        self.assertResponseContains('<h1>test date time fields</h1>')
        self.assertResponseContains('<p>{}</p>'.format(self.instance.datetime))

    @unittest.skip("permissions_required not implemented for generic_detail")
    def test_permissions_403(self):
        self.get('generic:permissions:detail', self.instance.pk)
        self.response_403()


class GenericEditTests(TestCase):

    def test_vanilla(self):
        self.assertGoodView('generic:vanilla:add')
        self.assertResponseContains('<title>Edit test date time field</title>')

        data = {
            'datetime_0': '1',
            'datetime_1': '1',
            'datetime_2': '2015',
            'datetime_3': '9',
            'datetime_4': '0',
            'datetime_5': 'UTC',
        }
        res = self.post('generic:vanilla:add', data=data)
        self.assertEqual(1, TestDateTimeField.objects.count())
        self.response_302()
        self.assertRedirects(res, self.reverse('generic:vanilla:list'))

        self.assertGoodView('generic:vanilla:list')
        self.assertResponseContains('<li>2015-01-01 09:00:00+00:00</li>')

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view and edit"
        self.assertLoginRequired('generic:permissions:add')

        data = {
            'datetime_0': '1',
            'datetime_1': '1',
            'datetime_2': '2015',
            'datetime_3': '9',
            'datetime_4': '0',
            'datetime_5': 'UTC',
        }

        with self.login(self.regular):
            self.get('generic:permissions:add')
            self.response_403()
            self.post('generic:permissions:add', data=data)
            self.response_403()

        with self.login(self.staff):
            self.assertGoodView('generic:permissions:add')
            self.post('generic:permissions:add', data=data)
            self.response_302()


class GenericDeleteTests(TestCase):

    def setUp(self):
        super(GenericDeleteTests, self).setUp()
        self.object = TestDateTimeFieldFactory.create()

    def test_vanilla(self):
        self.post('generic:vanilla:delete', self.object.pk)
        self.response_302()

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may delete"
        self.post('generic:permissions:delete', self.object.pk)
        self.response_302()  # Anonymous users will be redirected to login

        with self.login(self.regular):
            self.post('generic:permissions:delete', self.object.pk)
            self.response_403()

        with self.login(self.staff):
            self.post('generic:permissions:delete', self.object.pk)
            self.response_302()


class GenericPermissionsTests(TestCase):

    def setUp(self):
        super(GenericPermissionsTests, self).setUp()
        self.object = TestDateTimeFieldFactory.create()

    def test_vanilla(self):
        self.get('generic:vanilla:perms', self.object.pk)
        self.response_403()

        with self.login(self.regular):
            self.get('generic:vanilla:perms', self.object.pk)
            self.response_403()

        with self.login(self.staff):
            self.assertGoodView('generic:vanilla:perms', self.object.pk)
            self.response_200()
            self.assertResponseContains("""
                <p>
                    Control who <em>can change test date time field</em>
                    for the test date time field
                    <strong>{}</strong>.
                </p>
            """.format(self.object))


class GenericEditMultipleTests(TestCase):

    def test_vanilla(self):
        self.assertGoodView('generic:vanilla:edit')
        self.assertResponseContains(
            '<title>Edit multiple test date time fields</title>')

        data = {
            # management form hidden fields
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 0,
            'form-MIN_NUM_FORMS': 0,
            'form-MAX_NUM_FORMS': 1000,

            'form-0-datetime_0': '1',
            'form-0-datetime_1': '1',
            'form-0-datetime_2': '2015',
            'form-0-datetime_3': '9',
            'form-0-datetime_4': '0',
            'form-0-datetime_5': 'UTC',

            'form-1-datetime_0': '3',
            'form-1-datetime_1': '3',
            'form-1-datetime_2': '2016',
            'form-1-datetime_3': '9',
            'form-1-datetime_4': '0',
            'form-1-datetime_5': 'UTC',
        }
        res = self.post('generic:vanilla:edit', data=data)
        self.assertEqual(2, TestDateTimeField.objects.count())
        self.response_302()
        self.assertRedirects(res, self.reverse('generic:vanilla:list'))

        self.assertGoodView('generic:vanilla:list')
        self.assertResponseContains(
            '<ul>'
            '<li>2015-01-01 09:00:00+00:00</li>'
            '<li>2016-03-03 09:00:00+00:00</li>'
            '</ul>')

    def test_permissions_403(self):
        "Ensure unprivileged user is denied, superuser may view and edit"
        self.assertLoginRequired('generic:permissions:edit')

        data = {
            # management form hidden fields
            'form-TOTAL_FORMS': 2,
            'form-INITIAL_FORMS': 0,
            'form-MIN_NUM_FORMS': 0,
            'form-MAX_NUM_FORMS': 1000,

            'form-0-datetime_0': '1',
            'form-0-datetime_1': '1',
            'form-0-datetime_2': '2015',
            'form-0-datetime_3': '9',
            'form-0-datetime_4': '0',
            'form-0-datetime_5': 'UTC',

            'form-1-datetime_0': '3',
            'form-1-datetime_1': '3',
            'form-1-datetime_2': '2016',
            'form-1-datetime_3': '9',
            'form-1-datetime_4': '0',
            'form-1-datetime_5': 'UTC',
        }

        with self.login(self.regular):
            self.get('generic:permissions:edit')
            self.response_403()
            self.post('generic:permissions:edit', data=data)
            self.response_403()

        with self.login(self.staff):
            self.assertGoodView('generic:permissions:edit')
            self.post('generic:permissions:edit', data=data)
            self.response_302()

        self.assertEqual(2, TestDateTimeField.objects.count())
