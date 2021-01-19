import factory
from factory.django import DjangoModelFactory
from touchtechnology.content.models import Redirect


class RedirectFactory(DjangoModelFactory):

    class Meta:
        model = Redirect

    source_url = factory.Faker('uri_path')
    destination_url = factory.Faker('uri_path')
