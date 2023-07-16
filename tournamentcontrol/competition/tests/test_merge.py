from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from tournamentcontrol.competition.models import Person
from tournamentcontrol.competition.merge import merge_model_objects
from tournamentcontrol.competition.tests.factories import (
    PersonFactory,
    ClubFactory,
    UserFactory,
)
from django.contrib.auth import get_user_model


def transform(obj):
    return f"{obj.__class__.__name__}: {obj} ({obj.pk})"


class MergeObjectsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.club = ClubFactory.create()

    def test_merge_two_to_one(self):
        "Same person has signed up with a different email"
        people = PersonFactory.create_batch(
            2,
            first_name="John",
            last_name="Smith",
            date_of_birth=date(1982, 7, 17),
            club=self.club,
        )
        person = people[0]
        alias = people[1:]

        # Make sure state is as we expect.
        self.assertQuerysetEqual(
            Person.objects.all(),
            [transform(p) for p in people],
            transform=transform,
            ordered=False,
        )
        self.assertQuerySetEqual(
            get_user_model().objects.exclude(username="anonymous"),
            [transform(p.user) for p in people],
            transform=transform,
            ordered=False,
        )

        # Try merging aliases onto retained. Default of keep_old is False
        # so we should have removed the alias object.
        merge_model_objects(person, alias)

        self.assertQuerysetEqual(
            Person.objects.all(),
            [transform(person)],
            transform=transform,
        )

        # The User table should be unaffacted, we don't remove those.
        self.assertQuerySetEqual(
            get_user_model().objects.exclude(username="anonymous"),
            [transform(p.user) for p in people],
            transform=transform,
            ordered=False,
        )

    def test_merge_many_to_one(self):
        "Same person signs up every year with a different User"
        people = PersonFactory.create_batch(
            5,
            first_name="John",
            last_name="Smith",
            date_of_birth=date(1968, 4, 1),
            club=self.club,
        )
        person = people[0]
        alias = people[1:]

        # Make sure state is as we expect.
        self.assertQuerysetEqual(
            Person.objects.all(),
            [transform(p) for p in people],
            transform=transform,
            ordered=False,
        )
        self.assertQuerySetEqual(
            get_user_model().objects.exclude(username="anonymous"),
            [transform(p.user) for p in people],
            transform=transform,
            ordered=False,
        )

        # Try merging aliases onto retained. Default of keep_old is False
        # so we should have removed the alias object.
        merge_model_objects(person, alias)

        self.assertQuerysetEqual(
            Person.objects.all(),
            [transform(person)],
            transform=transform,
        )

        # The User table should be unaffacted, we don't remove those.
        self.assertQuerySetEqual(
            get_user_model().objects.exclude(username="anonymous"),
            [transform(p.user) for p in people],
            transform=transform,
            ordered=False,
        )

    def test_merge_single_object(self):
        "Incorrect usage of the API: duplicates are not a list"
        people = PersonFactory.create_batch(
            2,
            first_name="John",
            last_name="Smith",
            date_of_birth=date(1982, 7, 17),
            club=self.club,
        )
        person = people[0]
        alias = people[1]

        with self.assertRaisesRegex(
            AssertionError, "Must provide a list of alias objects"
        ):
            merge_model_objects(person, alias)

    def test_merge_non_model(self):
        "Incorrect usage of the API: not Django ORM models"

        class PyPerson:
            pass

        person = PyPerson()
        alias = [PyPerson()]

        with self.assertRaisesRegex(
            TypeError, "Only django.db.models.Model subclasses can be merged"
        ):
            merge_model_objects(person, alias)

    def test_merge_incompatible_models(self):
        "Incorrect usage of the API: Model type conflict"
        person = PersonFactory.create()
        with self.assertRaisesRegex(
            TypeError, "Only models of same class can be merged"
        ):
            merge_model_objects(person, [person.user])

    def test_merge_with_keep_old(self):
        "Alias objects are not deleted when keep_old=True"
        people = PersonFactory.create_batch(
            2,
            first_name="Jane",
            last_name="Jones",
            date_of_birth=date(1978, 3, 3),
            club=self.club,
        )
        person = people[0]
        alias = people[1:]

        # Check that the number of objects is the same before and after.
        before = Person.objects.count()
        merge_model_objects(person, alias, keep_old=True)
        self.assertEqual(Person.objects.count(), before)

    def test_merge_one_to_one_field(self):
        "If combining objects that have OneToOneField, deal appropriately"
        user, alias = UserFactory.create_batch(2, first_name="Jane", last_name="Jones")
        person = PersonFactory.create(user=alias)

        # Make sure state is as we expect.
        self.assertQuerysetEqual(
            User.objects.all(),
            [
                f"Jones, Jane -> {user.username}",
                "Jones, Jane -> Jones, Jane",
            ],
            transform=lambda u: f"{u.person} -> {u}",
            ordered=False,
        )

        merge_model_objects(user, [alias])
        alias.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(user.person, person)
