"""
Tests for the MySideline synchronisation.

The HTTP boundary is replaced with an in-memory ``requests.Session`` stand-in
that serves either captured fixtures (for the parsing tests) or responses
generated from a small mutable model of the remote dataset (for the
reconciliation tests), so that nothing here depends on the live site.
"""

import json
from datetime import datetime
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.forms import DivisionForm, TeamForm
from tournamentcontrol.competition.models import (
    Division,
    Ground,
    LadderSummary,
    Match,
    Stage,
    StageGroup,
    Team,
    Venue,
    mysideline_renamed,
)
from tournamentcontrol.competition.mysideline.client import (
    GRAPHQL_ENDPOINT,
    MySidelineClient,
    MySidelineResponseError,
    MySidelineTransportError,
    MySidelineURL,
    MySidelineURLError,
)
from tournamentcontrol.competition.mysideline.sync import (
    FINALS_STAGE_TITLE,
    REGULAR_STAGE_TITLE,
    apply_snapshot,
    synchronise_all,
    synchronise_season,
)
from tournamentcontrol.competition.mysideline.types import RemoteCompetition
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.mysideline import (
    STATE_CUP_SEASON,
    STATE_CUP_URL,
    FakeResponse,
    FakeSession,
    fixture,
    rsc_line,
    state_cup_session,
)

ASSOCIATION_URL = "https://tfa.mysideline.com.au/competitions/association/6338"
SYDNEY = ZoneInfo("Australia/Sydney")


class RemoteWorld:
    """
    A small mutable model of what MySideline publishes for an association,
    rendered into the same response shapes the real service produces.
    """

    VENUE = {
        "_id": 230,
        "name": "Garnet Adcock Memorial Park",
        "venueTimezone": "Australia/Sydney",
    }
    ADDRESS = {"lat": -33.42895924, "lng": 151.3261477}

    LADDER_TEMPLATE = {
        "name": "TFA Standard Ladder",
        "pointsWin": 3,
        "pointsDraw": 2,
        "pointsLoss": 1,
        "pointsBye": 3,
        "pointsFF": 3,
        "defaultScoreFFReceived": 5,
        "ffCountAsPlayed": True,
    }

    def __init__(self):
        self.competitions = []

    def add_competition(
        self, id, name, season=2026, season_tag=2, is_active=True, ladder=None
    ):
        competition = {
            "_id": id,
            "name": name,
            "season": season,
            "seasonTag": season_tag,
            "isActive": is_active,
            "teams": [],
            "matches": [],
            "laddertemplate": dict(self.LADDER_TEMPLATE, **(ladder or {})),
        }
        self.competitions.append(competition)
        return competition

    def competition(self, id):
        return next(c for c in self.competitions if c["_id"] == id)

    def add_team(self, competition_id, id, name, pool=None):
        team = {"_id": id, "name": name, "pool": pool}
        self.competition(competition_id)["teams"].append(team)
        return team

    def team(self, competition_id, id):
        return next(
            t for t in self.competition(competition_id)["teams"] if t["_id"] == id
        )

    def add_match(
        self,
        competition_id,
        id,
        round_number,
        home,
        away,
        when,
        status="pre-game",
        scores=(0, 0),
        round_type="Regular",
        round_name=None,
        field="1",
        is_bye=False,
        is_tba=False,
        forfeiting=None,
        venue=True,
    ):
        match = {
            "_id": id,
            "status": status,
            "dateTime": int(when.timestamp() * 1000) if when else None,
            "round": {
                "number": round_number,
                "type": round_type,
                "displayName": round_name or "Round %d" % round_number,
            },
            "homeTeam": self._team_ref(competition_id, home),
            "awayTeam": self._team_ref(competition_id, away),
            "scores": {"homeTeam": scores[0], "awayTeam": scores[1]},
            "meta": {
                "isTba": is_tba,
                "isBye": is_bye,
                "fieldNo": field,
                "forfeitingTeam": (
                    self._team_ref(competition_id, forfeiting) if forfeiting else None
                ),
            },
            "venue": dict(self.VENUE) if venue else None,
            "fullVenue": {"address": dict(self.ADDRESS)} if venue else None,
        }
        self.competition(competition_id)["matches"].append(match)
        return match

    def match(self, competition_id, id):
        return next(
            m for m in self.competition(competition_id)["matches"] if m["_id"] == id
        )

    def _team_ref(self, competition_id, team_id):
        if team_id is None:
            return {"_id": None, "name": None}
        team = self.team(competition_id, team_id)
        return {"_id": team["_id"], "name": team["name"]}

    # -- rendering ---------------------------------------------------------

    def association_rsc(self):
        listing = [
            {
                "_id": c["_id"],
                "name": c["name"],
                "season": c["season"],
                "seasonTag": c["seasonTag"],
                "isActive": c["isActive"],
                "teams": [{"_id": t["_id"], "name": t["name"]} for t in c["teams"]],
            }
            for c in self.competitions
        ]
        payload = ["$", "$L13", None, {"data": {"competitions": listing}}]
        return '1:"$Sreact.fragment"\n7:%s\n' % json.dumps(payload)

    def graphql(self, body):
        query = body["query"]
        variables = body["variables"]
        competition = self.competition(variables["competitionId"])
        if "competitionMatches" in query:
            return {"data": {"competitionMatches": competition["matches"]}}
        return {
            "data": {
                "teams": [
                    {"_id": t["_id"], "name": t["name"]} for t in competition["teams"]
                ],
                "competitionLadder": {
                    "teams": [
                        {"_id": t["_id"], "name": t["name"], "pool": t["pool"]}
                        for t in competition["teams"]
                    ]
                },
            }
        }

    def competition_rsc(self, url):
        competition = self.competition(int(url.rsplit("/", 1)[1]))
        return rsc_line(
            {
                "data": {
                    "competition": {
                        "_id": competition["_id"],
                        "laddertemplate": competition["laddertemplate"],
                    }
                }
            }
        )

    def install(self, session):
        session.handlers[ASSOCIATION_URL] = lambda method, url, kwargs: FakeResponse(
            text=self.association_rsc(), content_type="text/x-component"
        )
        session.handlers[GRAPHQL_ENDPOINT] = lambda method, url, kwargs: FakeResponse(
            text=json.dumps(self.graphql(kwargs["json"]))
        )
        session.default = lambda method, url, kwargs: FakeResponse(
            text=self.competition_rsc(url), content_type="text/x-component"
        )


def sydney(*args):
    return datetime(*args, tzinfo=SYDNEY)


class URLTests(TestCase):
    def test_association_url(self):
        url = MySidelineURL(
            "https://tfa.mysideline.com.au/competitions/association/6338/"
        )
        self.assertEqual(url.association_id, 6338)
        self.assertEqual(url.competition_id, None)
        self.assertEqual(url.national_id, "TFA")
        self.assertEqual(url.canonical, ASSOCIATION_URL)

    def test_competition_url(self):
        url = MySidelineURL(
            "https://tfa.mysideline.com.au/competitions/69295321?type=competition"
        )
        self.assertEqual(url.competition_id, 69295321)
        self.assertEqual(url.association_id, None)
        self.assertEqual(
            url.competition_url(1), "https://tfa.mysideline.com.au/competitions/1"
        )

    def test_invalid_urls(self):
        for url in (
            "https://example.com/competitions/association/6338",
            "https://tfa.mysideline.com.au/register",
            "tfa.mysideline.com.au/competitions/association/6338",
        ):
            with self.assertRaises(MySidelineURLError):
                MySidelineURL(url)


class ClientTests(TestCase):
    """Parsing of captured MySideline responses."""

    def setUp(self):
        super().setUp()
        self.session = FakeSession()
        self.client = MySidelineClient(session=self.session)
        self.url = MySidelineURL(ASSOCIATION_URL)

    def install_association(self, name, content_type):
        text = fixture(name)
        self.session.handlers[ASSOCIATION_URL] = lambda m, u, k: FakeResponse(
            text=text, content_type=content_type
        )

    def install_competition(self, competition_id):
        teams = fixture("competition_%d_teams.json" % competition_id)
        matches = fixture("competition_%d_matches.json" % competition_id)

        def handler(method, url, kwargs):
            if "competitionMatches" in kwargs["json"]["query"]:
                return FakeResponse(text=matches)
            return FakeResponse(text=teams)

        self.session.handlers[GRAPHQL_ENDPOINT] = handler

    def test_user_agent_and_rsc_header(self):
        self.install_association("association_6338.rsc", "text/x-component")
        self.client.get_association(self.url)
        self.assertEqual(
            self.session.headers["User-Agent"].startswith("vitriolic"), True
        )
        method, url, kwargs = self.session.calls[0]
        self.assertEqual(kwargs["headers"]["RSC"], "1")
        self.assertEqual(kwargs["timeout"], (5, 30))

    def test_association_from_rsc_payload(self):
        self.install_association("association_6338.rsc", "text/x-component")
        association = self.client.get_association(self.url)
        self.assertEqual(association.id, 6338)
        self.assertEqual(len(association.competitions), 18)
        u14 = next(c for c in association.competitions if c.id == 69295321)
        self.assertEqual(u14.name, "Born 2014 & 2013 u14 Boys")
        self.assertEqual(u14.season, 2026)
        self.assertEqual(u14.season_tag, 2)
        self.assertEqual(u14.is_active, True)

    def test_association_from_html_fallback(self):
        self.install_association("association_6338.html", "text/html; charset=utf-8")
        association = self.client.get_association(self.url)
        self.assertEqual(
            [c.id for c in association.competitions],
            [
                54622226,
                63613539,
                67513269,
                67513419,
                67513507,
                67513699,
                67513771,
                67513844,
                69295173,
                69295205,
                69295321,
                69295488,
                69295530,
                69295685,
                69295798,
                69295839,
                69295939,
                70466374,
            ],
        )

    def test_association_without_listing_is_an_error(self):
        self.session.handlers[ASSOCIATION_URL] = lambda m, u, k: FakeResponse(
            text='0:{"nothing":true}\n', content_type="text/x-component"
        )
        with self.assertRaises(MySidelineResponseError):
            self.client.get_association(self.url)

    def test_association_http_error(self):
        self.session.handlers[ASSOCIATION_URL] = lambda m, u, k: FakeResponse(
            status_code=503, text="", content_type="text/html"
        )
        with self.assertRaises(MySidelineTransportError):
            self.client.get_association(self.url)

    def test_connection_failure(self):
        self.session.exception = requests.ConnectionError("boom")
        with self.assertRaises(MySidelineTransportError):
            self.client.get_association(self.url)

    def test_pooled_competition(self):
        self.install_competition(66474844)
        competition = self.client.get_competition(66474844, "9/10 Girls", 2026, "TFA")
        self.assertEqual(competition.pools, ("Pool A", "Pool B"))
        self.assertEqual(len(competition.teams), 8)
        self.assertEqual(competition.team_pool[68697946], "Pool A")
        self.assertEqual(len(competition.matches), 19)
        grand_final = next(
            m for m in competition.matches if m.round_name == "Grand Final"
        )
        self.assertEqual(grand_final.is_final_round, True)
        self.assertEqual(grand_final.has_result, True)
        self.assertEqual((grand_final.home_score, grand_final.away_score), (3, 2))
        self.assertEqual(grand_final.home_team_id, 68697946)
        self.assertEqual(grand_final.field, "4")
        self.assertEqual(grand_final.venue.name, "Adcock Park")
        self.assertEqual(grand_final.venue.timezone, "Australia/Sydney")
        self.assertEqual(
            grand_final.start, datetime(2026, 5, 1, 4, 25, tzinfo=ZoneInfo("UTC"))
        )

    def test_byes_and_tba_finals(self):
        self.install_competition(69295173)
        competition = self.client.get_competition(69295173, "u16 Boys", 2026, "TFA")
        byes = [m for m in competition.matches if m.is_bye]
        self.assertEqual(len(byes), 11)
        played_bye = next(m for m in byes if m.status == "final")
        self.assertEqual(played_bye.has_result, False)
        self.assertEqual(played_bye.away_team_id, None)
        tba = [m for m in competition.matches if m.is_tba]
        self.assertEqual(len(tba), 3)
        self.assertEqual({m.home_team_id for m in tba}, {None})
        self.assertEqual({m.round_type for m in tba}, {"Final"})

    def test_forfeits(self):
        self.install_competition(67513269)
        competition = self.client.get_competition(67513269, "Mixed", 2026, "TFA")
        forfeits = [m for m in competition.matches if m.is_forfeit]
        self.assertEqual(len(forfeits), 2)
        self.assertEqual({m.forfeiting_team_id for m in forfeits}, {67727471})
        self.assertEqual({m.has_result for m in forfeits}, {False})

    def test_ladder_template_from_competition_page(self):
        text = fixture("competition_65396575.rsc")
        self.session.handlers["https://tfa.mysideline.com.au/competitions/65396575"] = (
            lambda m, u, k: FakeResponse(text=text, content_type="text/x-component")
        )
        template = self.client.get_ladder_template(self.url, 65396575)
        self.assertEqual(template.name, "Events Ladder - NSWTA")
        self.assertEqual(
            (template.points_win, template.points_draw, template.points_loss),
            (4, 2, 0),
        )
        self.assertEqual(template.points_bye, 0)
        self.assertEqual(template.points_forfeit_for, 4)
        self.assertEqual(template.forfeit_score, 5)
        self.assertEqual(template.forfeit_counts_as_played, True)
        self.assertEqual(template.points_formula, "4*win + 2*draw + 4*forfeit_for")

    def test_ladder_template_missing_is_a_response_error(self):
        self.session.handlers["https://tfa.mysideline.com.au/competitions/1"] = (
            lambda m, u, k: FakeResponse(
                text='0:{"data":{"competition":{"_id":1}}}\n',
                content_type="text/x-component",
            )
        )
        with self.assertRaises(MySidelineResponseError):
            self.client.get_ladder_template(self.url, 1)

    def test_graphql_errors_are_response_errors(self):
        self.session.handlers[GRAPHQL_ENDPOINT] = lambda m, u, k: FakeResponse(
            text=json.dumps({"errors": [{"message": "Cannot query field"}]})
        )
        with self.assertRaises(MySidelineResponseError):
            self.client.get_competition(1, "x", 2026, "TFA")

    def test_malformed_graphql_payloads(self):
        for text in ("<html>", "[]", '{"data": {"teams": {}}}'):
            self.session.handlers[GRAPHQL_ENDPOINT] = (
                lambda m, u, k, t=text: FakeResponse(text=t)
            )
            with self.assertRaises(MySidelineResponseError):
                self.client.get_competition(1, "x", 2026, "TFA")

    def test_malformed_match_entries(self):
        def handler(method, url, kwargs):
            if "competitionMatches" in kwargs["json"]["query"]:
                return FakeResponse(
                    text=json.dumps(
                        {"data": {"competitionMatches": [{"status": "final"}]}}
                    )
                )
            return FakeResponse(text=json.dumps({"data": {"teams": []}}))

        self.session.handlers[GRAPHQL_ENDPOINT] = handler
        with self.assertRaises(MySidelineResponseError):
            self.client.get_competition(1, "x", 2026, "TFA")


class SyncTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(
            title="2026",
            timezone=SYDNEY,
            competition__mysideline_url=ASSOCIATION_URL,
            mysideline_season=2026,
        )
        self.remote = RemoteWorld()
        self.session = FakeSession()
        self.remote.install(self.session)
        # Not ``self.client``, which is the Django test client used by the
        # tests which exercise the admin.
        self.mysideline = MySidelineClient(session=self.session)

    def sync(self):
        return synchronise_season(self.season, self.mysideline)

    def populate(self):
        """One un-pooled division with two rounds and one pooled division."""
        self.remote.add_competition(100, "Mens Div 1")
        self.remote.add_team(100, 1, "Sharks")
        self.remote.add_team(100, 2, "Dolphins")
        self.remote.add_team(100, 3, "Whales")
        self.remote.add_match(
            100, 1001, 1, 1, 2, sydney(2026, 9, 5, 18, 0), "final", (7, 3), field="1"
        )
        self.remote.add_match(
            100,
            1002,
            1,
            3,
            None,
            sydney(2026, 9, 5, 18, 0),
            "final",
            is_bye=True,
            field=None,
        )
        self.remote.add_match(100, 1003, 2, 2, 3, sydney(2026, 9, 12, 18, 0), field="2")
        self.remote.add_match(
            100, 1004, 2, None, 1, sydney(2026, 9, 12, 18, 0), is_bye=True, field=None
        )
        self.remote.add_match(
            100,
            1005,
            1,
            None,
            None,
            sydney(2026, 9, 19, 18, 0),
            round_type="Final",
            round_name="Grand Final",
            is_tba=True,
            field=None,
        )

        self.remote.add_competition(200, "Womens Div 1")
        self.remote.add_team(200, 11, "Reds", pool="Pool A")
        self.remote.add_team(200, 12, "Blues", pool="Pool A")
        self.remote.add_team(200, 13, "Greens", pool="Pool B")
        self.remote.add_team(200, 14, "Golds", pool="Pool B")
        self.remote.add_match(
            200, 2001, 1, 11, 12, sydney(2026, 9, 5, 19, 0), "final", (5, 5)
        )
        self.remote.add_match(
            200, 2002, 1, 13, 14, sydney(2026, 9, 5, 19, 0), "final", (2, 1)
        )
        self.remote.add_match(200, 2003, 2, 11, 13, sydney(2026, 9, 12, 19, 0))


class InitialImportTests(SyncTestCase):
    def test_structure(self):
        result = self.populate() or self.sync()

        self.assertEqual(result.created["division"], 2)
        self.assertEqual(result.created["team"], 7)
        self.assertEqual(result.created["match"], 8)
        self.assertEqual(result.created["stagegroup"], 2)
        self.assertEqual(result.created["venue"], 1)
        self.assertEqual(result.created["ground"], 2)
        self.assertEqual(result.updated, {})
        self.assertEqual(result.deleted, {})
        self.assertEqual(result.warnings, [])

        mens = self.season.divisions.get(mysideline_id=100)
        self.assertEqual(mens.title, "Mens Div 1")
        self.assertEqual(mens.slug, "mens-div-1")
        self.assertEqual(mens.order, 1)
        self.assertEqual(
            mens.points_formula, "3*win + 2*draw + 1*loss + 3*bye + 3*forfeit_for"
        )
        self.assertEqual(
            list(mens.stages.values_list("title", "order", "keep_ladder")),
            [(REGULAR_STAGE_TITLE, 1, True), (FINALS_STAGE_TITLE, 2, False)],
        )
        self.assertEqual(
            list(mens.teams.values_list("mysideline_id", "title", "order")),
            [(1, "Sharks", 1), (2, "Dolphins", 2), (3, "Whales", 3)],
        )

        womens = self.season.divisions.get(mysideline_id=200)
        self.assertEqual(womens.order, 2)
        self.assertEqual(
            list(womens.stages.values_list("title", flat=True)), [REGULAR_STAGE_TITLE]
        )
        regular = womens.stages.get()
        self.assertEqual(
            list(regular.pools.values_list("title", "order")),
            [("Pool A", 1), ("Pool B", 2)],
        )
        self.assertEqual(
            {t.title: t.stage_group.title for t in womens.teams.all()},
            {
                "Reds": "Pool A",
                "Blues": "Pool A",
                "Greens": "Pool B",
                "Golds": "Pool B",
            },
        )

    def test_matches(self):
        self.populate()
        self.sync()

        played = Match.objects.get(mysideline_id=1001)
        self.assertEqual(played.stage.title, REGULAR_STAGE_TITLE)
        self.assertEqual(played.round, 1)
        self.assertEqual(played.label, None)
        self.assertEqual(played.home_team.title, "Sharks")
        self.assertEqual(played.away_team.title, "Dolphins")
        self.assertEqual((played.home_team_score, played.away_team_score), (7, 3))
        self.assertEqual(played.datetime, sydney(2026, 9, 5, 18, 0))
        self.assertEqual(played.date, sydney(2026, 9, 5, 18, 0).date())
        self.assertEqual(played.time, sydney(2026, 9, 5, 18, 0).time())
        self.assertEqual(played.play_at.title, "Field 1")
        self.assertEqual(
            played.play_at.ground.venue.title, "Garnet Adcock Memorial Park"
        )
        self.assertEqual(played.play_at.ground.venue.timezone, SYDNEY)
        self.assertEqual(
            played.play_at.ground.venue.latlng, "-33.42895924,151.3261477,15"
        )
        self.assertEqual(played.is_bye, False)
        self.assertEqual(played.is_forfeit, False)

        unplayed = Match.objects.get(mysideline_id=1003)
        self.assertEqual(
            (unplayed.home_team_score, unplayed.away_team_score), (None, None)
        )
        self.assertEqual(unplayed.round, 2)
        self.assertEqual(unplayed.play_at.title, "Field 2")

        bye = Match.objects.get(mysideline_id=1002)
        self.assertEqual(bye.is_bye, True)
        self.assertEqual(bye.bye_processed, True)
        self.assertEqual(bye.home_team.title, "Whales")
        self.assertEqual(bye.away_team, None)
        self.assertEqual(bye.play_at.title, "Garnet Adcock Memorial Park")
        future_bye = Match.objects.get(mysideline_id=1004)
        self.assertEqual(future_bye.bye_processed, False)

        final = Match.objects.get(mysideline_id=1005)
        self.assertEqual(final.stage.title, FINALS_STAGE_TITLE)
        self.assertEqual(final.label, "Grand Final")
        self.assertEqual((final.home_team, final.away_team), (None, None))
        self.assertEqual(final.home_team_undecided.label, "TBA")
        self.assertEqual(final.away_team_undecided.label, "TBA")
        self.assertEqual(final.get_home_team_plain(), "TBA")

        # Matches within a pool are attached to it, cross-pool matches are not.
        self.assertEqual(
            Match.objects.get(mysideline_id=2001).stage_group.title, "Pool A"
        )
        self.assertEqual(
            Match.objects.get(mysideline_id=2002).stage_group.title, "Pool B"
        )
        self.assertEqual(Match.objects.get(mysideline_id=2003).stage_group, None)

    def test_ladder(self):
        self.populate()
        self.sync()
        mens = self.season.divisions.get(mysideline_id=100)
        summary = {
            row.team.title: (row.played, row.win, row.loss, row.bye, int(row.points))
            for row in LadderSummary.objects.filter(stage__division=mens)
        }
        self.assertEqual(
            summary,
            {
                "Sharks": (1, 1, 0, 0, 3),
                "Dolphins": (1, 0, 1, 0, 1),
                "Whales": (1, 0, 0, 1, 3),
            },
        )

    def test_repeat_is_idempotent(self):
        self.populate()
        self.sync()
        snapshot = list(Match.objects.values_list("pk", "datetime", "home_team_score"))
        result = self.sync()
        self.assertEqual(result.created, {})
        self.assertEqual(result.updated, {})
        self.assertEqual(result.deleted, {})
        self.assertEqual(result.detached, {})
        self.assertEqual(
            list(Match.objects.values_list("pk", "datetime", "home_team_score")),
            snapshot,
        )
        self.assertEqual(Division.objects.count(), 2)
        self.assertEqual(Team.objects.count(), 7)
        self.assertEqual(Match.objects.count(), 8)
        self.assertEqual(Venue.objects.count(), 1)
        self.assertEqual(Ground.objects.count(), 2)

    def test_ladder_template_seeds_new_division(self):
        self.remote.add_competition(
            300, "Cup", ladder={"pointsWin": 4, "pointsLoss": 0, "pointsBye": 0}
        )
        self.populate()
        self.sync()
        cup = self.season.divisions.get(mysideline_id=300)
        self.assertEqual(cup.points_formula, "4*win + 2*draw + 3*forfeit_for")
        self.assertEqual(cup.forfeit_for_score, 5)

        # Later changes to the template do not overwrite local configuration.
        self.remote.competition(300)["laddertemplate"]["pointsWin"] = 10
        self.sync()
        cup.refresh_from_db()
        self.assertEqual(cup.points_formula, "4*win + 2*draw + 3*forfeit_for")

    def test_unreadable_ladder_template_falls_back_to_default(self):
        self.populate()
        self.session.default = lambda m, u, k: FakeResponse(
            text="0:{}\n", content_type="text/x-component"
        )
        result = self.sync()
        self.assertEqual(result.created["division"], 2)
        self.assertEqual(
            self.season.divisions.get(mysideline_id=100).points_formula,
            "3*win + 2*draw + 1*loss + 3*bye + 3*forfeit_for",
        )

    def test_adopts_existing_division_and_teams_by_title(self):
        division = factories.DivisionFactory.create(
            season=self.season, title="Mens Div 1", points_formula="4*win"
        )
        team = factories.TeamFactory.create(division=division, title="sharks")
        self.populate()
        self.sync()
        division.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual(division.mysideline_id, 100)
        self.assertEqual(division.points_formula, "4*win")
        self.assertEqual(team.mysideline_id, 1)
        self.assertEqual(team.title, "Sharks")
        self.assertEqual(Division.objects.count(), 2)

    def test_reuses_existing_venue_and_ground(self):
        venue = factories.VenueFactory.create(
            season=self.season, title="garnet adcock memorial park"
        )
        ground = factories.GroundFactory.create(venue=venue, title="field 1")
        self.populate()
        self.sync()
        self.assertEqual(Match.objects.get(mysideline_id=1001).play_at_id, ground.pk)
        self.assertEqual(Venue.objects.count(), 1)
        self.assertEqual(Ground.objects.count(), 2)

    def test_venue_timezone_drives_local_date_and_time(self):
        self.remote.VENUE = dict(self.remote.VENUE, venueTimezone="Australia/Perth")
        self.populate()
        self.sync()
        match = Match.objects.get(mysideline_id=1001)
        self.assertEqual(match.datetime, sydney(2026, 9, 5, 18, 0))
        self.assertEqual(match.time, datetime(2026, 9, 5, 16, 0).time())
        self.assertEqual(
            match.play_at.ground.venue.timezone, ZoneInfo("Australia/Perth")
        )


class IncrementalSyncTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.populate()
        self.sync()

    def test_add_division_team_and_match(self):
        self.remote.add_competition(300, "Mixed")
        self.remote.add_team(300, 31, "Purples")
        self.remote.add_team(100, 4, "Orcas")
        self.remote.add_match(100, 1006, 3, 4, 1, sydney(2026, 9, 26, 18, 0))
        result = self.sync()
        self.assertEqual(
            result.created, {"division": 1, "stage": 1, "team": 2, "match": 1}
        )
        self.assertEqual(result.updated, {})
        self.assertEqual(self.season.divisions.get(mysideline_id=300).order, 3)
        orcas = Team.objects.get(mysideline_id=4)
        self.assertEqual((orcas.division.mysideline_id, orcas.order), (100, 4))
        self.assertEqual(Match.objects.get(mysideline_id=1006).home_team, orcas)

    def test_update_result(self):
        pk = Match.objects.get(mysideline_id=1003).pk
        self.remote.match(100, 1003).update(
            status="final", scores={"homeTeam": 4, "awayTeam": 9}
        )
        result = self.sync()
        self.assertEqual(result.updated, {"match": 1})
        match = Match.objects.get(pk=pk)
        self.assertEqual((match.home_team_score, match.away_team_score), (4, 9))
        self.assertEqual(
            LadderSummary.objects.get(
                stage__division__mysideline_id=100, team__title="Whales"
            ).win,
            1,
        )

    def test_change_result(self):
        self.remote.match(100, 1001)["scores"] = {"homeTeam": 7, "awayTeam": 8}
        self.sync()
        match = Match.objects.get(mysideline_id=1001)
        self.assertEqual((match.home_team_score, match.away_team_score), (7, 8))
        self.assertEqual(
            LadderSummary.objects.get(
                stage__division__mysideline_id=100, team__title="Dolphins"
            ).win,
            1,
        )

    def test_result_withdrawn(self):
        self.remote.match(100, 1001).update(
            status="pre-game", scores={"homeTeam": 0, "awayTeam": 0}
        )
        self.sync()
        match = Match.objects.get(mysideline_id=1001)
        self.assertEqual((match.home_team_score, match.away_team_score), (None, None))
        self.assertEqual(
            LadderSummary.objects.get(
                stage__division__mysideline_id=100, team__title="Sharks"
            ).played,
            0,
        )

    def test_forfeit(self):
        self.remote.match(100, 1003).update(status="forfeit")
        self.remote.match(100, 1003)["meta"]["forfeitingTeam"] = {
            "_id": 3,
            "name": "Whales",
        }
        self.sync()
        match = Match.objects.get(mysideline_id=1003)
        self.assertEqual(match.is_forfeit, True)
        self.assertEqual(match.forfeit_winner.title, "Dolphins")
        self.assertEqual((match.home_team_score, match.away_team_score), (5, 0))

        # ... and back again once MySideline corrects it.
        self.remote.match(100, 1003).update(
            status="final", scores={"homeTeam": 2, "awayTeam": 3}
        )
        self.remote.match(100, 1003)["meta"]["forfeitingTeam"] = None
        self.sync()
        match.refresh_from_db()
        self.assertEqual(match.is_forfeit, False)
        self.assertEqual(match.forfeit_winner, None)
        self.assertEqual((match.home_team_score, match.away_team_score), (2, 3))

    def test_reschedule(self):
        self.remote.match(100, 1003).update(
            dateTime=int(sydney(2026, 9, 13, 10, 30).timestamp() * 1000)
        )
        self.remote.match(100, 1003)["meta"]["fieldNo"] = "3"
        self.sync()
        match = Match.objects.get(mysideline_id=1003)
        self.assertEqual(match.datetime, sydney(2026, 9, 13, 10, 30))
        self.assertEqual(match.date, sydney(2026, 9, 13, 10, 30).date())
        self.assertEqual(match.play_at.title, "Field 3")

    def test_rename_preserves_identity(self):
        division_pk = self.season.divisions.get(mysideline_id=100).pk
        team_pk = Team.objects.get(mysideline_id=1).pk
        self.remote.competition(100)["name"] = "Mens Premier"
        self.remote.team(100, 1)["name"] = "Terrigal Sharks"
        result = self.sync()
        self.assertEqual(result.updated, {"division": 1, "team": 1})
        self.assertEqual(result.created, {})
        self.assertEqual(result.deleted, {})
        division = Division.objects.get(pk=division_pk)
        self.assertEqual(
            (division.title, division.slug), ("Mens Premier", "mens-premier")
        )
        team = Team.objects.get(pk=team_pk)
        self.assertEqual(
            (team.title, team.slug), ("Terrigal Sharks", "terrigal-sharks")
        )
        self.assertEqual(Match.objects.get(mysideline_id=1001).home_team_id, team_pk)

    def test_locked_slug_is_kept(self):
        division = self.season.divisions.get(mysideline_id=100)
        division.slug_locked = True
        division.save()
        self.remote.competition(100)["name"] = "Mens Premier"
        self.sync()
        division.refresh_from_db()
        self.assertEqual(
            (division.title, division.slug), ("Mens Premier", "mens-div-1")
        )

    def test_finals_fixtures_added_later(self):
        womens = self.season.divisions.get(mysideline_id=200)
        self.assertEqual(womens.stages.count(), 1)
        self.remote.add_match(
            200,
            2004,
            1,
            None,
            None,
            sydney(2026, 9, 19, 19, 0),
            round_type="Final",
            round_name="Semi Final",
            is_tba=True,
        )
        self.sync()
        self.assertEqual(
            list(womens.stages.values_list("title", "order")),
            [(REGULAR_STAGE_TITLE, 1), (FINALS_STAGE_TITLE, 2)],
        )
        self.assertEqual(
            Match.objects.get(mysideline_id=2004).stage.title, FINALS_STAGE_TITLE
        )

        # Once finalists are known the teams are filled in.
        self.remote.match(200, 2004).update(
            homeTeam={"_id": 11, "name": "Reds"}, awayTeam={"_id": 13, "name": "Greens"}
        )
        self.remote.match(200, 2004)["meta"]["isTba"] = False
        self.sync()
        match = Match.objects.get(mysideline_id=2004)
        self.assertEqual(
            (match.home_team.title, match.away_team.title), ("Reds", "Greens")
        )
        self.assertEqual(match.home_team_undecided, None)
        self.assertEqual(match.away_team_undecided, None)

    def test_pool_changes(self):
        # Move a team between pools, rename a pool, and un-pool a match.
        self.remote.team(200, 12)["pool"] = "Pool B"
        for team in self.remote.competition(200)["teams"]:
            if team["pool"] == "Pool A":
                team["pool"] = "Pool Alpha"
        self.sync()
        womens = self.season.divisions.get(mysideline_id=200)
        regular = womens.stages.get(title=REGULAR_STAGE_TITLE)
        self.assertEqual(
            list(regular.pools.values_list("title", flat=True)),
            ["Pool B", "Pool Alpha"],
        )
        self.assertEqual(Team.objects.get(mysideline_id=12).stage_group.title, "Pool B")
        self.assertEqual(
            Team.objects.get(mysideline_id=11).stage_group.title, "Pool Alpha"
        )
        self.assertEqual(Match.objects.get(mysideline_id=2001).stage_group, None)
        self.assertEqual(
            Match.objects.get(mysideline_id=2002).stage_group.title, "Pool B"
        )

    def test_pools_introduced_later(self):
        self.remote.team(100, 1)["pool"] = "Pool A"
        self.remote.team(100, 2)["pool"] = "Pool A"
        self.remote.team(100, 3)["pool"] = "Pool B"
        self.sync()
        mens = self.season.divisions.get(mysideline_id=100)
        self.assertEqual(
            Match.objects.get(mysideline_id=1001).stage_group.title, "Pool A"
        )
        self.assertEqual(Match.objects.get(mysideline_id=1003).stage_group, None)
        self.assertEqual(mens.stages.get(title=REGULAR_STAGE_TITLE).pools.count(), 2)


class TitleTests(SyncTestCase):
    """
    MySideline is not authoritative for the *name* of a division or team;
    a name chosen locally is kept and an upstream rename is reported.
    """

    def setUp(self):
        super().setUp()
        self.populate()
        self.sync()
        self.division = self.season.divisions.get(mysideline_id=100)
        self.team = Team.objects.get(mysideline_id=1)

    def rename_division(self, title="14 Boys"):
        self.division.title = title
        self.division.save()
        self.division.refresh_from_db()
        return self.division

    def test_remote_name_is_recorded(self):
        for obj, name in ((self.division, "Mens Div 1"), (self.team, "Sharks")):
            self.assertEqual(obj.title, name)
            self.assertEqual(obj.mysideline_title, name)
            self.assertEqual(obj.mysideline_title_synced, name)
            self.assertFalse(obj.mysideline_title_overridden)
            self.assertFalse(obj.mysideline_title_changed)

    def test_local_division_name_is_kept(self):
        self.rename_division()
        result = self.sync()
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "14 Boys")
        self.assertEqual(self.division.mysideline_title, "Mens Div 1")
        self.assertEqual(self.division.mysideline_title_synced, "Mens Div 1")
        self.assertTrue(self.division.mysideline_title_overridden)
        self.assertFalse(self.division.mysideline_title_changed)
        self.assertEqual(result.warnings, [])

    def test_local_team_name_is_kept(self):
        self.team.title = "Terrigal"
        self.team.save()
        result = self.sync()
        self.team.refresh_from_db()
        self.assertEqual(self.team.title, "Terrigal")
        self.assertEqual(self.team.mysideline_title, "Sharks")
        self.assertTrue(self.team.mysideline_title_overridden)
        self.assertEqual(result.warnings, [])

    def test_local_name_does_not_affect_the_rest_of_the_sync(self):
        self.rename_division()
        self.remote.match(100, 1003).update(
            status="final", scores={"homeTeam": 4, "awayTeam": 2}
        )
        self.sync()
        match = Match.objects.get(mysideline_id=1003)
        self.assertEqual((match.home_team_score, match.away_team_score), (4, 2))
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "14 Boys")

    def test_remote_rename_of_a_local_name_is_reported(self):
        self.rename_division()
        self.remote.competition(100)["name"] = "Mens Premier"
        result = self.sync()
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "14 Boys")
        self.assertEqual(self.division.mysideline_title, "Mens Premier")
        self.assertEqual(self.division.mysideline_title_synced, "Mens Div 1")
        self.assertTrue(self.division.mysideline_title_changed)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("renamed remotely", result.warnings[0])
        self.assertIn("'Mens Div 1' to 'Mens Premier'", result.warnings[0])

    def test_remote_rename_is_applied_while_the_name_is_not_local(self):
        self.remote.competition(100)["name"] = "Mens Premier"
        result = self.sync()
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "Mens Premier")
        self.assertEqual(self.division.mysideline_title, "Mens Premier")
        self.assertEqual(self.division.mysideline_title_synced, "Mens Premier")
        self.assertEqual(result.warnings, [])

    def test_clashing_remote_rename_is_reported_and_retried(self):
        self.remote.competition(200)["name"] = "Mens Div 1"
        result = self.sync()
        womens = self.season.divisions.get(mysideline_id=200)
        self.assertEqual(womens.title, "Womens Div 1")
        self.assertEqual(womens.mysideline_title, "Mens Div 1")
        self.assertEqual(womens.mysideline_title_synced, "Womens Div 1")
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("cannot be renamed", result.warnings[0])

        # Once the name is free the rename is applied by the next sync.
        self.remote.competition(100)["name"] = "Mens Premier"
        result = self.sync()
        womens.refresh_from_db()
        self.assertEqual(womens.title, "Mens Div 1")
        self.assertEqual(womens.mysideline_title_synced, "Mens Div 1")
        self.assertEqual(result.warnings, [])

    def test_adopted_records_follow_the_remote_name(self):
        division = factories.DivisionFactory.create(season=self.season, title="tba")
        self.remote.add_competition(300, "TBA")
        self.sync()
        division.refresh_from_db()
        self.assertEqual(division.mysideline_id, 300)
        self.assertEqual(division.title, "TBA")
        self.assertEqual(division.mysideline_title_synced, "TBA")
        self.assertFalse(division.mysideline_title_overridden)

    def test_renamed_queryset(self):
        self.rename_division()
        self.remote.competition(100)["name"] = "Mens Premier"
        self.remote.team(100, 1)["name"] = "Terrigal Sharks"
        self.team.title = "Terrigal"
        self.team.save()
        self.sync()
        self.assertEqual(
            [d.pk for d in mysideline_renamed(self.season.divisions)],
            [self.division.pk],
        )
        self.assertEqual(
            [t.pk for t in mysideline_renamed(Team.objects.all())], [self.team.pk]
        )


class TitleAdminTests(SyncTestCase):
    """Choosing between the local and the MySideline name in the admin."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.populate()
        self.sync()
        self.division = self.season.divisions.get(mysideline_id=100)
        self.division.title = "14 Boys"
        self.division.save()
        self.remote.competition(100)["name"] = "Mens Premier"
        self.sync()
        self.division.refresh_from_db()
        self.args = (self.season.competition_id, self.season.pk)

    def division_form(self, **kwargs):
        data = {
            "title": self.division.title,
            "slug": self.division.slug,
            "color": self.division.color,
            "points_formula_0": "3",
            "points_formula_1": "2",
            "points_formula_2": "1",
            "points_formula_3": "3",
            "points_formula_4": "3",
            "points_formula_5": "",
            "forfeit_for_score": self.division.forfeit_for_score,
            "forfeit_against_score": self.division.forfeit_against_score,
        }
        data.update(kwargs)
        return DivisionForm(data=data, instance=self.division, user=self.superuser)

    def test_form_shows_the_remote_name(self):
        form = self.division_form()
        self.assertIn("Mens Premier", form.fields["title"].help_text)
        self.assertIn("Mens Div 1", form.fields["title"].help_text)
        self.assertIn("mysideline_title_reset", form.fields)

    def test_form_without_a_link_is_unchanged(self):
        division = factories.DivisionFactory.create(season=self.season)
        form = DivisionForm(instance=division, user=self.superuser)
        self.assertNotIn("mysideline_title_reset", form.fields)

    def test_saving_keeps_the_local_name_and_acknowledges_the_change(self):
        form = self.division_form()
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "14 Boys")
        self.assertEqual(self.division.mysideline_title_synced, "Mens Premier")
        self.assertTrue(self.division.mysideline_title_overridden)
        self.assertFalse(self.division.mysideline_title_changed)
        # ... and the synchronisation stops reporting it.
        self.assertEqual(self.sync().warnings, [])

    def test_saving_with_reset_adopts_the_remote_name(self):
        form = self.division_form(mysideline_title_reset="1")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "Mens Premier")
        self.assertEqual(self.division.slug, "mens-premier")
        self.assertEqual(self.division.mysideline_title_synced, "Mens Premier")
        self.assertFalse(self.division.mysideline_title_overridden)
        # ... and later renames are applied again without intervention.
        self.remote.competition(100)["name"] = "Mens Division One"
        self.sync()
        self.division.refresh_from_db()
        self.assertEqual(self.division.title, "Mens Division One")

    def test_team_form_offers_the_remote_name(self):
        team = Team.objects.get(mysideline_id=1)
        team.title = "Terrigal"
        team.save()
        self.remote.team(100, 1)["name"] = "Terrigal Sharks"
        self.sync()
        team.refresh_from_db()
        form = TeamForm(
            team.division,
            data={
                "title": team.title,
                "slug": team.slug,
                "mysideline_title_reset": "1",
            },
            instance=team,
            user=self.superuser,
        )
        self.assertIn("Terrigal Sharks", form.fields["title"].help_text)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        team.refresh_from_db()
        self.assertEqual(team.title, "Terrigal Sharks")
        self.assertEqual(team.mysideline_title_synced, "Terrigal Sharks")

    def test_sync_page_lists_remote_renames(self):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:mysideline-sync",
                *self.args,
                test_query_count=60,
            )
            self.assertResponseContains("14 Boys", html=False)
            self.assertResponseContains("Mens Premier", html=False)
            self.assertResponseContains(
                self.reverse(
                    "admin:fixja:competition:season:division:edit",
                    self.season.competition_id,
                    self.season.pk,
                    self.division.pk,
                ),
                html=False,
            )


class RemovalTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.populate()
        self.sync()

    def test_match_removed(self):
        self.remote.competition(100)["matches"] = [
            m for m in self.remote.competition(100)["matches"] if m["_id"] != 1003
        ]
        result = self.sync()
        self.assertEqual(result.deleted, {"match": 1})
        self.assertEqual(Match.objects.filter(mysideline_id=1003).count(), 0)
        self.assertEqual(Match.objects.count(), 7)

    def test_team_removed_with_its_fixtures(self):
        competition = self.remote.competition(100)
        competition["teams"] = [t for t in competition["teams"] if t["_id"] != 3]
        competition["matches"] = [
            m
            for m in competition["matches"]
            if 3 not in (m["homeTeam"]["_id"], m["awayTeam"]["_id"])
        ]
        result = self.sync()
        self.assertEqual(result.deleted, {"match": 2, "team": 1})
        self.assertEqual(Team.objects.filter(mysideline_id=3).count(), 0)
        self.assertEqual(
            list(
                Team.objects.filter(division__mysideline_id=100).values_list(
                    "order", flat=True
                )
            ),
            [1, 2],
        )

    def test_team_protected_by_native_match_is_detached(self):
        whales = Team.objects.get(mysideline_id=3)
        sharks = Team.objects.get(mysideline_id=1)
        native = factories.MatchFactory.create(
            stage=whales.division.stages.get(title=REGULAR_STAGE_TITLE),
            home_team=whales,
            away_team=sharks,
        )
        competition = self.remote.competition(100)
        competition["teams"] = [t for t in competition["teams"] if t["_id"] != 3]
        competition["matches"] = [
            m
            for m in competition["matches"]
            if 3 not in (m["homeTeam"]["_id"], m["awayTeam"]["_id"])
        ]
        result = self.sync()
        self.assertEqual(result.deleted, {"match": 2})
        self.assertEqual(result.detached, {"team": 1})
        self.assertEqual(len(result.warnings), 1)
        whales.refresh_from_db()
        self.assertEqual(whales.mysideline_id, None)
        self.assertEqual(whales.division.mysideline_id, 100)
        self.assertEqual(Match.objects.filter(pk=native.pk).count(), 1)

    def test_division_removed(self):
        self.remote.competitions = [
            c for c in self.remote.competitions if c["_id"] != 200
        ]
        result = self.sync()
        self.assertEqual(
            result.deleted,
            {"division": 1, "stage": 1, "stagegroup": 2, "team": 4, "match": 3},
        )
        self.assertEqual(Division.objects.filter(mysideline_id=200).count(), 0)
        self.assertEqual(Division.objects.count(), 1)
        self.assertEqual(Match.objects.count(), 5)
        # Venues are shared with native data and never removed.
        self.assertEqual(Venue.objects.count(), 1)

    def test_division_with_native_data_is_marked_draft(self):
        division = self.season.divisions.get(mysideline_id=200)
        native_team = factories.TeamFactory.create(division=division, title="Locals")
        native = factories.MatchFactory.create(
            stage=division.stages.get(),
            home_team=native_team,
            away_team=Team.objects.get(mysideline_id=11),
        )
        self.remote.competitions = [
            c for c in self.remote.competitions if c["_id"] != 200
        ]
        result = self.sync()
        self.assertEqual(result.deleted, {"match": 3, "team": 3})
        self.assertEqual(result.detached, {"team": 1, "division": 1})
        division.refresh_from_db()
        self.assertEqual(division.draft, True)
        self.assertEqual(division.mysideline_id, 200)
        self.assertEqual(Match.objects.filter(pk=native.pk).count(), 1)
        self.assertEqual(Team.objects.filter(pk=native_team.pk).count(), 1)
        self.assertEqual(
            Team.objects.get(mysideline_id__isnull=True, title="Reds").pk,
            native.away_team_id,
        )

    def test_pool_removed(self):
        for team in self.remote.competition(200)["teams"]:
            team["pool"] = None
        result = self.sync()
        self.assertEqual(result.deleted, {"stagegroup": 2})
        self.assertEqual(StageGroup.objects.count(), 0)
        self.assertEqual(
            {t.stage_group for t in Team.objects.filter(division__mysideline_id=200)},
            {None},
        )
        self.assertEqual(Match.objects.get(mysideline_id=2001).stage_group, None)

    def test_finals_removed(self):
        self.remote.competition(100)["matches"] = [
            m
            for m in self.remote.competition(100)["matches"]
            if m["round"]["type"] != "Final"
        ]
        result = self.sync()
        self.assertEqual(result.deleted, {"match": 1, "stage": 1})
        self.assertEqual(Stage.objects.filter(division__mysideline_id=100).count(), 1)

    def test_native_data_is_never_touched(self):
        native_division = factories.DivisionFactory.create(
            season=self.season, title="Locals only"
        )
        native_stage = factories.StageFactory.create(division=native_division)
        native_match = factories.MatchFactory.create(stage=native_stage)
        self.remote.competitions = []
        result = self.sync()
        self.assertEqual(result.deleted["division"], 2)
        self.assertEqual(Division.objects.count(), 1)
        self.assertEqual(Match.objects.filter(pk=native_match.pk).count(), 1)


class FailureTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.populate()
        self.sync()
        self.before = (
            list(
                Division.objects.order_by("pk").values_list(
                    "pk", "title", "mysideline_id"
                )
            ),
            list(
                Team.objects.order_by("pk").values_list("pk", "title", "mysideline_id")
            ),
            list(
                Match.objects.order_by("pk").values_list(
                    "pk", "home_team_score", "datetime"
                )
            ),
        )

    def assertUnchanged(self):
        self.assertEqual(
            self.before,
            (
                list(
                    Division.objects.order_by("pk").values_list(
                        "pk", "title", "mysideline_id"
                    )
                ),
                list(
                    Team.objects.order_by("pk").values_list(
                        "pk", "title", "mysideline_id"
                    )
                ),
                list(
                    Match.objects.order_by("pk").values_list(
                        "pk", "home_team_score", "datetime"
                    )
                ),
            ),
        )

    def test_connection_failure_changes_nothing(self):
        self.session.exception = requests.ConnectionError("boom")
        with self.assertRaises(MySidelineTransportError):
            self.sync()
        self.assertUnchanged()

    def test_http_error_changes_nothing(self):
        self.session.handlers[ASSOCIATION_URL] = lambda m, u, k: FakeResponse(
            status_code=500, text="oops", content_type="text/html"
        )
        with self.assertRaises(MySidelineTransportError):
            self.sync()
        self.assertUnchanged()

    def test_empty_listing_is_not_treated_as_empty_competition(self):
        # A page without a listing is malformed, not empty.
        self.session.handlers[ASSOCIATION_URL] = lambda m, u, k: FakeResponse(
            text="", content_type="text/x-component"
        )
        with self.assertRaises(MySidelineResponseError):
            self.sync()
        self.assertUnchanged()

    def test_graphql_failure_for_one_competition_changes_nothing(self):
        # The first competition fetches fine, the second fails; because the
        # whole snapshot is fetched before anything is written, nothing
        # changes locally.
        self.remote.competition(100)["name"] = "Renamed"
        original = self.session.handlers[GRAPHQL_ENDPOINT]

        def flaky(method, url, kwargs):
            if kwargs["json"]["variables"]["competitionId"] == 200:
                return FakeResponse(status_code=502, text="bad gateway")
            return original(method, url, kwargs)

        self.session.handlers[GRAPHQL_ENDPOINT] = flaky
        with self.assertRaises(MySidelineTransportError):
            self.sync()
        self.assertUnchanged()

    def test_malformed_payload_changes_nothing(self):
        self.session.handlers[GRAPHQL_ENDPOINT] = lambda m, u, k: FakeResponse(
            text='{"data": {"competitionMatches": "nope"}}'
        )
        with self.assertRaises(MySidelineResponseError):
            self.sync()
        self.assertUnchanged()

    def test_database_error_rolls_back_whole_snapshot(self):
        # A write which fails part way through the snapshot must roll back
        # the rename of the first division, applied earlier in the same
        # transaction.
        self.remote.competition(100)["name"] = "Renamed"
        self.remote.competition(200)["name"] = "Taken"
        original = Division.save

        def save(division, *args, **kwargs):
            if division.mysideline_id == 200:
                raise IntegrityError("duplicate key value violates unique constraint")
            return original(division, *args, **kwargs)

        with mock.patch.object(Division, "save", save):
            with self.assertRaises(IntegrityError):
                self.sync()
        self.assertEqual(Division.objects.get(mysideline_id=100).title, "Mens Div 1")


class SelectionTests(SyncTestCase):
    def test_season_and_tag_filters(self):
        self.remote.add_competition(100, "Winter 2026", season=2026, season_tag=1)
        self.remote.add_competition(200, "Summer 2026/27", season=2026, season_tag=2)
        self.remote.add_competition(300, "Winter 2025", season=2025, season_tag=1)

        self.sync()
        self.assertEqual(
            set(self.season.divisions.values_list("mysideline_id", flat=True)),
            {100, 200},
        )

        self.season.mysideline_season_tag = 1
        self.season.save()
        self.sync()
        self.assertEqual(
            set(self.season.divisions.values_list("mysideline_id", flat=True)),
            {100},
        )

        self.season.mysideline_season = 2025
        self.season.save()
        self.sync()
        self.assertEqual(
            set(self.season.divisions.values_list("mysideline_id", flat=True)),
            {300},
        )

    def test_sibling_seasons_share_the_association(self):
        # Two seasons of the same competition mirror different MySideline
        # years without interfering with each other.
        self.remote.add_competition(100, "Open 2026", season=2026)
        self.remote.add_competition(300, "Open 2025", season=2025)
        earlier = factories.SeasonFactory.create(
            title="2025",
            competition=self.season.competition,
            timezone=SYDNEY,
            mysideline_season=2025,
        )
        self.sync()
        synchronise_season(earlier, self.mysideline)
        self.assertEqual(
            list(self.season.divisions.values_list("mysideline_id", flat=True)), [100]
        )
        self.assertEqual(
            list(earlier.divisions.values_list("mysideline_id", flat=True)), [300]
        )
        self.assertEqual(
            self.season.mysideline_url,
            "https://tfa.mysideline.com.au/competitions/association/6338?season=2026",
        )
        self.assertEqual(self.season.mysideline_enabled, True)

    def test_apply_snapshot_directly(self):
        result = apply_snapshot(
            self.season,
            [RemoteCompetition(id=1, name="Direct", teams=(), matches=())],
        )
        self.assertEqual(result.created, {"division": 1, "stage": 1})
        self.assertEqual(self.season.divisions.get(mysideline_id=1).title, "Direct")

    def test_season_without_year(self):
        self.season.mysideline_season = None
        with self.assertRaises(ValueError):
            self.sync()
        self.assertEqual(self.season.mysideline_enabled, False)

    def test_competition_without_url(self):
        self.season.competition.mysideline_url = None
        self.season.competition.save()
        self.assertEqual(self.season.mysideline_url, None)
        with self.assertRaises(ValueError):
            self.sync()


class InvocationTests(SyncTestCase):
    def test_synchronise_all_isolates_failures(self):
        self.remote.add_competition(100, "Mens Div 1")
        other = factories.SeasonFactory.create(
            competition__mysideline_url="https://tfa.mysideline.com.au/competitions/association/999",
            mysideline_season=2026,
            timezone=SYDNEY,
        )
        factories.SeasonFactory.create(
            competition=self.season.competition, mysideline_season=2026, enabled=False
        )
        factories.SeasonFactory.create(
            competition=self.season.competition, mysideline_season=2026, complete=True
        )
        factories.SeasonFactory.create(
            competition=self.season.competition, mysideline_season=None
        )
        factories.SeasonFactory.create(mysideline_season=2026)
        self.session.handlers[other.competition.mysideline_url] = (
            lambda m, u, k: FakeResponse(
                status_code=404, text="", content_type="text/html"
            )
        )

        results = synchronise_all(self.mysideline)
        self.assertEqual(list(results), [self.season.pk])
        self.assertEqual(results[self.season.pk].created, {"division": 1, "stage": 1})

    @mock.patch("tournamentcontrol.competition.tasks._mysideline_synchronise_season")
    def test_task(self, synchronise):
        from tournamentcontrol.competition.tasks import synchronise_mysideline_season

        synchronise.return_value = apply_snapshot(self.season, [])
        self.assertEqual(
            synchronise_mysideline_season.delay(self.season.pk).get(),
            {
                "created": {},
                "updated": {},
                "deleted": {},
                "detached": {},
                "warnings": [],
            },
        )
        synchronise.assert_called_once_with(self.season)

    @mock.patch(
        "tournamentcontrol.competition.management.commands.synchronise_mysideline.MySidelineClient"
    )
    def test_command(self, client_class):
        client_class.return_value = self.mysideline
        self.remote.add_competition(100, "Mens Div 1")
        stdout = StringIO()
        call_command("synchronise_mysideline", self.season.pk, stdout=stdout)
        self.assertEqual(
            stdout.getvalue(),
            "season %d: created: division=1, stage=1; updated: -; deleted: -; "
            "detached: -\n" % self.season.pk,
        )
        self.assertEqual(
            self.season.divisions.get(mysideline_id=100).title, "Mens Div 1"
        )

        with self.assertRaises(CommandError):
            call_command("synchronise_mysideline", self.season.pk + 1000)

        self.session.exception = requests.ConnectionError("boom")
        with self.assertRaises(CommandError):
            call_command("synchronise_mysideline", self.season.pk, stderr=StringIO())


class StateCupTests(TestCase):
    """
    Import the captured NSW State Cup 2025 -- a complete, pooled tournament
    with finals -- and check the hierarchy against what MySideline shows.
    """

    def setUp(self):
        super().setUp()
        self.season = factories.SeasonFactory.create(
            title="2025",
            timezone=SYDNEY,
            competition__title="NSW State Cup",
            competition__mysideline_url=STATE_CUP_URL,
            mysideline_season=STATE_CUP_SEASON,
        )
        self.client = MySidelineClient(session=state_cup_session())

    def test_import(self):
        result = synchronise_season(self.season, self.client)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.created["division"], 21)
        self.assertEqual(Team.objects.count(), 242)
        self.assertEqual(Match.objects.count(), 959)

        mens_open_b = self.season.divisions.get(mysideline_id=65396604)
        self.assertEqual(mens_open_b.title, "2025 SC Men's Open B")
        self.assertEqual(mens_open_b.teams.count(), 31)
        regular = mens_open_b.stages.get(title=REGULAR_STAGE_TITLE)
        self.assertEqual(
            list(regular.pools.values_list("title", flat=True)),
            ["Pool C", "Pool A", "Pool D", "Pool B"],
        )
        finals = mens_open_b.stages.get(title=FINALS_STAGE_TITLE)
        self.assertEqual(finals.matches.count(), 21)
        self.assertEqual(finals.keep_ladder, False)
        self.assertEqual(finals.ladder_summary.count(), 0)
        self.assertEqual(finals.matches.filter(label="Bowl Grand Final").count(), 1)

        # Byes reported with a capitalised status are still processed.
        self.assertEqual(
            Match.objects.filter(is_bye=True, bye_processed=True).count(),
            Match.objects.filter(is_bye=True).count(),
        )
        self.assertEqual(Match.objects.filter(is_forfeit=True).count(), 3)

        # Ladder for Men's Open A pool A matches MySideline's own ladder
        # (Events Ladder - NSWTA: 4 for a win, 2 for a draw, 0 for a loss).
        mens_open_a = self.season.divisions.get(mysideline_id=65396575)
        self.assertEqual(mens_open_a.points_formula, "4*win + 2*draw + 4*forfeit_for")
        ladder = LadderSummary.objects.filter(
            stage__division=mens_open_a, stage_group__title="Pool A"
        ).order_by("-points", "-difference")
        self.assertEqual(
            [
                (
                    row.team.title,
                    row.played,
                    row.win,
                    int(row.points),
                    int(row.difference),
                )
                for row in ladder
            ],
            [
                ("2025 SC Doyalson MOA", 5, 5, 20, 13),
                ("2025 SC Parramatta MOA", 5, 4, 16, 10),
                ("2025 SC Central Coast MOA", 5, 3, 12, 6),
                ("2025 SC Wests MOA", 5, 2, 8, 1),
                ("2025 SC Penrith MOA", 5, 1, 4, -16),
                ("2025 SC Hills MOA", 5, 0, 0, -14),
            ],
        )

        # "Men's 55s" and "Mens 55s" slugify identically.
        self.assertEqual(
            list(
                self.season.divisions.filter(title__contains="55s")
                .order_by("order")
                .values_list("title", "slug")
            ),
            [
                ("2025 SC Men's 55s", "2025-sc-mens-55s"),
                ("2025 SC Mens 55s", "2025-sc-mens-55s-2"),
            ],
        )

        result = synchronise_season(self.season, self.client)
        self.assertEqual(result.created, {})
        self.assertEqual(result.updated, {})
        self.assertEqual(result.deleted, {})


class AdminTests(TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.season = factories.SeasonFactory.create(
            competition__mysideline_url=ASSOCIATION_URL, mysideline_season=2025
        )
        self.args = (self.season.competition_id, self.season.pk)

    def test_login_required(self):
        self.assertLoginRequired(
            "admin:fixja:competition:season:mysideline-sync", *self.args
        )

    def test_forms_show_mysideline_fields(self):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:edit",
                self.season.competition_id,
                test_query_count=60,
            )
            self.assertResponseContains('name="mysideline_url"', html=False)
            self.assertGoodView(
                "admin:fixja:competition:season:edit", *self.args, test_query_count=60
            )
            self.assertResponseContains('name="mysideline_season"', html=False)
            self.assertResponseContains('name="mysideline_season_tag"', html=False)

    def test_season_list_shows_button(self):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:edit",
                self.season.competition_id,
                test_query_count=60,
            )
            self.assertResponseContains(
                self.reverse(
                    "admin:fixja:competition:season:mysideline-sync", *self.args
                ),
                html=False,
            )

    @mock.patch("tournamentcontrol.competition.admin.synchronise_mysideline_season")
    def test_sync_view(self, task):
        with self.login(self.superuser):
            self.assertGoodView(
                "admin:fixja:competition:season:mysideline-sync", *self.args
            )
            self.assertResponseContains("Synchronise now", html=False)
            self.post("admin:fixja:competition:season:mysideline-sync", *self.args)
            self.response_302()
        task.delay.assert_called_once_with(self.season.pk)

    def test_sync_view_requires_link(self):
        self.season.mysideline_season = None
        self.season.save()
        with self.login(self.superuser):
            self.get("admin:fixja:competition:season:mysideline-sync", *self.args)
            self.response_404()

    def test_competition_form_validation(self):
        from tournamentcontrol.competition.forms import CompetitionForm

        competition = self.season.competition
        data = {
            "title": competition.title,
            "slug": competition.slug,
            "enabled": True,
            "mysideline_url": (
                "https://tfa.mysideline.com.au/competitions/association/6338/"
                "?season=2025&seasonTag=2"
            ),
        }
        form = CompetitionForm(data=data, instance=competition, user=self.superuser)
        self.assertEqual(form.errors.get("mysideline_url"), None)
        self.assertEqual(form.cleaned_data["mysideline_url"], ASSOCIATION_URL)

        form = CompetitionForm(
            data=dict(
                data,
                mysideline_url="https://tfa.mysideline.com.au/competitions/69295321",
            ),
            instance=competition,
            user=self.superuser,
        )
        self.assertEqual(
            form.errors["mysideline_url"],
            [
                "Enter the MySideline association URL, for example "
                "https://tfa.mysideline.com.au/competitions/association/6338"
            ],
        )

        form = CompetitionForm(
            data=dict(
                data, mysideline_url="https://example.com/competitions/association/6338"
            ),
            instance=competition,
            user=self.superuser,
        )
        self.assertEqual(len(form.errors["mysideline_url"]), 1)

    def test_season_form_validation(self):
        from tournamentcontrol.competition.forms import SeasonForm

        data = {
            "title": self.season.title,
            "slug": self.season.slug,
            "mode": self.season.mode,
            "live_stream_privacy": "public",
            "mysideline_season": 2025,
            "mysideline_season_tag": 2,
        }
        form = SeasonForm(data=data, instance=self.season, user=self.superuser)
        self.assertEqual(form.errors, {})

        self.season.competition.mysideline_url = None
        self.season.competition.save()
        form = SeasonForm(data=data, instance=self.season, user=self.superuser)
        self.assertEqual(
            form.errors["mysideline_season"],
            ["Set the MySideline URL on the competition first."],
        )
        form = SeasonForm(
            data=dict(data, mysideline_season="", mysideline_season_tag=""),
            instance=self.season,
            user=self.superuser,
        )
        self.assertEqual(form.errors, {})
