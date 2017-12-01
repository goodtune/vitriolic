import factory
from touchtechnology.content.models import Redirect


class RedirectFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Redirect

    source_url = factory.Faker('uri_path')
    destination_url = factory.Faker('uri_path')
