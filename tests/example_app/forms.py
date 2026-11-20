from django import forms

from .models import Acceptance, TestDateTimeField


class TestDateTimeFieldForm(forms.ModelForm):
    class Meta:
        model = TestDateTimeField
        fields = "__all__"


class AcceptanceForm(forms.ModelForm):
    class Meta:
        model = Acceptance
        fields = ("name", "signature")
