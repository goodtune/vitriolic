# encoding=utf8

from __future__ import unicode_literals

import re
from urllib.parse import urlparse

from django.core import mail
from test_plus import TestCase
from touchtechnology.common.tests import factories

# Based on regular expression found at https://gist.github.com/gruber/8891611
url_re = re.compile(
    r"""# noqa
(?xi)
\b
(                                             # Capture 1: entire matched URL
  (?:
    https?:                                   # URL protocol and colon
    (?:
      /{1,3}                                  # 1-3 slashes
      |                                       #   or
      [a-z0-9%]                               # Single letter or digit or '%'
                                              # (Trying not to match e.g. "URI::Escape")
    )
    |                                         #   or
                                              # looks like domain name followed by a slash:
    [a-z0-9.\-]+[.]
    (?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj| Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)
    /
  )
  (?:                                         # One or more:
    [^\s()<>{}\[\]]+                          # Run of non-space, non-()<>{}[]
    |                                         #   or
    \([^\s()]*?\([^\s()]+\)[^\s()]*?\)        # balanced parens, one level deep: (â€¦(â€¦)â€¦)
    |
    \([^\s]+?\)                               # balanced parens, non-recursive: (â€¦)
  )+
  (?:                                         # End with:
    \([^\s()]*?\([^\s()]+\)[^\s()]*?\)        # balanced parens, one level deep: (â€¦(â€¦)â€¦)
    |
    \([^\s]+?\)                               # balanced parens, non-recursive: (â€¦)
    |                                         #   or
    [^\s`!()\[\]{};:'".,<>?Â«Â»â€œâ€â€˜â€™] # not a space or one of these punct chars
  )
#  |                                           # OR, the following to match naked domains:
#  (?:
#      (?<!@)                                  # not preceded by a @, avoid matching foo@_gmail.com_
#    [a-z0-9]+
#    (?:[.\-][a-z0-9]+)*
#    [.]
#    (?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj| Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)
#    \b
#    /?
#    (?!@)                                     # not succeeded by a @, avoid matching "foo.na" in "foo.na@example.com"
#  )
)
""",
    re.VERBOSE,
)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.staff = factories.UserFactory.create(is_staff=True, is_superuser=True)
        self.regular = factories.UserFactory.create()

    def test_login(self):
        self.assertGoodView("accounts:login")

    def test_logout(self):
        self.assertGoodView("accounts:logout")

    def test_password_change(self):
        with self.login(self.regular):
            self.assertGoodView("accounts:password_change")

    def test_password_change_done(self):
        with self.login(self.regular):
            self.assertGoodView("accounts:password_change_done")

    def test_password_reset_complete(self):
        self.assertGoodView("accounts:password_reset_complete")

    def test_password_reset_confirm(self):
        self.assertGoodView("accounts:password_reset_confirm", uidb64="z", token="1-a")

    def test_password_reset_GET(self):
        self.assertGoodView("accounts:password_reset")

    def test_password_reset_POST(self):
        data = {
            "email": self.staff.email,
        }
        self.post("accounts:password_reset", data=data)

        # check that the form submission was successful and
        # redirection to the "done" page has occured.
        redirect_to = self.reverse("accounts:password_reset_done")
        self.assertRedirects(self.last_response, redirect_to)

        # check that an email has been delivered
        self.assertEqual(len(mail.outbox), 1)

        # check that the email body is correct
        text_re = re.compile(
            """Just in case you've forgotten, your username is ".+"."""
        )
        self.assertRegex(mail.outbox[0].body, text_re)

        # check that the URL in the email body works
        link = url_re.findall(mail.outbox[0].body)[0]
        self.get(urlparse(link).path, follow=True)
        self.assertResponseContains("<h1>Enter new password</h1>")
