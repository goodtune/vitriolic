import datetime

import factory
import factory.fuzzy
from django.utils import timezone

from touchtechnology.news.models import Article, Category


class ArticleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Article

    headline = factory.Faker('sentence')
    abstract = factory.Faker('paragraph')
    published = factory.fuzzy.FuzzyDateTime(
        datetime.datetime(2013, 7, 15, tzinfo=timezone.utc),
        force_microsecond=0)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    title = factory.Faker('country')
