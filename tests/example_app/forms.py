from django import forms

from .models import TestDateTimeField


class TestDateTimeFieldForm(forms.ModelForm):
    class Meta:
        model = TestDateTimeField
