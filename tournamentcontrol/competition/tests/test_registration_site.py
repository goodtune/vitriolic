from test_plus import TestCase


class RegistrationSiteTests(TestCase):

    def test_registration_list(self):
        self.get('rego:index')
        self.response_404()
