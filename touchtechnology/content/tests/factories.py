import factory
from touchtechnology.content import models


class ChunkFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = models.Chunk


class RedirectFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = models.Redirect

    source_url = factory.Faker('uri_path')
    destination_url = factory.Faker('uri_path')
