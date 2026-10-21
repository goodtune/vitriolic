from django.test import RequestFactory
from django.urls import reverse_lazy
from test_plus import TestCase

from touchtechnology.common.views import login


class LoginTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/members/")

    def test_lazy_url_is_redirected_to_with_next(self):
        response = login(
            self.request, to=reverse_lazy("accounts:login"), next="/members/"
        )

        self.response_302(response)
        self.assertEqual(
            response["Location"], self.reverse("accounts:login") + "?next=%2Fmembers%2F"
        )

    def test_existing_query_parameters_are_preserved(self):
        response = login(self.request, to="/sign-in/?lang=en", next="/members/")

        self.response_302(response)
        self.assertEqual(response["Location"], "/sign-in/?lang=en&next=%2Fmembers%2F")
