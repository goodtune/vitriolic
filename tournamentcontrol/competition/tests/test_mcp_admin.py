"""
Tests for the competition administration MCP tools.

The tools are exercised directly on the toolset with a fake request (only
the request's ``user`` matters) and over the Streamable HTTP endpoint,
including the OAuth 2.1 flow an MCP client such as Claude Code runs to
obtain a bearer token.
"""

import base64
import datetime
import hashlib
import html
import json
import secrets
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from freezegun import freeze_time
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from guardian.shortcuts import assign_perm
from mcp.server.mcpserver.exceptions import ToolError
from test_plus import TestCase

from tournamentcontrol.competition import mcp
from tournamentcontrol.competition.mcp import admin as mcp_admin
from tournamentcontrol.competition.models import (
    Competition,
    Ground,
    LiveStreamEvent,
    LiveStreamKey,
    Match,
    Season,
)
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.tests.test_mcp_integration import (
    NOW,
    TZ,
    MCPFixtureMixin,
    _match,
)

# Build the servers before freezegun replaces ``datetime.date`` (see
# test_mcp_integration for why).
mcp.get_server()
mcp_admin.get_admin_server()

WRITE_TOOLS = {
    "create_competition",
    "update_competition",
    "delete_competition",
    "create_season",
    "update_season",
    "delete_season",
    "create_venue",
    "update_venue",
    "delete_venue",
    "create_ground",
    "update_ground",
    "delete_ground",
    "create_division",
    "update_division",
    "delete_division",
    "create_team",
    "update_team",
    "delete_team",
    "withdraw_team",
    "create_stage",
    "update_stage",
    "delete_stage",
    "create_pool",
    "update_pool",
    "delete_pool",
    "create_match",
    "update_match",
    "delete_match",
    "reschedule_match",
    "swap_match_allocations",
    "set_match_referees",
    "record_match_result",
    "create_season_stream_key",
    "delete_season_stream_key",
    "enable_ground_live_stream",
    "disable_ground_live_stream",
    "enable_match_live_stream",
    "disable_match_live_stream",
    "resync_match_live_stream",
    "create_season_stream_event",
    "update_season_stream_event",
    "delete_season_stream_event",
    "resync_season_stream_event",
    "create_draw_format",
    "update_draw_format",
    "delete_draw_format",
    "add_season_exclusion_dates",
    "delete_season_exclusion_dates",
    "add_division_exclusion_dates",
    "delete_division_exclusion_dates",
    "create_timeslot",
    "update_timeslot",
    "delete_timeslot",
    "build_draw",
    "schedule_matches",
    "auto_schedule",
}
READ_TOOLS = {
    "list_competitions",
    "list_venues",
    "list_season_referees",
    "list_matches_awaiting_results",
    "list_season_stream_keys",
    "list_season_stream_events",
    "list_streamed_grounds",
    "list_draw_formats",
    "get_draw_format",
    "preview_draw_format",
    "list_season_exclusion_dates",
    "list_division_exclusion_dates",
    "list_timeslots",
    "get_timeslots",
}


def _http_error(status, content=b""):
    return HttpError(SimpleNamespace(status=status, reason="boom"), content)


class AdminFixtureMixin(MCPFixtureMixin):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff = factories.UserFactory.create(is_staff=True)
        # An upcoming match that is not live streamed, on a ground that is
        # not a camera position.
        cls.fra_v_eng = _match(
            cls.mens_pools,
            cls.fra_men,
            cls.eng_men,
            datetime.date(2026, 7, 16),
            datetime.time(17, 0),
            stage_group=cls.pool_b,
            round=2,
            play_at=cls.field2,
        )
        cls.old_match = Match.objects.get(stage__division__season=cls.nationals_2026)

    def admin(self, user=None):
        request = SimpleNamespace(user=user or self.superuser)
        return mcp_admin.AdminToolset(request=request)

    def assertToolError(self, message, callable, *args, **kwargs):
        with self.assertRaises(ToolError) as cm:
            callable(*args, **kwargs)
        self.assertEqual(str(cm.exception), message)
        return cm.exception


@freeze_time(NOW)
class PermissionTests(AdminFixtureMixin, TestCase):
    def test_anonymous_and_non_staff_are_refused(self):
        message = "The competition administration tools require a signed-in staff user."
        for user in (AnonymousUser(), self.user):
            with self.subTest(user=user):
                self.assertToolError(message, self.admin(user).list_competitions)
                self.assertToolError(
                    message, self.admin(user).create_competition, title="X"
                )

    def test_staff_without_permission_is_refused(self):
        self.assertToolError(
            "Permission denied: add competition requires the "
            "competition.add_competition permission.",
            self.admin(self.staff).create_competition,
            title="Nationals",
        )
        self.assertToolError(
            "Permission denied: change season requires the "
            "competition.change_season permission for this season.",
            self.admin(self.staff).update_season,
            self.season.pk,
            title="2027",
        )
        self.assertToolError(
            "Permission denied: delete match requires the "
            "competition.delete_match permission for this match.",
            self.admin(self.staff).delete_match,
            self.aus_v_nzl.pk,
        )
        # Reading stream keys needs change permission on the season.
        self.assertToolError(
            "Permission denied: change season requires the "
            "competition.change_season permission for this season.",
            self.admin(self.staff).list_season_stream_keys,
            self.season.pk,
        )
        # Other read tools only need a staff user.
        self.assertEqual(
            self.admin(self.staff).list_competitions()["competitions"][0]["title"],
            "European Championships",
        )

    def test_global_permission(self):
        assign_perm("competition.add_competition", self.staff)
        res = self.admin(self.staff).create_competition(title="Nationals")
        self.assertEqual(res["saved"], True)
        self.assertEqual(res["competition"]["title"], "Nationals")

    def test_object_permission(self):
        assign_perm("change_season", self.staff, self.season)
        res = self.admin(self.staff).update_season(self.season.pk, hashtag="#Euros")
        self.assertEqual(res["season"]["hashtag"], "#Euros")
        self.assertToolError(
            "Permission denied: change season requires the "
            "competition.change_season permission for this season.",
            self.admin(self.staff).update_season,
            self.nationals_2026.pk,
            hashtag="#Old",
        )

    def test_administrators_see_everything(self):
        res = self.admin(self.staff).search("Old Series")
        self.assertEqual([c["title"] for c in res["competitions"]], ["Old Series"])
        season = self.admin(self.staff).get_season(self.season.pk)
        self.assertEqual(
            [d["title"] for d in season["divisions"]],
            ["Men's Open", "Women's Open", "Mixed Open"],
        )


@freeze_time(NOW)
class BuildCompetitionTests(AdminFixtureMixin, TestCase):
    """Build a competition up from scratch, then take it down again."""

    def test_build_up_and_tear_down(self):
        admin = self.admin()

        competition = admin.create_competition(
            title="National Championships",
            short_title="Nationals",
            club_ids=[self.australia.pk, self.new_zealand.pk],
        )["competition"]
        self.assertEqual(competition["slug"], "national-championships")
        self.assertEqual(
            [c["title"] for c in competition["clubs"]], ["Australia", "New Zealand"]
        )

        season = admin.create_season(
            competition["id"],
            title="2027",
            timezone="Australia/Sydney",
            start_date=datetime.date(2027, 3, 1),
            mode="tournament",
            hashtag="#Nats27",
        )["season"]
        self.assertEqual(season["timezone"], "Australia/Sydney")
        self.assertEqual(season["mode"], "tournament")
        self.assertEqual(season["start_date"], "2027-03-01")
        self.assertEqual(season["youtube_credentials_configured"], False)

        venue = admin.create_venue(
            season["id"],
            title="Coffs Harbour",
            latitude=-30.3,
            longitude=153.1,
            zoom=14,
        )["venue"]
        self.assertEqual(venue["timezone"], "Australia/Sydney")
        self.assertEqual(venue["latitude"], -30.3)
        ground = admin.create_ground(venue["id"], title="Field 1")["ground"]
        self.assertEqual(ground["timezone"], "Australia/Sydney")
        self.assertEqual(ground["latitude"], -30.3)
        self.assertEqual(ground["live_stream"], False)
        self.assertEqual(ground["venue"]["title"], "Coffs Harbour")

        division = admin.create_division(
            season["id"],
            title="Men's Open",
            points_formula="3*win + 2*draw + 1*loss",
            forfeit_for_score=5,
            forfeit_against_score=0,
            games_per_day=2,
        )["division"]
        self.assertEqual(division["points_formula"], "3*win + 2*draw + 1*loss")
        self.assertEqual(division["games_per_day"], 2)

        aus = admin.create_team(division["id"], club_id=self.australia.pk)["team"]
        self.assertEqual(aus["title"], "Australia")
        nzl = admin.create_team(
            division["id"], club_id=self.new_zealand.pk, title="Kiwis"
        )["team"]
        self.assertEqual(nzl["title"], "Kiwis")
        self.assertEqual(nzl["club"]["title"], "New Zealand")

        stage = admin.create_stage(division["id"], title="Round Robin")["stage"]
        self.assertEqual(stage["order"], 1)
        self.assertEqual(stage["keep_ladder"], True)
        finals = admin.create_stage(division["id"], title="Finals", keep_ladder=False)[
            "stage"
        ]
        self.assertEqual(finals["order"], 2)
        self.assertEqual(finals["follows"], None)

        pool = admin.create_pool(stage["id"], title="Pool A")["pool"]
        pool = admin.update_pool(pool["id"], team_ids=[aus["id"], nzl["id"]])["pool"]
        self.assertEqual([t["title"] for t in pool["teams"]], ["Australia", "Kiwis"])

        match = admin.create_match(
            stage["id"],
            home_team_id=aus["id"],
            away_team_id=nzl["id"],
            pool_id=pool["id"],
            round=1,
            date=datetime.date(2027, 3, 6),
            time=datetime.time(10, 30),
            place_id=ground["id"],
        )["match"]
        self.assertEqual(match["home_team"]["title"], "Australia")
        self.assertEqual(match["away_team"]["title"], "Kiwis")
        self.assertEqual(match["pool"]["title"], "Pool A")
        self.assertEqual(match["datetime"], "2027-03-06T10:30:00+11:00")
        self.assertEqual(match["ground"]["title"], "Field 1")
        self.assertEqual(match["status"], "upcoming")

        result = admin.record_match_result(
            match["id"], home_team_score=7, away_team_score=5
        )["match"]
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["winner"]["title"], "Australia")
        ladder = admin.get_ladder(stage_id=stage["id"])["stages"][0]["pools"][0]
        self.assertEqual(
            [(e["team"]["title"], e["points"]) for e in ladder["ladder"]],
            [("Australia", 3.0), ("Kiwis", 1.0)],
        )

        # Tear down in dependency order; the protected relations refuse
        # anything else.
        self.assertToolError(
            "This division cannot be deleted while other records depend on it: "
            "stage, team.",
            admin.delete_division,
            division["id"],
        )
        self.assertToolError(
            "This team cannot be deleted because it has matches scheduled or "
            "played; use withdraw_team to take it out of the draw.",
            admin.delete_team,
            aus["id"],
        )
        self.assertEqual(
            admin.delete_match(match["id"]), {"deleted": "match %d" % match["id"]}
        )
        self.assertEqual(admin.delete_pool(pool["id"]), {"deleted": "pool Pool A"})
        self.assertEqual(admin.delete_stage(finals["id"]), {"deleted": "stage Finals"})
        self.assertEqual(
            admin.delete_stage(stage["id"]), {"deleted": "stage Round Robin"}
        )
        self.assertEqual(admin.delete_team(aus["id"]), {"deleted": "team Australia"})
        self.assertEqual(admin.delete_team(nzl["id"]), {"deleted": "team Kiwis"})
        self.assertEqual(
            admin.delete_division(division["id"]), {"deleted": "division Men's Open"}
        )
        self.assertEqual(
            admin.delete_ground(ground["id"]), {"deleted": "ground Field 1"}
        )
        self.assertEqual(
            admin.delete_venue(venue["id"]), {"deleted": "venue Coffs Harbour"}
        )
        self.assertEqual(
            admin.delete_season(season["id"]),
            {"deleted": "season National Championships 2027"},
        )
        self.assertEqual(
            admin.delete_competition(competition["id"]),
            {"deleted": "competition National Championships"},
        )
        self.assertEqual(Competition.objects.filter(pk=competition["id"]).count(), 0)

    def test_update_only_changes_what_is_given(self):
        admin = self.admin()
        res = admin.update_competition(self.competition.pk, short_title="EC")
        self.assertEqual(res["competition"]["title"], "European Championships")
        self.assertEqual(res["competition"]["short_title"], "EC")
        self.assertEqual(res["competition"]["enabled"], True)

        res = admin.update_season(self.season.pk, complete=True)
        self.season.refresh_from_db()
        self.assertEqual(self.season.complete, True)
        self.assertEqual(self.season.hashtag, "#Euros2026")
        self.assertEqual(self.season.live_stream, True)
        self.assertEqual(res["season"]["complete"], True)

        res = admin.update_venue(self.venue.pk, latitude=52.9)
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.latlng, "52.9,-1.15,12")
        self.assertEqual(res["venue"]["longitude"], -1.15)

        res = admin.update_division(self.mixed.pk, draft=False)
        self.assertEqual(res["division"]["draft"], False)
        self.mixed.refresh_from_db()
        self.assertEqual(self.mixed.points_formula, "3*win + 2*draw + 1*loss")

        res = admin.update_stage(self.mens_finals.pk, carry_ladder=True)
        self.assertEqual(res["stage"]["carry_ladder"], True)
        self.assertEqual(res["stage"]["keep_ladder"], False)

        res = admin.update_team(self.aus_men.pk, short_title="AUS")
        self.assertEqual(res["team"]["short_title"], "AUS")
        self.assertEqual(res["team"]["pool"]["title"], "Pool A")

    def test_slug_is_for_superusers(self):
        assign_perm("competition.change_competition", self.staff)
        self.assertToolError(
            "slug cannot be set for this competition.",
            self.admin(self.staff).update_competition,
            self.competition.pk,
            slug="euros",
        )
        res = self.admin().update_competition(
            self.competition.pk, slug="euros", slug_locked=True
        )
        self.assertEqual(res["competition"]["slug"], "euros")

    def test_validation_errors(self):
        admin = self.admin()
        self.assertToolError(
            "Validation failed: points_formula: Expected end of text, found "
            "'wins'  (at char 2), (line:1, col:3)",
            admin.create_division,
            self.season.pk,
            title="Bad",
            points_formula="3 wins",
        )
        self.assertToolError(
            "Validation failed: latlng: This field is required.",
            admin.create_venue,
            self.season.pk,
            title="Nowhere",
        )
        self.assertToolError(
            "Validation failed: title: Team with this Title already exists.",
            admin.create_team,
            self.mens.pk,
            title="Australia",
        )
        self.assertToolError(
            "Validation failed: away_team: Teams cannot be scheduled to play "
            "against itself.",
            admin.create_match,
            self.womens_stage.pk,
            home_team_id=self.aus_women.pk,
            away_team_id=self.aus_women.pk,
        )
        self.assertToolError(
            "Validation failed: home_team: Select a valid choice. That choice is "
            "not one of the available choices.",
            admin.create_match,
            self.womens_stage.pk,
            home_team_id=self.aus_men.pk,
            away_team_id=self.nzl_women.pk,
        )
        self.assertToolError(
            "stage_group cannot be set for this match.",
            admin.create_match,
            self.womens_stage.pk,
            home_team_id=self.aus_women.pk,
            away_team_id=self.nzl_women.pk,
            pool_id=self.pool_a.pk,
        )
        self.assertToolError(
            "Season 999999 was not found.", admin.create_division, 999999, title="X"
        )
        self.assertToolError(
            "Give latitude, longitude and zoom together.",
            admin.create_venue,
            self.season.pk,
            title="Nowhere",
            latitude=1.0,
        )

    def test_pool_membership_rules(self):
        admin = self.admin()
        # Pool A already has matches so membership is fixed.
        self.assertToolError(
            "teams cannot be set for this pool.",
            admin.update_pool,
            self.pool_a.pk,
            team_ids=[self.aus_men.pk],
        )
        pool = admin.create_pool(self.womens_stage.pk, title="Pool W")["pool"]
        pool = admin.update_pool(pool["id"], team_ids=[self.aus_women.pk])["pool"]
        self.assertEqual([t["id"] for t in pool["teams"]], [self.aus_women.pk])
        self.aus_women.refresh_from_db()
        self.assertEqual(self.aus_women.stage_group_id, pool["id"])
        self.assertToolError(
            "Validation failed: teams: Select a valid choice. %d is not one of the "
            "available choices." % self.aus_men.pk,
            admin.update_pool,
            pool["id"],
            team_ids=[self.aus_men.pk],
        )


@freeze_time(NOW)
class SchedulingTests(AdminFixtureMixin, TestCase):
    def test_reschedule(self):
        admin = self.admin()
        res = admin.reschedule_match(
            self.fra_v_eng.pk,
            date=datetime.date(2026, 7, 17),
            time=datetime.time(9, 0),
            place_id=self.field1.pk,
        )
        self.assertEqual(res["live_stream_sync_queued"], False)
        self.assertEqual(res["match"]["date"], "2026-07-17")
        self.assertEqual(res["match"]["time"], "09:00")
        self.assertEqual(res["match"]["ground"]["title"], "Field 1")
        self.assertEqual(res["match"]["datetime"], "2026-07-17T09:00:00+02:00")
        self.fra_v_eng.refresh_from_db()
        self.assertEqual(self.fra_v_eng.play_at_id, self.field1.pk)

        # The venue itself is a valid place; only the place changes here.
        res = admin.reschedule_match(self.fra_v_eng.pk, place_id=self.venue.pk)
        self.assertEqual(res["match"]["ground"], None)
        self.assertEqual(res["match"]["venue"]["title"], "Nottingham")
        self.assertEqual(res["match"]["time"], "09:00")

    def test_reschedule_rules(self):
        admin = self.admin()
        self.assertToolError(
            "Give a date, time or place_id to change.",
            admin.reschedule_match,
            self.fra_v_eng.pk,
        )
        factories.SeasonExclusionDateFactory.create(
            season=self.season, date=datetime.date(2026, 7, 20)
        )
        self.assertToolError(
            "Validation failed: date: This date has been excluded for this season.",
            admin.reschedule_match,
            self.fra_v_eng.pk,
            date=datetime.date(2026, 7, 20),
        )
        self.season.start_date = datetime.date(2026, 7, 10)
        self.season.save()
        self.assertToolError(
            "Validation failed: date: This date is before the start of the season.",
            admin.reschedule_match,
            self.fra_v_eng.pk,
            date=datetime.date(2026, 7, 1),
        )
        # A place must belong to the season.
        other_venue = factories.VenueFactory.create(season=self.nationals_2026)
        self.assertToolError(
            "Venue or ground %d was not found." % other_venue.pk,
            admin.reschedule_match,
            self.fra_v_eng.pk,
            place_id=other_venue.pk,
        )
        # Team time preferences are respected.
        self.eng_men.timeslots_after = datetime.time(12, 0)
        self.eng_men.save()
        self.assertToolError(
            "Validation failed: time: England must play after 12:00.",
            admin.reschedule_match,
            self.fra_v_eng.pk,
            time=datetime.time(9, 0),
        )
        res = admin.reschedule_match(
            self.fra_v_eng.pk, time=datetime.time(9, 0), ignore_clashes=True
        )
        self.assertEqual(res["match"]["time"], "09:00")

    def test_clashes(self):
        admin = self.admin()
        # aus_v_eng and fra_v_eng are both on 16 July; put them in the same
        # slot, which also has England playing twice at once.
        self.assertToolError(
            "Another match is already scheduled for this time & place. "
            "England are already playing at 15:00 on 2026-07-16.",
            admin.reschedule_match,
            self.fra_v_eng.pk,
            time=datetime.time(15, 0),
            place_id=self.field1.pk,
        )
        res = admin.reschedule_match(
            self.fra_v_eng.pk,
            time=datetime.time(15, 0),
            place_id=self.field1.pk,
            ignore_clashes=True,
        )
        self.assertEqual(res["match"]["time"], "15:00")

        # Declared team clashes: Australia (women) must not play at the same
        # time as Australia (men), who play at 15:00 on 16 July.
        self.aus_women.team_clashes.add(self.aus_men)
        self.assertToolError(
            "Australia must not play at the same time as Australia (Men's Open), "
            "who are already scheduled at 15:00.",
            admin.reschedule_match,
            self.nzl_v_aus_women.pk,
            date=datetime.date(2026, 7, 16),
            time=datetime.time(15, 0),
        )

    def test_swap(self):
        admin = self.admin()
        first, second = self.fra_v_eng, self.nzl_v_aus_women
        before = (
            (first.date, first.time, first.play_at_id),
            (second.date, second.time, second.play_at_id),
        )
        res = admin.swap_match_allocations(first.pk, second.pk)
        self.assertEqual([m["id"] for m in res["matches"]], [first.pk, second.pk])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(
            (
                (second.date, second.time, second.play_at_id),
                (first.date, first.time, first.play_at_id),
            ),
            before,
        )
        self.assertEqual(res["matches"][0]["datetime"], "2026-07-18T09:00:00+02:00")
        self.assertEqual(res["matches"][0]["ground"], None)
        self.assertEqual(res["matches"][1]["datetime"], "2026-07-16T17:00:00+02:00")
        self.assertEqual(res["matches"][1]["ground"]["title"], "Field 2")

    def test_swap_rules(self):
        admin = self.admin()
        self.assertToolError(
            "Give two different matches to swap.",
            admin.swap_match_allocations,
            self.aus_v_eng.pk,
            self.aus_v_eng.pk,
        )
        self.assertToolError(
            "Both matches must belong to the same season.",
            admin.swap_match_allocations,
            self.aus_v_eng.pk,
            self.old_match.pk,
        )
        self.assertToolError(
            "Match %d is live streamed; remove its live stream before swapping "
            "its allocation." % self.aus_v_nzl.pk,
            admin.swap_match_allocations,
            self.fra_v_eng.pk,
            self.aus_v_nzl.pk,
        )

    def test_referees(self):
        admin = self.admin()
        referee = factories.SeasonRefereeFactory.create(
            season=self.season, club=self.england
        )
        other = factories.SeasonRefereeFactory.create(season=self.nationals_2026)
        res = admin.list_season_referees(self.season.pk)
        self.assertEqual([r["id"] for r in res["referees"]], [referee.pk])
        self.assertEqual(res["referees"][0]["club"]["title"], "England")

        res = admin.set_match_referees(self.aus_v_eng.pk, [referee.pk])
        self.assertEqual([r["id"] for r in res["match"]["referees"]], [referee.pk])
        self.assertEqual(res["match"]["home_team"]["title"], "Australia")
        self.assertToolError(
            "Validation failed: referees: Select a valid choice. %d is not one of "
            "the available choices." % other.pk,
            admin.set_match_referees,
            self.aus_v_eng.pk,
            [other.pk],
        )
        res = admin.set_match_referees(self.aus_v_eng.pk, [])
        self.assertEqual(res["match"]["referees"], [])

    def test_update_match(self):
        admin = self.admin()
        res = admin.update_match(self.aus_v_eng.pk, label="Grand Final", round=9)
        self.assertEqual(res["match"]["label"], "Grand Final")
        self.assertEqual(res["match"]["round"], 9)
        self.assertEqual(res["match"]["home_team"]["title"], "Australia")
        self.assertEqual(res["live_stream_sync_queued"], False)
        # Video links in a season that is not live streamed.
        res = admin.update_match(self.old_match.pk, videos=["https://youtu.be/abc123"])
        self.assertEqual(res["match"]["videos"], ["https://youtu.be/abc123"])
        self.assertToolError(
            "Video links of a live streamed season are managed by the broadcast "
            "synchronisation.",
            admin.update_match,
            self.aus_v_eng.pk,
            videos=["https://youtu.be/abc123"],
        )


@freeze_time(NOW)
class ByeTests(AdminFixtureMixin, TestCase):
    """A single bye through ``create_match``; conversions with ``update_match``."""

    def test_create_bye(self):
        # A bye is a match with one team and no opponent, time or place; it
        # keeps its date so it is processed with the round it belongs to.
        admin = self.admin()
        res = admin.create_match(
            self.womens_stage.pk,
            home_team_id=self.aus_women.pk,
            round=3,
            date=datetime.date(2026, 7, 20),
            is_bye=True,
        )
        match = Match.objects.get(stage=self.womens_stage, round=3)
        self.assertEqual(
            res,
            {
                "saved": True,
                "match": {
                    "id": match.pk,
                    "uuid": str(match.uuid),
                    "competition": {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": self.competition.slug,
                    },
                    "season": {
                        "id": self.season.pk,
                        "title": "2026",
                        "slug": self.season.slug,
                    },
                    "division": {
                        "id": self.womens.pk,
                        "title": "Women's Open",
                        "slug": self.womens.slug,
                    },
                    "stage": {
                        "id": self.womens_stage.pk,
                        "title": "Round Robin",
                        "slug": self.womens_stage.slug,
                    },
                    "pool": None,
                    "round": 3,
                    "label": None,
                    "datetime": None,
                    "date": "2026-07-20",
                    "time": None,
                    "timezone": "Europe/Amsterdam",
                    "home_team": {
                        "id": self.aus_women.pk,
                        "title": "Australia",
                        "slug": self.aus_women.slug,
                        "club": {
                            "id": self.australia.pk,
                            "title": "Australia",
                            "slug": self.australia.slug,
                        },
                    },
                    "away_team": {
                        "id": None,
                        "title": "Bye",
                        "slug": None,
                        "club": None,
                    },
                    "home_team_score": None,
                    "away_team_score": None,
                    "status": "bye",
                    "winner": None,
                    "is_draw": False,
                    "live_stream": False,
                    "live_stream_url": None,
                    "videos": [],
                    "venue": None,
                    "ground": None,
                    "is_bye": True,
                    "is_forfeit": False,
                    "is_washout": False,
                    "bye_processed": False,
                    "include_in_ladder": True,
                    "youtube_broadcast_id": None,
                    "referees": [],
                },
            },
        )
        self.assertTrue(match.is_bye)
        self.assertIsNone(match.away_team)
        self.assertIsNone(match.datetime)

    def test_create_bye_rules(self):
        admin = self.admin()
        one_team = (
            "A bye is one team with no opponent: exactly one side must have a team."
        )
        self.assertToolError(
            one_team,
            admin.create_match,
            self.womens_stage.pk,
            home_team_id=self.aus_women.pk,
            away_team_id=self.nzl_women.pk,
            is_bye=True,
        )
        self.assertToolError(
            one_team, admin.create_match, self.womens_stage.pk, is_bye=True
        )
        # Evals and undecided teams describe a side to be decided later; a bye
        # has nothing to decide.
        self.assertToolError(
            "A bye is one team with no opponent: it cannot have an undecided team "
            "or an eval.",
            admin.create_match,
            self.mens_finals.pk,
            home_team_id=self.aus_men.pk,
            away_team_eval="P1",
            is_bye=True,
        )
        self.assertToolError(
            "A bye has no time or place: leave time and place_id out.",
            admin.create_match,
            self.womens_stage.pk,
            home_team_id=self.aus_women.pk,
            date=datetime.date(2026, 7, 20),
            time=datetime.time(9, 0),
            is_bye=True,
        )
        # None of the refused calls created a match: the stage still holds
        # only the two fixture matches.
        self.assertEqual(
            set(
                Match.objects.filter(stage=self.womens_stage).values_list(
                    "pk", flat=True
                )
            ),
            {self.aus_v_nzl_women.pk, self.nzl_v_aus_women.pk},
        )

    def test_convert_match_to_bye(self):
        # France v England is unplayed and scheduled with a referee; making it
        # a bye for France must release the slot and the appointment.
        admin = self.admin()
        referee = factories.SeasonRefereeFactory.create(season=self.season)
        admin.set_match_referees(self.fra_v_eng.pk, [referee.pk])
        # The slot France v England holds is taken until it is released.
        taken = "Another match is already scheduled for this time & place."
        self.assertToolError(
            taken,
            admin.reschedule_match,
            self.mixed_match.pk,
            date=datetime.date(2026, 7, 16),
            time=datetime.time(17, 0),
            place_id=self.field2.pk,
        )

        res = admin.update_match(self.fra_v_eng.pk, is_bye=True, clear_away_team=True)
        self.assertEqual(
            res,
            {
                "saved": True,
                "live_stream_sync_queued": False,
                "referees_removed": 1,
                "match": {
                    "id": self.fra_v_eng.pk,
                    "uuid": str(self.fra_v_eng.uuid),
                    "competition": {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": self.competition.slug,
                    },
                    "season": {
                        "id": self.season.pk,
                        "title": "2026",
                        "slug": self.season.slug,
                    },
                    "division": {
                        "id": self.mens.pk,
                        "title": "Men's Open",
                        "slug": self.mens.slug,
                    },
                    "stage": {
                        "id": self.mens_pools.pk,
                        "title": "Pool Stage",
                        "slug": self.mens_pools.slug,
                    },
                    "pool": {
                        "id": self.pool_b.pk,
                        "title": "Pool B",
                        "slug": self.pool_b.slug,
                    },
                    "round": 2,
                    "label": None,
                    "datetime": None,
                    "date": "2026-07-16",
                    "time": None,
                    "timezone": "Europe/Amsterdam",
                    "home_team": {
                        "id": self.fra_men.pk,
                        "title": "France",
                        "slug": self.fra_men.slug,
                        "club": {
                            "id": self.france.pk,
                            "title": "France",
                            "slug": self.france.slug,
                        },
                    },
                    "away_team": {
                        "id": None,
                        "title": "Bye",
                        "slug": None,
                        "club": None,
                    },
                    "home_team_score": None,
                    "away_team_score": None,
                    "status": "bye",
                    "winner": None,
                    "is_draw": False,
                    "live_stream": False,
                    "live_stream_url": None,
                    "videos": [],
                    "venue": None,
                    "ground": None,
                    "is_bye": True,
                    "is_forfeit": False,
                    "is_washout": False,
                    "bye_processed": False,
                    "include_in_ladder": True,
                    "youtube_broadcast_id": None,
                    "referees": [],
                },
            },
        )
        self.fra_v_eng.refresh_from_db()
        self.assertTrue(self.fra_v_eng.is_bye)
        self.assertIsNone(self.fra_v_eng.away_team)
        self.assertIsNone(self.fra_v_eng.time)
        self.assertIsNone(self.fra_v_eng.datetime)
        self.assertIsNone(self.fra_v_eng.play_at)
        self.assertFalse(self.fra_v_eng.referees.exists())

        # The released slot is free for another match.
        admin.reschedule_match(
            self.mixed_match.pk,
            date=datetime.date(2026, 7, 16),
            time=datetime.time(17, 0),
            place_id=self.field2.pk,
        )
        self.mixed_match.refresh_from_db()
        self.assertEqual(self.mixed_match.date, datetime.date(2026, 7, 16))
        self.assertEqual(self.mixed_match.time, datetime.time(17, 0))
        self.assertEqual(self.mixed_match.play_at_id, self.field2.pk)

    def test_convert_match_to_bye_rules(self):
        # England v France has a result and Australia v England is live
        # streamed: neither can become a bye. France v England can, but only
        # with exactly one side left.
        admin = self.admin()
        before = Match.objects.filter(pk=self.fra_v_eng.pk).values().get()
        self.assertToolError(
            "This match has a result; it cannot be converted to a bye.",
            admin.update_match,
            self.eng_v_fra.pk,
            is_bye=True,
            clear_away_team=True,
        )
        self.assertToolError(
            "A live streamed match cannot be converted to a bye; remove the live "
            "stream first with disable_match_live_stream.",
            admin.update_match,
            self.aus_v_eng.pk,
            is_bye=True,
            clear_away_team=True,
        )
        one_team = (
            "A bye is one team with no opponent: exactly one side must have a team."
        )
        self.assertToolError(
            one_team, admin.update_match, self.fra_v_eng.pk, is_bye=True
        )
        self.assertToolError(
            one_team,
            admin.update_match,
            self.fra_v_eng.pk,
            is_bye=True,
            clear_home_team=True,
            clear_away_team=True,
        )
        self.assertToolError(
            "clear_away_team cannot be combined with giving the away side a team, "
            "an undecided team or an eval.",
            admin.update_match,
            self.fra_v_eng.pk,
            away_team_id=self.aus_men.pk,
            clear_away_team=True,
        )
        # The refused calls left the match exactly as it was.
        self.assertEqual(
            Match.objects.filter(pk=self.fra_v_eng.pk).values().get(), before
        )
        self.assertFalse(Match.objects.get(pk=self.eng_v_fra.pk).is_bye)
        self.assertFalse(Match.objects.get(pk=self.aus_v_eng.pk).is_bye)

    def test_convert_bye_to_match(self):
        # Australia's round 2 bye becomes a match against New Zealand, left
        # for the scheduler; once a bye has been processed (points awarded)
        # it stays a bye.
        admin = self.admin()
        self.assertToolError(
            "A match has two sides: give the away side a team, an undecided team "
            "or an eval.",
            admin.update_match,
            self.bye.pk,
            is_bye=False,
        )
        res = admin.update_match(
            self.bye.pk, is_bye=False, away_team_id=self.nzl_men.pk
        )
        self.assertEqual(
            res,
            {
                "saved": True,
                "live_stream_sync_queued": False,
                "match": {
                    "id": self.bye.pk,
                    "uuid": str(self.bye.uuid),
                    "competition": {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": self.competition.slug,
                    },
                    "season": {
                        "id": self.season.pk,
                        "title": "2026",
                        "slug": self.season.slug,
                    },
                    "division": {
                        "id": self.mens.pk,
                        "title": "Men's Open",
                        "slug": self.mens.slug,
                    },
                    "stage": {
                        "id": self.mens_pools.pk,
                        "title": "Pool Stage",
                        "slug": self.mens_pools.slug,
                    },
                    "pool": {
                        "id": self.pool_a.pk,
                        "title": "Pool A",
                        "slug": self.pool_a.slug,
                    },
                    "round": 2,
                    "label": None,
                    "datetime": None,
                    "date": "2026-07-15",
                    "time": None,
                    "timezone": "Europe/Amsterdam",
                    "home_team": {
                        "id": self.aus_men.pk,
                        "title": "Australia",
                        "slug": self.aus_men.slug,
                        "club": {
                            "id": self.australia.pk,
                            "title": "Australia",
                            "slug": self.australia.slug,
                        },
                    },
                    "away_team": {
                        "id": self.nzl_men.pk,
                        "title": "New Zealand",
                        "slug": self.nzl_men.slug,
                        "club": {
                            "id": self.new_zealand.pk,
                            "title": "New Zealand",
                            "slug": self.new_zealand.slug,
                        },
                    },
                    "home_team_score": None,
                    "away_team_score": None,
                    "status": "upcoming",
                    "winner": None,
                    "is_draw": False,
                    "live_stream": False,
                    "live_stream_url": None,
                    "videos": [],
                    "venue": None,
                    "ground": None,
                    "is_bye": False,
                    "is_forfeit": False,
                    "is_washout": False,
                    "bye_processed": False,
                    "include_in_ladder": True,
                    "youtube_broadcast_id": None,
                    "referees": [],
                },
            },
        )
        self.bye.refresh_from_db()
        self.assertFalse(self.bye.is_bye)
        self.assertEqual(self.bye.away_team, self.nzl_men)
        self.assertIsNone(self.bye.time)
        # Back to a bye, processed: it can no longer be turned into a match.
        admin.update_match(self.bye.pk, is_bye=True, clear_away_team=True)
        admin.record_match_result(self.bye.pk, bye_processed=True)
        before = Match.objects.filter(pk=self.bye.pk).values().get()
        self.assertToolError(
            "This bye has been processed; revert it with "
            "record_match_result(bye_processed=false) before turning it into a "
            "match.",
            admin.update_match,
            self.bye.pk,
            is_bye=False,
            away_team_id=self.nzl_men.pk,
        )
        self.assertEqual(Match.objects.filter(pk=self.bye.pk).values().get(), before)
        self.assertTrue(before["is_bye"])
        self.assertTrue(before["bye_processed"])
        self.assertIsNone(before["away_team_id"])

    def test_bye_flag_is_explicit_and_idempotent(self):
        # is_bye is a statement of what the match is, not a toggle: repeating
        # it is harmless, and a bye only changes kind when told to.
        admin = self.admin()
        # Restating what a match already is changes nothing: the database
        # row is identical afterwards and the response is the ordinary saved
        # match (its scheduled fields carry the fixture's random time zone, so
        # the row, not a literal, is the reference here).
        before = Match.objects.filter(pk=self.fra_v_eng.pk).values().get()
        res = admin.update_match(self.fra_v_eng.pk, is_bye=False)
        self.assertEqual(
            Match.objects.filter(pk=self.fra_v_eng.pk).values().get(), before
        )
        self.assertEqual(
            {k: v for k, v in res.items() if k != "match"},
            {"saved": True, "live_stream_sync_queued": False},
        )
        self.assertEqual(res["match"]["id"], self.fra_v_eng.pk)
        before = Match.objects.filter(pk=self.bye.pk).values().get()
        res = admin.update_match(self.bye.pk, is_bye=True)
        self.assertEqual(Match.objects.filter(pk=self.bye.pk).values().get(), before)
        self.assertEqual(
            {k: v for k, v in res.items() if k != "match"},
            {"saved": True, "live_stream_sync_queued": False},
        )
        self.assertEqual(res["match"]["id"], self.bye.pk)
        # A bye is not given an opponent without is_bye=false ...
        one_team = (
            "A bye is one team with no opponent: exactly one side must have a team."
        )
        self.assertToolError(
            one_team, admin.update_match, self.bye.pk, away_team_id=self.nzl_men.pk
        )
        # ... nor an undecided team or an eval while it stays a bye.
        other = (
            "A bye is one team with no opponent: it cannot have an undecided team "
            "or an eval."
        )
        self.assertToolError(
            other, admin.update_match, self.bye.pk, is_bye=True, away_team_eval="P1"
        )
        self.assertToolError(
            other,
            admin.update_match,
            self.bye.pk,
            is_bye=True,
            away_team_undecided_id=1,
        )
        self.assertEqual(Match.objects.filter(pk=self.bye.pk).values().get(), before)
        # The empty side of a bye can be an eval when it becomes a match: the
        # winner of England v France (round 1 of the same stage, which has no
        # label, so the side is titled just "Winner").
        res = admin.update_match(
            self.bye.pk,
            is_bye=False,
            away_team_eval="W",
            away_team_eval_related_id=self.eng_v_fra.pk,
        )
        self.assertEqual(
            res,
            {
                "saved": True,
                "live_stream_sync_queued": False,
                "match": {
                    "id": self.bye.pk,
                    "uuid": str(self.bye.uuid),
                    "competition": {
                        "id": self.competition.pk,
                        "title": "European Championships",
                        "slug": self.competition.slug,
                    },
                    "season": {
                        "id": self.season.pk,
                        "title": "2026",
                        "slug": self.season.slug,
                    },
                    "division": {
                        "id": self.mens.pk,
                        "title": "Men's Open",
                        "slug": self.mens.slug,
                    },
                    "stage": {
                        "id": self.mens_pools.pk,
                        "title": "Pool Stage",
                        "slug": self.mens_pools.slug,
                    },
                    "pool": {
                        "id": self.pool_a.pk,
                        "title": "Pool A",
                        "slug": self.pool_a.slug,
                    },
                    "round": 2,
                    "label": None,
                    "datetime": None,
                    "date": "2026-07-15",
                    "time": None,
                    "timezone": "Europe/Amsterdam",
                    "home_team": {
                        "id": self.aus_men.pk,
                        "title": "Australia",
                        "slug": self.aus_men.slug,
                        "club": {
                            "id": self.australia.pk,
                            "title": "Australia",
                            "slug": self.australia.slug,
                        },
                    },
                    "away_team": {
                        "id": None,
                        "title": "Winner",
                        "slug": None,
                        "club": None,
                        "eval": "W",
                        "eval_related_id": self.eng_v_fra.pk,
                    },
                    "home_team_score": None,
                    "away_team_score": None,
                    "status": "upcoming",
                    "winner": None,
                    "is_draw": False,
                    "live_stream": False,
                    "live_stream_url": None,
                    "videos": [],
                    "venue": None,
                    "ground": None,
                    "is_bye": False,
                    "is_forfeit": False,
                    "is_washout": False,
                    "bye_processed": False,
                    "include_in_ladder": True,
                    "youtube_broadcast_id": None,
                    "referees": [],
                },
            },
        )
        self.bye.refresh_from_db()
        self.assertFalse(self.bye.is_bye)
        self.assertEqual(self.bye.away_team_eval, "W")
        self.assertEqual(self.bye.away_team_eval_related, self.eng_v_fra)


@freeze_time(NOW)
class ResultTests(AdminFixtureMixin, TestCase):
    def test_awaiting_results(self):
        admin = self.admin()
        Match.objects.filter(pk=self.eng_v_fra.pk).update(
            home_team_score=None, away_team_score=None
        )
        res = admin.list_matches_awaiting_results(season_id=self.season.pk)
        # The bye on 15 July is after the last day played, so the dashboard
        # does not list it yet.
        self.assertEqual([m["id"] for m in res["matches"]], [self.eng_v_fra.pk])
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["matches"][0]["status"], "awaiting_result")
        res = admin.list_matches_awaiting_results(division_id=self.womens.pk)
        self.assertEqual(res["matches"], [])
        res = admin.list_matches_awaiting_results(date=datetime.date(2026, 7, 14))
        self.assertEqual([m["id"] for m in res["matches"]], [self.eng_v_fra.pk])

    def test_awaiting_results_excludes_mysideline(self):
        admin = self.admin()
        Match.objects.filter(pk=self.eng_v_fra.pk).update(
            home_team_score=None, away_team_score=None, mysideline_id=12345
        )
        res = admin.list_matches_awaiting_results(season_id=self.season.pk)
        self.assertEqual(res["matches"], [])
        self.assertEqual(res["total"], 0)

    def test_record_and_revise(self):
        admin = self.admin()
        res = admin.record_match_result(
            self.eng_v_fra.pk, home_team_score=4, away_team_score=4
        )
        self.assertEqual(res["match"]["status"], "completed")
        self.assertEqual(res["match"]["is_draw"], True)
        res = admin.record_match_result(
            self.eng_v_fra.pk, home_team_score=6, away_team_score=4
        )
        self.assertEqual(res["match"]["winner"]["title"], "England")
        ladder = admin.get_ladder(stage_id=self.mens_pools.pk)["stages"][0]["pools"][1]
        self.assertEqual(
            [(e["team"]["title"], e["win"]) for e in ladder["ladder"]],
            [("England", 1), ("France", 0)],
        )
        self.assertEqual(
            admin.list_matches_awaiting_results(division_id=self.mens.pk)["total"], 0
        )

    def test_result_rules(self):
        admin = self.admin()
        Match.objects.filter(pk=self.eng_v_fra.pk).update(
            home_team_score=None, away_team_score=None
        )
        self.assertToolError(
            "Validation failed: away_team_score: Both scores are required.",
            admin.record_match_result,
            self.eng_v_fra.pk,
            home_team_score=4,
        )
        self.assertToolError(
            "bye_processed cannot be set for this match.",
            admin.record_match_result,
            self.eng_v_fra.pk,
            bye_processed=True,
        )
        self.assertToolError(
            "home_team_score cannot be set for this match.",
            admin.record_match_result,
            self.bye.pk,
            home_team_score=1,
        )
        res = admin.record_match_result(self.bye.pk, bye_processed=True)
        self.assertEqual(res["match"]["bye_processed"], True)

    def test_result_on_excluded_date(self):
        # The model rejects the date, which the result form does not offer;
        # the model's message is reported rather than a crash.
        factories.SeasonExclusionDateFactory.create(
            season=self.season, date=datetime.date(2026, 7, 14)
        )
        self.assertToolError(
            "Validation failed: date: This date has been excluded for this season.",
            self.admin().record_match_result,
            self.eng_v_fra.pk,
            home_team_score=1,
            away_team_score=0,
        )

    def test_forfeit(self):
        admin = self.admin()
        res = admin.record_match_result(
            self.eng_v_fra.pk,
            home_team_score=5,
            away_team_score=0,
            is_forfeit=True,
            forfeit_winner_id=self.eng_men.pk,
        )
        self.assertEqual(res["match"]["status"], "forfeit")
        self.assertEqual(res["match"]["is_forfeit"], True)
        self.eng_v_fra.refresh_from_db()
        self.assertEqual(self.eng_v_fra.forfeit_winner_id, self.eng_men.pk)
        self.assertToolError(
            "Validation failed: forfeit_winner: Select a valid choice. That choice "
            "is not one of the available choices.",
            admin.record_match_result,
            self.eng_v_fra.pk,
            is_forfeit=True,
            forfeit_winner_id=self.aus_men.pk,
        )
        res = admin.record_match_result(self.eng_v_fra.pk, is_forfeit=False)
        self.assertEqual(res["match"]["is_forfeit"], False)
        self.eng_v_fra.refresh_from_db()
        self.assertEqual(self.eng_v_fra.forfeit_winner_id, None)


@freeze_time(NOW)
@mock.patch("tournamentcontrol.competition.mcp.admin.sync_live_stream")
@mock.patch(
    "tournamentcontrol.competition.models.Season.youtube",
    new_callable=mock.PropertyMock,
)
class LiveStreamTests(AdminFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.season.live_stream_client_id = "client-id"
        cls.season.live_stream_client_secret = "client-secret"
        cls.season.save()
        cls.field1.live_stream = True
        cls.field1.external_identifier = "yt-field-1"
        cls.field1.stream_key = "key-field-1"
        cls.field1.save()
        cls.key = factories.LiveStreamKeyFactory.create(
            season=cls.season, title="Roaming camera"
        )
        cls.used_key = factories.LiveStreamKeyFactory.create(
            season=cls.season, title="Presentation"
        )
        cls.event = factories.LiveStreamEventFactory.create(
            season=cls.season,
            title="Opening ceremony",
            stream_key=cls.used_key,
            start=datetime.datetime(2026, 7, 15, 18, 0, tzinfo=TZ),
            stop=datetime.datetime(2026, 7, 15, 19, 0, tzinfo=TZ),
        )

    def youtube(self, mock_youtube_prop):
        youtube = mock.MagicMock()
        mock_youtube_prop.return_value = youtube
        youtube.liveStreams.return_value.insert.return_value.execute.return_value = {
            "id": "yt-new",
            "cdn": {"ingestionInfo": {"streamName": "key-new"}},
        }
        youtube.liveStreams.return_value.update.return_value.execute.side_effect = (
            lambda: {
                "id": youtube.liveStreams.return_value.update.call_args.kwargs["body"][
                    "id"
                ],
                "cdn": {"ingestionInfo": {"streamName": "key-new"}},
            }
        )
        return youtube

    def test_lists(self, mock_youtube_prop, mock_sync):
        admin = self.admin()
        res = admin.list_season_stream_keys(self.season.pk)
        self.assertEqual(
            res["stream_keys"],
            [
                {
                    "id": self.used_key.pk,
                    "title": "Presentation",
                    "youtube_stream_id": self.used_key.pk,
                    "stream_key": self.used_key.stream_key,
                    "events": 1,
                },
                {
                    "id": self.key.pk,
                    "title": "Roaming camera",
                    "youtube_stream_id": self.key.pk,
                    "stream_key": self.key.stream_key,
                    "events": 0,
                },
            ],
        )
        res = admin.list_season_stream_events(self.season.pk)
        self.assertEqual(
            res["events"],
            [
                {
                    "id": self.event.pk,
                    "title": "Opening ceremony",
                    "description": None,
                    "start": "2026-07-15T18:00:00+02:00",
                    "stop": "2026-07-15T19:00:00+02:00",
                    "live_stream": True,
                    "stream_key": {"id": self.used_key.pk, "title": "Presentation"},
                    "youtube_broadcast_id": self.event.pk,
                    "video_url": "https://youtu.be/%s" % self.event.pk,
                }
            ],
        )
        res = admin.list_streamed_grounds(self.season.pk)
        self.assertEqual(len(res["grounds"]), 1)
        self.assertEqual(res["grounds"][0]["id"], self.field1.pk)
        self.assertEqual(res["grounds"][0]["youtube_stream_id"], "yt-field-1")
        self.assertEqual(res["grounds"][0]["stream_key"], "key-field-1")
        # aus_v_nzl (past, streamed) does not count; aus_v_eng and the final
        # are upcoming and streamed on field 1.
        self.assertEqual(res["grounds"][0]["upcoming_streamed_matches"], 2)

    def test_season_stream_keys(self, mock_youtube_prop, mock_sync):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        res = admin.create_season_stream_key(self.season.pk, title="Camera 3")
        self.assertEqual(
            res["stream_key"],
            {
                "id": "yt-new",
                "title": "Camera 3",
                "youtube_stream_id": "yt-new",
                "stream_key": "key-new",
                "events": 0,
            },
        )
        youtube.liveStreams.return_value.insert.assert_called_once_with(
            part="snippet,cdn",
            body={
                "snippet": {"title": "European Championships 2026 (Camera 3)"},
                "cdn": {
                    "ingestionType": "rtmp",
                    "frameRate": "variable",
                    "resolution": "variable",
                },
            },
        )
        self.assertEqual(
            LiveStreamKey.objects.get(pk="yt-new").season_id, self.season.pk
        )

        self.assertToolError(
            "This stream key is used by 1 live stream event; reassign or delete "
            "them first.",
            admin.delete_season_stream_key,
            self.season.pk,
            self.used_key.pk,
        )
        self.assertToolError(
            "Stream key nope was not found.",
            admin.delete_season_stream_key,
            self.season.pk,
            "nope",
        )
        res = admin.delete_season_stream_key(self.season.pk, "yt-new")
        self.assertEqual(res, {"deleted": "stream key Camera 3"})
        youtube.liveStreams.return_value.delete.assert_called_once_with(id="yt-new")
        self.assertEqual(LiveStreamKey.objects.filter(pk="yt-new").count(), 0)

        # Already gone on the platform is as good as deleted; any other
        # platform error keeps the record.
        youtube.liveStreams.return_value.delete.return_value.execute.side_effect = (
            _http_error(404)
        )
        self.assertEqual(
            admin.delete_season_stream_key(self.season.pk, self.key.pk),
            {"deleted": "stream key Roaming camera"},
        )
        youtube.liveStreams.return_value.delete.return_value.execute.side_effect = (
            _http_error(500)
        )
        admin.create_season_stream_key(self.season.pk, title="Camera 4")
        self.assertToolError(
            "YouTube API error: boom",
            admin.delete_season_stream_key,
            self.season.pk,
            "yt-new",
        )
        self.assertEqual(LiveStreamKey.objects.filter(pk="yt-new").count(), 1)

    def test_stream_keys_need_credentials_and_live_stream(
        self, mock_youtube_prop, mock_sync
    ):
        admin = self.admin()
        self.assertToolError(
            "Live streaming is not enabled for this season.",
            admin.create_season_stream_key,
            self.nationals_2026.pk,
            title="Camera",
        )
        self.season.live_stream_client_secret = None
        self.season.save()
        self.assertToolError(
            "YouTube credentials must be configured for this season before live "
            "streams can be managed.",
            admin.create_season_stream_key,
            self.season.pk,
            title="Camera",
        )

    def test_ground_live_stream(self, mock_youtube_prop, mock_sync):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        res = admin.enable_ground_live_stream(self.field2.pk)
        self.assertEqual(res["ground"]["live_stream"], True)
        self.assertEqual(res["ground"]["youtube_stream_id"], "yt-new")
        self.assertEqual(res["ground"]["stream_key"], "key-new")
        youtube.liveStreams.return_value.insert.assert_called_once_with(
            part="snippet,cdn",
            body={
                "snippet": {"title": "European Championships 2026 (Field 2)"},
                "cdn": {
                    "ingestionType": "rtmp",
                    "frameRate": "variable",
                    "resolution": "variable",
                },
            },
        )
        self.assertToolError(
            "This ground is already live streamed.",
            admin.enable_ground_live_stream,
            self.field2.pk,
        )
        self.assertEqual(
            [g["id"] for g in admin.list_streamed_grounds(self.season.pk)["grounds"]],
            [self.field1.pk, self.field2.pk],
        )

        # Renaming a streamed ground renames its stream.
        res = admin.update_ground(self.field2.pk, title="Field 2 (TV)")
        youtube.liveStreams.return_value.update.assert_called_once_with(
            part="snippet,cdn",
            body={
                "id": "yt-new",
                "snippet": {"title": "European Championships 2026 (Field 2 (TV))"},
                "cdn": {
                    "ingestionType": "rtmp",
                    "frameRate": "variable",
                    "resolution": "variable",
                },
            },
        )
        self.assertEqual(res["ground"]["title"], "Field 2 (TV)")

        # Field 1 has upcoming streamed matches, so it cannot be disabled.
        self.assertToolError(
            "2 upcoming matches on this ground are set to be live streamed; "
            "disable their live streams first.",
            admin.disable_ground_live_stream,
            self.field1.pk,
        )
        # Field 2 now has aus_v_nzl_women set to stream on it.
        self.assertToolError(
            "1 upcoming match on this ground is set to be live streamed; disable "
            "their live streams first.",
            admin.disable_ground_live_stream,
            self.field2.pk,
        )
        admin.disable_match_live_stream(self.aus_v_nzl_women.pk)
        res = admin.disable_ground_live_stream(self.field2.pk)
        self.assertEqual(res["ground"]["live_stream"], False)
        self.assertEqual(res["ground"]["youtube_stream_id"], None)
        self.assertEqual(res["ground"]["stream_key"], None)
        youtube.liveStreams.return_value.delete.assert_called_once_with(id="yt-new")
        self.assertToolError(
            "This ground is not live streamed.",
            admin.disable_ground_live_stream,
            self.field2.pk,
        )

    def test_create_ground_streamed(self, mock_youtube_prop, mock_sync):
        self.youtube(mock_youtube_prop)
        admin = self.admin()
        res = admin.create_ground(self.venue.pk, title="Field 3", live_stream=True)
        self.assertEqual(res["ground"]["stream_key"], "key-new")
        ground = Ground.objects.get(pk=res["ground"]["id"])
        self.assertEqual(ground.external_identifier, "yt-new")
        # Not a live streamed season: the flag is not offered.
        venue = factories.VenueFactory.create(
            season=self.nationals_2026, latlng="-33.8,151.2,10"
        )
        self.assertToolError(
            "live_stream cannot be set for this ground.",
            admin.create_ground,
            venue.pk,
            title="Court",
            live_stream=True,
        )
        res = admin.create_ground(venue.pk, title="Court")
        self.assertEqual(res["ground"]["live_stream"], False)

    def test_match_live_stream(self, mock_youtube_prop, mock_sync):
        admin = self.admin()
        # nzl_v_fra is on field 2, which is not streamed.
        self.assertToolError(
            "This match is not scheduled on a live streamed ground. Move it to a "
            "ground with a stream key (see list_streamed_grounds) or enable live "
            "streaming on its ground first.",
            admin.enable_match_live_stream,
            self.fra_v_eng.pk,
        )
        self.assertToolError(
            "This match is not set to be live streamed.",
            admin.disable_match_live_stream,
            self.fra_v_eng.pk,
        )
        res = admin.reschedule_match(self.fra_v_eng.pk, place_id=self.field1.pk)
        self.assertEqual(res["live_stream_sync_queued"], False)
        res = admin.enable_match_live_stream(self.fra_v_eng.pk)
        self.assertEqual(res["live_stream_sync_queued"], True)
        self.assertEqual(res["match"]["live_stream"], True)
        mock_sync.s.assert_called_once_with(self.fra_v_eng.pk, base_url=None)
        mock_sync.s.return_value.apply_async.assert_called_once_with()
        self.assertToolError(
            "This match is already set to be live streamed.",
            admin.enable_match_live_stream,
            self.fra_v_eng.pk,
        )

        # A streamed match cannot move off a streamed ground, but may move
        # between streamed grounds (its broadcast is resynchronised).
        self.assertToolError(
            "A live streamed match can only be played on a ground that is live "
            "streamed. Remove the live stream from the match first, or choose a "
            "streamed ground.",
            admin.reschedule_match,
            self.fra_v_eng.pk,
            place_id=self.field2.pk,
        )
        mock_sync.s.reset_mock()
        res = admin.reschedule_match(self.fra_v_eng.pk, time=datetime.time(18, 0))
        self.assertEqual(res["live_stream_sync_queued"], True)
        mock_sync.s.assert_called_once_with(self.fra_v_eng.pk, base_url=None)

        mock_sync.s.reset_mock()
        res = admin.disable_match_live_stream(self.fra_v_eng.pk)
        self.assertEqual(res["match"]["live_stream"], False)
        # No broadcast was ever created (the task is mocked), so there is
        # nothing to remove.
        self.assertEqual(res["live_stream_sync_queued"], False)
        mock_sync.s.assert_not_called()

        # A match with a broadcast always syncs when disabled.
        res = admin.disable_match_live_stream(self.aus_v_nzl.pk)
        self.assertEqual(res["live_stream_sync_queued"], True)
        mock_sync.s.assert_called_once_with(self.aus_v_nzl.pk, base_url=None)

    def test_live_stream_requires_season_flag(self, mock_youtube_prop, mock_sync):
        admin = self.admin()
        self.assertToolError(
            "Live streaming is not enabled for this season.",
            admin.enable_match_live_stream,
            self.old_match.pk,
        )
        self.assertToolError(
            "Live streaming is not enabled for this season.",
            admin.enable_ground_live_stream,
            factories.GroundFactory.create(venue__season=self.nationals_2026).pk,
        )


@mock.patch("tournamentcontrol.competition.mcp.admin.sync_live_stream_event")
@mock.patch(
    "tournamentcontrol.competition.models.Season.youtube",
    new_callable=mock.PropertyMock,
)
class LiveStreamEventTests(AdminFixtureMixin, TestCase):
    """The create, update and delete tools for ad-hoc live stream events."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.season.live_stream_client_id = "client-id"
        cls.season.live_stream_client_secret = "client-secret"
        cls.season.save()
        cls.key = factories.LiveStreamKeyFactory.create(
            season=cls.season, title="Roaming camera"
        )
        cls.other_key = factories.LiveStreamKeyFactory.create(
            season=cls.nationals_2026, title="Elsewhere"
        )
        cls.event = factories.LiveStreamEventFactory.create(
            season=cls.season,
            title="Opening ceremony",
            start=datetime.datetime(2026, 7, 15, 18, 0, tzinfo=TZ),
            stop=datetime.datetime(2026, 7, 15, 19, 0, tzinfo=TZ),
        )

    def youtube(self, mock_youtube_prop):
        youtube = mock.MagicMock()
        mock_youtube_prop.return_value = youtube
        youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "yt-new-event",
        }
        return youtube

    def test_create(self, mock_youtube_prop, mock_sync):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        res = admin.create_season_stream_event(
            self.season.pk,
            title="Closing ceremony",
            description="Presentations and farewell.",
            start=datetime.datetime(2026, 7, 19, 17, 0, tzinfo=TZ),
            stop=datetime.datetime(2026, 7, 19, 18, 30, tzinfo=TZ),
            stream_key_id=self.key.pk,
        )
        self.assertEqual(res["saved"], True)
        self.assertEqual(res["live_stream_sync_queued"], True)
        self.assertEqual(
            res["event"],
            {
                "id": "yt-new-event",
                "title": "Closing ceremony",
                "description": "Presentations and farewell.",
                "start": "2026-07-19T17:00:00+02:00",
                "stop": "2026-07-19T18:30:00+02:00",
                "live_stream": True,
                "stream_key": {"id": self.key.pk, "title": "Roaming camera"},
                "youtube_broadcast_id": "yt-new-event",
                "video_url": "https://youtu.be/yt-new-event",
            },
        )
        youtube.liveBroadcasts.return_value.insert.assert_called_once_with(
            part="id,snippet,status,contentDetails",
            body={
                "snippet": {
                    "title": "Closing ceremony",
                    "description": "Presentations and farewell.",
                    "scheduledStartTime": "2026-07-19T15:00:00+00:00",
                    "scheduledEndTime": "2026-07-19T16:30:00+00:00",
                },
                "status": {
                    "privacyStatus": self.season.live_stream_privacy,
                    "selfDeclaredMadeForKids": False,
                },
                "contentDetails": {
                    "enableAutoStart": False,
                    "enableAutoStop": False,
                    "monitorStream": {
                        "broadcastStreamDelayMs": 0,
                        "enableMonitorStream": True,
                    },
                },
            },
        )
        mock_sync.s.assert_called_once_with("yt-new-event")
        mock_sync.s.return_value.apply_async.assert_called_once_with()
        event = LiveStreamEvent.objects.get(pk="yt-new-event")
        self.assertEqual(event.season_id, self.season.pk)
        self.assertEqual(event.stream_key_id, self.key.pk)
        self.assertEqual(
            [
                e["id"]
                for e in admin.list_season_stream_events(self.season.pk)["events"]
            ],
            [self.event.pk, "yt-new-event"],
        )

    def test_create_naive_times_are_in_the_season_zone(
        self, mock_youtube_prop, mock_sync
    ):
        self.youtube(mock_youtube_prop)
        admin = self.admin()
        res = admin.create_season_stream_event(
            self.season.pk,
            title="Welcome",
            start=datetime.datetime(2026, 7, 13, 9, 0),
            stop=datetime.datetime(2026, 7, 13, 9, 45),
        )
        self.assertEqual(res["event"]["start"], "2026-07-13T09:00:00+02:00")
        self.assertEqual(res["event"]["stop"], "2026-07-13T09:45:00+02:00")
        self.assertEqual(res["event"]["description"], None)
        self.assertEqual(res["event"]["stream_key"], None)

    def test_create_rules(self, mock_youtube_prop, mock_sync):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        start = datetime.datetime(2026, 7, 19, 17, 0, tzinfo=TZ)
        self.assertToolError(
            "Validation failed: stop: The scheduled finish must be after the "
            "scheduled start.",
            admin.create_season_stream_event,
            self.season.pk,
            title="Backwards",
            start=start,
            stop=start,
        )
        self.assertToolError(
            "Validation failed: stream_key: Select a valid choice. That choice is "
            "not one of the available choices.",
            admin.create_season_stream_event,
            self.season.pk,
            title="Wrong key",
            start=start,
            stop=start + datetime.timedelta(hours=1),
            stream_key_id=self.other_key.pk,
        )
        self.assertToolError(
            "Live streaming is not enabled for this season.",
            admin.create_season_stream_event,
            self.nationals_2026.pk,
            title="Elsewhere",
            start=start,
            stop=start + datetime.timedelta(hours=1),
        )
        # Nothing was created on the platform for a refused request.
        youtube.liveBroadcasts.return_value.insert.assert_not_called()
        self.assertEqual(LiveStreamEvent.objects.count(), 1)

        # A rejection by YouTube is reported and nothing is saved.
        youtube.liveBroadcasts.return_value.insert.return_value.execute.side_effect = (
            _http_error(400)
        )
        self.assertToolError(
            "YouTube API error: boom",
            admin.create_season_stream_event,
            self.season.pk,
            title="Rejected",
            start=start,
            stop=start + datetime.timedelta(hours=1),
        )
        self.assertEqual(LiveStreamEvent.objects.count(), 1)
        mock_sync.s.assert_not_called()

        self.season.live_stream_client_secret = None
        self.season.save()
        self.assertToolError(
            "YouTube credentials must be configured for this season before live "
            "streams can be managed.",
            admin.create_season_stream_event,
            self.season.pk,
            title="No credentials",
            start=start,
            stop=start + datetime.timedelta(hours=1),
        )

    def test_update(self, mock_youtube_prop, mock_sync):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        # The event's row is held while it is saved, so the save cannot race
        # a concurrent deletion or synchronisation of the event.
        with CaptureQueriesContext(connection) as ctx:
            res = admin.update_season_stream_event(
                self.season.pk,
                self.event.pk,
                title="Opening Ceremony",
                description="Welcome to Nottingham.",
                stop=datetime.datetime(2026, 7, 15, 19, 30, tzinfo=TZ),
                stream_key_id=self.key.pk,
            )
        self.assertEqual(
            1,
            len(
                [
                    q["sql"]
                    for q in ctx.captured_queries
                    if "FOR UPDATE" in q["sql"]
                    and '"competition_livestreamevent"' in q["sql"]
                ]
            ),
        )
        self.assertEqual(res["saved"], True)
        self.assertEqual(res["live_stream_sync_queued"], True)
        self.assertEqual(
            res["event"],
            {
                "id": self.event.pk,
                "title": "Opening Ceremony",
                "description": "Welcome to Nottingham.",
                "start": "2026-07-15T18:00:00+02:00",
                "stop": "2026-07-15T19:30:00+02:00",
                "live_stream": True,
                "stream_key": {"id": self.key.pk, "title": "Roaming camera"},
                "youtube_broadcast_id": self.event.pk,
                "video_url": "https://youtu.be/%s" % self.event.pk,
            },
        )
        # The broadcast is brought into line by the queued synchronisation,
        # not by the tool itself.
        youtube.liveBroadcasts.assert_not_called()
        mock_sync.s.assert_called_once_with(self.event.pk)
        mock_sync.s.return_value.apply_async.assert_called_once_with()

        # An empty stream key id clears the key; a withdrawn event keeps
        # its record.
        mock_sync.s.reset_mock()
        res = admin.update_season_stream_event(
            self.season.pk, self.event.pk, stream_key_id="", live_stream=False
        )
        self.assertEqual(res["event"]["stream_key"], None)
        self.assertEqual(res["event"]["live_stream"], False)
        mock_sync.s.assert_called_once_with(self.event.pk)

        self.assertToolError(
            "Validation failed: stop: The scheduled finish must be after the "
            "scheduled start.",
            admin.update_season_stream_event,
            self.season.pk,
            self.event.pk,
            start=datetime.datetime(2026, 7, 15, 20, 0, tzinfo=TZ),
        )
        self.assertToolError(
            "Live stream event nope was not found.",
            admin.update_season_stream_event,
            self.season.pk,
            "nope",
            title="Nope",
        )
        self.assertToolError(
            "Live stream event %s was not found." % self.event.pk,
            admin.update_season_stream_event,
            self.nationals_2026.pk,
            self.event.pk,
            title="Wrong season",
        )

    def test_update_without_credentials_does_not_queue(
        self, mock_youtube_prop, mock_sync
    ):
        self.season.live_stream_client_secret = None
        self.season.save()
        admin = self.admin()
        res = admin.update_season_stream_event(
            self.season.pk, self.event.pk, title="Renamed"
        )
        self.assertEqual(res["event"]["title"], "Renamed")
        self.assertEqual(res["live_stream_sync_queued"], False)
        mock_sync.s.assert_not_called()

    def test_delete(self, mock_youtube_prop, mock_sync):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        self.assertToolError(
            "Live stream event nope was not found.",
            admin.delete_season_stream_event,
            self.season.pk,
            "nope",
        )
        # Any platform error other than "already gone" keeps the record.
        youtube.liveBroadcasts.return_value.delete.return_value.execute.side_effect = (
            _http_error(500)
        )
        self.assertToolError(
            "YouTube API error: boom",
            admin.delete_season_stream_event,
            self.season.pk,
            self.event.pk,
        )
        self.assertEqual(LiveStreamEvent.objects.filter(pk=self.event.pk).count(), 1)

        youtube.liveBroadcasts.return_value.delete.return_value.execute.side_effect = (
            _http_error(404)
        )
        # The event's row is held while the broadcast and then the record are
        # removed, so a queued synchronisation cannot run in between.
        with CaptureQueriesContext(connection) as ctx:
            res = admin.delete_season_stream_event(self.season.pk, self.event.pk)
        self.assertEqual(res, {"deleted": "live stream event Opening ceremony"})
        self.assertEqual(
            1,
            len(
                [
                    q["sql"]
                    for q in ctx.captured_queries
                    if "FOR UPDATE" in q["sql"]
                    and '"competition_livestreamevent"' in q["sql"]
                ]
            ),
        )
        youtube.liveBroadcasts.return_value.delete.assert_called_with(id=self.event.pk)
        self.assertEqual(LiveStreamEvent.objects.filter(pk=self.event.pk).count(), 0)

    def test_permissions(self, mock_youtube_prop, mock_sync):
        self.youtube(mock_youtube_prop)
        admin = self.admin(self.staff)
        start = datetime.datetime(2026, 7, 19, 17, 0, tzinfo=TZ)
        self.assertToolError(
            "Permission denied: add live stream event requires the "
            "competition.add_livestreamevent permission.",
            admin.create_season_stream_event,
            self.season.pk,
            title="Closing ceremony",
            start=start,
            stop=start + datetime.timedelta(hours=1),
        )
        self.assertToolError(
            "Permission denied: change live stream event requires the "
            "competition.change_livestreamevent permission for this live stream "
            "event.",
            admin.update_season_stream_event,
            self.season.pk,
            self.event.pk,
            title="Renamed",
        )
        self.assertToolError(
            "Permission denied: delete live stream event requires the "
            "competition.delete_livestreamevent permission for this live stream "
            "event.",
            admin.delete_season_stream_event,
            self.season.pk,
            self.event.pk,
        )
        self.assertToolError(
            "Permission denied: change live stream event requires the "
            "competition.change_livestreamevent permission for this live stream "
            "event.",
            admin.resync_season_stream_event,
            self.season.pk,
            self.event.pk,
        )
        assign_perm("competition.change_livestreamevent", self.staff, self.event)
        res = admin.update_season_stream_event(
            self.season.pk, self.event.pk, title="Renamed"
        )
        self.assertEqual(res["event"]["title"], "Renamed")


@mock.patch("tournamentcontrol.competition.tasks.set_live_stream_event_thumbnail")
@mock.patch("tournamentcontrol.competition.tasks.set_youtube_thumbnail")
@mock.patch(
    "tournamentcontrol.competition.models.Season.youtube",
    new_callable=mock.PropertyMock,
)
class LiveStreamResyncTests(AdminFixtureMixin, TestCase):
    """
    The resync tools run the broadcast synchronisation of the celery tasks
    in the request, so the outcome (and any YouTube rejection) is reported
    in the result.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.season.live_stream_client_id = "client-id"
        cls.season.live_stream_client_secret = "client-secret"
        cls.season.save()
        cls.field1.live_stream = True
        cls.field1.external_identifier = "yt-field-1"
        cls.field1.stream_key = "key-field-1"
        cls.field1.save()
        cls.key = factories.LiveStreamKeyFactory.create(
            season=cls.season, title="Roaming camera"
        )
        cls.event = factories.LiveStreamEventFactory.create(
            season=cls.season,
            title="Opening ceremony",
            stream_key=cls.key,
            start=datetime.datetime(2026, 7, 15, 18, 0, tzinfo=TZ),
            stop=datetime.datetime(2026, 7, 15, 19, 0, tzinfo=TZ),
        )

    def youtube(self, mock_youtube_prop):
        youtube = mock.MagicMock()
        mock_youtube_prop.return_value = youtube
        broadcasts = youtube.liveBroadcasts.return_value
        broadcasts.insert.return_value.execute.return_value = {"id": "yt-inserted"}
        broadcasts.bind.return_value.execute.side_effect = lambda: {
            "contentDetails": {
                "boundStreamId": broadcasts.bind.call_args.kwargs.get("streamId")
            }
        }
        return youtube

    def test_match_created_then_updated(
        self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail
    ):
        youtube = self.youtube(mock_youtube_prop)
        broadcasts = youtube.liveBroadcasts.return_value
        admin = self.admin()

        # aus_v_eng is set to stream but has no broadcast yet.
        res = admin.resync_match_live_stream(self.aus_v_eng.pk)
        self.assertEqual(res["saved"], True)
        self.assertEqual(res["action"], "created")
        self.assertEqual(res["youtube_broadcast_id"], "yt-inserted")
        self.assertEqual(res["video_url"], "https://youtu.be/yt-inserted")
        self.assertEqual(res["bound_stream_id"], "yt-field-1")
        self.assertEqual(res["match"]["id"], self.aus_v_eng.pk)
        self.assertEqual(res["match"]["youtube_broadcast_id"], "yt-inserted")
        self.assertEqual(
            res["match"]["live_stream_url"], "https://youtu.be/yt-inserted"
        )
        broadcasts.insert.assert_called_once()
        body = broadcasts.insert.call_args.kwargs["body"]
        self.assertEqual(
            body["snippet"]["scheduledStartTime"], "2026-07-16T13:00:00+00:00"
        )
        broadcasts.update.assert_not_called()
        broadcasts.bind.assert_called_once_with(
            part="id,snippet,contentDetails,status",
            id="yt-inserted",
            streamId="yt-field-1",
        )
        mock_thumbnail.s.assert_called_once_with(self.aus_v_eng.pk)
        self.aus_v_eng.refresh_from_db()
        self.assertEqual(self.aus_v_eng.external_identifier, "yt-inserted")
        self.assertEqual(self.aus_v_eng.live_stream_bind, "yt-field-1")

        # Running it again on the unchanged match updates the broadcast in
        # place and reports success.
        broadcasts.reset_mock()
        mock_thumbnail.reset_mock()
        res = admin.resync_match_live_stream(self.aus_v_eng.pk)
        self.assertEqual(res["action"], "updated")
        self.assertEqual(res["youtube_broadcast_id"], "yt-inserted")
        broadcasts.insert.assert_not_called()
        broadcasts.update.assert_called_once()
        self.assertEqual(
            broadcasts.update.call_args.kwargs["body"]["id"], "yt-inserted"
        )
        broadcasts.bind.assert_called_once()
        mock_thumbnail.s.assert_called_once_with(self.aus_v_eng.pk)

        # A match whose live stream was withdrawn has its broadcast removed.
        broadcasts.reset_mock()
        with mock.patch("tournamentcontrol.competition.mcp.admin.sync_live_stream"):
            admin.disable_match_live_stream(self.aus_v_eng.pk)
        res = admin.resync_match_live_stream(self.aus_v_eng.pk)
        self.assertEqual(res["action"], "removed")
        self.assertEqual(res["youtube_broadcast_id"], None)
        self.assertEqual(res["video_url"], None)
        self.assertEqual(res["bound_stream_id"], None)
        broadcasts.delete.assert_called_once_with(id="yt-inserted")
        self.assertToolError(
            "This match is not set to be live streamed.",
            admin.resync_match_live_stream,
            self.aus_v_eng.pk,
        )

    def test_match_youtube_errors_are_reported(
        self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail
    ):
        youtube = self.youtube(mock_youtube_prop)
        broadcasts = youtube.liveBroadcasts.return_value
        admin = self.admin()

        # A title that is too long is retried with short titles by the task;
        # when that is rejected too YouTube's own message is reported, not
        # swallowed.
        broadcasts.insert.return_value.execute.side_effect = _http_error(
            400, b'{"error": {"message": "The request title is too long"}}'
        )
        self.assertToolError(
            "YouTube API error: The request title is too long",
            admin.resync_match_live_stream,
            self.aus_v_eng.pk,
        )
        self.assertEqual(broadcasts.insert.call_count, 2)
        self.aus_v_eng.refresh_from_db()
        self.assertEqual(self.aus_v_eng.external_identifier, None)

        # Updating an existing broadcast can be rejected too.
        broadcasts.reset_mock()
        broadcasts.update.return_value.execute.side_effect = _http_error(403)
        self.assertToolError(
            "YouTube API error: boom",
            admin.resync_match_live_stream,
            self.aus_v_nzl.pk,
        )
        broadcasts.update.assert_called_once()

        # Expired authorisation is reported with the admin site's message.
        mock_youtube_prop.side_effect = RefreshError("expired")
        self.assertToolError(
            str(mcp_admin.YOUTUBE_AUTH_EXPIRED_MESSAGE),
            admin.resync_match_live_stream,
            self.aus_v_nzl.pk,
        )

    def test_match_rules(self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        self.assertToolError(
            "This match is not set to be live streamed.",
            admin.resync_match_live_stream,
            self.fra_v_eng.pk,
        )
        self.assertToolError(
            "Permission denied: change match requires the competition.change_match "
            "permission for this match.",
            self.admin(self.staff).resync_match_live_stream,
            self.aus_v_eng.pk,
        )
        # The final is the only match of its round, so it has no sibling to
        # borrow a kick-off time from once its own is cleared.
        Match.objects.filter(pk=self.final.pk).update(time=None, datetime=None)
        self.assertToolError(
            "Cannot resync a match without a scheduled date and time.",
            admin.resync_match_live_stream,
            self.final.pk,
        )
        self.season.live_stream_client_secret = None
        self.season.save()
        self.assertToolError(
            "YouTube credentials must be configured for this season before live "
            "streams can be managed.",
            admin.resync_match_live_stream,
            self.aus_v_nzl.pk,
        )
        youtube.liveBroadcasts.assert_not_called()

    def test_event(self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail):
        youtube = self.youtube(mock_youtube_prop)
        broadcasts = youtube.liveBroadcasts.return_value
        admin = self.admin()

        res = admin.resync_season_stream_event(self.season.pk, self.event.pk)
        self.assertEqual(res["saved"], True)
        self.assertEqual(res["action"], "updated")
        self.assertEqual(res["youtube_broadcast_id"], self.event.pk)
        self.assertEqual(res["video_url"], "https://youtu.be/%s" % self.event.pk)
        self.assertEqual(res["bound_stream_id"], self.key.pk)
        self.assertEqual(res["event"]["id"], self.event.pk)
        self.assertEqual(res["event"]["title"], "Opening ceremony")
        broadcasts.update.assert_called_once()
        body = broadcasts.update.call_args.kwargs["body"]
        self.assertEqual(body["id"], self.event.pk)
        self.assertEqual(body["snippet"]["title"], "Opening ceremony")
        self.assertEqual(
            body["snippet"]["scheduledStartTime"], "2026-07-15T16:00:00+00:00"
        )
        broadcasts.bind.assert_called_once_with(
            part="id,snippet,contentDetails,status",
            id=self.event.pk,
            streamId=self.key.pk,
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.live_stream_bind, self.key.pk)

        # Repeating it on the unchanged event is harmless.
        broadcasts.reset_mock()
        res = admin.resync_season_stream_event(self.season.pk, self.event.pk)
        self.assertEqual(res["action"], "updated")
        broadcasts.update.assert_called_once()

        # A YouTube rejection is reported.
        broadcasts.reset_mock()
        broadcasts.update.return_value.execute.side_effect = _http_error(400)
        self.assertToolError(
            "YouTube API error: boom",
            admin.resync_season_stream_event,
            self.season.pk,
            self.event.pk,
        )

        # A broadcast that no longer exists cannot be reinstated: the
        # identifier is the event's primary key.
        broadcasts.update.return_value.execute.side_effect = _http_error(404)
        self.assertToolError(
            "The YouTube broadcast of this live stream event no longer exists "
            "and cannot be reinstated; delete the event and create it again.",
            admin.resync_season_stream_event,
            self.season.pk,
            self.event.pk,
        )

        # A withdrawn event has its broadcast removed; already gone is fine.
        broadcasts.reset_mock()
        LiveStreamEvent.objects.filter(pk=self.event.pk).update(live_stream=False)
        broadcasts.delete.return_value.execute.side_effect = _http_error(404)
        res = admin.resync_season_stream_event(self.season.pk, self.event.pk)
        self.assertEqual(res["action"], "removed")
        self.assertEqual(res["youtube_broadcast_id"], self.event.pk)
        self.assertEqual(res["bound_stream_id"], None)
        broadcasts.delete.assert_called_once_with(id=self.event.pk)
        broadcasts.update.assert_not_called()

    def test_event_rules(self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail):
        youtube = self.youtube(mock_youtube_prop)
        admin = self.admin()
        self.assertToolError(
            "Live stream event nope was not found.",
            admin.resync_season_stream_event,
            self.season.pk,
            "nope",
        )
        self.assertToolError(
            "Live stream event %s was not found." % self.event.pk,
            admin.resync_season_stream_event,
            self.nationals_2026.pk,
            self.event.pk,
        )
        self.season.live_stream_client_secret = None
        self.season.save()
        self.assertToolError(
            "YouTube credentials must be configured for this season before live "
            "streams can be managed.",
            admin.resync_season_stream_event,
            self.season.pk,
            self.event.pk,
        )
        youtube.liveBroadcasts.assert_not_called()

    def _lock_queries(self, queries, table):
        return [
            q["sql"]
            for q in queries
            if "FOR UPDATE" in q["sql"] and '"%s"' % table in q["sql"]
        ]

    def test_match_resync_locks_the_match(
        self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail
    ):
        """
        A resync and any concurrent synchronisation of one match (another
        resync, or the queued task) are serialised on its row, so the second
        sees the broadcast the first created rather than inserting a
        duplicate.
        """
        self.youtube(mock_youtube_prop)
        admin = self.admin()
        with CaptureQueriesContext(connection) as ctx:
            res = admin.resync_match_live_stream(self.aus_v_eng.pk)
        self.assertEqual(res["action"], "created")
        self.assertEqual(
            1, len(self._lock_queries(ctx.captured_queries, "competition_match"))
        )

    def test_match_broadcast_kept_when_binding_fails(
        self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail
    ):
        """
        A broadcast inserted before a later step is rejected stays recorded
        against the match, so it is updated (not duplicated) by the next
        resync rather than orphaned on YouTube.
        """
        youtube = self.youtube(mock_youtube_prop)
        broadcasts = youtube.liveBroadcasts.return_value
        broadcasts.bind.return_value.execute.side_effect = _http_error(
            403, b'{"error": {"message": "The stream is already bound"}}'
        )
        admin = self.admin()
        self.assertToolError(
            "YouTube API error: The stream is already bound",
            admin.resync_match_live_stream,
            self.aus_v_eng.pk,
        )
        broadcasts.insert.assert_called_once()
        self.aus_v_eng.refresh_from_db()
        self.assertEqual(self.aus_v_eng.external_identifier, "yt-inserted")

        broadcasts.bind.return_value.execute.side_effect = lambda: {
            "contentDetails": {"boundStreamId": "yt-field-1"}
        }
        res = admin.resync_match_live_stream(self.aus_v_eng.pk)
        self.assertEqual(res["action"], "updated")
        self.assertEqual(res["youtube_broadcast_id"], "yt-inserted")
        broadcasts.insert.assert_called_once()

    def test_event_resync_locks_the_event(
        self, mock_youtube_prop, mock_thumbnail, mock_event_thumbnail
    ):
        self.youtube(mock_youtube_prop)
        admin = self.admin()
        with CaptureQueriesContext(connection) as ctx:
            res = admin.resync_season_stream_event(self.season.pk, self.event.pk)
        self.assertEqual(res["action"], "updated")
        self.assertEqual(
            1,
            len(
                self._lock_queries(ctx.captured_queries, "competition_livestreamevent")
            ),
        )


def _pkce():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


@freeze_time(NOW)
@override_settings(ROOT_URLCONF="vitriolic.urls")
class AdminMCPHTTPTests(AdminFixtureMixin, TestCase):
    """Drive the administration tools over the Streamable HTTP transport."""

    def rpc(self, method, params=None, id=1, expect=200, **extra):
        payload = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
        response = self.client.post(
            self.reverse("mcp-admin"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            **extra,
        )
        self.assertEqual(response.status_code, expect)
        if expect != 200:
            return response
        data = response.json()
        self.assertEqual(data["jsonrpc"], "2.0")
        self.assertEqual(data["id"], id)
        return data["result"]

    def test_anonymous_is_challenged(self):
        response = self.rpc("tools/list", expect=401)
        self.assertEqual(
            response["WWW-Authenticate"],
            'Bearer resource_metadata="http://testserver/.well-known/'
            'oauth-protected-resource/admin/mcp/"',
        )
        self.assertEqual(response.json()["error"], "unauthorized")
        response = self.rpc(
            "tools/list", expect=401, HTTP_AUTHORIZATION="Bearer not-a-token"
        )
        self.assertEqual(
            response["WWW-Authenticate"],
            'Bearer error="invalid_token", resource_metadata="http://testserver/'
            '.well-known/oauth-protected-resource/admin/mcp/"',
        )
        self.assertEqual(
            response.json()["error_description"],
            "The bearer token is invalid or has expired.",
        )

    def test_non_staff_is_forbidden(self):
        self.login(self.user)
        response = self.rpc("tools/list", expect=403)
        self.assertEqual(response.json()["error"], "forbidden")

    def test_tools_list(self):
        self.login(self.superuser)
        result = self.rpc("tools/list")
        by_name = {tool["name"]: tool for tool in result["tools"]}
        self.assertEqual(
            WRITE_TOOLS | READ_TOOLS, set(by_name) & (WRITE_TOOLS | READ_TOOLS)
        )
        # The read tools of the public server are available too.
        self.assertIn("list_matches", by_name)
        self.assertIn("whoami", by_name)
        for name in READ_TOOLS | {"list_matches", "whoami"}:
            with self.subTest(tool=name):
                self.assertEqual(by_name[name]["annotations"]["readOnlyHint"], True)
                self.assertEqual(by_name[name]["annotations"]["destructiveHint"], False)
        for name in WRITE_TOOLS:
            with self.subTest(tool=name):
                self.assertEqual(by_name[name]["annotations"]["readOnlyHint"], False)
                self.assertEqual(
                    by_name[name]["annotations"]["title"], by_name[name]["title"]
                )
        self.assertEqual(
            by_name["delete_match"]["annotations"]["destructiveHint"], True
        )
        self.assertEqual(
            by_name["create_match"]["annotations"]["destructiveHint"], False
        )
        self.assertEqual(
            by_name["enable_ground_live_stream"]["annotations"]["openWorldHint"], True
        )
        self.assertEqual(
            by_name["update_season"]["annotations"]["idempotentHint"], True
        )
        for name in ("resync_match_live_stream", "resync_season_stream_event"):
            with self.subTest(tool=name):
                self.assertEqual(by_name[name]["annotations"]["idempotentHint"], True)
                self.assertEqual(by_name[name]["annotations"]["openWorldHint"], True)
                self.assertEqual(by_name[name]["annotations"]["destructiveHint"], False)
        self.assertEqual(
            by_name["delete_season_stream_event"]["annotations"]["destructiveHint"],
            True,
        )
        self.assertEqual(
            by_name["create_season_stream_event"]["inputSchema"]["properties"]["start"],
            {"format": "date-time", "title": "Start", "type": "string"},
        )
        self.assertEqual(
            by_name["create_season"]["inputSchema"]["properties"]["mode"]["enum"],
            ["season", "tournament"],
        )
        self.assertEqual(
            by_name["reschedule_match"]["inputSchema"]["properties"]["time"]["anyOf"],
            [{"format": "time", "type": "string"}, {"type": "null"}],
        )
        self.assertEqual(
            by_name["swap_match_allocations"]["title"], "Swap match allocations"
        )

    def test_server_instructions(self):
        self.login(self.superuser)
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.assertEqual(result["serverInfo"]["name"], "vitriolic-admin")
        self.assertEqual(
            result["instructions"],
            "MCP server for the Tournament Control competition management system."
            "\n\n" + mcp_admin.ADMIN_INSTRUCTIONS + "\n\n" + mcp.INSTRUCTIONS,
        )

    def test_tools_call(self):
        self.login(self.superuser)
        result = self.rpc(
            "tools/call",
            {
                "name": "create_season",
                "arguments": {
                    "competition_id": self.competition.pk,
                    "title": "2028",
                    "start_date": "2028-06-01",
                    "timezone": "Europe/Paris",
                },
            },
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(result["structuredContent"]["season"]["title"], "2028")
        self.assertEqual(
            result["structuredContent"]["season"]["timezone"], "Europe/Paris"
        )
        self.assertEqual(
            Season.objects.get(title="2028").start_date, datetime.date(2028, 6, 1)
        )

        result = self.rpc(
            "tools/call",
            {
                "name": "reschedule_match",
                "arguments": {"match_id": self.fra_v_eng.pk, "time": "11:15"},
            },
        )
        self.assertEqual(result["structuredContent"]["match"]["time"], "11:15")

        # A refused call is an error result carrying the reason.
        result = self.rpc(
            "tools/call",
            {
                "name": "swap_match_allocations",
                "arguments": {
                    "match_id": self.aus_v_eng.pk,
                    "other_match_id": self.aus_v_nzl.pk,
                },
            },
        )
        self.assertEqual(result["isError"], True)
        self.assertEqual(
            result["content"][0]["text"],
            "Error executing tool swap_match_allocations: Match %d is live "
            "streamed; remove its live stream before swapping its allocation."
            % self.aus_v_eng.pk,
        )

    def test_draw_tools_over_http(self):
        """
        The list arguments of the batch tools are JSON objects; dates and
        times arrive as ISO strings.
        """
        self.login(self.superuser)
        tools = {t["name"]: t for t in self.rpc("tools/list")["tools"]}
        build_schema = tools["build_draw"]["inputSchema"]
        self.assertEqual(build_schema["required"], ["builds"])
        self.assertEqual(
            sorted(build_schema["$defs"]["BuildSpec"]["properties"]),
            [
                "alternate_home_away_on_repeat",
                "draw_format_id",
                "draw_format_text",
                "offset",
                "pool_id",
                "rounds",
                "stage_id",
                "start_date",
            ],
        )
        self.assertEqual(tools["build_draw"]["annotations"]["destructiveHint"], True)

        division = factories.DivisionFactory.create(season=self.season, order=4)
        stage = factories.StageFactory.create(division=division, order=1)
        factories.TeamFactory.create_batch(2, division=division)
        result = self.rpc(
            "tools/call",
            {
                "name": "build_draw",
                "arguments": {
                    "builds": [
                        {
                            "stage_id": stage.pk,
                            "draw_format_text": "ROUND\n1: 1 vs 2",
                            "start_date": "2026-07-20",
                        }
                    ]
                },
            },
        )
        self.assertEqual(result["isError"], False)
        build = result["structuredContent"]["builds"][0]
        self.assertEqual((build["matches"], build["first_date"]), (1, "2026-07-20"))
        result = self.rpc(
            "tools/call",
            {
                "name": "schedule_matches",
                "arguments": {
                    "items": [
                        {
                            "match_id": build["match_ids"][0],
                            "time": "10:00",
                            "place_id": self.field2.pk,
                        }
                    ]
                },
            },
        )
        self.assertEqual(result["isError"], False)
        self.assertEqual(result["structuredContent"]["matches"][0]["time"], "10:00")

    def test_plain_text_titles_over_http(self):
        """
        An ampersand sent over the wire is stored as it was sent: the
        server does not escape titles (an escaped "&amp;" seen in practice
        came from the client, and is decoded defensively).
        """
        self.login(self.superuser)
        for title, slug in (("Hit & Run", "hit-run"), ("Hit &amp; Miss", "hit-miss")):
            with self.subTest(title=title):
                result = self.rpc(
                    "tools/call",
                    {
                        "name": "create_team",
                        "arguments": {"division_id": self.womens.pk, "title": title},
                    },
                )
                team = result["structuredContent"]["team"]
                self.assertEqual(team["slug"], slug)
                self.assertEqual(
                    self.womens.teams.get(slug=slug).title, html.unescape(title)
                )

    def test_staff_permissions_apply_over_http(self):
        self.login(self.staff)
        result = self.rpc(
            "tools/call",
            {"name": "create_competition", "arguments": {"title": "Nope"}},
        )
        self.assertEqual(result["isError"], True)
        self.assertEqual(
            result["content"][0]["text"],
            "Error executing tool create_competition: Permission denied: add "
            "competition requires the competition.add_competition permission.",
        )


@freeze_time(NOW)
@override_settings(ROOT_URLCONF="vitriolic.urls")
class OAuthFlowTests(AdminFixtureMixin, TestCase):
    """
    The OAuth 2.1 flow an MCP client runs: discover the protected resource
    and authorization server metadata, register dynamically, authorize in
    the browser with PKCE, exchange the code, then call the tools with the
    bearer token.
    """

    def test_discovery(self):
        response = self.client.get("/.well-known/oauth-protected-resource/admin/mcp/")
        self.assertEqual(response.status_code, 200)
        metadata = response.json()
        self.assertEqual(metadata["resource"], "http://testserver/admin/mcp")
        self.assertEqual(metadata["authorization_servers"], ["http://testserver/o"])
        self.assertEqual(metadata["scopes_supported"], ["competition"])
        self.assertEqual(metadata["bearer_methods_supported"], ["header"])
        self.assertEqual(metadata["resource_name"], "Tournament Control")

        response = self.client.get("/.well-known/oauth-authorization-server/o")
        self.assertEqual(response.status_code, 200)
        metadata = response.json()
        self.assertEqual(metadata["issuer"], "http://testserver/o")
        self.assertEqual(
            metadata["authorization_endpoint"], "http://testserver/o/authorize/"
        )
        self.assertEqual(metadata["token_endpoint"], "http://testserver/o/token/")
        self.assertEqual(
            metadata["registration_endpoint"], "http://testserver/o/register/"
        )
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])
        self.assertIn("authorization_code", metadata["grant_types_supported"])
        self.assertIn("refresh_token", metadata["grant_types_supported"])
        self.assertIn("none", metadata["token_endpoint_auth_methods_supported"])

    def authorize(self, user, redirect_uri="http://localhost:43110/callback"):
        """Register a public client and authorize it as ``user``."""
        response = self.client.post(
            "/o/register/",
            data=json.dumps(
                {
                    "client_name": "Claude Code",
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        client = response.json()
        self.assertEqual(client["client_name"], "Claude Code")
        self.assertEqual(client["token_endpoint_auth_method"], "none")

        verifier, challenge = _pkce()
        params = {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "scope": "competition",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": "http://testserver/admin/mcp/",
        }
        # Anonymous: sent to the site's login page first.
        response = self.client.get("/o/authorize/", params)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response["Location"]).path, self.reverse("accounts:login")
        )

        self.login(user)
        response = self.client.get("/o/authorize/", params)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Claude Code")
        response = self.client.post(
            "/o/authorize/",
            dict(params, allow="Authorize"),
        )
        self.assertEqual(response.status_code, 302)
        location = urlparse(response["Location"])
        self.assertEqual(location.netloc, "localhost:43110")
        query = parse_qs(location.query)
        self.assertEqual(query["state"], ["xyz"])
        self.client.logout()

        response = self.client.post(
            "/o/token/",
            {
                "grant_type": "authorization_code",
                "code": query["code"][0],
                "redirect_uri": redirect_uri,
                "client_id": client["client_id"],
                "code_verifier": verifier,
                "resource": "http://testserver/admin/mcp/",
            },
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()
        self.assertEqual(token["token_type"], "Bearer")
        self.assertEqual(token["scope"], "competition")
        self.assertIn("refresh_token", token)
        return client, token

    def rpc(self, token, method, params=None, id=1):
        payload = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
        response = self.client.post(
            self.reverse("mcp-admin"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_AUTHORIZATION="Bearer %s" % token,
        )
        return response

    def test_authorization_code_flow(self):
        __, token = self.authorize(self.superuser)
        response = self.rpc(token["access_token"], "tools/call", {"name": "whoami"})
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]["structuredContent"]
        self.assertEqual(result["authenticated"], True)
        self.assertEqual(result["username"], self.superuser.username)

        response = self.rpc(
            token["access_token"],
            "tools/call",
            {
                "name": "update_season",
                "arguments": {"season_id": self.season.pk, "hashtag": "#E26"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["result"]["structuredContent"]["season"]["hashtag"], "#E26"
        )

    def test_refresh_token(self):
        client, token = self.authorize(self.superuser)
        response = self.client.post(
            "/o/token/",
            {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": client["client_id"],
            },
        )
        self.assertEqual(response.status_code, 200)
        refreshed = response.json()
        self.assertNotEqual(refreshed["access_token"], token["access_token"])
        response = self.rpc(refreshed["access_token"], "tools/list")
        self.assertEqual(response.status_code, 200)
        # The old access token was revoked by the rotation.
        response = self.rpc(token["access_token"], "tools/list")
        self.assertEqual(response.status_code, 401)

    def test_token_is_bound_to_the_resource(self):
        __, token = self.authorize(self.superuser)
        response = self.client.post(
            self.reverse("mcp"),
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "whoami"},
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json, text/event-stream",
            HTTP_AUTHORIZATION="Bearer %s" % token["access_token"],
        )
        # A token issued for /admin/mcp is not valid for /mcp, so the public
        # server treats the caller as anonymous.
        self.assertEqual(
            response.json()["result"]["structuredContent"]["authenticated"], False
        )

    def test_non_staff_token_is_forbidden(self):
        __, token = self.authorize(self.user)
        response = self.rpc(token["access_token"], "tools/list")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "forbidden")

    def test_staff_permissions_apply_to_tokens(self):
        __, token = self.authorize(self.staff)
        response = self.rpc(
            token["access_token"],
            "tools/call",
            {"name": "delete_match", "arguments": {"match_id": self.aus_v_eng.pk}},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["isError"], True)
        self.assertEqual(
            result["content"][0]["text"],
            "Error executing tool delete_match: Permission denied: delete match "
            "requires the competition.delete_match permission for this match.",
        )
        self.assertEqual(Match.objects.filter(pk=self.aus_v_eng.pk).count(), 1)
