"""[Developer API] Forms used by the News admin interface."""

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
    """Form for creating and editing Article instances."""

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
    """Form for managing article categories."""

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
    """Form for editing translations of an Article."""

    class Meta:
        model = Translation
        fields = (
            "locale",
            "headline",
            "abstract",
            "copy",
        )

    locale = forms.ChoiceField(choices=settings.LANGUAGES, label=_("Language"))
