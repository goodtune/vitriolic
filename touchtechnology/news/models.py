from __future__ import unicode_literals

from django.db import models
from django.db.models import DateTimeField, ManyToManyField
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from imagekit.models import ImageSpecField
from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.common.db.models import BooleanField, HTMLField
from touchtechnology.news.app_settings import (
    CONTENT_LABEL_CHOICES, DETAIL_IMAGE_KWARGS, DETAIL_IMAGE_PROCESSORS, THUMBNAIL_IMAGE_KWARGS,
    THUMBNAIL_IMAGE_PROCESSORS,
)
from touchtechnology.news.image_processors import processor_factory
from touchtechnology.news.query import ArticleQuerySet, CategoryQuerySet


class AdminUrlModel(AdminUrlMixin, models.Model):

    class Meta:
        abstract = True

    def _get_admin_namespace(self):
        return 'admin:news:%s' % self._meta.model_name

    def _get_url_args(self):
        return (self.pk,)


@python_2_unicode_compatible
class Article(AdminUrlModel):

    headline = models.CharField(max_length=150, verbose_name=_('Headline'))
    slug = models.SlugField(max_length=150, verbose_name=_('Slug'))
    slug_locked = BooleanField(default=False, verbose_name=_('Locked Slug'))

    image = models.ImageField(
        blank=True, null=True, upload_to='news', verbose_name=_('Image'))

    abstract = models.TextField(verbose_name=_('Abstract'))

    published = DateTimeField(
        verbose_name=_('Published'),
        help_text=_("Set a date & time in the future to schedule "
                    "an announcement."))

    byline = models.CharField(
        max_length=75, blank=True, verbose_name=_('Byline'))
    keywords = models.CharField(
        max_length=255, blank=True, verbose_name=_('Keywords'))
    categories = ManyToManyField(
        'Category', blank=True, verbose_name=_('Categories'))

    is_active = BooleanField(default=True, verbose_name=_('Enabled'))

    # image and imagekit spec files
    thumbnail = ImageSpecField(
        source='image',
        processors=processor_factory(THUMBNAIL_IMAGE_PROCESSORS),
        **THUMBNAIL_IMAGE_KWARGS)
    detail_image = ImageSpecField(
        source='image',
        processors=processor_factory(DETAIL_IMAGE_PROCESSORS),
        **DETAIL_IMAGE_KWARGS)

    last_modified = DateTimeField(auto_now=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ('-published',)

    def clean(self):
        if not self.slug_locked or not self.slug:
            self.slug = slugify(self.headline)

    def __str__(self):
        return self.headline

    @property
    def copy(self):
        """
        Backwards compatibility -- concatenate all of the content sections
        into a single string and return this instead.
        """
        return ''.join(self.content.sections.values_list('copy', flat=True))


class ArticleContent(models.Model):

    article = models.ForeignKey(
        Article, related_name='content', verbose_name=_('Article'),
        on_delete=models.PROTECT)
    label = models.SlugField(
        max_length=20, choices=CONTENT_LABEL_CHOICES,
        verbose_name=_('CSS class'))
    sequence = models.PositiveIntegerField(verbose_name=_('Sequence'))
    copy = HTMLField(_("Copy"), blank=True)

    class Meta:
        ordering = ('sequence',)

    def __repr__(self):
        return '<ArticleContent: #%d, article=%d>' % (self.pk, self.article.pk)


@python_2_unicode_compatible
class Category(AdminUrlModel):

    title = models.CharField(max_length=75, verbose_name=_('Title'))
    short_title = models.CharField(
        max_length=50, blank=True, verbose_name=_('Short Title'),
        help_text=_("Used in navigation, a shorter alternative "
                    "to the main title."))
    slug = models.SlugField(max_length=75, verbose_name=_('Slug'))
    slug_locked = BooleanField(default=False, verbose_name=_('Locked Slug'))

    is_active = BooleanField(default=True, verbose_name='Enabled')

    hidden_from_navigation = BooleanField(
        default=False, verbose_name=_("Hide from menus"),
        help_text=_("When set to 'Yes' this object will still be available, "
                    "but will not appear in menus."))

    last_modified = DateTimeField(auto_now=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        verbose_name_plural = 'categories'

    def clean(self):
        if not self.slug_locked or not self.slug:
            self.slug = slugify(self.title)

    def get_absolute_url(self):
        kwargs = {'category': self.slug}
        return reverse('news:category-index', kwargs=kwargs)

    def __str__(self):
        return self.title
