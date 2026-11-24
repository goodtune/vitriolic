from unittest import mock

from django.core.files.storage import default_storage
from django.test import SimpleTestCase

from touchtechnology.content.forms import NewFolderForm


class NewFolderFormTests(SimpleTestCase):
    def test_an_empty_name_does_not_ask_the_storage(self):
        form = NewFolderForm(path="reports", data={"name": ""})
        with mock.patch.object(default_storage, "exists") as exists:
            self.assertEqual(form.errors, {})
        self.assertEqual(form.cleaned_data, {"name": ""})
        self.assertEqual(exists.call_args_list, [])

    def test_a_name_that_exists_is_refused(self):
        form = NewFolderForm(path="reports", data={"name": "2026"})
        with mock.patch.object(default_storage, "exists", return_value=True) as exists:
            self.assertEqual(form.errors, {"name": ["Already exists."]})
        self.assertEqual(exists.call_args_list, [mock.call("reports/2026")])

    def test_a_name_at_the_top_is_asked_for_alone(self):
        form = NewFolderForm(path=None, data={"name": "reports"})
        with mock.patch.object(default_storage, "exists", return_value=False) as exists:
            self.assertEqual(form.errors, {})
        self.assertEqual(exists.call_args_list, [mock.call("reports")])
