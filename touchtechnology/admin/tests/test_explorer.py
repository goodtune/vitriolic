"""
What the explorer takes a page's context to say about where the page is.
"""

from django.test import RequestFactory
from django.utils.functional import SimpleLazyObject
from test_plus import TestCase

from touchtechnology.admin.explorer import build_tree
from touchtechnology.admin.sites import site
from touchtechnology.admin.templatetags.admin import allowed
from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests import factories
from touchtechnology.news.admin import NewsAdminComponent
from touchtechnology.news.tests.factories import ArticleFactory, TranslationFactory


@per_shell
class LazyObjectTests(TestCase):
    """
    A lazy object, such as the ``user`` that every page's context holds,
    answers ``isinstance`` for the model it stands in for but is not an
    instance of it: its type is the wrapper. The page's own objects are in the
    context as themselves, and the trail is found from those.
    """

    def test_a_lazy_object_is_not_a_place_on_the_trail(self):
        article = ArticleFactory.create(headline="Flow Cup begins")
        translation = TranslationFactory.create(article=article, locale="fr")
        request = RequestFactory().get(
            self.reverse(
                "admin:news:article:translation:edit", article.pk, translation.locale
            )
        )
        request.user = factories.UserFactory.create(is_staff=True, is_superuser=True)
        context = {"object": translation, "article": SimpleLazyObject(lambda: article)}

        tree = build_tree(request, context, allowed(site.get_components(), request))

        self.assertEqual(
            [node.label for node in tree.crumbs],
            ["News", "Articles", "Flow Cup begins"],
        )


class TrailKeyTests(TestCase):
    """
    The trail names each object by the lower-case label of its model. An
    article's translations are its only relation, so they have no folder.
    """

    def test_the_trail_to_a_translation(self):
        article = ArticleFactory.create()
        translation = TranslationFactory.create(article=article, locale="fr")
        explorer = site._components[NewsAdminComponent].explorer()

        self.assertEqual(
            explorer.trail_of(translation),
            [
                "news/s0",
                f"news/o:news.article:{article.pk}",
                f"news/o:news.translation:{translation.pk}",
            ],
        )
