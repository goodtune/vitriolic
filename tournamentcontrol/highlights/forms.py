from modelforms.forms import ModelForm

from .models import BaseTemplate, SeasonTemplate


class BaseTemplateForm(ModelForm):
    class Meta:
        model = BaseTemplate
        fields = ["name", "slug", "template_type", "svg"]


class SeasonTemplateForm(ModelForm):
    class Meta:
        model = SeasonTemplate
        fields = ["season", "base", "name", "svg", "config"]
