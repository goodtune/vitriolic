from django.db import models
from django.db.models import DateTimeField, ManyToManyField
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from imagekit.models import ImageSpecField

from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.common.db.models import BooleanField, HTMLField
from touchtechnology.news.app_settings import (
    DETAIL_IMAGE_KWARGS,
    DETAIL_IMAGE_PROCESSORS,
    THUMBNAIL_IMAGE_KWARGS,
    THUMBNAIL_IMAGE_PROCESSORS,
)
from touchtechnology.news.image_processors import processor_factory
from touchtechnology.news.query import ArticleQuerySet, CategoryQuerySet


class AdminUrlModel(AdminUrlMixin, models.Model):
    class Meta:
        abstract = True

    def _get_admin_namespace(self):
        return "admin:news:%s" % self._meta.model_name

    def _get_url_args(self):
        return (self.pk,)


class Article(AdminUrlModel):

    headline = models.CharField(max_length=150, verbose_name=_("Headline"))
    slug = models.SlugField(max_length=150, verbose_name=_("Slug"))
    slug_locked = BooleanField(default=False, verbose_name=_("Locked Slug"))

    image = models.ImageField(
        blank=True, null=True, upload_to="news", verbose_name=_("Image")
    )

    abstract = models.TextField(verbose_name=_("Abstract"))

    published = DateTimeField(
        verbose_name=_("Published"),
        help_text=_("Set a date & time in the future to schedule " "an announcement."),
    )

    byline = models.CharField(max_length=75, blank=True, verbose_name=_("Byline"))
    keywords = models.CharField(max_length=255, blank=True, verbose_name=_("Keywords"))
    categories = ManyToManyField("Category", blank=True, verbose_name=_("Categories"))

    is_active = BooleanField(default=True, verbose_name=_("Enabled"))

    copy = HTMLField(_("Copy"), blank=True)

    # image and imagekit spec files
    thumbnail = ImageSpecField(
        source="image",
        processors=processor_factory(THUMBNAIL_IMAGE_PROCESSORS),
        **THUMBNAIL_IMAGE_KWARGS
    )
    detail_image = ImageSpecField(
        source="image",
        processors=processor_factory(DETAIL_IMAGE_PROCESSORS),
        **DETAIL_IMAGE_KWARGS
    )

    last_modified = DateTimeField(auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ("-published",)

    def clean(self):
        if not self.slug_locked or not self.slug:
            self.slug = slugify(self.headline)

    def get_absolute_url(self):
        return reverse(
            "news:article",
            kwargs={
                "year": self.published.year,
                "month": self.published.strftime("%b").lower(),
                "day": self.published.day,
                "slug": self.slug,
            },
        )

    def __str__(self):
        return self.headline


class Translation(AdminUrlModel):

    article = models.ForeignKey(
        Article, related_name="translations", on_delete=models.CASCADE
    )
    locale = models.CharField(max_length=10, blank=False, null=False)
    headline = models.CharField(max_length=150, verbose_name=_("Headline"))
    abstract = models.TextField(verbose_name=_("Abstract"))
    copy = HTMLField(_("Copy"), blank=True)

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return getattr(self.article, name)

    def _get_admin_namespace(self):
        return "admin:news:article:%s" % self._meta.model_name

    def _get_url_args(self):
        return (self.article.pk, self.locale)

    def get_absolute_url(self):
        published = self.article.published
        return reverse(
            "news:translation",
            kwargs={
                "year": published.year,
                "month": published.strftime("%b").lower(),
                "day": published.day,
                "slug": self.article.slug,
                "locale": self.locale,
            },
        )

    def __str__(self):
        return self.headline

    class Meta:
        unique_together = ("article", "locale")


class Category(AdminUrlModel):

    title = models.CharField(max_length=75, verbose_name=_("Title"))
    short_title = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Short Title"),
        help_text=_("Used in navigation, a shorter alternative " "to the main title."),
    )
    slug = models.SlugField(max_length=75, verbose_name=_("Slug"))
    slug_locked = BooleanField(default=False, verbose_name=_("Locked Slug"))

    is_active = BooleanField(default=True, verbose_name="Enabled")

    hidden_from_navigation = BooleanField(
        default=False,
        verbose_name=_("Hide from menus"),
        help_text=_(
            "When set to 'Yes' this object will still be available, "
            "but will not appear in menus."
        ),
    )

    last_modified = DateTimeField(auto_now=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "categories"

    def clean(self):
        if not self.slug_locked or not self.slug:
            self.slug = slugify(self.title)

    def get_absolute_url(self):
        return reverse("news:category", kwargs={"category": self.slug})

    def __str__(self):
        return self.title
