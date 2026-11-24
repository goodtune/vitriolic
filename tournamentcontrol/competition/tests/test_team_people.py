"""
The people of a team: the rules shared by the admin site, the club
registration pages and the administration MCP tools.

* a team without a club is given one before it has people
  (``Team.ensure_club``);
* a number is worn by one person of a team at a time;
* a person with statistics for a team stays in it;
* a person with statistics, or part way through a season, is not deleted;
* a club does not take the address of another.
"""

import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from tournamentcontrol.competition.forms import ClubEditForm, TeamAssociationFormSet
from tournamentcontrol.competition.models import Club, Competition, Person, Team
from tournamentcontrol.competition.tests import factories

TEAM_CLUB = "admin:fixja:competition:season:division:team:club"
ASSOCIATION = "admin:fixja:competition:season:division:team:teamassociation"


class SocialTeamMixin:
    """A team entered without a club, in a competition that has none."""

    @classmethod
    def setUpTestData(cls):
        cls.competition = factories.CompetitionFactory.create(
            title="Coastal Midweek Touch"
        )
        cls.season = factories.SeasonFactory.create(competition=cls.competition)
        cls.division = factories.DivisionFactory.create(season=cls.season)
        cls.team = factories.TeamFactory.create(
            division=cls.division, title="Terrigal Tide", club=None
        )
        cls.args = (cls.competition.pk, cls.season.pk, cls.division.pk, cls.team.pk)


class EnsureClubTests(SocialTeamMixin, TestCase):
    def test_a_club_named_after_the_team_is_created(self):
        club = self.team.ensure_club()
        self.team.refresh_from_db()
        self.assertEqual(self.team.club, club)
        self.assertEqual((club.title, club.slug), ("Terrigal Tide", "terrigal-tide"))
        self.assertCountEqual(self.competition.clubs.all(), [club])

    def test_the_club_of_the_competition_with_its_name_is_taken(self):
        club = factories.ClubFactory.create(title="TERRIGAL TIDE")
        other = factories.ClubFactory.create(title="Kincumber Kingfishers")
        self.competition.clubs.add(club, other)
        self.assertEqual(self.team.ensure_club(), club)
        self.team.refresh_from_db()
        self.assertEqual(self.team.club, club)
        self.assertCountEqual(self.competition.clubs.all(), [club, other])
        self.assertEqual(Club.objects.count(), 2)

    def test_a_name_that_belongs_to_a_club_elsewhere_is_refused(self):
        factories.ClubFactory.create(title="Terrigal Tide", slug="terrigal-tide")
        with self.assertRaises(ValidationError) as cm:
            self.team.ensure_club()
        self.assertEqual(
            cm.exception.messages,
            [
                'The club "Terrigal Tide" already has the name of this team, '
                "and is not one of the clubs of Coastal Midweek Touch. Add it "
                "to the competition's clubs and give it to the team, or create "
                "a club of another name for the team."
            ],
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.club, None)
        self.assertCountEqual(self.competition.clubs.all(), [])

    def test_a_club_of_the_competition_with_the_address_of_its_name_is_taken(self):
        club = factories.ClubFactory.create(title="Terrigal-Tide!")
        self.competition.clubs.add(club)
        self.assertEqual(self.team.ensure_club(), club)
        self.assertEqual(Club.objects.count(), 1)

    def test_a_name_that_makes_no_address_is_refused(self):
        team = factories.TeamFactory.create(
            division=self.division, title="!!!", club=None
        )
        with self.assertRaises(ValidationError) as cm:
            team.ensure_club()
        self.assertEqual(
            cm.exception.messages,
            [
                'A club cannot be named after "!!!". Create a club for the '
                "team and give it to the team."
            ],
        )

    def test_permissions_it_takes(self):
        self.assertEqual(
            self.team.ensure_club_permissions(),
            [
                ("change", Team, self.team),
                ("add", Club, None),
                ("change", Competition, self.competition),
            ],
        )
        self.competition.clubs.add(factories.ClubFactory.create(title="Terrigal Tide"))
        self.assertEqual(
            self.team.ensure_club_permissions(), [("change", Team, self.team)]
        )
        self.team.ensure_club()
        self.assertEqual(self.team.ensure_club_permissions(), [])

    def test_a_team_with_a_club_keeps_it(self):
        club = factories.ClubFactory.create(title="Eagles")
        team = factories.TeamFactory.create(division=self.division, club=club)
        self.assertEqual(team.ensure_club(), club)
        self.assertEqual(Club.objects.count(), 1)


@per_shell
class TeamClubAdminTests(SocialTeamMixin, TestCase):
    user_factory = factories.SuperUserFactory

    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def test_login_required(self):
        self.assertLoginRequired(TEAM_CLUB, *self.args)

    def test_adding_a_person_to_a_team_without_a_club_asks_for_one(self):
        with self.login(self.user):
            self.get(f"{ASSOCIATION}:add", *self.args)
        self.assert_http_302_found(url=self.reverse(TEAM_CLUB, *self.args))

    def test_page_says_a_club_will_be_created(self):
        with self.login(self.user):
            self.get_check_200(TEAM_CLUB, *self.args)
        self.assertResponseContains(
            "<p>The people of a team come from its club. Terrigal Tide has no "
            "club, so nobody can be added to it yet.</p>"
        )
        self.assertResponseContains(
            "<p>A club named Terrigal Tide will be created, added to the clubs "
            "of Coastal Midweek Touch and given this team.</p>"
        )

    def test_page_names_the_club_the_team_will_join(self):
        self.competition.clubs.add(factories.ClubFactory.create(title="Terrigal Tide"))
        with self.login(self.user):
            self.get_check_200(TEAM_CLUB, *self.args)
        self.assertResponseContains(
            "<p>Terrigal Tide will join Terrigal Tide, the club of Coastal "
            "Midweek Touch that has its name.</p>"
        )

    def test_post_gives_the_team_a_club(self):
        with self.login(self.user):
            self.post(TEAM_CLUB, *self.args)
        self.team.refresh_from_db()
        self.assertEqual(self.team.club.title, "Terrigal Tide")
        self.assert_http_302_found(
            url=self.reverse("admin:fixja:club:edit", self.team.club.pk)
        )
        self.assertCountEqual(self.competition.clubs.all(), [self.team.club])
        self.assertResponseMessages(
            [
                messages.Message(
                    messages.SUCCESS,
                    "Terrigal Tide is now in the club Terrigal Tide. Add its "
                    "people to the club, then link them to the team.",
                )
            ]
        )

    def test_post_is_refused_when_the_name_belongs_to_a_club_elsewhere(self):
        factories.ClubFactory.create(title="Terrigal Tide", slug="terrigal-tide")
        with self.login(self.user):
            self.post(TEAM_CLUB, *self.args)
        self.assert_http_200_ok()
        self.assertResponseMessages(
            [
                messages.Message(
                    messages.ERROR,
                    'The club "Terrigal Tide" already has the name of this '
                    "team, and is not one of the clubs of Coastal Midweek "
                    "Touch. Add it to the competition's clubs and give it to "
                    "the team, or create a club of another name for the team.",
                )
            ]
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.club, None)

    def test_a_team_with_a_club_goes_back_to_its_people(self):
        team = factories.TeamFactory.create(division=self.division)
        args = (self.competition.pk, self.season.pk, self.division.pk, team.pk)
        with self.login(self.user):
            self.get(TEAM_CLUB, *args)
        self.assert_http_302_found(url=f"{team.urls['edit']}#people-tab")

    def test_permissions(self):
        """
        What doing the same by hand takes: changing the team, adding a club
        and changing the competition's clubs.
        """
        staff = factories.UserFactory.create(is_staff=True)
        with self.login(staff):
            self.post(TEAM_CLUB, *self.args)
            self.assert_http_403_forbidden()

            assign_perm("competition.change_team", staff)
            self.post(TEAM_CLUB, *self.args)
            self.assert_http_403_forbidden()

            assign_perm("competition.add_club", staff)
            assign_perm("competition.change_competition", staff, self.competition)
            self.post(TEAM_CLUB, *self.args)
        self.team.refresh_from_db()
        self.assert_http_302_found(
            url=self.reverse("admin:fixja:club:edit", self.team.club.pk)
        )

    def test_joining_a_club_only_takes_changing_the_team(self):
        club = factories.ClubFactory.create(title="Terrigal Tide")
        self.competition.clubs.add(club)
        staff = factories.UserFactory.create(is_staff=True)
        assign_perm("competition.change_team", staff, self.team)
        with self.login(staff):
            self.post(TEAM_CLUB, *self.args)
        self.assert_http_302_found(url=self.reverse("admin:fixja:club:edit", club.pk))


class SquadMixin:
    """A club's team with two of its people in it, numbered 7 and 9."""

    @classmethod
    def setUpTestData(cls):
        cls.club = factories.ClubFactory.create(title="Eagles")
        cls.team = factories.TeamFactory.create(club=cls.club, title="Eagles")
        cls.division = cls.team.division
        cls.season = cls.division.season
        cls.season.competition.clubs.add(cls.club)
        cls.alice = factories.PersonFactory.create(
            club=cls.club, first_name="Alice", last_name="Walker"
        )
        cls.bella = factories.PersonFactory.create(
            club=cls.club, first_name="Bella", last_name="Young"
        )
        cls.carla = factories.PersonFactory.create(
            club=cls.club, first_name="Carla", last_name="Zhou"
        )
        cls.seven = factories.TeamAssociationFactory.create(
            team=cls.team, person=cls.alice, number=7
        )
        cls.nine = factories.TeamAssociationFactory.create(
            team=cls.team, person=cls.bella, number=9
        )
        cls.args = (
            cls.season.competition.pk,
            cls.season.pk,
            cls.division.pk,
            cls.team.pk,
        )

    def play(self, person):
        """Record statistics for ``person`` in a match of the team."""
        stage = factories.StageFactory.create(division=self.division)
        match = factories.MatchFactory.create(stage=stage, home_team=self.team)
        return factories.SimpleScoreMatchStatisticFactory.create(
            match=match, player=person
        )


class TeamAssociationAdminTests(SquadMixin, TestCase):
    user_factory = factories.SuperUserFactory

    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def data(self, person, **kwargs):
        return {"number": "", "person": person.pk, "is_player": "1", **kwargs}

    def test_a_number_is_worn_once(self):
        with self.login(self.user):
            self.post(
                f"{ASSOCIATION}:add", *self.args, data=self.data(self.carla, number="7")
            )
        self.assert_http_200_ok()
        self.assertEqual(
            self.get_context("form").errors,
            {"number": ["Number 7 is already worn by Walker, Alice."]},
        )
        self.assertEqual(self.team.people.count(), 2)

    def test_a_number_cannot_be_changed_to_one_that_is_worn(self):
        with self.login(self.user):
            self.post(
                f"{ASSOCIATION}:edit",
                *self.args,
                self.nine.pk,
                data=self.data(self.bella, number="7"),
            )
        self.assert_http_200_ok()
        self.assertEqual(
            self.get_context("form").errors,
            {"number": ["Number 7 is already worn by Walker, Alice."]},
        )

    def test_a_free_number_is_saved(self):
        with self.login(self.user):
            self.post(
                f"{ASSOCIATION}:add", *self.args, data=self.data(self.carla, number="8")
            )
        self.assert_http_302_found(url=self.team.urls["edit"])
        self.assertEqual(self.team.people.get(person=self.carla).number, 8)

    def test_a_person_who_already_shares_a_number_is_saved_as_they_stand(self):
        self.nine.number = 7
        self.nine.save()
        with self.login(self.user):
            self.post(
                f"{ASSOCIATION}:edit",
                *self.args,
                self.nine.pk,
                data=self.data(self.bella, number="7", is_player="0"),
            )
        self.assert_http_302_found(url=self.team.urls["edit"])
        self.nine.refresh_from_db()
        self.assertEqual((self.nine.number, self.nine.is_player), (7, False))

    def test_a_person_without_statistics_is_removed(self):
        with self.login(self.user):
            self.post(f"{ASSOCIATION}:delete", *self.args, self.seven.pk)
        self.assert_http_302_found(url=f"{self.team.urls['edit']}#people-tab")
        self.assertCountEqual(self.team.people.all(), [self.nine])

    def test_a_person_with_statistics_for_the_team_stays(self):
        self.play(self.alice)
        with self.login(self.user):
            self.post(f"{ASSOCIATION}:delete", *self.args, self.seven.pk)
        self.assert_http_404_not_found()
        self.assertCountEqual(self.team.people.all(), [self.seven, self.nine])


class TeamAssociationFormSetTests(SquadMixin, TestCase):
    """The formset of a team's people, as the club registration pages post it."""

    def formset(self, *rows):
        data = {
            "people-TOTAL_FORMS": str(len(rows)),
            "people-INITIAL_FORMS": "2",
            "people-MIN_NUM_FORMS": "",
            "people-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            for name, value in row.items():
                data[f"people-{index}-{name}"] = value
        return TeamAssociationFormSet(data=data, instance=self.team)

    def row(self, association=None, **kwargs):
        if association is None:
            return {"is_player": "1", "team": self.team.pk, **kwargs}
        return {
            "id": association.pk,
            "team": self.team.pk,
            "number": association.number,
            "person": association.person.pk,
            "is_player": "1",
            **kwargs,
        }

    def test_two_people_exchange_numbers(self):
        formset = self.formset(
            self.row(self.seven, number="9"), self.row(self.nine, number="7")
        )
        self.assertEqual(formset.errors, [{}, {}])
        formset.save()
        self.assertCountEqual(
            self.team.people.values_list("person__first_name", "number"),
            [("Alice", 9), ("Bella", 7)],
        )

    def test_a_number_given_twice_is_refused(self):
        formset = self.formset(
            self.row(self.seven),
            self.row(self.nine),
            self.row(person=self.carla.pk, number="9"),
        )
        self.assertEqual(
            formset.errors,
            [{}, {}, {"number": ["Number 9 is already worn by Young, Bella."]}],
        )

    def test_a_team_that_already_has_a_number_twice_is_saved_as_it_stands(self):
        self.nine.number = 7
        self.nine.save()
        formset = self.formset(self.row(self.seven), self.row(self.nine))
        self.assertEqual(formset.errors, [{}, {}])
        self.assertEqual(formset.non_form_errors(), [])

    def test_the_number_of_a_person_being_removed_is_free(self):
        formset = self.formset(
            self.row(self.seven, DELETE="on"),
            self.row(self.nine),
            self.row(person=self.carla.pk, number="7"),
        )
        # A form being removed is not validated, so it reports nothing.
        self.assertEqual(formset.errors, [{}, {}])
        formset.save()
        self.assertCountEqual(
            self.team.people.values_list("person__first_name", "number"),
            [("Bella", 9), ("Carla", 7)],
        )

    def test_a_person_with_statistics_for_the_team_is_not_removed(self):
        self.play(self.alice)
        formset = self.formset(self.row(self.seven, DELETE="on"), self.row(self.nine))
        self.assertEqual(
            formset.non_form_errors(),
            [
                "Walker, Alice has statistics for Eagles and cannot be removed "
                "from the team."
            ],
        )

    def test_statistics_for_another_team_do_not_keep_a_person(self):
        other = factories.TeamFactory.create(club=self.club, division=self.division)
        stage = factories.StageFactory.create(division=self.division)
        match = factories.MatchFactory.create(stage=stage, home_team=other)
        factories.SimpleScoreMatchStatisticFactory.create(
            match=match, player=self.alice
        )
        self.assertCountEqual(self.team.people.removable(), [self.seven, self.nine])


@freeze_time("2026-07-15 12:00:00")
class PersonDeletableTests(SquadMixin, TestCase):
    """One rule for ``Person.can_delete`` and the admin's delete view."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.season.start_date = datetime.date(2026, 8, 1)
        cls.season.save()

    def test_people_of_a_season_yet_to_start_can_be_deleted(self):
        self.assertCountEqual(
            Person.objects.deletable(), [self.alice, self.bella, self.carla]
        )
        self.assertEqual(self.alice.can_delete, True)

    def test_not_part_way_through_a_season(self):
        self.season.start_date = datetime.date(2026, 7, 1)
        self.season.save()
        self.assertCountEqual(Person.objects.deletable(), [self.carla])
        self.assertEqual(self.alice.can_delete, False)

    def test_not_with_statistics(self):
        self.play(self.carla)
        self.assertCountEqual(Person.objects.deletable(), [self.alice, self.bella])
        self.assertEqual(self.carla.can_delete, False)

    def test_admin_delete_view_applies_the_rule(self):
        self.play(self.carla)
        with self.login(factories.SuperUserFactory.create()):
            self.post("admin:fixja:club:person:delete", self.club.pk, self.carla.pk)
        self.assert_http_404_not_found()
        self.assertEqual(self.club.members.count(), 3)


class ClubAddressTests(TestCase):
    """The public site finds a club by its slug alone."""

    def data(self, **kwargs):
        return {
            "title": "Eagles",
            "short_title": "",
            "abbreviation": "",
            "email": "",
            "website": "",
            "twitter": "",
            "facebook": "",
            "youtube": "",
            "primary": "",
            "primary_position": "",
            "status": "active",
            "slug": "eagles",
            "slug_locked": "0",
            **kwargs,
        }

    def test_a_new_club_cannot_take_the_address_of_another(self):
        factories.ClubFactory.create(title="Eagles!", slug="eagles")
        form = ClubEditForm(data=self.data())
        self.assertEqual(
            form.errors,
            {
                "title": [
                    'The club "Eagles!" already has the address "eagles". '
                    "Give this club another name, or an address (slug) of its "
                    "own."
                ]
            },
        )

    def test_a_club_cannot_be_renamed_to_the_address_of_another(self):
        factories.ClubFactory.create(title="Eagles", slug="eagles")
        hawks = factories.ClubFactory.create(title="Hawks", slug="hawks")
        form = ClubEditForm(data=self.data(), instance=hawks)
        self.assertEqual(
            form.errors,
            {
                "title": [
                    'The club "Eagles" already has the address "eagles". '
                    "Give this club another name, or an address (slug) of its "
                    "own."
                ]
            },
        )

    def test_a_club_that_already_shares_an_address_is_saved_as_it_stands(self):
        factories.ClubFactory.create(title="Eagles", slug="eagles")
        twin = factories.ClubFactory.create(title="Eagles", slug="eagles")
        form = ClubEditForm(data=self.data(abbreviation="EAG"), instance=twin)
        self.assertEqual(form.errors, {})
        self.assertEqual(form.save().abbreviation, "EAG")
