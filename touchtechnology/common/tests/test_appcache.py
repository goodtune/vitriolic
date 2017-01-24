import pickle

from django.test import TestCase
from touchtechnology.common.sites import AccountsSite


class AppCacheTests(TestCase):

    def test_account_site_simple(self):
        site = AccountsSite()
        pickle.loads(pickle.dumps(site))
