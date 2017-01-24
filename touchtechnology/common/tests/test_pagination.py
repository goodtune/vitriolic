from django.test.utils import override_settings
from test_plus import TestCase


@override_settings(ROOT_URLCONF='example_app.urls')
class PaginationTest(TestCase):

    # Reuse the existing fixture, but might be better to use factory_boy to
    # create and arbitrary set of values in case the query_string fixture ever
    # needs to change.
    fixtures = ['query_string']

    def test_setting_only(self):
        self.get('pagination:setting_only')
        n = len(self.get_context('object_list'))
        self.assertEqual(n, 5)

    def test_parameter(self):
        self.get('pagination:parameter', 3)
        n = len(self.get_context('object_list'))
        self.assertNotEqual(n, 5)
        self.assertEqual(n, 3)

    def test_parameter_no_pagination(self):
        self.get('pagination:parameter', 0)
        n = len(self.get_context('object_list'))
        self.assertIsNone(self.get_context('paginator'))
        self.assertEqual(n, 12)  # if fixture changes, may need updating
