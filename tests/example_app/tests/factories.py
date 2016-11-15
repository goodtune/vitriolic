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
        datetime.datetime(2015, 6, 15, tzinfo=timezone.utc),
        force_microsecond=0,
    )


class RelativeFactory(factory.DjangoModelFactory):
    class Meta:
        model = models.Relative

    name = factory.Sequence(lambda n: 'Sample %d' % n)

    link = factory.SubFactory(TestDateTimeFieldFactory)
