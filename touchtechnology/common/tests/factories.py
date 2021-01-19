import factory
from django.contrib.auth.models import User
from django.utils import timezone
from factory.django import DjangoModelFactory
from touchtechnology.common.models import SitemapNode


class SitemapNodeFactory(DjangoModelFactory):
    class Meta:
        model = SitemapNode

    title = factory.Faker('country')


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)

    username = factory.Sequence(lambda n: 'username{0}'.format(n + 1))

    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

    email = factory.LazyAttribute(
        lambda a: '{0}@example.com'.format(a.first_name.lower()))
    date_joined = factory.LazyFunction(timezone.now)

    password = factory.PostGenerationMethodCall('set_password', 'password')
