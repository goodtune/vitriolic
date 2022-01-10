# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import logging
from importlib import import_module

from django.contrib.contenttypes.fields import GenericRelation
from django.core.cache import caches
from django.db import models
from django.db.models import DateTimeField
from django.utils.module_loading import import_string
from django.utils.text import slugify
from django.utils.translation import gettext, gettext_lazy as _
from first import first

from touchtechnology.admin.mixins import AdminUrlMixin
from touchtechnology.common.db.models import (
    BooleanField,
    HTMLField,
    TemplatePathField,
)
from touchtechnology.content.app_settings import (
    NODE_CACHE,
    PAGE_CONTENT_CLASSES,
    PAGE_TEMPLATE_BASE,
    PAGE_TEMPLATE_FOLDER,
    PAGE_TEMPLATE_REGEX,
)

logger = logging.getLogger(__name__)

PAGE_CONTENT_CLASS_CHOICES = zip(PAGE_CONTENT_CLASSES, PAGE_CONTENT_CLASSES)

PAGE_CONTENT_CLASS_DEFAULT = first(PAGE_CONTENT_CLASSES)

SITE_CACHE_KEY = "_site_cache"


class AdminUrlModel(AdminUrlMixin, models.Model):
    class Meta:
        abstract = True

    def _get_admin_namespace(self):
        return "admin:content:%s" % self._meta.model_name

    def _get_url_args(self):
        return (self.id,)

    def __repr__(self):
        return "<{}: {}>".format(self.__class__, self)


class Page(models.Model):

    # allows us to customise the template on a per page basis

    template = TemplatePathField(
        max_length=200,
        blank=True,
        template_base=PAGE_TEMPLATE_BASE,
        template_folder=PAGE_TEMPLATE_FOLDER,
        match=PAGE_TEMPLATE_REGEX,
        recursive=True,
        verbose_name=_("Template"),
    )

    # SEO metadata fields

    keywords = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Keywords"),
        help_text=_(
            "This should be a comma-separated list of terms that "
            "indicate the content of this page - used to assist "
            "Search Engines rank your page."
        ),
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Description"),
        help_text=_(
            "Search Engines may use this when determining the "
            "relevance of your page."
        ),
    )

    last_modified = DateTimeField(auto_now=True)

    def __repr__(self):
        return "<Page: #{}>".format(self.pk)


class Content(models.Model):

    # FIXME and put the ``copy`` attribute on the ``PageContent`` model, we
    # aren't actually reusing the ``Content`` in any way, so simplify the
    # implementation to move the data back up and onto.

    # The M2M relation on ``Page`` will become a FK on ``PageContent``
    # instead.

    copy = HTMLField(blank=True)

    def __repr__(self):
        return "<Content: #%d>" % self.pk


class PageContent(models.Model):

    page = models.ForeignKey(
        Page, related_name="content", verbose_name=_("Page"), on_delete=models.PROTECT
    )
    label = models.SlugField(
        max_length=20,
        choices=PAGE_CONTENT_CLASS_CHOICES,
        default=PAGE_CONTENT_CLASS_DEFAULT,
        verbose_name=_("CSS class"),
    )
    sequence = models.PositiveIntegerField(verbose_name=_("Sequence"))
    copy = HTMLField(blank=True, verbose_name=_("Copy"))

    last_modified = DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence",)

    def __repr__(self):
        return "<PageContent: #%d, page=%d>" % (self.pk, self.page.pk)


class Chunk(AdminUrlModel):

    slug = models.SlugField(verbose_name=_("Slug"))
    copy = HTMLField(blank=True, verbose_name=_("Page Copy"))

    def __str__(self):
        return self.slug


class NodeContent(models.Model):

    node = models.ForeignKey(
        "common.SitemapNode",
        related_name="contents",
        verbose_name=_("Node"),
        on_delete=models.PROTECT,
    )
    copy = HTMLField(blank=True, verbose_name=_("Page Copy"))


class Placeholder(models.Model):

    path = models.CharField(max_length=255, verbose_name=_("Module path"))
    namespace = models.CharField(
        max_length=255, db_index=True, verbose_name=_("Namespace")
    )

    nodes = GenericRelation("common.SitemapNode", verbose_name=_("Nodes"))

    class Meta:
        ordering = ("path",)

    def __str__(self):
        try:
            cls = import_string(self.path)
        except (ImportError, ValueError):
            return gettext("Not installed")
        return cls.verbose_name()

    def _install(self, parent=None):
        """
        Adding an internal method to allow us to rig up all the applications.
        """
        if not self.nodes.count():
            module_path, site = self.path.rsplit(".", 1)
            module = import_module(module_path)
            if hasattr(module, site):
                instance = getattr(module, site)
                self.nodes.create(
                    title=instance.name.title(),
                    slug=slugify(instance.name),
                    parent=parent,
                )

    @property
    def module(self):
        if not hasattr(self, "_module"):
            module_path = self.path.split(".")
            while module_path:
                try:
                    module = import_module(".".join(module_path))
                    if hasattr(module, "VERSION"):
                        self._module = module
                        break
                except ImportError:
                    module = None
                module_path.pop()
        return self._module

    def callable(self):
        try:
            return import_string(self.path)
        except ValueError:
            return None

    def site(self, node):
        cache_key = "node%d" % node.pk
        cls = import_string(self.path)
        site = cls(node=node, name=cache_key, **node.kwargs)
        return site

    def invalidate_cache(self):
        # Since this is forced cache invalidation, we should log it.
        logger.info("Forced invalidation of Application cache.")
        cache = caches[NODE_CACHE]
        return cache.clear()

    invalidate_cache.alters_data = True


class Redirect(AdminUrlModel):

    source_url = models.CharField(
        max_length=250,
        verbose_name=_("Source URL"),
        help_text=_("The path that will trigger the redirection."),
    )

    destination_url = models.CharField(
        max_length=500,
        verbose_name=_("Destination URL"),
        help_text=_("The URL or path that the browser will be sent to."),
    )

    label = models.CharField(max_length=100, blank=True, verbose_name=_("Label"))

    active = BooleanField(default=True, verbose_name=_("Active"))
    permanent = BooleanField(default=False, verbose_name=_("Permanent"))

    class Meta:
        ordering = ("destination_url",)

    def __str__(self):
        if self.label:
            return self.label
        return "{src} → {dst}".format(src=self.source_url, dst=self.destination_url)
