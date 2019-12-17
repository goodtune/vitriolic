import datetime

import factory
import factory.fuzzy
from django.utils import timezone
from django.utils.text import slugify
from touchtechnology.news.models import Article, Category, Translation


class ArticleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Article

    headline = factory.Faker("sentence")
    abstract = factory.Faker("paragraph")
    published = factory.fuzzy.FuzzyDateTime(
        datetime.datetime(2013, 7, 15, tzinfo=timezone.utc), force_microsecond=0
    )
    copy = factory.Faker("paragraph")
    slug = factory.LazyAttribute(lambda a: slugify(a.headline))


class TranslationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Translation

    headline = factory.Faker("sentence")
    abstract = factory.Faker("paragraph")
    copy = factory.Faker("paragraph")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    title = factory.Faker("country")
