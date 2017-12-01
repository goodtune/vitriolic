from django import forms
from django.conf import settings
from django.forms.models import inlineformset_factory
from django.utils.translation import ugettext_lazy as _
from modelforms.forms import ModelForm
from touchtechnology.common.forms.mixins import (
    BootstrapFormControlMixin, SuperUserSlugMixin,
)
from touchtechnology.content.forms import PlaceholderConfigurationBase
from touchtechnology.news.app_settings import NEWS_CONTENT_BLOCKS
from touchtechnology.news.models import Article, ArticleContent, Category


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
    def __init__(self, *args, **kwargs):
        super(ArticleForm, self).__init__(*args, **kwargs)
        if not self.fields['categories'].queryset.count():
            self.fields.pop('categories', None)
        self.fields['image'].required = \
            getattr(settings, 'TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED', True)

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
        )


class ArticleContentForm(BootstrapFormControlMixin, ModelForm):
    def __init__(self, *args, **kwargs):
        super(ArticleContentForm, self).__init__(*args, **kwargs)
        # hide the label field if it may only contain one value
        choices = [
            each[0]
            for each in self.fields['label'].choices
            if each[0]
        ]
        if len(choices) < 2:
            self.fields['label'].widget = forms.HiddenInput()
            self.initial['label'] = choices[0]

    class Meta:
        model = ArticleContent
        fields = ('copy', 'label', 'sequence')
        widgets = {
            'sequence': forms.HiddenInput,
        }


BaseArticleContentFormset = inlineformset_factory(
    Article, ArticleContent, form=ArticleContentForm,
    can_delete=False, extra=0)


class ArticleContentFormset(BaseArticleContentFormset):
    def total_form_count(self):
        return max(self.get_queryset().count(), NEWS_CONTENT_BLOCKS)

    def _construct_form(self, i, **kwargs):
        return super(ArticleContentFormset, self)._construct_form(
            i, empty_permitted=False, initial={'sequence': i + 1})


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
