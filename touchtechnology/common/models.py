import logging
from operator import attrgetter
from os.path import join

import mptt
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse_lazy
from django.db import models
from django.db.models.signals import post_save
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _

from touchtechnology.common.db.models import (
    BooleanField,
    DateTimeField,
    ManyToManyField,
    TreeField,
)
from touchtechnology.common.default_settings import SITEMAP_ROOT
from touchtechnology.common.mixins import NodeRelationMixin

logger = logging.getLogger(__name__)


@python_2_unicode_compatible
class SitemapNodeBase(models.Model):

    title = models.CharField(max_length=255, verbose_name=_(u"Title"))

    short_title = models.CharField(
        max_length=100, blank=True, verbose_name=_(u"Short title"),
        help_text=_(u"This is used in navigation menus instead of the longer "
                    u"title value."))

    slug = models.SlugField(
        max_length=255, db_index=True, verbose_name=_(u"Slug"))

    slug_locked = BooleanField(default=False, verbose_name=_(u"Slug locked"))

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def clean(self):
        if SITEMAP_ROOT is None or self.slug != SITEMAP_ROOT:
            if not self.slug_locked or not self.slug:
                self.slug = slugify(self.title)


class SitemapNode(NodeRelationMixin, SitemapNodeBase):
    """
    Base class which can be used to represent the structure of the site.
    """
    parent = TreeField(
        'self', blank=True, null=True, verbose_name=_(u"Parent"),
        related_name='children')

    content_type = models.ForeignKey(ContentType, blank=True, null=True)

    object_id = models.PositiveIntegerField(blank=True, null=True)

    object = GenericForeignKey('content_type', 'object_id')

    require_https = BooleanField(
        default=False, verbose_name=_(u"HTTPS Required"),
        help_text=_(u"Force this to be served via HTTPS."))

    # visibility and access control
    enabled = BooleanField(
        default=True, verbose_name=_(u"Enabled"),
        help_text=_(u"Set this to 'No' to disable this object and it's "
                    u"children on the site."))

    hidden_from_navigation = BooleanField(
        default=False, verbose_name=_(u"Hide from menus"),
        help_text=_(u"When set to 'Yes' this object will still be available, "
                    u"but will not appear in menus."))

    hidden_from_sitemap = BooleanField(
        default=False, verbose_name=_(u"Hide from sitemap"),
        help_text=_(u"When set to 'Yes' this object will not be listed in "
                    u"the auto-generated sitemap."))

    hidden_from_robots = BooleanField(
        default=False, verbose_name=_(u"Hide from spiders"),
        help_text=_(u"Set this to 'Yes' to prevent search engines from "
                    u"indexing this part of the site.<br />\n"
                    u"<strong>Warning:</strong> this may affect your ranking "
                    u"in search engines."))

    restrict_to_groups = ManyToManyField(
        to='auth.Group', blank=True, verbose_name=_(u"Restrict to Groups"),
        help_text=_(u"If you select one or more of these groups your "
                    u"visitors will need to be logged in and a member of an "
                    u"appropriate group to view this part of the site."))

    last_modified = DateTimeField(auto_now=True)

    def __repr__(self):
        return u'<{0}: "{1}" ({2}:{3},{4})>'.format(
            self.__class__.__name__, self.title,
            self.level, self.lft, self.rght)

    def disable(self):
        logger.debug("Disabling node %r", self)
        self.enabled = False
        return self.save()
    disable.alters_data = True

    def is_home_page(self):
        return self.level == 0 and self.slug == SITEMAP_ROOT

    def is_accessible(self, user):
        groups = Group.objects.filter(sitemapnode=self)
        groups |= Group.objects.filter(sitemapnode__in=self.get_ancestors())
        return set(groups).difference(user.groups.all())

    def get_absolute_url(self):
        """
        This really needs to be made more efficient -- at present we hit the
        database an awful lot of times to calculate the initial
        ``get_absolute_url`` call so we can build our URLconf in middleware...
        chicken and egg!
        """
        url = '/'
        node = SitemapNode.objects.get(pk=self.pk)
        parts = node.get_ancestors(include_self=True).exclude(
            level=0, slug=SITEMAP_ROOT).values_list('slug', flat=True)
        if parts:
            url += join(*parts)
        if not url.endswith('/') and settings.APPEND_SLASH:
            url += '/'
        return url

    def _move(self, direction):
        """
        Move a node around within the same level of the tree (ie. parent does
        not change, just the order amongst siblings).
        """
        if direction == 'left':
            target = self.get_previous_sibling()
        elif direction == 'right':
            target = self.get_next_sibling()
        else:
            raise ValueError(_(u"direction must be one of 'left' or 'right'"))
        if target is not None:
            self.move_to(target, direction)
            post_save.send(self.__class__, instance=self)

    def move_up(self):
        self._move('left')
    move_up.alters_data = True

    def move_down(self):
        self._move('right')
    move_down.alters_data = True

    @cached_property
    def kwargs(self):
        return dict(map(attrgetter('key', 'value'), self.kw.all()))

    @cached_property
    def urls(self):
        # This namespace won't exist unless you are using the
        # touchtechnology.content application in tandem with the
        # touchtechnology.admin application, but you probably won't be using
        # the .urls API if that isn't true anyway!
        namespace = 'admin:content:%s' % (self.content_type or "folder")
        args = (self.id,)
        crud = {
            'edit': reverse_lazy('%s:edit' % namespace, args=args),
            'delete': reverse_lazy('%s:delete' % namespace, args=args),
            'perms': reverse_lazy('%s:perms' % namespace, args=args),
        }
        return crud

    class Meta:
        ordering = ('tree_id', 'lft')
        verbose_name = 'folder'


mptt.register(SitemapNode)