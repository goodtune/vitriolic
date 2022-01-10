import os.path

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.forms.models import inlineformset_factory
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from modelforms.forms import ModelForm

from touchtechnology.common.default_settings import (
    SITEMAP_EDIT_PARENT,
    SITEMAP_HTTPS_OPTION,
    SITEMAP_ROOT,
)
from touchtechnology.common.forms.mixins import (
    BootstrapFormControlMixin,
    SuperUserSlugMixin,
)
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.app_settings import PAGE_CONTENT_BLOCKS
from touchtechnology.content.models import (
    Content,
    NodeContent,
    Page,
    PageContent,
    Placeholder,
    Redirect,
)


class PlaceholderChoiceField(forms.ModelChoiceField):
    def clean(self, value):
        return super(PlaceholderChoiceField, self).clean(value).pk

    def label_from_instance(self, obj):
        try:
            cls = import_string(obj.path)
        except (ImportError, ValueError):
            return obj.path
        return cls.verbose_name()


class ParentChildModelForm(BootstrapFormControlMixin, ModelForm):
    """
    ``ModelForm`` subclass that can be used to tie together the editing of a
    parent/child relationship in a single form.

    Typical use will be ``SitemapNode`` and any model which is connected by a
    generic foriegn key relationship.
    """

    def __init__(
        self,
        parent_form_class,
        parent_form_kwargs=None,
        child_attr="object",
        instance=None,
        *args,
        **kwargs
    ):
        # we are initiated with the parent instance, but this form is
        # fundamentally that of the child form; track the parent.
        parent = instance if instance is not None else None
        instance = getattr(parent, child_attr, None)
        self.child_attr = child_attr

        # initialise with our newly obtained child instance
        super(ParentChildModelForm, self).__init__(instance=instance, *args, **kwargs)

        # determine if there are any keyword arguments for the parent form to
        # be initialised with and establish the form instance
        pfkw = parent_form_kwargs if parent_form_kwargs else {}
        self.parent_form = parent_form_class(
            instance=parent,
            data=self.data if self.is_bound else None,
            prefix="parent-%s" % self.prefix,
            **pfkw
        )

    def is_valid(self):
        """
        Ensure both the regular ModelForm and the parent_form are valid.
        """
        result = super(ParentChildModelForm, self).is_valid()
        if self.is_bound:
            result = result and self.parent_form.is_valid()
        return result

    def save(self, commit=True):
        """
        Respond with the ``parent_form`` saved instance.
        """
        child = super(ParentChildModelForm, self).save(commit=commit)
        setattr(self.parent_form.instance, self.child_attr, child)
        return self.parent_form.save(commit=commit)

    def __iter__(self):
        """
        Iterate through the fields from the ``parent_form`` first, then
        proceed onto the fields explicitly available on this form.
        """
        for name in self.parent_form.fields:
            yield self.parent_form[name]
        for name in self.fields:
            yield self[name]

    def _get_media(self):
        return super(ParentChildModelForm, self).media + self.parent_form.media

    media = property(_get_media)


class BaseSitemapNodeForm(SuperUserSlugMixin, ModelForm):
    def __init__(self, *args, **kwargs):
        super(BaseSitemapNodeForm, self).__init__(*args, **kwargs)
        if not self.instance.level and self.instance.slug == SITEMAP_ROOT:
            self.fields.pop("slug", None)
            self.fields.pop("slug_locked", None)
        if not self.fields["restrict_to_groups"].queryset.count():
            self.fields.pop("restrict_to_groups", None)
        if not SITEMAP_HTTPS_OPTION:
            self.fields.pop("require_https", None)

    class Meta:
        model = SitemapNode
        fields = (
            "parent",
            "title",
            "short_title",
            "enabled",
            "hidden_from_navigation",
            "hidden_from_sitemap",
            "require_https",
            "restrict_to_groups",
            "slug",
            "slug_locked",
        )


class NewSitemapNodeForm(BaseSitemapNodeForm):
    pass


class SitemapNodeForm(BaseSitemapNodeForm):
    def __init__(self, *args, **kwargs):
        super(SitemapNodeForm, self).__init__(*args, **kwargs)
        if not SITEMAP_EDIT_PARENT and self.instance.pk:
            self.fields.pop("parent", None)
        elif self.instance.pk:
            # update the queryset to exclude the node itself, as well as any
            # nodes which are descendants of itself -- these will both result
            # in an invalid move in the tree.
            nodes = self.fields["parent"].queryset
            nodes = nodes.exclude(pk=self.instance.pk)
            nodes = nodes.exclude(
                tree_id=self.instance.tree_id, level__gt=self.instance.level
            )
            self.fields["parent"].queryset = nodes


class PlaceholderSitemapNodeForm(SitemapNodeForm):
    object_id = PlaceholderChoiceField(
        queryset=Placeholder.objects.all(),
        label=_("Application"),
    )

    def __init__(self, *args, **kwargs):
        super(PlaceholderSitemapNodeForm, self).__init__(*args, **kwargs)
        if not self.instance.content_type:
            self.instance.content_type = ContentType.objects.get_for_model(Placeholder)

    class Meta(SitemapNodeForm.Meta):
        fields = ("object_id",) + SitemapNodeForm.Meta.fields


class NewPlaceholderSitemapNodeForm(PlaceholderSitemapNodeForm):
    class Meta(PlaceholderSitemapNodeForm.Meta):
        fields = ("parent",) + PlaceholderSitemapNodeForm.Meta.fields
        exclude = None


class PlaceholderConfigurationBase(forms.Form):
    def __init__(self, user, instance, *args, **kwargs):
        self.user = user
        self.instance = instance
        initial = kwargs.pop("initial", {})
        initial.update(instance.kwargs)
        super(PlaceholderConfigurationBase, self).__init__(
            initial=initial, *args, **kwargs
        )

    def save(self, *args, **kwargs):
        self.instance.kwargs = self.cleaned_data
        self.instance.save()
        return self.instance.kwargs


PlaceholderContentFormset = inlineformset_factory(
    SitemapNode, NodeContent, fields=("copy",), max_num=1, can_delete=False
)


class PageForm(ParentChildModelForm):
    class Meta:
        model = Page
        fields = ("template", "keywords", "description")


class PageContentForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = PageContent
        fields = ("copy", "label", "sequence")
        widgets = {
            "sequence": forms.HiddenInput(),
        }


BasePageContentFormset = inlineformset_factory(
    Page, PageContent, form=PageContentForm, can_delete=False, extra=0
)


class PageContentFormset(BasePageContentFormset):
    def __init__(self, instance=None, *args, **kwargs):
        self.node = None
        if instance is not None:
            self.node = instance
            instance = instance.object
        super(PageContentFormset, self).__init__(instance=instance, *args, **kwargs)

    def total_form_count(self):
        if isinstance(PAGE_CONTENT_BLOCKS, str):
            # We may want to overload this by tenant.
            callback = import_string(PAGE_CONTENT_BLOCKS)
            return callback(self.node)
        return PAGE_CONTENT_BLOCKS

    def _construct_form(self, i, **kwargs):
        return super(PageContentFormset, self)._construct_form(
            i, empty_permitted=False, initial={"sequence": i + 1}
        )


class ContentForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Content
        fields = ("copy",)


class RedirectEditForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Redirect
        fields = (
            "source_url",
            "destination_url",
            "label",
            "active",
            "permanent",
        )


class FileFormMixin(BootstrapFormControlMixin):
    def __init__(self, path, *args, **kwargs):
        super(FileFormMixin, self).__init__(*args, **kwargs)
        self.path = path


class NewFolderForm(FileFormMixin, forms.Form):

    name = forms.SlugField(max_length=30, required=False, label=_("New folder name"))

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if self.path is None:
            path = name
        else:
            path = os.path.join(self.path, name)
        if name and default_storage.exists(path):
            raise forms.ValidationError(_("Already exists."))
        return name

    def save(self, *args, **kwargs):
        return default_storage.mkdir(name=self.cleaned_data["name"], path=self.path)


class FileUploadForm(FileFormMixin, forms.Form):

    file = forms.FileField(label=_("File to upload"), required=False)

    def save(self, *args, **kwargs):
        f = self.cleaned_data.get("file")
        name = os.path.join(self.path or "", f.name)
        default_storage.save(name, f)
        return name
