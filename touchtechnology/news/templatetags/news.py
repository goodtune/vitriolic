from django.core.paginator import Paginator
from django.template import Library
from django.utils.translation import gettext_lazy as _

from touchtechnology.news.models import Article, Category

register = Library()


@register.filter("category")
def get_category(slug):
    return Category.objects.get(slug=slug)


@register.inclusion_tag("touchtechnology/news/_related_list.html", takes_context=True)
def related_articles(context, article, limit=None, order_by=None):
    categories = article.categories.live()
    articles = (
        Article.objects.live()
        .exclude(pk=article.pk)
        .filter(categories__in=categories)
        .distinct()
    )

    if order_by is not None:
        articles = articles.order_by(*order_by.split(","))

    if limit is not None:
        articles = articles[: int(limit)]

    # FIXME backwards compatibility for custom templates
    context["slice"] = ":"

    context["article_list"] = articles
    return context


@register.inclusion_tag("touchtechnology/news/_related_list.html", takes_context=True)
def related_categories(context, article=None, limit=None):
    """
    If an article is provided, then we select categories relating to it.
    Otherwise we select all article categories.
    """
    if article is None:
        categories = Category.objects.all()
    else:
        categories = article.categories.all()
    context["category_list"] = categories
    return context


@register.inclusion_tag(
    "touchtechnology/news/_latest_articles.html", takes_context=True
)
def latest_articles(context, count=5, title=_("Latest News")):
    articles = Article.objects.live()
    paginator = Paginator(articles, count)
    page = paginator.page(1)
    context["paginator"] = paginator
    context["page"] = page
    context["article_list"] = page.object_list
    context["title"] = title
    return context
