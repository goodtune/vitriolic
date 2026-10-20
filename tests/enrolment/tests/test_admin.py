from test_plus import test as test_plus

from touchtechnology.admin.sites import site
from touchtechnology.common.tests.factories import UserFactory


class RegistrationTests(test_plus.TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_component_is_registered(self):
        names = [c.app_name for c in site._components.values()]
        self.assertIn("enrolment", names)

    def test_index_redirects_to_years(self):
        with self.login(self.superuser):
            self.get("admin:enrolment:index")
            self.response_302()
            self.assertEqual(
                self.last_response["Location"],
                self.reverse("admin:enrolment:schoolyear:list"),
            )
