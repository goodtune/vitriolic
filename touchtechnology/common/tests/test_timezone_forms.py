from django import forms
from touchtechnology.common.forms.fields import SelectDateTimeField


class TestForm1(forms.Form):
    """
    The `timestamp` field is declared inside of the constructor because if we
    do not the field instance will be evaluated at module import time. In a
    real site this would be fine, however in our test cases we need to be able
    to override the USE_TZ setting to test for both modes of operation.
    """
    def __init__(self, *args, **kwargs):
        super(TestForm1, self).__init__(*args, **kwargs)
        self.fields['timestamp'] = SelectDateTimeField()
