from django import forms


class URLInput(forms.URLInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {"class": "form-control"}
        super().__init__(attrs)


class URLField(forms.URLField):
    widget = URLInput
