from urllib.parse import urlencode, urlunsplit

from django.test import RequestFactory
from django.urls import reverse_lazy
from test_plus import TestCase

from touchtechnology.common.views import login


class LoginTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/members/")

    def test_lazy_url_is_redirected_to_with_next(self):
        self.assert_http_302_found(
            login(self.request, to=reverse_lazy("accounts:login"), next="/members/"),
            url=urlunsplit(
                (
                    "",
                    "",
                    self.reverse("accounts:login"),
                    urlencode({"next": "/members/"}),
                    "",
                )
            ),
        )

    def test_existing_query_parameters_are_preserved(self):
        self.assert_http_302_found(
            login(self.request, to="/sign-in/?lang=en", next="/members/"),
            url=urlunsplit(
                (
                    "",
                    "",
                    "/sign-in/",
                    urlencode({"lang": "en", "next": "/members/"}),
                    "",
                )
            ),
        )
