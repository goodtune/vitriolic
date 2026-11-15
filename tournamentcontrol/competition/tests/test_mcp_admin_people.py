"""
Tests for the clubs, people, team squad and team role tools of the
competition administration MCP server (#648).

The rules themselves (a number is worn once, a person with statistics stays,
a team without a club is given one) belong to the forms and models the admin
site uses and are tested in ``test_team_people``; these tests check the
tools apply them.
"""

import datetime
import json

from django.db import connection
from django.test.utils import CaptureQueriesContext
from freezegun import freeze_time
from guardian.shortcuts import assign_perm
from test_plus import TestCase

from tournamentcontrol.competition import mcp
from tournamentcontrol.competition.mcp import admin as mcp_admin
from tournamentcontrol.competition.models import (
    Club,
    Person,
    Team,
    TeamAssociation,
    TeamRole,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_mcp_admin import AdminFixtureMixin
from tournamentcontrol.competition.tests.test_mcp_integration import NOW

# Build the servers before freezegun replaces ``datetime.date`` (see
# test_mcp_integration for why).
mcp.get_server()
mcp_admin.get_admin_server()

WRITE_TOOLS = {
    "create_club",
    "update_club",
    "link_competition_clubs",
    "unlink_competition_clubs",
    "create_team_role",
    "create_people",
    "update_person",
    "delete_person",
    "set_team_squad",
    "remove_team_member",
}
READ_TOOLS = {"list_clubs", "list_team_roles", "list_people", "get_team"}


class PeopleFixtureMixin(AdminFixtureMixin):
    """
    The international tournament, with its nations linked to it as clubs and
    a few people in two of them, and a social competition without clubs.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.competition.clubs.set([cls.australia, cls.new_zealand])
        cls.alice = factories.PersonFactory.create(
            club=cls.australia, first_name="Alice", last_name="Walker", gender="F"
        )
        cls.bella = factories.PersonFactory.create(
            club=cls.australia, first_name="Bella", last_name="Young", gender="F"
        )
        cls.kiri = factories.PersonFactory.create(
            club=cls.new_zealand, first_name="Kiri", last_name="Tane", gender="F"
        )
        cls.captain = factories.TeamRoleFactory.create(
            competition=cls.competition, name="Captain"
        )
        cls.coach = factories.TeamRoleFactory.create(
            competition=cls.competition, name="Coach"
        )

        cls.midweek = factories.CompetitionFactory.create(title="Coastal Midweek Touch")
        cls.midweek_season = factories.SeasonFactory.create(
            competition=cls.midweek, title="Spring 2026"
        )
        cls.midweek_mens = factories.DivisionFactory.create(
            season=cls.midweek_season, title="Men's"
        )
        cls.tide = factories.TeamFactory.create(
            division=cls.midweek_mens, title="Terrigal Tide", club=None
        )

    def grant(self, perm, obj=None):
        """
        Grant the staff user a permission. A user remembers the permissions
        it was found to have, so it is read again.
        """
        assign_perm(perm, self.staff, obj)
        self.staff = type(self.staff).objects.get(pk=self.staff.pk)

    def squad(self, team):
        """The squad as ``get_team`` reports it: (name, number, plays, roles)."""
        return [
            (
                member["person"]["name"],
                member["number"],
                member["is_player"],
                [role["name"] for role in member["roles"]],
            )
            for member in self.admin().get_team(team.pk)["people"]
        ]

    def play(self, team, person):
        """Record statistics for ``person`` in a match of ``team``."""
        stage = factories.StageFactory.create(division=team.division)
        match = factories.MatchFactory.create(stage=stage, home_team=team)
        return factories.SimpleScoreMatchStatisticFactory.create(
            match=match, player=person
        )


@freeze_time(NOW)
class ClubToolTests(PeopleFixtureMixin, TestCase):
    def test_list_clubs(self):
        res = self.admin(self.staff).list_clubs()
        self.assertEqual(
            (res["total"], [c["title"] for c in res["clubs"]]),
            (4, ["Australia", "England", "France", "New Zealand"]),
        )
        self.assertEqual(
            res["clubs"][0],
            {
                "id": self.australia.pk,
                "title": "Australia",
                "short_title": None,
                "slug": self.australia.slug,
                "abbreviation": "AUS",
                "status": "active",
                "email": None,
                "website": None,
                "twitter": None,
                "facebook": None,
                "youtube": None,
                "primary": None,
                "primary_position": None,
                "competitions": [
                    {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": self.competition.slug,
                    }
                ],
            },
        )

    def test_list_clubs_filters(self):
        res = self.admin().list_clubs(competition_id=self.competition.pk)
        self.assertEqual(
            [c["title"] for c in res["clubs"]], ["Australia", "New Zealand"]
        )
        res = self.admin().list_clubs(query="new zea")
        self.assertEqual([c["title"] for c in res["clubs"]], ["New Zealand"])
        res = self.admin().list_clubs(limit=1, offset=2)
        self.assertEqual(
            (res["total"], res["offset"], [c["title"] for c in res["clubs"]]),
            (4, 2, ["France"]),
        )

    def test_create_club_linked_to_a_competition(self):
        res = self.admin().create_club(
            title="Hit &amp; Run",
            abbreviation="HNR",
            website="https://hitandrun.example.com/",
            competition_ids=[self.competition.pk],
        )
        club = Club.objects.get(pk=res["club"]["id"])
        self.assertEqual(
            (club.title, club.slug, club.abbreviation, club.website),
            ("Hit & Run", "hit-run", "HNR", "https://hitandrun.example.com/"),
        )
        self.assertEqual(
            [c["title"] for c in res["club"]["competitions"]],
            ["European Championships"],
        )
        # The clubs already linked stay linked.
        self.assertCountEqual(
            self.competition.clubs.all(), [self.australia, self.new_zealand, club]
        )
        # It can be given to a team of the competition straight away.
        res = self.admin().update_team(self.fra_men.pk, club_id=club.pk)
        self.assertEqual(res["team"]["club"]["title"], "Hit & Run")

    def test_create_club_rules(self):
        self.assertToolError(
            'Validation failed: title: The club "Australia" already has the '
            'address "australia". Give this club another name, or an address '
            "(slug) of its own.",
            self.admin().create_club,
            title="Australia!",
        )
        self.assertToolError(
            "Validation failed: abbreviation: Ensure this value has at most 3 "
            "characters (it has 4).",
            self.admin().create_club,
            title="Wales",
            abbreviation="WALE",
        )
        self.assertToolError(
            "Competition 999999 was not found.",
            self.admin().create_club,
            title="Wales",
            competition_ids=[999999],
        )
        self.assertEqual(Club.objects.count(), 4)

    def test_update_club(self):
        res = self.admin().update_club(
            self.australia.pk,
            email="office@australia.example.com",
            status="inactive",
            primary_person_uuid=str(self.alice.pk),
            primary_position="Secretary",
        )
        self.assertEqual(
            (
                res["club"]["title"],
                res["club"]["abbreviation"],
                res["club"]["email"],
                res["club"]["status"],
                res["club"]["primary"],
                res["club"]["primary_position"],
            ),
            (
                "Australia",
                "AUS",
                "office@australia.example.com",
                "inactive",
                {"uuid": str(self.alice.pk), "name": "Walker, Alice"},
                "Secretary",
            ),
        )
        # The primary contact is one of the club's own people.
        self.assertToolError(
            "Validation failed: primary: Select a valid choice. That choice is "
            "not one of the available choices.",
            self.admin().update_club,
            self.australia.pk,
            primary_person_uuid=str(self.kiri.pk),
        )

    def test_link_leaves_the_other_clubs_linked(self):
        res = self.admin().link_competition_clubs(
            self.competition.pk, [self.england.pk, self.australia.pk]
        )
        self.assertEqual([c["title"] for c in res["linked"]], ["England"])
        self.assertEqual([c["title"] for c in res["already_linked"]], ["Australia"])
        self.assertEqual(
            [c["title"] for c in res["competition"]["clubs"]],
            ["Australia", "England", "New Zealand"],
        )
        self.assertCountEqual(
            self.competition.clubs.all(),
            [self.australia, self.england, self.new_zealand],
        )

    def test_unlink_leaves_the_other_clubs_linked(self):
        res = self.admin().unlink_competition_clubs(
            self.competition.pk, [self.new_zealand.pk, self.france.pk]
        )
        self.assertEqual([c["title"] for c in res["unlinked"]], ["New Zealand"])
        self.assertEqual([c["title"] for c in res["not_linked"]], ["France"])
        self.assertCountEqual(self.competition.clubs.all(), [self.australia])
        # The club and the teams it entered are kept.
        self.nzl_men.refresh_from_db()
        self.assertEqual(self.nzl_men.club, self.new_zealand)

    def test_link_rules(self):
        self.assertToolError(
            "Club 999999 was not found.",
            self.admin().link_competition_clubs,
            self.competition.pk,
            [999999],
        )
        self.assertToolError(
            "Give one or more clubs to link.",
            self.admin().link_competition_clubs,
            self.competition.pk,
            [],
        )
        self.assertToolError(
            "Give one or more clubs to unlink.",
            self.admin().unlink_competition_clubs,
            self.competition.pk,
            [],
        )

    def test_a_team_is_given_a_club_of_its_competition(self):
        message = (
            "France is not one of the clubs of European Championships. Link it "
            f"first: link_competition_clubs(competition_id={self.competition.pk}, "
            f"club_ids=[{self.france.pk}])."
        )
        self.assertToolError(
            message,
            self.admin().update_team,
            self.aus_women.pk,
            club_id=self.france.pk,
        )
        self.assertToolError(
            message,
            self.admin().create_team,
            self.womens.pk,
            club_id=self.france.pk,
        )
        self.assertToolError(
            f"Nothing was saved. team 0: {message}",
            self.admin().create_teams,
            [{"division_id": self.womens.pk, "club_id": self.france.pk}],
        )
        # The same in a competition that has no clubs at all, where the
        # team form does not offer a club.
        self.assertToolError(
            "France is not one of the clubs of Coastal Midweek Touch. Link it "
            f"first: link_competition_clubs(competition_id={self.midweek.pk}, "
            f"club_ids=[{self.france.pk}]).",
            self.admin().update_team,
            self.tide.pk,
            club_id=self.france.pk,
        )

        self.admin().link_competition_clubs(self.competition.pk, [self.france.pk])
        res = self.admin().update_team(self.aus_women.pk, club_id=self.france.pk)
        self.assertEqual(res["team"]["club"]["title"], "France")

    def test_permissions(self):
        admin = self.admin(self.staff)
        self.assertToolError(
            "Permission denied: add club requires the competition.add_club permission.",
            admin.create_club,
            title="Wales",
        )
        self.assertToolError(
            "Permission denied: change club requires the competition.change_club "
            "permission for this club.",
            admin.update_club,
            self.australia.pk,
            email="office@australia.example.com",
        )
        for tool in (admin.link_competition_clubs, admin.unlink_competition_clubs):
            with self.subTest(tool=tool.__name__):
                self.assertToolError(
                    "Permission denied: change competition requires the "
                    "competition.change_competition permission for this "
                    "competition.",
                    tool,
                    self.competition.pk,
                    [self.england.pk],
                )
        # Linking a new club to a competition takes changing the competition.
        self.grant("competition.add_club")
        self.assertToolError(
            "Permission denied: change competition requires the "
            "competition.change_competition permission for this competition.",
            self.admin(self.staff).create_club,
            title="Wales",
            competition_ids=[self.competition.pk],
        )
        self.assertEqual(Club.objects.count(), 4)
        self.grant("change_competition", self.competition)
        res = self.admin(self.staff).create_club(
            title="Wales", competition_ids=[self.competition.pk]
        )
        self.assertEqual(res["saved"], True)


@freeze_time(NOW)
class TeamRoleToolTests(PeopleFixtureMixin, TestCase):
    def test_list_and_create(self):
        res = self.admin().create_team_role(self.competition.pk, name="Manager")
        self.assertEqual(res["team_role"]["name"], "Manager")
        self.assertEqual(
            TeamRole.objects.get(pk=res["team_role"]["id"]).competition,
            self.competition,
        )
        res = self.admin(self.staff).list_team_roles(self.competition.pk)
        self.assertEqual(
            [r["name"] for r in res["team_roles"]], ["Captain", "Coach", "Manager"]
        )
        self.assertEqual(
            self.admin().list_team_roles(self.midweek.pk)["team_roles"], []
        )

    def test_rules(self):
        self.assertToolError(
            "Validation failed: name: Ensure this value has at most 50 "
            "characters (it has 51).",
            self.admin().create_team_role,
            self.competition.pk,
            name="x" * 51,
        )
        self.assertToolError(
            "Permission denied: add team role requires the "
            "competition.add_teamrole permission.",
            self.admin(self.staff).create_team_role,
            self.competition.pk,
            name="Manager",
        )


@freeze_time(NOW)
class PeopleToolTests(PeopleFixtureMixin, TestCase):
    def test_create_people(self):
        res = self.admin().create_people(
            [
                {
                    "club_id": self.england.pk,
                    "first_name": "Emma",
                    "last_name": "Stone",
                    "gender": "F",
                    "date_of_birth": "1994-02-11",
                    "email": "Emma@Example.com",
                    "mobile_phone": "0400 000 000",
                },
                {
                    "club_id": self.france.pk,
                    "first_name": "Louis",
                    "last_name": "Martin",
                    "gender": "M",
                },
            ]
        )
        self.assertEqual(res["saved"], True)
        emma = Person.objects.get(pk=res["people"][0]["uuid"])
        self.assertEqual(
            res["people"][0],
            {
                "uuid": str(emma.pk),
                "name": "Stone, Emma",
                "first_name": "Emma",
                "last_name": "Stone",
                "gender": "F",
                "date_of_birth": "1994-02-11",
                "email": emma.email,
                "home_phone": None,
                "work_phone": None,
                "mobile_phone": "0400 000 000",
                "club": {
                    "id": self.england.pk,
                    "title": "England",
                    "slug": self.england.slug,
                },
            },
        )
        self.assertEqual(
            (res["people"][1]["name"], res["people"][1]["club"]["title"]),
            ("Martin, Louis", "France"),
        )
        self.assertEqual(emma.date_of_birth, datetime.date(1994, 2, 11))

    def test_create_people_saves_all_or_none(self):
        count = Person.objects.count()
        self.assertToolError(
            "Nothing was saved. "
            "person 1 (Louis ): Validation failed: last_name: This field is "
            "required. "
            "person 2 (Mia Novak): Club 999999 was not found.",
            self.admin().create_people,
            [
                {
                    "club_id": self.england.pk,
                    "first_name": "Emma",
                    "last_name": "Stone",
                    "gender": "F",
                },
                {
                    "club_id": self.france.pk,
                    "first_name": "Louis",
                    "last_name": "",
                    "gender": "M",
                },
                {
                    "club_id": 999999,
                    "first_name": "Mia",
                    "last_name": "Novak",
                    "gender": "F",
                },
            ],
        )
        self.assertEqual(Person.objects.count(), count)

    def test_create_people_limits(self):
        self.assertToolError("Give one or more people.", self.admin().create_people, [])
        self.assertToolError(
            "Give at most 50 people at once.",
            self.admin().create_people,
            [
                {
                    "club_id": self.england.pk,
                    "first_name": "Emma",
                    "last_name": f"Stone {n}",
                    "gender": "F",
                }
                for n in range(51)
            ],
        )
        self.assertToolError(
            "person 0: gender: Input should be 'M', 'F' or 'X'",
            self.admin().create_people,
            [
                {
                    "club_id": self.england.pk,
                    "first_name": "Emma",
                    "last_name": "Stone",
                    "gender": "female",
                }
            ],
        )

    def test_list_people(self):
        res = self.admin().list_people(club_id=self.australia.pk)
        self.assertEqual(
            (res["total"], [p["name"] for p in res["people"]]),
            (3, ["Reynolds, Gary", "Walker, Alice", "Young, Bella"]),
        )
        res = self.admin().list_people(team_id=self.aus_men.pk)
        self.assertEqual([p["uuid"] for p in res["people"]], [str(self.person.pk)])
        res = self.admin().list_people(query="ali walk")
        self.assertEqual([p["name"] for p in res["people"]], ["Walker, Alice"])
        res = self.admin().list_people(club_id=self.australia.pk, query="young")
        self.assertEqual([p["name"] for p in res["people"]], ["Young, Bella"])
        res = self.admin().list_people(query="a", limit=1, offset=1)
        self.assertEqual((res["offset"], len(res["people"])), (1, 1))

    def test_list_people_takes_permission_to_see_them(self):
        """Contact details are personal: staff alone does not show them."""
        self.assertToolError(
            "Permission denied: change club requires the competition.change_club "
            "permission for this club.",
            self.admin(self.staff).list_people,
            club_id=self.australia.pk,
        )
        for filters in ({"team_id": self.aus_men.pk}, {"query": "walker"}):
            with self.subTest(filters=filters):
                self.assertToolError(
                    "Permission denied: change person requires the "
                    "competition.change_person permission.",
                    self.admin(self.staff).list_people,
                    **filters,
                )
        # Whoever may change a club sees its people, as on the club's page.
        self.grant("change_club", self.australia)
        res = self.admin(self.staff).list_people(club_id=self.australia.pk)
        self.assertEqual(res["total"], 3)
        self.assertToolError(
            "Permission denied: change club requires the competition.change_club "
            "permission for this club.",
            self.admin(self.staff).list_people,
            club_id=self.new_zealand.pk,
        )
        # Whoever may change people sees anybody.
        self.grant("competition.change_person")
        res = self.admin(self.staff).list_people(query="tane")
        self.assertEqual([p["name"] for p in res["people"]], ["Tane, Kiri"])
        res = self.admin(self.staff).list_people(club_id=self.new_zealand.pk)
        self.assertEqual(res["total"], 1)

    def test_lists_do_not_ask_the_database_for_each_row(self):
        with CaptureQueriesContext(connection) as few:
            self.admin().list_people(club_id=self.australia.pk)
            self.admin().list_clubs()
            self.admin().get_team(self.aus_men.pk)
        club = factories.ClubFactory.create(title="Wales")
        self.competition.clubs.add(club)
        for number in range(1, 6):
            person = factories.PersonFactory.create(club=self.australia)
            factories.TeamAssociationFactory.create(
                team=self.aus_men, person=person, number=number
            ).roles.add(self.captain)
        with CaptureQueriesContext(connection) as many:
            self.admin().list_people(club_id=self.australia.pk)
            self.admin().list_clubs()
            self.admin().get_team(self.aus_men.pk)
        self.assertEqual(len(many.captured_queries), len(few.captured_queries))

    def test_list_people_needs_a_filter(self):
        self.assertToolError(
            "Provide at least one of club_id, team_id or query.",
            self.admin().list_people,
        )
        self.assertToolError(
            "Club 999999 was not found.", self.admin().list_people, club_id=999999
        )

    def test_update_person(self):
        res = self.admin().update_person(
            str(self.alice.pk), first_name="Alicia", mobile_phone="0411 111 111"
        )
        self.assertEqual(
            (
                res["person"]["name"],
                res["person"]["gender"],
                res["person"]["mobile_phone"],
                res["person"]["club"]["title"],
            ),
            ("Walker, Alicia", "F", "0411 111 111", "Australia"),
        )
        self.assertToolError(
            "Validation failed: email: Enter a valid email address.",
            self.admin().update_person,
            str(self.alice.pk),
            email="not an address",
        )
        self.assertToolError(
            "Person not-a-uuid was not found.",
            self.admin().update_person,
            "not-a-uuid",
            first_name="Alicia",
        )

    def test_delete_person(self):
        res = self.admin().delete_person(str(self.bella.pk))
        self.assertEqual(res, {"deleted": "person Young, Bella"})
        self.assertCountEqual(self.australia.members.all(), [self.person, self.alice])

    def test_delete_person_rules(self):
        # With statistics recorded.
        self.play(self.aus_women, self.alice)
        self.assertToolError(
            "Walker, Alice cannot be deleted: they have statistics recorded, or "
            "are in a team of a season that has started.",
            self.admin().delete_person,
            str(self.alice.pk),
        )
        # Part way through a season.
        factories.TeamAssociationFactory.create(team=self.aus_women, person=self.bella)
        self.season.start_date = datetime.date(2026, 7, 14)
        self.season.save()
        self.assertToolError(
            "Young, Bella cannot be deleted: they have statistics recorded, or "
            "are in a team of a season that has started.",
            self.admin().delete_person,
            str(self.bella.pk),
        )
        # In a team of a season yet to start.
        factories.TeamAssociationFactory.create(team=self.nzl_women, person=self.kiri)
        self.season.start_date = datetime.date(2026, 8, 1)
        self.season.save()
        self.assertToolError(
            "This person cannot be deleted while other records depend on it: "
            "linked person.",
            self.admin().delete_person,
            str(self.kiri.pk),
        )
        self.assertEqual(Person.objects.filter(club=self.new_zealand).count(), 1)

    def test_permissions(self):
        admin = self.admin(self.staff)
        self.assertToolError(
            "Permission denied: add person requires the competition.add_person "
            "permission.",
            admin.create_people,
            [
                {
                    "club_id": self.england.pk,
                    "first_name": "Emma",
                    "last_name": "Stone",
                    "gender": "F",
                }
            ],
        )
        self.assertToolError(
            "Permission denied: change person requires the "
            "competition.change_person permission for this person.",
            admin.update_person,
            str(self.alice.pk),
            first_name="Alicia",
        )
        self.assertToolError(
            "Permission denied: delete person requires the "
            "competition.delete_person permission for this person.",
            admin.delete_person,
            str(self.alice.pk),
        )
        self.grant("change_person", self.alice)
        res = self.admin(self.staff).update_person(
            str(self.alice.pk), first_name="Alicia"
        )
        self.assertEqual(res["person"]["first_name"], "Alicia")


@freeze_time(NOW)
class SquadToolTests(PeopleFixtureMixin, TestCase):
    def test_club_to_squad(self):
        """
        Create a club, link it to the competition and to a team, add its
        people and name the team's squad (#648).
        """
        admin = self.admin()
        club = admin.create_club(title="Wales", abbreviation="WAL")["club"]
        admin.link_competition_clubs(self.competition.pk, [club["id"]])
        team = admin.create_team(self.womens.pk, club_id=club["id"])["team"]
        people = admin.create_people(
            [
                {
                    "club_id": club["id"],
                    "first_name": first_name,
                    "last_name": last_name,
                    "gender": "F",
                }
                for first_name, last_name in (
                    ("Carys", "Bowen"),
                    ("Ffion", "Davies"),
                    ("Megan", "Evans"),
                    ("Nia", "Hughes"),
                )
            ]
        )["people"]
        carys, ffion, megan, nia = (person["uuid"] for person in people)
        res = admin.set_team_squad(
            team["id"],
            [
                {"person_uuid": megan, "number": 10},
                {"person_uuid": carys, "number": 2, "role_ids": [self.captain.pk]},
                {"person_uuid": nia, "is_player": False, "role_ids": [self.coach.pk]},
                {"person_uuid": ffion},
            ],
        )
        self.assertEqual(res["saved"], True)
        self.assertEqual(res["club_created"], None)
        self.assertEqual(res["people_created"], [])
        self.assertCountEqual(
            [person["name"] for person in res["added"]],
            ["Evans, Megan", "Bowen, Carys", "Hughes, Nia", "Davies, Ffion"],
        )
        # Players before staff, by number, then those without one by name,
        # as ``TeamAssociation.Meta.ordering`` has them.
        expected = [
            ("Bowen, Carys", 2, True, ["Captain"]),
            ("Evans, Megan", 10, True, []),
            ("Davies, Ffion", None, True, []),
            ("Hughes, Nia", None, False, ["Coach"]),
        ]
        self.assertEqual(
            [
                (
                    m["person"]["name"],
                    m["number"],
                    m["is_player"],
                    [r["name"] for r in m["roles"]],
                )
                for m in res["people"]
            ],
            expected,
        )
        self.assertEqual(self.squad(Team.objects.get(pk=team["id"])), expected)

    def test_get_team(self):
        factories.TeamAssociationFactory.create(
            team=self.aus_women, person=self.alice, number=4
        )
        res = self.admin(self.staff).get_team(self.aus_women.pk)
        association = self.aus_women.people.get()
        self.assertEqual(
            res["people"],
            [
                {
                    "id": association.pk,
                    "person": {"uuid": str(self.alice.pk), "name": "Walker, Alice"},
                    "number": 4,
                    "is_player": True,
                    "roles": [],
                }
            ],
        )
        self.assertEqual(res["team"]["title"], "Australia")
        self.assertEqual(
            self.admin().get_team(999999), {"error": "Team 999999 was not found."}
        )

    def test_only_what_is_given_changes(self):
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {
                    "person_uuid": str(self.alice.pk),
                    "number": 4,
                    "role_ids": [self.captain.pk],
                },
                {"person_uuid": str(self.bella.pk), "number": 5},
            ],
        )
        res = self.admin().set_team_squad(
            self.aus_women.pk, [{"person_uuid": str(self.alice.pk), "number": 6}]
        )
        self.assertEqual(res["added"], [])
        self.assertEqual([p["name"] for p in res["updated"]], ["Walker, Alice"])
        self.assertEqual(
            self.squad(self.aus_women),
            [
                ("Young, Bella", 5, True, []),
                ("Walker, Alice", 6, True, ["Captain"]),
            ],
        )
        # A number is taken away with clear_number.
        self.admin().set_team_squad(
            self.aus_women.pk,
            [{"person_uuid": str(self.bella.pk), "clear_number": True}],
        )
        self.assertEqual(
            self.squad(self.aus_women),
            [
                ("Walker, Alice", 6, True, ["Captain"]),
                ("Young, Bella", None, True, []),
            ],
        )
        self.admin().set_team_squad(
            self.aus_women.pk, [{"person_uuid": str(self.bella.pk), "number": 5}]
        )
        # Roles are replaced, or cleared with an empty list.
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk), "role_ids": []},
                {
                    "person_uuid": str(self.bella.pk),
                    "is_player": False,
                    "role_ids": [self.coach.pk, self.captain.pk],
                },
            ],
        )
        self.assertEqual(
            self.squad(self.aus_women),
            [
                ("Walker, Alice", 6, True, []),
                ("Young, Bella", 5, False, ["Captain", "Coach"]),
            ],
        )

    def test_new_people_are_created_in_the_teams_club(self):
        res = self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {
                    "first_name": "Chloe",
                    "last_name": "Adams",
                    "gender": "F",
                    "date_of_birth": "2001-05-06",
                    "number": 1,
                },
                {"person_uuid": str(self.alice.pk), "number": 2},
            ],
        )
        self.assertEqual([p["name"] for p in res["people_created"]], ["Adams, Chloe"])
        chloe = Person.objects.get(pk=res["people_created"][0]["uuid"])
        self.assertEqual(
            (chloe.club, chloe.gender, chloe.date_of_birth),
            (self.australia, "F", datetime.date(2001, 5, 6)),
        )
        self.assertEqual(
            self.squad(self.aus_women),
            [("Adams, Chloe", 1, True, []), ("Walker, Alice", 2, True, [])],
        )

    def test_a_number_is_worn_once(self):
        self.admin().set_team_squad(
            self.aus_women.pk, [{"person_uuid": str(self.alice.pk), "number": 4}]
        )
        # By somebody already in the team.
        self.assertToolError(
            "Validation failed: Young, Bella: number: Number 4 is already worn "
            "by Walker, Alice.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.bella.pk), "number": 4}],
        )
        # By two people of the same call; nothing of it is saved, the new
        # person included.
        count = Person.objects.count()
        self.assertToolError(
            "Validation failed: Young, Bella: number: Number 8 is already worn "
            "by Adams, Chloe.; Adams, Chloe: number: Number 8 is already worn "
            "by Young, Bella.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [
                {"person_uuid": str(self.bella.pk), "number": 8},
                {
                    "first_name": "Chloe",
                    "last_name": "Adams",
                    "gender": "F",
                    "number": 8,
                },
            ],
        )
        self.assertEqual(Person.objects.count(), count)
        self.assertEqual(self.squad(self.aus_women), [("Walker, Alice", 4, True, [])])

    def test_two_people_exchange_numbers(self):
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk), "number": 4},
                {"person_uuid": str(self.bella.pk), "number": 5},
            ],
        )
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk), "number": 5},
                {"person_uuid": str(self.bella.pk), "number": 4},
            ],
        )
        self.assertEqual(
            self.squad(self.aus_women),
            [("Young, Bella", 4, True, []), ("Walker, Alice", 5, True, [])],
        )

    def test_people_come_from_the_teams_club(self):
        self.assertToolError(
            "Nothing was saved. "
            f"member 1 ({self.kiri.pk}): Tane, Kiri belongs to New Zealand, not "
            "to Australia, the club of Australia. "
            f"member 2 ({self.alice.pk}): Walker, Alice is listed more than once. "
            "member 3 (Chloe): Give person_uuid, or first_name, last_name and "
            "gender for a new person. "
            f"member 4 ({self.bella.pk}): Give person_uuid or the names of a new "
            "person, not both; update_person changes a person's details. "
            "member 5 (not-a-uuid): Person not-a-uuid was not found.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk)},
                {"person_uuid": str(self.kiri.pk)},
                {"person_uuid": str(self.alice.pk)},
                {"first_name": "Chloe"},
                {"person_uuid": str(self.bella.pk), "first_name": "Isabella"},
                {"person_uuid": "not-a-uuid"},
            ],
        )
        self.assertEqual(self.squad(self.aus_women), [])

    def test_roles_belong_to_the_competition(self):
        role = factories.TeamRoleFactory.create(
            competition=self.midweek, name="Captain"
        )
        self.assertToolError(
            f"Validation failed: Walker, Alice: roles: Select a valid choice. "
            f"{role.pk} is not one of the available choices.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.alice.pk), "role_ids": [role.pk]}],
        )

    def test_rules(self):
        self.assertToolError(
            "Give one or more members, or replace=true to empty the squad.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [],
        )
        self.assertToolError(
            "Give at most 100 members at once.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.alice.pk)}] * 101,
        )
        self.assertToolError(
            f"Nothing was saved. member 0 ({self.alice.pk}): Give a number or "
            "clear_number, not both.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.alice.pk), "number": 4, "clear_number": True}],
        )
        self.assertToolError(
            "member 0: shirt: Extra inputs are not permitted",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.alice.pk), "shirt": 4}],
        )
        self.assertToolError(
            "Team 999999 was not found.",
            self.admin().set_team_squad,
            999999,
            [{"person_uuid": str(self.alice.pk)}],
        )

    def test_replace(self):
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk), "number": 4},
                {"person_uuid": str(self.bella.pk), "number": 5},
            ],
        )
        res = self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.bella.pk)},
                # Alice's number is free once she is out of the team.
                {
                    "first_name": "Chloe",
                    "last_name": "Adams",
                    "gender": "F",
                    "number": 4,
                },
            ],
            replace=True,
        )
        self.assertEqual([p["name"] for p in res["removed"]], ["Walker, Alice"])
        self.assertEqual([p["name"] for p in res["added"]], ["Adams, Chloe"])
        self.assertEqual(res["updated"], [])
        self.assertEqual(
            self.squad(self.aus_women),
            [("Adams, Chloe", 4, True, []), ("Young, Bella", 5, True, [])],
        )
        # The person is kept, with their club.
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.club, self.australia)

        res = self.admin().set_team_squad(self.aus_women.pk, [], replace=True)
        self.assertCountEqual(
            [p["name"] for p in res["removed"]], ["Adams, Chloe", "Young, Bella"]
        )
        self.assertEqual(self.squad(self.aus_women), [])

    def test_replace_keeps_a_person_with_statistics(self):
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk), "number": 4},
                {"person_uuid": str(self.bella.pk), "number": 5},
            ],
        )
        self.play(self.aus_women, self.alice)
        self.assertToolError(
            "Validation failed: Walker, Alice has statistics for Australia and "
            "cannot be removed from the team.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.bella.pk), "number": 6}],
            replace=True,
        )
        self.assertEqual(
            self.squad(self.aus_women),
            [("Walker, Alice", 4, True, []), ("Young, Bella", 5, True, [])],
        )

    def test_somebody_not_named_does_not_stand_in_the_way(self):
        """
        A person since moved to another club stays in the team as they are;
        adding somebody else is not refused on their account.
        """
        factories.TeamAssociationFactory.create(
            team=self.aus_women, person=self.kiri, number=9
        )
        self.admin().set_team_squad(
            self.aus_women.pk, [{"person_uuid": str(self.alice.pk), "number": 4}]
        )
        self.assertEqual(
            self.squad(self.aus_women),
            [("Walker, Alice", 4, True, []), ("Tane, Kiri", 9, True, [])],
        )
        # Their number is still theirs.
        self.assertToolError(
            "Validation failed: Young, Bella: number: Number 9 is already worn "
            "by Tane, Kiri.",
            self.admin().set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.bella.pk), "number": 9}],
        )

    def test_remove_team_member(self):
        self.admin().set_team_squad(
            self.aus_women.pk,
            [
                {"person_uuid": str(self.alice.pk), "number": 4},
                {"person_uuid": str(self.bella.pk), "number": 5},
            ],
        )
        res = self.admin().remove_team_member(self.aus_women.pk, str(self.bella.pk))
        self.assertEqual(res, {"deleted": "Young, Bella from Australia"})
        self.assertEqual(self.squad(self.aus_women), [("Walker, Alice", 4, True, [])])
        self.assertEqual(Person.objects.filter(pk=self.bella.pk).count(), 1)

        self.assertToolError(
            "Young, Bella is not in Australia.",
            self.admin().remove_team_member,
            self.aus_women.pk,
            str(self.bella.pk),
        )
        self.play(self.aus_women, self.alice)
        self.assertToolError(
            "Walker, Alice has statistics for Australia and cannot be removed "
            "from the team.",
            self.admin().remove_team_member,
            self.aus_women.pk,
            str(self.alice.pk),
        )
        self.assertEqual(self.squad(self.aus_women), [("Walker, Alice", 4, True, [])])

    def test_permissions(self):
        member = {"person_uuid": str(self.alice.pk), "number": 4}
        self.assertToolError(
            "Permission denied: add linked person requires the "
            "competition.add_teamassociation permission.",
            self.admin(self.staff).set_team_squad,
            self.aus_women.pk,
            [member],
        )
        self.grant("competition.add_teamassociation")
        self.admin(self.staff).set_team_squad(self.aus_women.pk, [member])

        self.assertToolError(
            "Permission denied: change linked person requires the "
            "competition.change_teamassociation permission for this linked "
            "person.",
            self.admin(self.staff).set_team_squad,
            self.aus_women.pk,
            [{"person_uuid": str(self.alice.pk), "number": 5}],
        )
        self.assertToolError(
            "Permission denied: delete linked person requires the "
            "competition.delete_teamassociation permission for this linked "
            "person.",
            self.admin(self.staff).set_team_squad,
            self.aus_women.pk,
            [],
            replace=True,
        )
        self.assertToolError(
            "Permission denied: delete linked person requires the "
            "competition.delete_teamassociation permission for this linked "
            "person.",
            self.admin(self.staff).remove_team_member,
            self.aus_women.pk,
            str(self.alice.pk),
        )
        # A new person takes adding a person.
        self.assertToolError(
            "Nothing was saved. member 0 (Chloe Adams): Permission denied: add "
            "person requires the competition.add_person permission.",
            self.admin(self.staff).set_team_squad,
            self.aus_women.pk,
            [{"first_name": "Chloe", "last_name": "Adams", "gender": "F"}],
        )
        self.assertEqual(self.squad(self.aus_women), [("Walker, Alice", 4, True, [])])

    def test_read_tools_need_a_staff_user(self):
        message = "The competition administration tools require a signed-in staff user."
        admin = self.admin(self.user)
        self.assertToolError(message, admin.get_team, self.aus_women.pk)
        self.assertToolError(message, admin.list_clubs)
        self.assertToolError(message, admin.list_team_roles, self.competition.pk)


@freeze_time(NOW)
class ClublessSquadTests(PeopleFixtureMixin, TestCase):
    """A team entered without a club is given one when it gets a squad."""

    members = [
        {"first_name": "Tom", "last_name": "Reid", "gender": "M", "number": 1},
        {"first_name": "Sam", "last_name": "Cole", "gender": "M", "number": 2},
    ]

    def test_a_club_is_created_for_the_team(self):
        res = self.admin().set_team_squad(self.tide.pk, self.members)
        club = Club.objects.get(title="Terrigal Tide")
        self.assertEqual(
            res["club_created"],
            {"id": club.pk, "title": "Terrigal Tide", "slug": "terrigal-tide"},
        )
        self.assertEqual(res["team"]["club"]["id"], club.pk)
        self.assertEqual(
            [p["name"] for p in res["people_created"]], ["Reid, Tom", "Cole, Sam"]
        )
        self.tide.refresh_from_db()
        self.assertEqual(self.tide.club, club)
        self.assertCountEqual(self.midweek.clubs.all(), [club])
        self.assertCountEqual(
            club.members.values_list("first_name", flat=True), ["Tom", "Sam"]
        )
        self.assertEqual(
            self.squad(self.tide),
            [("Reid, Tom", 1, True, []), ("Cole, Sam", 2, True, [])],
        )

    def test_the_club_of_the_competition_with_its_name_is_taken(self):
        club = factories.ClubFactory.create(title="Terrigal Tide")
        self.midweek.clubs.add(club)
        res = self.admin().set_team_squad(self.tide.pk, self.members)
        self.assertEqual(res["club_created"], None)
        self.assertEqual(res["team"]["club"]["id"], club.pk)
        self.assertEqual(Club.objects.filter(title="Terrigal Tide").count(), 1)
        self.assertEqual(club.members.count(), 2)

    def test_a_name_that_belongs_to_a_club_elsewhere_is_refused(self):
        factories.ClubFactory.create(title="Terrigal Tide", slug="terrigal-tide")
        count = Person.objects.count()
        self.assertToolError(
            'Terrigal Tide has no club. The club "Terrigal Tide" already has '
            "the name of this team, and is not one of the clubs of Coastal "
            "Midweek Touch. Add it to the competition's clubs and give it to "
            "the team, or create a club of another name for the team.",
            self.admin().set_team_squad,
            self.tide.pk,
            self.members,
        )
        self.tide.refresh_from_db()
        self.assertEqual(self.tide.club, None)
        self.assertEqual(Person.objects.count(), count)

    def test_nothing_is_kept_when_the_squad_is_refused(self):
        self.assertToolError(
            "Validation failed: Reid, Tom: number: Number 1 is already worn by "
            "Cole, Sam.; Cole, Sam: number: Number 1 is already worn by Reid, "
            "Tom.",
            self.admin().set_team_squad,
            self.tide.pk,
            [
                {"first_name": "Tom", "last_name": "Reid", "gender": "M", "number": 1},
                {"first_name": "Sam", "last_name": "Cole", "gender": "M", "number": 1},
            ],
        )
        self.tide.refresh_from_db()
        self.assertEqual(self.tide.club, None)
        self.assertEqual(Club.objects.filter(title="Terrigal Tide").count(), 0)
        self.assertCountEqual(self.midweek.clubs.all(), [])

    def test_emptying_the_squad_does_not_make_a_club(self):
        res = self.admin().set_team_squad(self.tide.pk, [], replace=True)
        self.assertEqual((res["club_created"], res["people"]), (None, []))
        self.tide.refresh_from_db()
        self.assertEqual(self.tide.club, None)

    def test_permissions(self):
        """What giving the team a club by hand takes."""
        self.grant("competition.add_teamassociation")
        self.grant("competition.add_person")
        self.assertToolError(
            "Permission denied: change team requires the competition.change_team "
            "permission for this team.",
            self.admin(self.staff).set_team_squad,
            self.tide.pk,
            self.members,
        )
        self.grant("change_team", self.tide)
        self.assertToolError(
            "Permission denied: add club requires the competition.add_club permission.",
            self.admin(self.staff).set_team_squad,
            self.tide.pk,
            self.members,
        )
        self.grant("competition.add_club")
        self.assertToolError(
            "Permission denied: change competition requires the "
            "competition.change_competition permission for this competition.",
            self.admin(self.staff).set_team_squad,
            self.tide.pk,
            self.members,
        )
        self.grant("change_competition", self.midweek)
        res = self.admin(self.staff).set_team_squad(self.tide.pk, self.members)
        self.assertEqual(res["club_created"]["title"], "Terrigal Tide")


@freeze_time(NOW)
class PeopleToolsHTTPTests(PeopleFixtureMixin, TestCase):
    """The new tools as an MCP client sees them, over the HTTP transport."""

    def rpc(self, method, params=None):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        self.post(
            "mcp-admin",
            data=json.dumps(payload),
            extra={
                "content_type": "application/json",
                "HTTP_ACCEPT": "application/json, text/event-stream",
            },
        )
        self.assert_http_200_ok()
        return self.last_response.json()["result"]

    def test_tools_list(self):
        self.login(self.superuser)
        by_name = {tool["name"]: tool for tool in self.rpc("tools/list")["tools"]}
        self.assertEqual(
            WRITE_TOOLS | READ_TOOLS, set(by_name) & (WRITE_TOOLS | READ_TOOLS)
        )
        for name in READ_TOOLS:
            with self.subTest(tool=name):
                self.assertEqual(by_name[name]["annotations"]["readOnlyHint"], True)
        for name in WRITE_TOOLS:
            with self.subTest(tool=name):
                self.assertEqual(by_name[name]["annotations"]["readOnlyHint"], False)
        self.assertEqual(
            {
                name
                for name in WRITE_TOOLS
                if by_name[name]["annotations"]["destructiveHint"]
            },
            {"unlink_competition_clubs", "delete_person", "remove_team_member"},
        )
        self.assertEqual(
            mcp_admin.get_admin_server().sensitive_arguments["set_team_squad"],
            frozenset({"members"}),
        )
        self.assertEqual(
            mcp_admin.get_admin_server().sensitive_arguments["create_people"],
            frozenset({"people"}),
        )

    def test_set_team_squad(self):
        self.login(self.superuser)
        result = self.rpc(
            "tools/call",
            {
                "name": "set_team_squad",
                "arguments": {
                    "team_id": self.tide.pk,
                    "members": [
                        {
                            "first_name": "Tom",
                            "last_name": "Reid",
                            "gender": "M",
                            "number": 1,
                        }
                    ],
                },
            },
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(
            result["structuredContent"]["club_created"]["title"], "Terrigal Tide"
        )
        self.assertEqual(
            list(
                TeamAssociation.objects.filter(team=self.tide).values_list(
                    "person__last_name", "number"
                )
            ),
            [("Reid", 1)],
        )

        result = self.rpc(
            "tools/call",
            {
                "name": "get_team",
                "arguments": {"team_id": self.tide.pk},
            },
        )
        self.assertEqual(
            [m["person"]["name"] for m in result["structuredContent"]["people"]],
            ["Reid, Tom"],
        )
