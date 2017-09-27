from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from modelforms.forms import ModelForm
from touchtechnology.common.forms.mixins import SuperUserSlugMixin
from touchtechnology.content.forms import PlaceholderConfigurationBase
from touchtechnology.news.models import Article, Category
from django.contrib.postgres.forms import SplitArrayField
from touchtechnology.common.forms.fields import HTMLField

class ConfigurationForm(PlaceholderConfigurationBase):

    def __init__(self, *args, **kwargs):
        super(ConfigurationForm, self).__init__(*args, **kwargs)
        choices = [('', _('Please select...'))]
        choices += list(Category.objects.values_list('slug', 'title'))
        self.fields['category'] = forms.ChoiceField(
            choices=choices, required=False)
        self.fields['category'].widget.attrs.update(
            {'class': 'form-control'})


class ArticleForm(SuperUserSlugMixin, ModelForm):
    content_copy = SplitArrayField(HTMLField, 2)

    def __init__(self, *args, **kwargs):
        super(ArticleForm, self).__init__(*args, **kwargs)
        if not self.fields['categories'].queryset.count():
            self.fields.pop('categories', None)
        self.fields['image'].required = \
            getattr(settings, 'TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED', True)
        print self.fields['content_copy'].widget.attrs
        for widget in self.fields['content_copy'].widget.subwidgets:
            print widget

    class Meta:
        model = Article
        fields = (
            'headline',
            'image',
            'abstract',
            'published',
            'slug',
            'slug_locked',
            'byline',
            'keywords',
            'categories',
            'is_active',
            'content_copy',
            'content_class',
        )


class CategoryForm(SuperUserSlugMixin, ModelForm):
    class Meta:
        model = Category
        fields = (
            'title',
            'short_title',
            'slug',
            'slug_locked',
            'is_active',
            'hidden_from_navigation',
        )
