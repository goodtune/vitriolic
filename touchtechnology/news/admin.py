from urllib.parse import urljoin

from django.conf.urls import include, url
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _
from touchtechnology.admin.base import AdminComponent
from touchtechnology.common.decorators import staff_login_required_m
from touchtechnology.news.forms import ArticleForm, CategoryForm
from touchtechnology.news.models import Article, Category, Translation


class NewsAdminComponent(AdminComponent):
    verbose_name = _("News")
    unprotected = False

    def __init__(self, app, name="news", app_name="news"):
        super(NewsAdminComponent, self).__init__(app, name, app_name)

    def get_urls(self):
        translation_patterns = (
            [
                url(r"^add/$", self.edit_translation, name="add"),
                url(r"^(?P<locale>[^/]+)/$", self.edit_translation, name="edit"),
                url(
                    r"^(?P<locale>[^/]+)/delete/$",
                    self.delete_translation,
                    name="delete",
                ),
                url(
                    r"^(?P<locale>[^/]+)/permission/$",
                    self.perms_translation,
                    name="perms",
                ),
            ],
            self.app_name,
        )

        article_patterns = (
            [
                url(r"^$", self.list_articles, name="list"),
                url(r"^add/$", self.edit_article, name="add"),
                url(r"^(?P<pk>\d+)/$", self.edit_article, name="edit"),
                url(r"^(?P<pk>\d+)/delete/$", self.delete_article, name="delete"),
                url(r"^(?P<pk>\d+)/permission/$", self.perms_article, name="perms"),
                url(
                    r"^(?P<pk>\d+)/",
                    include(translation_patterns, namespace="translation"),
                ),
            ],
            self.app_name,
        )

        category_patterns = (
            [
                url(r"^$", self.list_categories, name="list"),
                url(r"^add/$", self.edit_category, name="add"),
                url(r"^(?P<pk>\d+)/$", self.edit_category, name="edit"),
                url(r"^(?P<pk>\d+)/delete/$", self.delete_category, name="delete"),
                url(r"^(?P<pk>\d+)/permission/$", self.perms_category, name="perms"),
            ],
            self.app_name,
        )

        urlpatterns = [
            url(r"^$", self.index, name="index"),
            url(r"^article/", include(article_patterns, namespace="article")),
            url(r"^category/", include(category_patterns, namespace="category")),
        ]
        return urlpatterns

    def dropdowns(self):
        dl = (
            (_("Articles"), self.reverse("article:list"), "newspaper-o"),
            (_("Categories"), self.reverse("category:list"), "tag"),
        )
        return dl

    @staff_login_required_m
    def index(self, request, *args, **kwargs):
        return self.redirect(self.reverse("article:list"))

    # Article views

    @staff_login_required_m
    def list_articles(self, request, **kwargs):
        return self.generic_list(
            request,
            Article,
            paginate_by=25,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_article(self, request, pk=None, **kwargs):
        return self.generic_edit(
            request,
            Article,
            pk=pk,
            form_class=ArticleForm,
            form_kwargs={"user": request.user},
            # permission_required=True,
            post_save_redirect=self.redirect(urljoin(request.path, "..")),
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_article(self, request, pk, **kwargs):
        return self.generic_delete(request, Article, pk=pk, permission_required=True)

    @staff_login_required_m
    def perms_article(self, request, pk, **extra_context):
        return self.generic_permissions(request, Article, pk=pk, **extra_context)

    # Translations

    def edit_translation(self, request, pk, locale=None, **extra_context):
        article = get_object_or_404(Article, pk=pk)

        if locale is None:
            instance = Translation(article=article)
        else:
            instance = get_object_or_404(article.translations, locale=locale)

        return self.generic_edit(
            request,
            article.translations,
            instance=instance,
            form_fields=("locale", "headline", "abstract", "copy",),
            post_save_redirect=self.redirect(article.urls["edit"]),
            extra_context=extra_context,
        )

    def delete_translation(self, request, pk, locale, **kwargs):
        instance = get_object_or_404(Translation, article__pk=pk, locale=locale)
        return self.generic_permissions(request, Translation, instance=instance)

    def perms_translation(self, request, pk, locale, **extra_context):
        instance = get_object_or_404(Translation, article__pk=pk, locale=locale)
        return self.generic_permissions(
            request,
            Translation,
            instance=instance,
            post_save_redirect=self.redirect(instance.article.urls["edit"]),
            **extra_context
        )

    # Category views

    @staff_login_required_m
    def list_categories(self, request, *args, **kwargs):
        return self.generic_list(
            request,
            Category,
            paginate_by=25,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_category(self, request, pk=None, *args, **kwargs):
        return self.generic_edit(
            request,
            Category,
            pk=pk,
            form_class=CategoryForm,
            form_kwargs={"user": request.user},
            permission_required=True,
            post_save_redirect=self.redirect(urljoin(request.path, "..")),
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_category(self, request, pk, **kwargs):
        return self.generic_delete(request, Category, pk=pk, permission_required=True)

    @staff_login_required_m
    def perms_category(self, request, pk, **extra_context):
        return self.generic_permissions(
            request,
            Category,
            pk=pk,
            post_save_redirect=self.redirect(
                self.reverse("category:edit", kwargs={"pk": pk})
            ),
            **extra_context
        )
