from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from modelforms.forms import ModelForm

from touchtechnology.common.forms.mixins import (
    BootstrapFormControlMixin,
    SuperUserSlugMixin,
)
from touchtechnology.news.models import Article, Category, Translation


class ArticleForm(SuperUserSlugMixin, ModelForm):
    def __init__(self, *args, **kwargs):
        super(ArticleForm, self).__init__(*args, **kwargs)
        if not self.fields["categories"].queryset.count():
            self.fields.pop("categories", None)
        self.fields["image"].required = getattr(
            settings, "TOUCHTECHNOLOGY_NEWS_IMAGE_REQUIRED", True
        )

    class Meta:
        model = Article
        fields = (
            "headline",
            "image",
            "abstract",
            "copy",
            "published",
            "slug",
            "slug_locked",
            "byline",
            "keywords",
            "categories",
            "is_active",
        )


class CategoryForm(SuperUserSlugMixin, ModelForm):
    class Meta:
        model = Category
        fields = (
            "title",
            "short_title",
            "slug",
            "slug_locked",
            "is_active",
            "hidden_from_navigation",
        )


class TranslationForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Translation
        fields = (
            "locale",
            "headline",
            "abstract",
            "copy",
        )

    locale = forms.ChoiceField(choices=settings.LANGUAGES, label=_("Language"))
