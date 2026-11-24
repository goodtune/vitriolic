import factory
from django.contrib.auth.models import User
from django.utils import timezone
from factory.django import DjangoModelFactory

from touchtechnology.common.models import SitemapNode


class SitemapNodeFactory(DjangoModelFactory):
    class Meta:
        model = SitemapNode

    title = factory.Faker("country")


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"username{n + 1}")

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")

    # Include the (unique) username so two users who happen to draw the same
    # first name do not share an email address; the password reset form
    # sends one email per matching user, which broke tests that expected one.
    email = factory.LazyAttribute(
        lambda a: f"{a.first_name.lower()}.{a.username}@example.com"
    )
    date_joined = factory.LazyFunction(timezone.now)

    password = factory.PostGenerationMethodCall("set_password", "password")


class StaffFactory(UserFactory):
    """A person who may sign in to the admin, with no permissions of their own."""

    is_staff = True


class SuperUserFactory(StaffFactory):
    """A person who may do anything in the admin."""

    is_superuser = True
