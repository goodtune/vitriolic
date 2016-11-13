import datetime
import factory
import factory.fuzzy

from django.utils import timezone

from example_app import models


class TestDateTimeFieldFactory(factory.DjangoModelFactory):
    class Meta:
        model = models.TestDateTimeField

    datetime = factory.fuzzy.FuzzyDateTime(
        datetime.datetime(2013, 7, 15, tzinfo=timezone.utc),
        datetime.datetime(2015, 6, 15, tzinfo=timezone.utc))
