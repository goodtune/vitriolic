"""
Tests for the competition management MCP tools.

The tools are exercised two ways: directly on the toolset with a fake
request (the toolset only needs the request's ``user``) and end-to-end over
the Streamable HTTP endpoint using JSON-RPC, which is how an MCP client
talks to the server.
"""

import datetime
import json
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.utils import override_settings
from django.utils import timezone
from freezegun import freeze_time
from test_plus import TestCase

from tournamentcontrol.competition import mcp
from tournamentcontrol.competition.mcp.admin import get_admin_server
from tournamentcontrol.competition.mcp.signals import mcp_request_handled
from tournamentcontrol.competition.mcp.views import MCPView
from tournamentcontrol.competition.tests import factories

TZ = ZoneInfo("Europe/Amsterdam")
NOW = "2026-07-15 12:00:00"

# The server derives each tool's schema from its type hints with pydantic,
# which recognises ``datetime.date`` by identity, and freezegun replaces
# that class while time is frozen. Build the server before any test does.
mcp.get_server()

TOOL_NAMES = {
    "upcoming_events",
    "recent_events",
    "search",
    "get_season",
    "list_teams",
    "get_team",
    "list_matches",
    "count_matches",
    "get_match",
    "get_ladder",
    "whoami",
}


def _match(stage, home, away, date, time, **kwargs):
    """Create a match at a local ``date`` and ``time`` in the season zone."""
    if time is None:
        aware = None
    else:
        aware = timezone.make_aware(datetime.datetime.combine(date, time), TZ)
    return factories.MatchFactory.create(
        stage=stage,
        home_team=home,
        away_team=away,
        date=date,
        time=time,
        datetime=aware,
        **kwargs,
    )


class MCPFixtureMixin:
    """
    A small international tournament frozen mid-event, plus a finished
    event, a future event, a draft division and a disabled competition.
    """

    @classmethod
    def setUpTestData(cls):
        cls.australia = factories.ClubFactory.create(
            title="Australia", abbreviation="AUS"
        )
        cls.new_zealand = factories.ClubFactory.create(
            title="New Zealand", abbreviation="NZL"
        )
        cls.england = factories.ClubFactory.create(title="England", abbreviation="ENG")
        cls.france = factories.ClubFactory.create(title="France", abbreviation="FRA")

        cls.competition = factories.CompetitionFactory.create(
            title="European Championships", short_title="Euros"
        )
        cls.season = factories.SeasonFactory.create(
            competition=cls.competition,
            title="2026",
            hashtag="#Euros2026",
            timezone=TZ,
            live_stream=True,
        )
        cls.venue = factories.VenueFactory.create(
            season=cls.season, title="Nottingham", latlng="52.95,-1.15,12"
        )
        cls.field1 = factories.GroundFactory.create(venue=cls.venue, title="Field 1")
        cls.field2 = factories.GroundFactory.create(venue=cls.venue, title="Field 2")

        cls.mens = factories.DivisionFactory.create(
            season=cls.season, title="Men's Open", order=1
        )
        cls.womens = factories.DivisionFactory.create(
            season=cls.season, title="Women's Open", order=2
        )
        cls.mixed = factories.DivisionFactory.create(
            season=cls.season, title="Mixed Open", order=3, draft=True
        )

        cls.mens_pools = factories.StageFactory.create(
            division=cls.mens, title="Pool Stage", order=1
        )
        cls.mens_finals = factories.StageFactory.create(
            division=cls.mens, title="Finals", order=2, keep_ladder=False
        )
        cls.pool_a = factories.StageGroupFactory.create(
            stage=cls.mens_pools, title="Pool A", order=1
        )
        cls.pool_b = factories.StageGroupFactory.create(
            stage=cls.mens_pools, title="Pool B", order=2
        )
        cls.womens_stage = factories.StageFactory.create(
            division=cls.womens, title="Round Robin", order=1
        )
        cls.mixed_stage = factories.StageFactory.create(
            division=cls.mixed, title="Round Robin", order=1
        )

        cls.aus_men = factories.TeamFactory.create(
            club=cls.australia,
            division=cls.mens,
            title="Australia",
            stage_group=cls.pool_a,
        )
        cls.nzl_men = factories.TeamFactory.create(
            club=cls.new_zealand,
            division=cls.mens,
            title="New Zealand",
            stage_group=cls.pool_a,
        )
        cls.eng_men = factories.TeamFactory.create(
            club=cls.england, division=cls.mens, title="England", stage_group=cls.pool_b
        )
        cls.fra_men = factories.TeamFactory.create(
            club=cls.france, division=cls.mens, title="France", stage_group=cls.pool_b
        )
        cls.aus_women = factories.TeamFactory.create(
            club=cls.australia, division=cls.womens, title="Australia"
        )
        cls.nzl_women = factories.TeamFactory.create(
            club=cls.new_zealand, division=cls.womens, title="New Zealand"
        )
        cls.aus_mixed = factories.TeamFactory.create(
            club=cls.australia, division=cls.mixed, title="Australia"
        )
        cls.eng_mixed = factories.TeamFactory.create(
            club=cls.england, division=cls.mixed, title="England"
        )

        cls.aus_v_nzl = _match(
            cls.mens_pools,
            cls.aus_men,
            cls.nzl_men,
            datetime.date(2026, 7, 14),
            datetime.time(10, 0),
            stage_group=cls.pool_a,
            round=1,
            play_at=cls.field1,
            home_team_score=8,
            away_team_score=6,
            live_stream=True,
            external_identifier="ytAUSNZL",
        )
        cls.eng_v_fra = _match(
            cls.mens_pools,
            cls.eng_men,
            cls.fra_men,
            datetime.date(2026, 7, 14),
            datetime.time(11, 0),
            stage_group=cls.pool_b,
            round=1,
            play_at=cls.field2,
            home_team_score=5,
            away_team_score=5,
            videos=["https://youtu.be/engfra"],
        )
        cls.aus_v_eng = _match(
            cls.mens_pools,
            cls.aus_men,
            cls.eng_men,
            datetime.date(2026, 7, 16),
            datetime.time(15, 0),
            round=2,
            label="Semi Final 1",
            play_at=cls.field1,
            live_stream=True,
        )
        cls.aus_v_nzl_women = _match(
            cls.womens_stage,
            cls.aus_women,
            cls.nzl_women,
            datetime.date(2026, 7, 16),
            datetime.time(16, 30),
            round=1,
            play_at=cls.field2,
            live_stream=True,
        )
        cls.nzl_v_aus_women = _match(
            cls.womens_stage,
            cls.nzl_women,
            cls.aus_women,
            datetime.date(2026, 7, 18),
            datetime.time(9, 0),
            round=2,
            play_at=cls.venue,
        )
        cls.final = _match(
            cls.mens_finals,
            None,
            None,
            datetime.date(2026, 7, 19),
            datetime.time(14, 0),
            round=1,
            label="Final",
            play_at=cls.field1,
            home_team_eval="W",
            home_team_eval_related=cls.aus_v_eng,
            away_team_eval="L",
            away_team_eval_related=cls.aus_v_eng,
            live_stream=True,
        )
        cls.bye = _match(
            cls.mens_pools,
            cls.aus_men,
            None,
            datetime.date(2026, 7, 15),
            None,
            stage_group=cls.pool_a,
            round=2,
            is_bye=True,
        )
        cls.mixed_match = _match(
            cls.mixed_stage,
            cls.aus_mixed,
            cls.eng_mixed,
            datetime.date(2026, 7, 17),
            datetime.time(12, 0),
            round=1,
            play_at=cls.field1,
        )

        # Ladder summaries are computed by signals from the recorded results.

        # A finished event last month.
        cls.nationals = factories.CompetitionFactory.create(title="Nationals")
        cls.nationals_2026 = factories.SeasonFactory.create(
            competition=cls.nationals, title="2026", timezone=TZ
        )
        nationals_division = factories.DivisionFactory.create(
            season=cls.nationals_2026, title="Open"
        )
        nationals_stage = factories.StageFactory.create(division=nationals_division)
        _match(
            nationals_stage,
            factories.TeamFactory.create(club=cls.england, division=nationals_division),
            factories.TeamFactory.create(club=cls.france, division=nationals_division),
            datetime.date(2026, 6, 20),
            datetime.time(10, 0),
            home_team_score=3,
            away_team_score=1,
        )

        # A future event next year.
        cls.world_cup = factories.CompetitionFactory.create(title="World Cup")
        cls.world_cup_2027 = factories.SeasonFactory.create(
            competition=cls.world_cup, title="2027", timezone=TZ
        )
        world_cup_division = factories.DivisionFactory.create(
            season=cls.world_cup_2027, title="Men's Open"
        )
        _match(
            factories.StageFactory.create(division=world_cup_division),
            factories.TeamFactory.create(
                club=cls.australia, division=world_cup_division, title="Australia"
            ),
            factories.TeamFactory.create(
                club=cls.new_zealand, division=world_cup_division, title="New Zealand"
            ),
            datetime.date(2027, 1, 10),
            datetime.time(10, 0),
        )

        # A disabled competition is never visible.
        disabled = factories.CompetitionFactory.create(
            title="Old Series", enabled=False
        )
        disabled_season = factories.SeasonFactory.create(
            competition=disabled, title="2026", timezone=TZ
        )
        disabled_division = factories.DivisionFactory.create(season=disabled_season)
        _match(
            factories.StageFactory.create(division=disabled_division),
            factories.TeamFactory.create(
                club=cls.australia, division=disabled_division
            ),
            factories.TeamFactory.create(club=cls.england, division=disabled_division),
            datetime.date(2026, 7, 16),
            datetime.time(10, 0),
        )

        cls.user = factories.UserFactory.create(first_name="Gary", last_name="Reynolds")
        cls.person = factories.PersonFactory.create(user=cls.user, club=cls.australia)
        factories.TeamAssociationFactory.create(team=cls.aus_men, person=cls.person)
        cls.superuser = factories.SuperUserFactory.create()

    def toolset(self, user=None):
        request = SimpleNamespace(user=user or AnonymousUser())
        return mcp.CompetitionToolset(request=request)


@freeze_time(NOW)
class NarrowingToolTests(MCPFixtureMixin, TestCase):
    def test_upcoming_events_in_progress(self):
        res = self.toolset().upcoming_events()
        self.assertEqual(res["today"], "2026-07-15")
        self.assertEqual(
            res["events"],
            [
                {
                    "season": {"id": self.season.pk, "title": "2026", "slug": "2026"},
                    "competition": {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": "european-championships",
                    },
                    "title": "European Championships 2026",
                    "status": "in_progress",
                    "first_match_date": "2026-07-14",
                    "last_match_date": "2026-07-19",
                    "days_until_start": -1,
                    "hashtag": "#Euros2026",
                    "timezone": "Europe/Amsterdam",
                    "live_stream": True,
                    "division_count": 2,
                    "match_count": 7,
                }
            ],
        )

    def test_upcoming_events_window(self):
        res = self.toolset().upcoming_events(days=365)
        self.assertEqual(
            [(e["title"], e["status"], e["days_until_start"]) for e in res["events"]],
            [
                ("European Championships 2026", "in_progress", -1),
                ("World Cup 2027", "upcoming", 179),
            ],
        )

    def test_upcoming_events_superuser_sees_draft_divisions(self):
        res = self.toolset(self.superuser).upcoming_events()
        self.assertEqual(res["events"][0]["division_count"], 3)
        self.assertEqual(res["events"][0]["match_count"], 8)

    def test_recent_events(self):
        res = self.toolset().recent_events()
        self.assertEqual(
            [(e["title"], e["status"], e["last_match_date"]) for e in res["events"]],
            [
                ("European Championships 2026", "in_progress", "2026-07-19"),
                ("Nationals 2026", "finished", "2026-06-20"),
            ],
        )

    def test_recent_events_window(self):
        res = self.toolset().recent_events(days=7)
        self.assertEqual(
            [e["title"] for e in res["events"]], ["European Championships 2026"]
        )

    def test_search_club_and_teams(self):
        res = self.toolset().search("Australia")
        self.assertEqual(res["query"], "Australia")
        self.assertEqual(
            res["clubs"],
            [
                {
                    "club": {
                        "id": self.australia.pk,
                        "title": "Australia",
                        "slug": "australia",
                    },
                    "abbreviation": "AUS",
                }
            ],
        )
        self.assertEqual(
            [
                (t["team"]["id"], t["division"]["title"], t["competition"]["title"])
                for t in res["teams"]
            ],
            [
                (self.aus_men.pk, "Men's Open", "European Championships"),
                (self.aus_women.pk, "Women's Open", "European Championships"),
                (
                    self.world_cup_2027.divisions.get().teams.get(title="Australia").pk,
                    "Men's Open",
                    "World Cup",
                ),
            ],
        )
        self.assertEqual(res["competitions"], [])
        self.assertEqual(res["seasons"], [])
        self.assertEqual(res["divisions"], [])
        self.assertEqual(res["venues"], [])

    def test_search_multiple_words_narrow(self):
        res = self.toolset().search("Australia Women's")
        self.assertEqual([t["team"]["id"] for t in res["teams"]], [self.aus_women.pk])

    def test_search_season_by_hashtag_and_competition(self):
        for query in ("Euros2026", "European 2026", "euros"):
            res = self.toolset().search(query)
            self.assertEqual(
                res["seasons"],
                [
                    {
                        "season": {
                            "id": self.season.pk,
                            "title": "2026",
                            "slug": "2026",
                        },
                        "competition": {
                            "id": self.competition.pk,
                            "title": "European Championships",
                            "slug": "european-championships",
                        },
                        "title": "European Championships 2026",
                        "hashtag": "#Euros2026",
                    }
                ],
                query,
            )

    def test_search_division_and_venue(self):
        res = self.toolset().search("Women's")
        self.assertEqual(
            [d["division"]["id"] for d in res["divisions"]], [self.womens.pk]
        )
        res = self.toolset().search("Nottingham")
        self.assertEqual(
            res["venues"],
            [
                {
                    "venue": {"id": self.venue.pk, "title": "Nottingham"},
                    "season": {"id": self.season.pk, "title": "2026", "slug": "2026"},
                    "competition": {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": "european-championships",
                    },
                    "timezone": "Europe/Amsterdam",
                }
            ],
        )

    def test_search_hides_draft_divisions_from_anonymous(self):
        res = self.toolset().search("Mixed")
        self.assertEqual(res["divisions"], [])
        self.assertEqual(res["teams"], [])
        res = self.toolset(self.superuser).search("Mixed")
        self.assertEqual(
            [d["division"]["id"] for d in res["divisions"]], [self.mixed.pk]
        )
        self.assertEqual(
            [t["team"]["id"] for t in res["teams"]],
            [self.aus_mixed.pk, self.eng_mixed.pk],
        )

    def test_search_requires_words(self):
        self.assertEqual(
            self.toolset().search("  "),
            {"error": "Provide one or more words to search for."},
        )


@freeze_time(NOW)
class StructureToolTests(MCPFixtureMixin, TestCase):
    def test_get_season(self):
        res = self.toolset().get_season(self.season.pk)
        self.assertEqual(res["title"], "European Championships 2026")
        self.assertEqual(res["hashtag"], "#Euros2026")
        self.assertEqual(res["timezone"], "Europe/Amsterdam")
        self.assertEqual(res["first_match_date"], "2026-07-14")
        self.assertEqual(res["last_match_date"], "2026-07-19")
        self.assertEqual(res["live_stream"], True)
        self.assertEqual(
            res["matches"],
            {"total": 7, "completed": 2, "upcoming": 5, "live_streamed": 4},
        )
        self.assertEqual(
            res["divisions"],
            [
                {
                    "id": self.mens.pk,
                    "title": "Men's Open",
                    "slug": "mens-open",
                    "draft": False,
                    "team_count": 4,
                    "stages": [
                        {
                            "id": self.mens_pools.pk,
                            "title": "Pool Stage",
                            "order": 1,
                            "keep_ladder": True,
                            "pools": [
                                {
                                    "id": self.pool_a.pk,
                                    "title": "Pool A",
                                    "slug": "pool-a",
                                },
                                {
                                    "id": self.pool_b.pk,
                                    "title": "Pool B",
                                    "slug": "pool-b",
                                },
                            ],
                        },
                        {
                            "id": self.mens_finals.pk,
                            "title": "Finals",
                            "order": 2,
                            "keep_ladder": False,
                            "pools": [],
                        },
                    ],
                },
                {
                    "id": self.womens.pk,
                    "title": "Women's Open",
                    "slug": "womens-open",
                    "draft": False,
                    "team_count": 2,
                    "stages": [
                        {
                            "id": self.womens_stage.pk,
                            "title": "Round Robin",
                            "order": 1,
                            "keep_ladder": True,
                            "pools": [],
                        }
                    ],
                },
            ],
        )
        self.assertEqual(
            res["venues"],
            [
                {
                    "id": self.venue.pk,
                    "title": "Nottingham",
                    "timezone": "Europe/Amsterdam",
                    "grounds": [
                        {"id": self.field1.pk, "title": "Field 1", "slug": "field-1"},
                        {"id": self.field2.pk, "title": "Field 2", "slug": "field-2"},
                    ],
                }
            ],
        )

    def test_get_season_superuser_sees_draft(self):
        res = self.toolset(self.superuser).get_season(self.season.pk)
        self.assertEqual(
            [d["title"] for d in res["divisions"]],
            ["Men's Open", "Women's Open", "Mixed Open"],
        )
        self.assertEqual(res["matches"]["total"], 8)

    def test_get_season_not_found(self):
        self.assertEqual(
            self.toolset().get_season(0), {"error": "Season 0 was not found."}
        )

    def test_list_teams_by_season(self):
        res = self.toolset().list_teams(season_id=self.season.pk)
        self.assertEqual(res["total"], 6)
        self.assertEqual(
            [(t["team"]["title"], t["division"]["title"]) for t in res["teams"]],
            [
                ("Australia", "Men's Open"),
                ("New Zealand", "Men's Open"),
                ("England", "Men's Open"),
                ("France", "Men's Open"),
                ("Australia", "Women's Open"),
                ("New Zealand", "Women's Open"),
            ],
        )

    def test_list_teams_by_query_and_club(self):
        res = self.toolset().list_teams(
            season_id=self.season.pk, query="Australia Women"
        )
        self.assertEqual([t["team"]["id"] for t in res["teams"]], [self.aus_women.pk])
        res = self.toolset().list_teams(club_id=self.new_zealand.pk)
        self.assertEqual(res["total"], 3)

    def test_list_teams_requires_filter(self):
        self.assertEqual(
            self.toolset().list_teams(),
            {
                "error": "Provide at least one of season_id, division_id, club_id or query."
            },
        )

    def test_get_team(self):
        res = self.toolset().get_team(self.aus_men.pk)
        self.assertEqual(
            res["team"],
            {
                "id": self.aus_men.pk,
                "title": "Australia",
                "slug": "australia",
                "club": {
                    "id": self.australia.pk,
                    "title": "Australia",
                    "slug": "australia",
                },
            },
        )
        self.assertEqual(
            res["pool"], {"id": self.pool_a.pk, "title": "Pool A", "slug": "pool-a"}
        )
        self.assertEqual(res["season"]["id"], self.season.pk)
        # The bye "today" is skipped; the next real match is the semi final.
        self.assertEqual(res["next_match"]["id"], self.aus_v_eng.pk)
        self.assertEqual(res["next_match"]["datetime"], "2026-07-16T15:00:00+02:00")
        self.assertEqual(res["last_match"]["id"], self.aus_v_nzl.pk)
        self.assertEqual(
            res["ladders"],
            [
                {
                    "stage": {
                        "id": self.mens_pools.pk,
                        "title": "Pool Stage",
                        "slug": "pool-stage",
                    },
                    "pool": {"id": self.pool_a.pk, "title": "Pool A", "slug": "pool-a"},
                    "position": 1,
                    "teams": 2,
                    "played": 1,
                    "win": 1,
                    "loss": 0,
                    "draw": 0,
                    "points": 3.0,
                }
            ],
        )

    def test_get_team_without_matches(self):
        res = self.toolset().get_team(self.fra_men.pk)
        self.assertEqual(res["next_match"], None)
        self.assertEqual(res["last_match"]["id"], self.eng_v_fra.pk)
        self.assertEqual(res["ladders"][0]["position"], 2)

    def test_get_team_draft_hidden(self):
        self.assertEqual(
            self.toolset().get_team(self.aus_mixed.pk),
            {"error": f"Team {self.aus_mixed.pk} was not found."},
        )
        self.assertEqual(
            self.toolset(self.superuser).get_team(self.aus_mixed.pk)["team"]["id"],
            self.aus_mixed.pk,
        )


@freeze_time(NOW)
class MatchToolTests(MCPFixtureMixin, TestCase):
    def test_match_summary(self):
        res = self.toolset().list_matches(
            club_id=self.australia.pk,
            opponent_club_id=self.new_zealand.pk,
            status="completed",
        )
        self.assertEqual(res["total"], 1)
        self.assertEqual(
            res["matches"][0],
            {
                "id": self.aus_v_nzl.pk,
                "uuid": str(self.aus_v_nzl.uuid),
                "competition": {
                    "id": self.competition.pk,
                    "title": "European Championships",
                    "slug": "european-championships",
                },
                "season": {"id": self.season.pk, "title": "2026", "slug": "2026"},
                "division": {
                    "id": self.mens.pk,
                    "title": "Men's Open",
                    "slug": "mens-open",
                },
                "stage": {
                    "id": self.mens_pools.pk,
                    "title": "Pool Stage",
                    "slug": "pool-stage",
                },
                "pool": {"id": self.pool_a.pk, "title": "Pool A", "slug": "pool-a"},
                "round": 1,
                "label": None,
                "datetime": "2026-07-14T10:00:00+02:00",
                "date": "2026-07-14",
                "time": "10:00",
                "timezone": "Europe/Amsterdam",
                "home_team": {
                    "id": self.aus_men.pk,
                    "title": "Australia",
                    "slug": "australia",
                    "club": {
                        "id": self.australia.pk,
                        "title": "Australia",
                        "slug": "australia",
                    },
                },
                "away_team": {
                    "id": self.nzl_men.pk,
                    "title": "New Zealand",
                    "slug": "new-zealand",
                    "club": {
                        "id": self.new_zealand.pk,
                        "title": "New Zealand",
                        "slug": "new-zealand",
                    },
                },
                "home_team_score": 8,
                "away_team_score": 6,
                "status": "completed",
                "winner": {
                    "id": self.aus_men.pk,
                    "title": "Australia",
                    "slug": "australia",
                    "club": {
                        "id": self.australia.pk,
                        "title": "Australia",
                        "slug": "australia",
                    },
                },
                "is_draw": False,
                "live_stream": True,
                "live_stream_url": "https://youtu.be/ytAUSNZL",
                "videos": [],
                "venue": {"id": self.venue.pk, "title": "Nottingham"},
                "ground": {"id": self.field1.pk, "title": "Field 1"},
            },
        )

    def test_draw_and_videos(self):
        res = self.toolset().get_match(self.eng_v_fra.pk)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["winner"], None)
        self.assertEqual(res["is_draw"], True)
        self.assertEqual(res["live_stream_url"], None)
        self.assertEqual(res["videos"], ["https://youtu.be/engfra"])

    def test_undecided_teams(self):
        res = self.toolset().get_match(self.final.pk)
        self.assertEqual(
            res["home_team"],
            {
                "id": None,
                "title": "Winner Semi Final 1",
                "slug": None,
                "club": None,
                "eval": "W",
                "eval_related_id": self.final.home_team_eval_related_id,
            },
        )
        self.assertEqual(
            res["away_team"],
            {
                "id": None,
                "title": "Loser Semi Final 1",
                "slug": None,
                "club": None,
                "eval": "L",
                "eval_related_id": self.final.away_team_eval_related_id,
            },
        )
        self.assertEqual(res["status"], "upcoming")
        self.assertEqual(res["label"], "Final")

    def test_bye(self):
        res = self.toolset().get_match(self.bye.pk)
        self.assertEqual(res["status"], "bye")
        self.assertEqual(res["is_bye"], True)
        self.assertEqual(res["datetime"], None)
        self.assertEqual(res["date"], "2026-07-15")
        self.assertEqual(res["time"], None)
        self.assertEqual(
            res["away_team"], {"id": None, "title": "Bye", "slug": None, "club": None}
        )
        self.assertEqual(res["venue"], None)
        self.assertEqual(res["ground"], None)

    def test_get_match_at_venue(self):
        res = self.toolset().get_match(self.nzl_v_aus_women.pk)
        self.assertEqual(res["venue"], {"id": self.venue.pk, "title": "Nottingham"})
        self.assertEqual(res["ground"], None)
        self.assertEqual(res["latitude"], 52.95)
        self.assertEqual(res["longitude"], -1.15)
        self.assertEqual(res["timezone"], "Europe/Amsterdam")
        self.assertEqual(res["is_forfeit"], False)
        self.assertEqual(res["is_washout"], False)

    def test_get_match_not_found(self):
        self.assertEqual(
            self.toolset().get_match(0), {"error": "Match 0 was not found."}
        )
        self.assertEqual(
            self.toolset().get_match(self.mixed_match.pk),
            {"error": f"Match {self.mixed_match.pk} was not found."},
        )
        self.assertEqual(
            self.toolset(self.superuser).get_match(self.mixed_match.pk)["id"],
            self.mixed_match.pk,
        )

    def test_list_matches_club_versus_club(self):
        res = self.toolset().list_matches(
            club_id=self.australia.pk, opponent_club_id=self.new_zealand.pk
        )
        # The World Cup fixture next year is included; the disabled
        # competition's fixture is not.
        self.assertEqual(res["total"], 4)
        self.assertEqual(
            [(m["id"], m["datetime"]) for m in res["matches"]],
            [
                (self.aus_v_nzl.pk, "2026-07-14T10:00:00+02:00"),
                (self.aus_v_nzl_women.pk, "2026-07-16T16:30:00+02:00"),
                (self.nzl_v_aus_women.pk, "2026-07-18T09:00:00+02:00"),
                (self.world_cup_2027.matches.get().pk, "2027-01-10T10:00:00+01:00"),
            ],
        )

    def test_list_matches_team_versus_team(self):
        res = self.toolset().list_matches(
            team_id=self.aus_women.pk,
            opponent_team_id=self.nzl_women.pk,
            status="upcoming",
        )
        self.assertEqual(
            [m["id"] for m in res["matches"]],
            [self.aus_v_nzl_women.pk, self.nzl_v_aus_women.pk],
        )

    def test_list_matches_opponent_only(self):
        res = self.toolset().list_matches(opponent_team_id=self.fra_men.pk)
        self.assertEqual([m["id"] for m in res["matches"]], [self.eng_v_fra.pk])

    def test_list_matches_status_and_order(self):
        res = self.toolset().list_matches(
            season_id=self.season.pk, status="completed", order="desc"
        )
        self.assertEqual(
            [m["id"] for m in res["matches"]], [self.eng_v_fra.pk, self.aus_v_nzl.pk]
        )
        res = self.toolset().list_matches(season_id=self.season.pk, status="upcoming")
        self.assertEqual(
            [m["id"] for m in res["matches"]],
            [
                self.aus_v_eng.pk,
                self.aus_v_nzl_women.pk,
                self.nzl_v_aus_women.pk,
                self.final.pk,
                self.bye.pk,
            ],
        )
        res = self.toolset().list_matches(season_id=self.season.pk, status="past")
        self.assertEqual(
            [m["id"] for m in res["matches"]], [self.aus_v_nzl.pk, self.eng_v_fra.pk]
        )

    def test_list_matches_exclude_byes(self):
        res = self.toolset().list_matches(team_id=self.aus_men.pk, include_byes=False)
        self.assertEqual(
            [m["id"] for m in res["matches"]], [self.aus_v_nzl.pk, self.aus_v_eng.pk]
        )

    def test_list_matches_live_stream_and_division(self):
        res = self.toolset().list_matches(
            season_id=self.season.pk, live_stream_only=True
        )
        self.assertEqual(
            [m["id"] for m in res["matches"]],
            [
                self.aus_v_nzl.pk,
                self.aus_v_eng.pk,
                self.aus_v_nzl_women.pk,
                self.final.pk,
            ],
        )
        res = self.toolset().list_matches(
            division_id=self.womens.pk, live_stream_only=True
        )
        self.assertEqual([m["id"] for m in res["matches"]], [self.aus_v_nzl_women.pk])

    def test_list_matches_stage_venue_and_dates(self):
        res = self.toolset().list_matches(stage_id=self.mens_finals.pk)
        self.assertEqual([m["id"] for m in res["matches"]], [self.final.pk])
        res = self.toolset().list_matches(venue_id=self.venue.pk)
        self.assertEqual(res["total"], 6)
        res = self.toolset().list_matches(
            competition_id=self.competition.pk,
            date_from=datetime.date(2026, 7, 16),
            date_to=datetime.date(2026, 7, 16),
        )
        self.assertEqual(
            [m["id"] for m in res["matches"]],
            [self.aus_v_eng.pk, self.aus_v_nzl_women.pk],
        )

    def test_list_matches_pagination(self):
        res = self.toolset().list_matches(season_id=self.season.pk, limit=2, offset=1)
        self.assertEqual(res["total"], 7)
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["offset"], 1)
        self.assertEqual(res["limit"], 2)
        self.assertEqual(
            [m["id"] for m in res["matches"]], [self.eng_v_fra.pk, self.aus_v_eng.pk]
        )
        res = self.toolset().list_matches(season_id=self.season.pk, limit=10000)
        self.assertEqual(res["limit"], mcp.MAX_LIMIT)

    def test_list_matches_draft_visibility(self):
        res = self.toolset().list_matches(division_id=self.mixed.pk)
        self.assertEqual(res["total"], 0)
        res = self.toolset(self.superuser).list_matches(division_id=self.mixed.pk)
        self.assertEqual([m["id"] for m in res["matches"]], [self.mixed_match.pk])

    def test_count_matches_total(self):
        self.assertEqual(
            self.toolset().count_matches(season_id=self.season.pk),
            {
                "count": 7,
                "completed": 2,
                "live_streamed": 4,
                "group_by": None,
                "groups": [],
            },
        )

    def test_count_matches_by_division(self):
        res = self.toolset().count_matches(
            season_id=self.season.pk, group_by="division"
        )
        self.assertEqual(
            res["groups"],
            [
                {
                    "id": self.mens.pk,
                    "title": "Men's Open",
                    "count": 5,
                    "completed": 2,
                    "live_streamed": 3,
                },
                {
                    "id": self.womens.pk,
                    "title": "Women's Open",
                    "count": 2,
                    "completed": 0,
                    "live_streamed": 1,
                },
            ],
        )
        res = self.toolset().count_matches(
            season_id=self.season.pk, group_by="division", live_stream_only=True
        )
        self.assertEqual(
            [(g["title"], g["count"]) for g in res["groups"]],
            [("Men's Open", 3), ("Women's Open", 1)],
        )

    def test_count_matches_by_pool_stage_and_season(self):
        res = self.toolset().count_matches(division_id=self.mens.pk, group_by="pool")
        self.assertEqual(
            [(g["id"], g["title"], g["count"]) for g in res["groups"]],
            [
                (self.pool_a.pk, "Pool A", 2),
                (self.pool_b.pk, "Pool B", 1),
                (None, None, 2),
            ],
        )
        res = self.toolset().count_matches(division_id=self.mens.pk, group_by="stage")
        self.assertEqual(
            [(g["title"], g["count"]) for g in res["groups"]],
            [("Pool Stage", 4), ("Finals", 1)],
        )
        res = self.toolset().count_matches(club_id=self.australia.pk, group_by="season")
        self.assertEqual(
            [(g["title"], g["count"]) for g in res["groups"]],
            [("2026", 5), ("2027", 1)],
        )
        res = self.toolset().count_matches(
            club_id=self.australia.pk, group_by="competition"
        )
        self.assertEqual(
            [(g["title"], g["count"]) for g in res["groups"]],
            [("European Championships", 5), ("World Cup", 1)],
        )

    def test_count_matches_by_date_venue_live_stream_and_status(self):
        res = self.toolset().count_matches(season_id=self.season.pk, group_by="date")
        self.assertEqual(
            [(g["id"], g["count"]) for g in res["groups"]],
            [
                ("2026-07-14", 2),
                ("2026-07-15", 1),
                ("2026-07-16", 2),
                ("2026-07-18", 1),
                ("2026-07-19", 1),
            ],
        )
        res = self.toolset().count_matches(season_id=self.season.pk, group_by="venue")
        self.assertEqual(
            [(g["id"], g["title"], g["count"]) for g in res["groups"]],
            [(self.venue.pk, "Nottingham", 6), (None, None, 1)],
        )
        res = self.toolset().count_matches(
            season_id=self.season.pk, group_by="live_stream"
        )
        self.assertEqual(
            [(g["id"], g["title"], g["count"]) for g in res["groups"]],
            [(True, "live streamed", 4), (False, "not live streamed", 3)],
        )
        res = self.toolset().count_matches(season_id=self.season.pk, group_by="status")
        self.assertEqual(
            [
                (g["id"], g["count"], g["completed"], g["live_streamed"])
                for g in res["groups"]
            ],
            [("bye", 1, 0, 0), ("completed", 2, 2, 1), ("upcoming", 4, 0, 3)],
        )

    def test_get_ladder_for_division(self):
        res = self.toolset().get_ladder(division_id=self.mens.pk)
        self.assertEqual(
            res["division"],
            {"id": self.mens.pk, "title": "Men's Open", "slug": "mens-open"},
        )
        self.assertEqual(res["season"]["id"], self.season.pk)
        self.assertEqual(len(res["stages"]), 1)
        stage = res["stages"][0]
        self.assertEqual(
            stage["stage"],
            {"id": self.mens_pools.pk, "title": "Pool Stage", "slug": "pool-stage"},
        )
        self.assertEqual(
            [p["pool"]["title"] for p in stage["pools"]], ["Pool A", "Pool B"]
        )
        self.assertEqual(
            stage["pools"][0]["ladder"],
            [
                {
                    "position": 1,
                    "team": {
                        "id": self.aus_men.pk,
                        "title": "Australia",
                        "slug": "australia",
                        "club": {
                            "id": self.australia.pk,
                            "title": "Australia",
                            "slug": "australia",
                        },
                    },
                    "played": 1,
                    "win": 1,
                    "loss": 0,
                    "draw": 0,
                    "bye": 0,
                    "forfeit_for": 0,
                    "forfeit_against": 0,
                    "score_for": 8,
                    "score_against": 6,
                    "difference": 2.0,
                    "percentage": 133.33,
                    "bonus_points": 0,
                    "points": 3.0,
                },
                {
                    "position": 2,
                    "team": {
                        "id": self.nzl_men.pk,
                        "title": "New Zealand",
                        "slug": "new-zealand",
                        "club": {
                            "id": self.new_zealand.pk,
                            "title": "New Zealand",
                            "slug": "new-zealand",
                        },
                    },
                    "played": 1,
                    "win": 0,
                    "loss": 1,
                    "draw": 0,
                    "bye": 0,
                    "forfeit_for": 0,
                    "forfeit_against": 0,
                    "score_for": 6,
                    "score_against": 8,
                    "difference": -2.0,
                    "percentage": 75.0,
                    "bonus_points": 0,
                    "points": 1.0,
                },
            ],
        )
        self.assertEqual(
            [(e["position"], e["team"]["title"]) for e in stage["pools"][1]["ladder"]],
            [(1, "England"), (2, "France")],
        )

    def test_get_ladder_for_stage_without_pools(self):
        res = self.toolset().get_ladder(stage_id=self.womens_stage.pk)
        self.assertEqual(res["division"]["id"], self.womens.pk)
        self.assertEqual(
            res["stages"],
            [
                {
                    "stage": {
                        "id": self.womens_stage.pk,
                        "title": "Round Robin",
                        "slug": "round-robin",
                    },
                    "pools": [{"pool": None, "ladder": []}],
                }
            ],
        )

    def test_get_ladder_errors(self):
        self.assertEqual(
            self.toolset().get_ladder(),
            {"error": "Provide a division_id or a stage_id."},
        )
        self.assertEqual(
            self.toolset().get_ladder(stage_id=self.mens_finals.pk),
            {"error": "No ladder was found for the given division or stage."},
        )
        self.assertEqual(
            self.toolset().get_ladder(division_id=self.mixed.pk),
            {"error": "No ladder was found for the given division or stage."},
        )


@freeze_time(NOW)
class WhoAmITests(MCPFixtureMixin, TestCase):
    def test_anonymous(self):
        res = self.toolset().whoami()
        self.assertEqual(res["authenticated"], False)
        self.assertEqual(
            res["message"],
            "The MCP client is not authenticated, so there is no 'me'. Ask which team or club the person follows.",
        )

    def test_user_with_teams(self):
        res = self.toolset(self.user).whoami()
        self.assertEqual(res["authenticated"], True)
        self.assertEqual(res["username"], self.user.username)
        self.assertEqual(res["name"], "Gary Reynolds")
        self.assertEqual(res["is_superuser"], False)
        self.assertEqual(
            res["person"], {"id": str(self.person.pk), "name": "Gary Reynolds"}
        )
        self.assertEqual(
            res["club"],
            {"id": self.australia.pk, "title": "Australia", "slug": "australia"},
        )
        self.assertEqual(len(res["teams"]), 1)
        team = res["teams"][0]
        self.assertEqual(team["team"]["id"], self.aus_men.pk)
        self.assertEqual(team["division"]["title"], "Men's Open")
        self.assertEqual(team["next_match"]["id"], self.aus_v_eng.pk)
        self.assertEqual(team["next_match"]["datetime"], "2026-07-16T15:00:00+02:00")
        self.assertEqual(team["last_match"]["id"], self.aus_v_nzl.pk)

    def test_user_without_person(self):
        res = self.toolset(self.superuser).whoami()
        self.assertEqual(res["authenticated"], True)
        self.assertEqual(res["is_superuser"], True)
        self.assertEqual(res["person"], None)
        self.assertEqual(res["teams"], [])
        self.assertEqual(
            res["message"],
            "This user is not linked to a person in the competition system, so no team registrations are known.",
        )


@freeze_time(NOW)
@override_settings(ROOT_URLCONF="vitriolic.urls")
class MCPServerHTTPTests(MCPFixtureMixin, TestCase):
    """Drive the tools over the Streamable HTTP transport with JSON-RPC."""

    def rpc(self, method, params=None, id=1):
        payload = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
        response = self.client.post(
            self.reverse("mcp"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], id)
        return data["result"]

    def test_server_instructions(self):
        self.assertIn(mcp.INSTRUCTIONS, mcp.get_server().instructions)
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.assertEqual(result["serverInfo"]["name"], "vitriolic")
        self.assertEqual(
            result["instructions"],
            "MCP server for the Tournament Control competition management system."
            "\n\n" + mcp.INSTRUCTIONS,
        )

    def test_endpoint_only_speaks_mcp(self):
        # GET is the transport's server-to-client stream and DELETE ends a
        # session; a stateless server offers neither, and answering them
        # promptly matters because a synchronous worker would otherwise hold
        # the connection open until it is killed.
        for method in ("get", "delete", "put"):
            response = getattr(self.client, method)(
                self.reverse("mcp"), HTTP_ACCEPT="application/json, text/event-stream"
            )
            self.assertEqual(response.status_code, 405, method)
            self.assertEqual(response["Allow"], "POST, OPTIONS", method)
        response = self.client.options(self.reverse("mcp"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Allow"], "POST, OPTIONS")
        # A POST without the MCP Accept header is not for the SDK either.
        response = self.client.post(
            self.reverse("mcp"),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 406)

    def test_tools_list(self):
        result = self.rpc("tools/list")
        names = {tool["name"] for tool in result["tools"]}
        self.assertEqual(TOOL_NAMES, names & TOOL_NAMES)
        self.assertNotIn("query_data_collections", names)
        by_name = {tool["name"]: tool for tool in result["tools"]}
        self.assertEqual(
            by_name["list_matches"]["inputSchema"]["properties"]["status"]["enum"],
            ["any", "upcoming", "past", "completed"],
        )
        self.assertEqual(
            by_name["list_matches"]["inputSchema"]["properties"]["date_from"]["anyOf"],
            [{"format": "date", "type": "string"}, {"type": "null"}],
        )
        self.assertIn("when is my next game", by_name["whoami"]["description"])
        # The connector directories require a title and read-only annotation
        # on every tool, and clients use them to skip per-call approval.
        for tool in result["tools"]:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["title"])
                # The Claude directory reads the title from the annotations.
                self.assertEqual(tool["annotations"]["title"], tool["title"])
                self.assertEqual(tool["annotations"]["readOnlyHint"], True)
                self.assertEqual(tool["annotations"]["destructiveHint"], False)
        self.assertEqual(by_name["upcoming_events"]["title"], "Upcoming events")
        self.assertEqual(by_name["whoami"]["title"], "Who am I")

    def test_tools_call_upcoming_events(self):
        result = self.rpc(
            "tools/call", {"name": "upcoming_events", "arguments": {"days": 365}}
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(
            [e["title"] for e in result["structuredContent"]["events"]],
            ["European Championships 2026", "World Cup 2027"],
        )
        self.assertEqual(
            json.loads(result["content"][0]["text"])["today"], "2026-07-15"
        )

    def test_tools_call_list_matches_with_dates(self):
        result = self.rpc(
            "tools/call",
            {
                "name": "list_matches",
                "arguments": {
                    "club_id": self.australia.pk,
                    "opponent_club_id": self.new_zealand.pk,
                    "date_from": "2026-07-16",
                    "date_to": "2026-07-18",
                    "status": "upcoming",
                },
            },
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(
            [m["id"] for m in result["structuredContent"]["matches"]],
            [self.aus_v_nzl_women.pk, self.nzl_v_aus_women.pk],
        )

    def test_tools_call_anonymous_whoami(self):
        result = self.rpc("tools/call", {"name": "whoami", "arguments": {}})
        self.assertEqual(result["structuredContent"]["authenticated"], False)

    def test_tools_call_invalid_argument(self):
        result = self.rpc(
            "tools/call", {"name": "list_matches", "arguments": {"status": "finished"}}
        )
        self.assertEqual(result["isError"], True)


@freeze_time(NOW)
@override_settings(ROOT_URLCONF="vitriolic.urls")
class MCPRequestHandledSignalTests(MCPFixtureMixin, TestCase):
    """``mcp_request_handled`` describes each request the endpoint answers."""

    def setUp(self):
        super().setUp()
        self.sent = []
        mcp_request_handled.connect(self.receiver)
        self.addCleanup(mcp_request_handled.disconnect, self.receiver)

    def receiver(self, sender, **kwargs):
        self.sent.append(kwargs)

    def rpc(self, method, params=None):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        response = self.client.post(
            self.reverse("mcp"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["request"].path, self.reverse("mcp"))
        return response.json()["result"], self.sent[0]

    def test_method_without_tool(self):
        __, sent = self.rpc("tools/list")
        self.assertEqual(sent["method"], "tools/list")
        self.assertIsNone(sent["tool"])
        self.assertIsNone(sent["arguments"])
        self.assertIsNone(sent["duration"])
        self.assertIsNone(sent["error"])

    def test_tool_call(self):
        result, sent = self.rpc(
            "tools/call", {"name": "upcoming_events", "arguments": {"days": 365}}
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(sent["method"], "tools/call")
        self.assertEqual(sent["tool"], "upcoming_events")
        self.assertEqual(sent["arguments"], {"days": 365})
        self.assertGreaterEqual(sent["duration"], 0)
        self.assertIsNone(sent["error"])
        self.assertIsNone(sent["status_code"])

    def test_unknown_method_is_a_status_code_not_an_error(self):
        # Method not found is the caller's mistake, not the server's.
        payload = {"jsonrpc": "2.0", "id": 1, "method": "no/such/method"}
        response = self.client.post(
            self.reverse("mcp"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
        )
        self.assertEqual(response.json()["error"]["code"], -32601)
        (sent,) = self.sent
        self.assertEqual(sent["method"], "no/such/method")
        self.assertEqual(sent["status_code"], "-32601")
        self.assertIsNone(sent["error"])

    def test_server_error_code_is_an_error(self):
        # A JSON-RPC error outside the caller's mistakes, such as an internal
        # error, is reported as the error, by its code.
        request = RequestFactory().post(
            "/mcp/",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            content_type="application/json",
        )
        response = HttpResponse(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32603, "message": "Internal error"},
                }
            )
        )
        MCPView().request_handled(request, response, mcp.ToolCall())
        (sent,) = self.sent
        self.assertEqual(sent["status_code"], "-32603")
        self.assertEqual(sent["error"], "-32603")

    def test_sensitive_arguments_are_redacted(self):
        result, sent = self.rpc(
            "tools/call",
            {"name": "search", "arguments": {"query": "Jane Citizen", "limit": 5}},
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(sent["tool"], "search")
        self.assertEqual(sent["arguments"], {"query": "[redacted]", "limit": 5})

    def test_sensitive_arguments_are_redacted_when_rejected(self):
        # Arguments the SDK rejects are reported too, so they must be
        # redacted before validation, not after.
        result, sent = self.rpc(
            "tools/call",
            {"name": "search", "arguments": {"query": "Jane Citizen", "limit": "x"}},
        )
        self.assertEqual(result["isError"], True)
        self.assertEqual(sent["arguments"], {"query": "[redacted]", "limit": "x"})

    def test_tool_call_with_invalid_arguments(self):
        # The SDK rejects the arguments before the tool runs.
        result, sent = self.rpc(
            "tools/call", {"name": "list_matches", "arguments": {"status": "finished"}}
        )
        self.assertEqual(result["isError"], True)
        self.assertEqual(sent["tool"], "list_matches")
        # The rejected arguments are reported, to show what the client sent.
        self.assertEqual(sent["arguments"], {"status": "finished"})
        self.assertIsNone(sent["duration"])
        self.assertEqual(sent["error"], "tool_error")
        self.assertIsNone(sent["status_code"])

    def test_tool_call_that_raises(self):
        with mock.patch.object(
            mcp.CompetitionToolset, "whoami", side_effect=RuntimeError("boom")
        ):
            result, sent = self.rpc("tools/call", {"name": "whoami", "arguments": {}})
        self.assertEqual(result["isError"], True)
        self.assertEqual(sent["tool"], "whoami")
        self.assertGreaterEqual(sent["duration"], 0)
        self.assertEqual(sent["error"], "RuntimeError")

    def test_failing_receiver_does_not_break_the_response(self):
        def broken(sender, **kwargs):
            raise RuntimeError("receiver bug")

        mcp_request_handled.connect(broken)
        self.addCleanup(mcp_request_handled.disconnect, broken)
        with self.assertLogs("tournamentcontrol.competition.mcp.views", "ERROR"):
            result, __ = self.rpc("tools/call", {"name": "whoami", "arguments": {}})
        self.assertEqual(result["structuredContent"]["authenticated"], False)


class SensitiveArgumentsTests(TestCase):
    def test_servers_know_their_sensitive_arguments(self):
        self.assertEqual(
            mcp.get_server().sensitive_arguments,
            {"search": {"query"}, "list_teams": {"query"}},
        )
        self.assertEqual(
            get_admin_server().sensitive_arguments["update_season"],
            {"live_stream_client_secret"},
        )

    def test_redact_arguments(self):
        server = mcp.get_server()
        self.assertEqual(
            mcp.redact_arguments(server, "search", {"query": "Jane", "limit": 5}),
            {"query": mcp.REDACTED, "limit": 5},
        )
        # Only the arguments that were sent are reported.
        self.assertEqual(mcp.redact_arguments(server, "search", {}), {})
        # Tools with nothing sensitive, unknown tools and arguments that are
        # not an object are left alone.
        self.assertEqual(
            mcp.redact_arguments(server, "get_match", {"match_id": 1}),
            {"match_id": 1},
        )
        self.assertEqual(
            mcp.redact_arguments(server, "no_such_tool", {"query": "Jane"}),
            {"query": "Jane"},
        )
        self.assertEqual(mcp.redact_arguments(server, "search", "Jane"), "Jane")

    def test_a_misspelt_sensitive_argument_is_refused(self):
        class Toolset(mcp.CompetitionToolset):
            @mcp.sensitive_arguments("qeury")
            def search(self, query: str, limit: int = 10) -> dict:
                return {}

        with self.assertRaisesMessage(
            ImproperlyConfigured, "search marks qeury as sensitive"
        ):
            mcp.build_server(toolset_class=Toolset)
