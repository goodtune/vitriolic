"""
Tests for the administration MCP tools that build and schedule a draw: draw
formats, exclusion dates, time slots, the shared scheduling rules,
``build_draw``, the eval fields of ``create_match`` / ``update_match``,
``schedule_matches`` and ``auto_schedule``, compact responses, and the
title fixes (plain text titles, "TBA" placeholders).

The tools are called directly on the toolset with a fake request, as in
``test_mcp_admin``.
"""

import datetime
import itertools
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY
from django.db import connection
from django.test.utils import CaptureQueriesContext
from guardian.shortcuts import assign_perm
from mcp.server.mcpserver.exceptions import ToolError
from test_plus import TestCase

from tournamentcontrol.competition.draw.services import generate_stage_draw
from tournamentcontrol.competition.forms import DrawFormatForm, DrawGenerationForm
from tournamentcontrol.competition.mcp import admin as mcp_admin
from tournamentcontrol.competition.mcp.admin.scheduling import ScheduleValidator
from tournamentcontrol.competition.models import DrawFormat, Match, SeasonMatchTime
from tournamentcontrol.competition.tests import factories
from tournamentcontrol.competition.utils import round_robin_format

# Build the server before any test freezes time (see test_mcp_integration).
mcp_admin.get_admin_server()

TZ = ZoneInfo("Australia/Sydney")
WEDNESDAYS = [
    datetime.date(2026, 10, 7) + datetime.timedelta(weeks=n) for n in range(20)
]
CHRISTMAS = [
    datetime.date(2026, 12, 23),
    datetime.date(2026, 12, 30),
    datetime.date(2027, 1, 6),
]
FINALS_TEXT = (
    "ROUND Semi Finals\n"
    "1: P1 vs P4 Semi 1\n"
    "2: P2 vs P3 Semi 2\n"
    "ROUND Grand Final\n"
    "3: W1 vs W2 Final"
)


class DemoMixin:
    """
    The demo competition: a weekly season starting on Wednesday 7 October
    2026 at one venue with four grounds, and Men's (8 teams), Women's (6)
    and Mixed (10) divisions, each with a Regular Season and Finals stage.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = factories.SuperUserFactory.create()
        cls.staff = factories.UserFactory.create(is_staff=True)
        cls.season = cls.make_season("Demo League")
        cls.other_season = cls.make_season("Twin League")

    @classmethod
    def make_season(cls, title):
        competition = factories.CompetitionFactory.create(title=title)
        season = factories.SeasonFactory.create(
            competition=competition,
            title="2026/27",
            timezone=TZ,
            start_date=datetime.date(2026, 10, 7),
        )
        venue = factories.VenueFactory.create(
            season=season, title="Park", latlng="-33.8,151.2,14"
        )
        season.grounds = [
            factories.GroundFactory.create(venue=venue, title=f"Field {n}", order=n)
            for n in range(1, 5)
        ]
        season.divisions_by_title = {}
        for order, (division_title, count) in enumerate(
            (("Men's", 8), ("Women's", 6), ("Mixed", 10)), start=1
        ):
            division = factories.DivisionFactory.create(
                season=season, title=division_title, order=order
            )
            division.regular = factories.StageFactory.create(
                division=division, title="Regular Season", order=1
            )
            division.finals = factories.StageFactory.create(
                division=division, title="Finals", order=2, keep_ladder=False
            )
            division.team_list = [
                factories.TeamFactory.create(
                    division=division, title=f"{division_title} {n}", order=n
                )
                for n in range(1, count + 1)
            ]
            season.divisions_by_title[division_title] = division
        return season

    def admin(self, user=None):
        return mcp_admin.AdminToolset(
            request=SimpleNamespace(user=user or self.superuser)
        )

    @staticmethod
    def fresh(user):
        """The user without its cached permissions."""
        return type(user).objects.get(pk=user.pk)

    def assertToolError(self, message, callable, *args, **kwargs):
        with self.assertRaises(ToolError) as cm:
            callable(*args, **kwargs)
        self.assertEqual(str(cm.exception), message)
        return cm.exception

    def round_robin(self, teams):
        return factories.DrawFormatFactory.create(
            name=f"Round Robin ({teams} teams)",
            text=round_robin_format(teams),
            teams=teams,
        )

    def finals_format(self):
        return factories.DrawFormatFactory.create(
            name="Top 4 finals", text=FINALS_TEXT, teams=4, is_final=True
        )

    def regular_builds(self, season, rounds=12):
        formats = {n: self.round_robin(n) for n in (6, 8, 10)}
        return [
            {
                "stage_id": division.regular.pk,
                "draw_format_id": formats[len(division.team_list)].pk,
                "start_date": WEDNESDAYS[0],
                "rounds": rounds,
            }
            for division in season.divisions_by_title.values()
        ]


class DrawFormatToolTests(DemoMixin, TestCase):
    def test_create_preview_list_and_delete(self):
        admin = self.admin()
        text = round_robin_format(4)
        preview = admin.preview_draw_format(text, teams=4)["structure"]
        self.assertEqual(preview["round_count"], 3)
        self.assertEqual(preview["match_count"], 6)
        self.assertEqual(preview["pairings"], {"covered": 6, "possible": 6})
        self.assertEqual(preview["warnings"], [])
        self.assertEqual(
            preview["rounds"][0],
            {
                "round": 1,
                "label": None,
                "matches": [
                    {"id": "1", "home": "1", "away": "4", "label": None},
                    {"id": "2", "home": "2", "away": "3", "label": None},
                ],
            },
        )

        created = admin.create_draw_format(
            name="Round Robin (4 teams)", text=text, teams=4
        )["draw_format"]
        self.assertEqual(
            created,
            {
                "id": created["id"],
                "name": "Round Robin (4 teams)",
                "teams": 4,
                "is_final": False,
                "text": text,
            },
        )
        finals = admin.create_draw_format(
            name="Top 4 finals", text=FINALS_TEXT, teams=4, is_final=True
        )["draw_format"]
        six = admin.create_draw_format(
            name="Round Robin (6 teams)", text=round_robin_format(6), teams=6
        )["draw_format"]

        def names(**kwargs):
            return [
                f["name"] for f in admin.list_draw_formats(**kwargs)["draw_formats"]
            ]

        # The wizard's suitability rule: 3 teams round up to 4, and formats
        # for 4 or 3 teams suit.
        self.assertEqual(names(teams=3), ["Round Robin (4 teams)", "Top 4 finals"])
        self.assertEqual(names(teams=4, is_final=False), ["Round Robin (4 teams)"])
        self.assertEqual(names(teams=5), ["Round Robin (6 teams)"])
        self.assertEqual(names(is_final=True), ["Top 4 finals"])
        self.assertEqual(
            admin.list_draw_formats(teams=6, include_text=True)["draw_formats"],
            [six],
        )

        detail = admin.get_draw_format(finals["id"])["draw_format"]
        self.assertEqual(detail["structure"]["round_count"], 2)
        self.assertEqual(
            detail["structure"]["rounds"][1]["matches"],
            [{"id": "3", "home": "W1", "away": "W2", "label": "Final"}],
        )

        updated = admin.update_draw_format(created["id"], name="RR4")["draw_format"]
        self.assertEqual(updated["name"], "RR4")
        self.assertEqual(updated["text"], text)

        self.assertEqual(
            admin.delete_draw_format(created["id"]),
            {"deleted": "draw format RR4"},
        )
        self.assertEqual(DrawFormat.objects.filter(pk=created["id"]).count(), 0)

    def test_invalid_text_reports_the_form_error(self):
        admin = self.admin()
        text = "ROUND\n1: 1 vs 2\n2: 3 v 4\nROUND\n1: 1 vs 3"
        form = DrawFormatForm(data={"name": "Broken", "text": text, "teams": 4})
        self.assertEqual(
            form.errors["text"],
            ["Draw formula is invalid: line(s) '2, 4' are not in the correct format."],
        )
        message = (
            "Validation failed: text: Draw formula is invalid: line(s) '2, 4' are "
            "not in the correct format."
        )
        self.assertToolError(message, admin.preview_draw_format, text)
        self.assertToolError(
            message, admin.create_draw_format, name="Broken", text=text
        )
        self.assertEqual(DrawFormat.objects.count(), 0)
        self.assertToolError(
            "Validation failed: text: This field is required.",
            admin.preview_draw_format,
            "   ",
        )
        # A match must follow a ROUND line.
        orphan = "1: 1 vs 2\nROUND\n2: 1 vs 3"
        self.assertEqual(
            DrawFormatForm(data={"name": "Orphan", "text": orphan}).errors["text"],
            ["Draw formula is invalid: line(s) '0' are not in the correct format."],
        )
        for tool in (admin.preview_draw_format, admin.create_draw_format):
            with self.subTest(tool=tool.__name__):
                kwargs = {"name": "Orphan"} if tool == admin.create_draw_format else {}
                self.assertToolError(
                    "Validation failed: text: Draw formula is invalid: line(s) '0' "
                    "are not in the correct format.",
                    tool,
                    text=orphan,
                    **kwargs,
                )

    def test_preview_warnings(self):
        structure = self.admin().preview_draw_format(
            "ROUND\n1: 1 vs 2\n2: 1 vs 3\n3: W4 vs 4\nROUND\n4: 2 vs 3", teams=3
        )["structure"]
        self.assertEqual(
            structure["warnings"],
            [
                "Team 1 plays more than once in round 1.",
                "Match 3 refers to W4, but match 4 is not in an earlier round.",
                "Teams 4 are byes for 3 teams.",
            ],
        )
        self.assertEqual(structure["pairings"], {"covered": 3, "possible": 3})

    def test_deleting_a_format_leaves_built_matches(self):
        admin = self.admin()
        division = self.season.divisions_by_title["Women's"]
        draw_format = self.round_robin(6)
        admin.build_draw(
            [
                {
                    "stage_id": division.regular.pk,
                    "draw_format_id": draw_format.pk,
                    "start_date": WEDNESDAYS[0],
                }
            ]
        )
        before = list(division.regular.matches.values_list("pk", "round", "date"))
        self.assertEqual(len(before), 15)
        admin.delete_draw_format(draw_format.pk)
        self.assertEqual(
            list(division.regular.matches.values_list("pk", "round", "date")), before
        )

    def test_permissions(self):
        staff = self.admin(self.staff)
        draw_format = self.round_robin(4)
        self.assertEqual(
            [f["id"] for f in staff.list_draw_formats()["draw_formats"]],
            [draw_format.pk],
        )
        self.assertToolError(
            "Permission denied: add draw format requires the "
            "competition.add_drawformat permission.",
            staff.create_draw_format,
            name="X",
            text=FINALS_TEXT,
        )
        self.assertToolError(
            "Permission denied: delete draw format requires the "
            "competition.delete_drawformat permission for this draw format.",
            staff.delete_draw_format,
            draw_format.pk,
        )
        assign_perm("competition.delete_drawformat", self.staff)
        self.assertEqual(
            self.admin(self.fresh(self.staff)).delete_draw_format(draw_format.pk),
            {"deleted": "draw format Round Robin (4 teams)"},
        )


class ExclusionDateToolTests(DemoMixin, TestCase):
    def test_christmas_break_in_one_call(self):
        admin = self.admin()
        division = self.season.divisions_by_title["Men's"]
        home, away = division.team_list[:2]
        on_christmas = factories.MatchFactory.create(
            stage=division.regular,
            home_team=home,
            away_team=away,
            date=CHRISTMAS[0],
            time=None,
            datetime=None,
            round=12,
        )
        res = admin.add_season_exclusion_dates(self.season.pk, CHRISTMAS)
        self.assertEqual(res["added"], ["2026-12-23", "2026-12-30", "2027-01-06"])
        self.assertEqual(res["already_excluded"], [])
        self.assertEqual(
            [e["date"] for e in res["exclusion_dates"]],
            ["2026-12-23", "2026-12-30", "2027-01-06"],
        )
        # The match already on an excluded date is reported, not moved.
        self.assertEqual(
            res["matches_on_excluded_dates"],
            [
                {
                    "id": on_christmas.pk,
                    "round": 12,
                    "date": "2026-12-23",
                    "time": None,
                    "place_id": None,
                    "home_team_id": home.pk,
                    "away_team_id": away.pk,
                    "status": "upcoming",
                    "division_id": division.pk,
                }
            ],
        )
        on_christmas.refresh_from_db()
        self.assertEqual(on_christmas.date, CHRISTMAS[0])

        # Adding a date again is a no-op.
        res = admin.add_season_exclusion_dates(
            self.season.pk, [CHRISTMAS[0], datetime.date(2027, 1, 13)]
        )
        self.assertEqual(res["added"], ["2027-01-13"])
        self.assertEqual(res["already_excluded"], ["2026-12-23"])
        self.assertEqual(self.season.exclusions.count(), 4)

        res = admin.delete_season_exclusion_dates(
            self.season.pk, [datetime.date(2027, 1, 13), datetime.date(2027, 2, 1)]
        )
        self.assertEqual(res["deleted"], ["2027-01-13"])
        self.assertEqual(res["not_excluded"], ["2027-02-01"])
        self.assertEqual(
            [
                e["date"]
                for e in admin.list_season_exclusion_dates(self.season.pk)[
                    "exclusion_dates"
                ]
            ],
            ["2026-12-23", "2026-12-30", "2027-01-06"],
        )

    def test_adding_and_deleting_dates_locks_the_season(self):
        """
        The existing dates are read under the season lock the scheduling
        tools take (for a division's dates too), so concurrent calls adding
        or deleting the same date cannot both act on it, and no match is
        scheduled on a date while it is being excluded.
        """
        division = self.season.divisions_by_title["Mixed"]
        admin = self.admin()
        for tool, owner in (
            (admin.add_season_exclusion_dates, self.season),
            (admin.add_division_exclusion_dates, division),
            (admin.delete_season_exclusion_dates, self.season),
            (admin.delete_division_exclusion_dates, division),
        ):
            with self.subTest(tool=tool.__name__):
                with CaptureQueriesContext(connection) as queries:
                    tool(owner.pk, [CHRISTMAS[0]])
                self.assertEqual(
                    [
                        q["sql"].startswith('SELECT "competition_season"."id"')
                        for q in queries.captured_queries
                        if q["sql"].endswith("FOR UPDATE")
                    ],
                    [True],
                )

    def test_division_exclusions(self):
        admin = self.admin()
        division = self.season.divisions_by_title["Mixed"]
        admin.add_season_exclusion_dates(self.season.pk, [CHRISTMAS[0]])
        res = admin.add_division_exclusion_dates(division.pk, [WEDNESDAYS[2]])
        self.assertEqual(res["added"], ["2026-10-21"])
        self.assertEqual(res["matches_on_excluded_dates"], [])
        listing = admin.list_division_exclusion_dates(division.pk)
        self.assertEqual(
            [e["date"] for e in listing["exclusion_dates"]], ["2026-10-21"]
        )
        self.assertEqual(listing["season_exclusion_dates"], ["2026-12-23"])
        res = admin.delete_division_exclusion_dates(division.pk, [WEDNESDAYS[2]])
        self.assertEqual(res["deleted"], ["2026-10-21"])
        self.assertEqual(division.exclusions.count(), 0)

    def test_permissions(self):
        staff = self.admin(self.staff)
        self.assertToolError(
            "Permission denied: add exclusion date requires the "
            "competition.add_seasonexclusiondate permission.",
            staff.add_season_exclusion_dates,
            self.season.pk,
            CHRISTMAS,
        )
        self.assertToolError(
            "Permission denied: delete exclusion date requires the "
            "competition.delete_divisionexclusiondate permission.",
            staff.delete_division_exclusion_dates,
            self.season.divisions_by_title["Mixed"].pk,
            CHRISTMAS,
        )
        assign_perm("competition.add_seasonexclusiondate", self.staff)
        self.assertEqual(
            self.admin(self.fresh(self.staff)).add_season_exclusion_dates(
                self.season.pk, CHRISTMAS
            )["added"],
            ["2026-12-23", "2026-12-30", "2027-01-06"],
        )


class TimeslotToolTests(DemoMixin, TestCase):
    def test_weeknight_slots_from_one_rule(self):
        admin = self.admin()
        res = admin.create_timeslot(
            self.season.pk, start=datetime.time(18, 40), interval=50, count=3
        )
        self.assertEqual(res["times"], ["18:40", "19:30", "20:20"])
        self.assertEqual(
            res["timeslot"],
            {
                "id": res["timeslot"]["id"],
                "start": "18:40",
                "interval": 50,
                "count": 3,
                "start_date": None,
                "end_date": None,
            },
        )
        self.assertEqual(
            admin.get_timeslots(self.season.pk, date=WEDNESDAYS[0]),
            {
                "season": {
                    "id": self.season.pk,
                    "title": "2026/27",
                    "slug": self.season.slug,
                },
                "date": "2026-10-07",
                "rules": 1,
                "times": ["18:40", "19:30", "20:20"],
            },
        )
        self.assertEqual(
            admin.list_timeslots(self.season.pk)["timeslots"], [res["timeslot"]]
        )

        # A rule limited to the new year adds a late slot from then on.
        late = admin.create_timeslot(
            self.season.pk,
            start=datetime.time(21, 10),
            interval=50,
            count=1,
            start_date=datetime.date(2027, 1, 1),
        )["timeslot"]
        self.assertEqual(
            admin.get_timeslots(self.season.pk, date=WEDNESDAYS[0])["times"],
            ["18:40", "19:30", "20:20"],
        )
        self.assertEqual(
            admin.get_timeslots(self.season.pk, date=datetime.date(2027, 1, 13))[
                "times"
            ],
            ["18:40", "19:30", "20:20", "21:10"],
        )
        updated = admin.update_timeslot(late["id"], count=2)["timeslot"]
        self.assertEqual(updated["count"], 2)
        self.assertEqual(
            admin.delete_timeslot(late["id"]), {"deleted": f"time slot {late['id']}"}
        )
        self.assertEqual(self.season.timeslots.count(), 1)

    def test_validation_and_permissions(self):
        admin = self.admin()
        self.assertToolError(
            "Validation failed: interval: The interval must be at least 1 minute.",
            admin.create_timeslot,
            self.season.pk,
            start=datetime.time(18, 40),
            interval=0,
            count=3,
        )
        self.assertToolError(
            "Validation failed: end_date: The rule cannot end before it starts.",
            admin.create_timeslot,
            self.season.pk,
            start=datetime.time(18, 40),
            interval=50,
            count=3,
            start_date=datetime.date(2027, 1, 1),
            end_date=datetime.date(2026, 1, 1),
        )
        self.assertToolError(
            "Permission denied: add time slot requires the "
            "competition.add_seasonmatchtime permission.",
            self.admin(self.staff).create_timeslot,
            self.season.pk,
            start=datetime.time(18, 40),
            interval=50,
            count=3,
        )
        self.assertEqual(SeasonMatchTime.objects.count(), 0)


class ScheduleRuleTests(DemoMixin, TestCase):
    """Item 4: one set of date and time rules on every path."""

    def setUp(self):
        super().setUp()
        self.division = self.season.divisions_by_title["Women's"]
        self.home, self.away = self.division.team_list[:2]
        self.field = self.season.grounds[0]
        self.match = factories.MatchFactory.create(
            stage=self.division.regular,
            home_team=self.home,
            away_team=self.away,
            date=WEDNESDAYS[1],
            time=None,
            datetime=None,
            round=2,
        )

    def test_excluded_dates_on_every_path(self):
        admin = self.admin()
        factories.SeasonExclusionDateFactory.create(
            season=self.season, date=CHRISTMAS[0]
        )
        factories.DivisionExclusionDateFactory.create(
            division=self.division, date=WEDNESDAYS[3]
        )
        season_message = (
            "Validation failed: date: This date has been excluded for this season."
        )
        division_message = (
            "Validation failed: date: This date has been excluded for this division."
        )
        for ignore_clashes in (False, True):
            with self.subTest(ignore_clashes=ignore_clashes):
                self.assertToolError(
                    season_message,
                    admin.reschedule_match,
                    self.match.pk,
                    date=CHRISTMAS[0],
                    ignore_clashes=ignore_clashes,
                )
                self.assertToolError(
                    division_message,
                    admin.reschedule_match,
                    self.match.pk,
                    date=WEDNESDAYS[3],
                    ignore_clashes=ignore_clashes,
                )
                self.assertToolError(
                    division_message,
                    admin.create_match,
                    self.division.regular.pk,
                    home_team_id=self.home.pk,
                    away_team_id=self.away.pk,
                    date=WEDNESDAYS[3],
                    time=datetime.time(18, 40),
                    ignore_clashes=ignore_clashes,
                )
                self.assertToolError(
                    "Nothing was scheduled: 1 of 1 item failed.\n"
                    f"item 0 (match {self.match.pk}): {season_message}",
                    admin.schedule_matches,
                    [{"match_id": self.match.pk, "date": CHRISTMAS[0]}],
                    ignore_clashes=ignore_clashes,
                )
        self.match.refresh_from_db()
        self.assertEqual(self.match.date, WEDNESDAYS[1])
        self.assertEqual(self.division.regular.matches.count(), 1)

    def test_time_slots(self):
        admin = self.admin()
        # No rules: any time is allowed.
        res = admin.reschedule_match(self.match.pk, time=datetime.time(19, 0))
        self.assertEqual(res["match"]["time"], "19:00")

        factories.SeasonMatchTimeFactory.create(
            season=self.season, start=datetime.time(18, 40), interval=50, count=3
        )
        message = (
            "Validation failed: time: 19:00 is not a time slot on 2026-10-14; "
            "valid: 18:40, 19:30, 20:20."
        )
        for ignore_clashes in (False, True):
            with self.subTest(ignore_clashes=ignore_clashes):
                self.assertToolError(
                    message,
                    admin.reschedule_match,
                    self.match.pk,
                    time=datetime.time(19, 0),
                    ignore_clashes=ignore_clashes,
                )
                self.assertToolError(
                    message,
                    admin.create_match,
                    self.division.regular.pk,
                    home_team_id=self.division.team_list[2].pk,
                    away_team_id=self.division.team_list[3].pk,
                    date=WEDNESDAYS[1],
                    time=datetime.time(19, 0),
                    ignore_clashes=ignore_clashes,
                )
        res = admin.reschedule_match(
            self.match.pk, time=datetime.time(19, 30), place_id=self.field.pk
        )
        self.assertEqual(res["match"]["datetime"], "2026-10-14T19:30:00+11:00")
        # Moving the date re-checks the time against the new date's slots.
        factories.SeasonMatchTimeFactory.create(
            season=self.season,
            start=datetime.time(21, 10),
            interval=50,
            count=1,
            start_date=datetime.date(2027, 1, 1),
        )
        res = admin.reschedule_match(
            self.match.pk, date=datetime.date(2027, 1, 13), time=datetime.time(21, 10)
        )
        self.assertEqual(res["match"]["time"], "21:10")
        self.assertToolError(
            "Validation failed: time: 21:10 is not a time slot on 2026-10-21; "
            "valid: 18:40, 19:30, 20:20.",
            admin.reschedule_match,
            self.match.pk,
            date=WEDNESDAYS[2],
        )

    def test_team_preferences_and_clashes(self):
        admin = self.admin()
        self.home.timeslots_after = datetime.time(19, 0)
        self.home.save()
        self.assertToolError(
            f"Validation failed: time: {self.home.title} must play after 19:00.",
            admin.reschedule_match,
            self.match.pk,
            time=datetime.time(18, 40),
        )
        # As in the admin scheduler, ignore_clashes waives preferences.
        res = admin.reschedule_match(
            self.match.pk, time=datetime.time(18, 40), ignore_clashes=True
        )
        self.assertEqual(res["match"]["time"], "18:40")


class BuildDrawTests(DemoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin_tools = self.admin()
        self.admin_tools.create_timeslot(
            self.season.pk, start=datetime.time(18, 40), interval=50, count=3
        )
        self.admin_tools.add_season_exclusion_dates(self.season.pk, CHRISTMAS)

    def build_season(self, **kwargs):
        return self.admin_tools.build_draw(self.regular_builds(self.season), **kwargs)

    def test_regular_season_in_one_call(self):
        res = self.build_season()
        self.assertEqual(res["dry_run"], False)
        self.assertEqual(res["matches"], 48 + 36 + 60)
        self.assertEqual(
            [
                (
                    b["stage"]["id"],
                    b["matches"],
                    b["byes"],
                    b["first_round"],
                    b["last_round"],
                    b["first_date"],
                    b["last_date"],
                )
                for b in res["builds"]
            ],
            [
                (division.regular.pk, n, 0, 1, 12, "2026-10-07", "2027-01-13")
                for division, n in zip(
                    self.season.divisions_by_title.values(), (48, 36, 60)
                )
            ],
        )
        self.assertNotIn("rows", res["builds"][0])
        mens = self.season.divisions_by_title["Men's"]
        self.assertCountEqual(
            res["builds"][0]["match_ids"],
            mens.regular.matches.values_list("pk", flat=True),
        )
        # One round a week, skipping the Christmas break.
        expected_dates = [d for d in WEDNESDAYS if d not in CHRISTMAS][:12]
        for division in self.season.divisions_by_title.values():
            with self.subTest(division=division.title):
                matches = division.regular.matches.all()
                self.assertEqual(
                    sorted(set(matches.values_list("round", "date"))),
                    list(enumerate(expected_dates, start=1)),
                )
                teams = len(division.team_list)
                pairings = {
                    frozenset((m.home_team_id, m.away_team_id)) for m in matches
                }
                self.assertEqual(len(pairings), teams * (teams - 1) // 2)
                for date in expected_dates:
                    on_date = matches.filter(date=date)
                    playing = [
                        t for m in on_date for t in (m.home_team_id, m.away_team_id)
                    ]
                    self.assertEqual(len(playing), len(set(playing)))
                    self.assertEqual(len(playing), teams)

    def test_finals_with_wired_evals(self):
        self.build_season()
        finals = self.finals_format()
        res = self.admin_tools.build_draw(
            [
                {
                    "stage_id": division.finals.pk,
                    "draw_format_id": finals.pk,
                    "start_date": datetime.date(2027, 1, 20),
                }
                for division in self.season.divisions_by_title.values()
            ],
            verbose=True,
        )
        self.assertEqual(res["matches"], 9)
        mens = self.season.divisions_by_title["Men's"]
        rows = res["builds"][0]["rows"]
        semi_1, semi_2, final = (row["id"] for row in rows)
        self.assertEqual(
            rows,
            [
                {
                    "id": semi_1,
                    "ref": "13.1",
                    "round": 13,
                    "date": "2027-01-20",
                    "pool_id": None,
                    "label": "Semi 1",
                    "is_bye": False,
                    "home": {"eval": "P1", "title": "1st"},
                    "away": {"eval": "P4", "title": "4th"},
                },
                {
                    "id": semi_2,
                    "ref": "13.2",
                    "round": 13,
                    "date": "2027-01-20",
                    "pool_id": None,
                    "label": "Semi 2",
                    "is_bye": False,
                    "home": {"eval": "P2", "title": "2nd"},
                    "away": {"eval": "P3", "title": "3rd"},
                },
                {
                    "id": final,
                    "ref": "14.3",
                    "round": 14,
                    "date": "2027-01-27",
                    "pool_id": None,
                    "label": "Final",
                    "is_bye": False,
                    "home": {
                        "eval": "W",
                        "title": "Winner Semi 1",
                        "eval_ref": "13.1",
                        "eval_related_id": semi_1,
                    },
                    "away": {
                        "eval": "W",
                        "title": "Winner Semi 2",
                        "eval_ref": "13.2",
                        "eval_related_id": semi_2,
                    },
                },
            ],
        )
        final = Match.objects.get(pk=final)
        self.assertEqual(
            (final.home_team_eval, final.home_team_eval_related_id),
            ("W", semi_1),
        )
        self.assertEqual(
            (final.away_team_eval, final.away_team_eval_related_id),
            ("W", semi_2),
        )
        self.assertEqual(final.evaluated, False)

        # Play the regular season: the lower numbered team always wins, so
        # the ladder is in team order. The semis then evaluate to 1 v 4 and
        # 2 v 3, and the final to the semi winners.
        order = {team.pk: n for n, team in enumerate(mens.team_list)}
        for match in mens.regular.matches.all():
            home_wins = order[match.home_team_id] < order[match.away_team_id]
            self.admin_tools.record_match_result(
                match.pk,
                home_team_score=5 if home_wins else 1,
                away_team_score=1 if home_wins else 5,
                verbose=False,
            )
        semi_1 = Match.objects.get(pk=semi_1)
        semi_2 = Match.objects.get(pk=semi_2)
        team = mens.team_list
        # Ladder positions evaluate to the teams' identifiers.
        self.assertEqual(semi_1.eval(lazy=True), (team[0].pk, team[3].pk))
        self.assertEqual(semi_2.eval(lazy=True), (team[1].pk, team[2].pk))
        for semi, (home, away) in (
            (semi_1, (team[0], team[3])),
            (semi_2, (team[1], team[2])),
        ):
            semi.home_team, semi.away_team = home, away
            semi.save()
        self.admin_tools.record_match_result(
            semi_1.pk, home_team_score=3, away_team_score=2
        )
        self.admin_tools.record_match_result(
            semi_2.pk, home_team_score=1, away_team_score=4
        )
        self.assertEqual(
            Match.objects.get(pk=final.pk).eval(lazy=True), (team[0], team[2])
        )

    def test_dry_run_matches_the_real_run(self):
        finals = self.finals_format()
        builds = self.regular_builds(self.season) + [
            {
                "stage_id": division.finals.pk,
                "draw_format_id": finals.pk,
                "start_date": datetime.date(2027, 1, 20),
            }
            for division in self.season.divisions_by_title.values()
        ]
        plan = self.admin_tools.build_draw(builds, dry_run=True)
        self.assertEqual(plan["dry_run"], True)
        self.assertEqual(plan["saved"], False)
        self.assertEqual(plan["matches"], 153)
        self.assertEqual(Match.objects.count(), 0)
        self.assertNotIn("match_ids", plan["builds"][0])

        real = self.admin_tools.build_draw(builds, verbose=True)
        self.assertEqual(real["matches"], 153)

        def without_ids(row):
            row = {k: v for k, v in row.items() if k != "id"}
            for side in ("home", "away"):
                row[side] = {
                    k: v for k, v in row[side].items() if k != "eval_related_id"
                }
            return row

        self.assertEqual(
            [b["rows"] for b in plan["builds"]],
            [[without_ids(row) for row in b["rows"]] for b in real["builds"]],
        )
        # And the rows describe what was saved.
        for build in real["builds"]:
            for row in build["rows"]:
                match = Match.objects.get(pk=row["id"])
                self.assertEqual(
                    (match.round, match.date.isoformat(), match.label or None),
                    (row["round"], row["date"], row["label"]),
                )
                self.assertEqual(match.home_team_id, row["home"].get("team_id"))
                self.assertEqual(match.away_team_id, row["away"].get("team_id"))

    def test_deterministic(self):
        """
        The same spec in two identical but separate structures builds the
        same rounds, dates and pairings (by team name), and a dry run
        repeated gives the same plan.
        """

        def pairings(season):
            res = self.admin_tools.build_draw(self.regular_builds(season))
            return [
                sorted(
                    (m.round, m.date, m.home_team.title, m.away_team.title)
                    for m in Match.objects.filter(pk__in=build["match_ids"])
                )
                for build in res["builds"]
            ]

        self.admin_tools.add_season_exclusion_dates(self.other_season.pk, CHRISTMAS)
        builds = self.regular_builds(self.season)
        self.assertEqual(
            self.admin_tools.build_draw(builds, dry_run=True),
            self.admin_tools.build_draw(builds, dry_run=True),
        )
        self.assertEqual(pairings(self.season), pairings(self.other_season))

    def test_repeats_alternate_home_and_away(self):
        division = self.season.divisions_by_title["Women's"]
        draw_format = self.round_robin(6)
        res = self.admin_tools.build_draw(
            [
                {
                    "stage_id": division.regular.pk,
                    "draw_format_id": draw_format.pk,
                    "start_date": WEDNESDAYS[0],
                    "rounds": 10,
                    "alternate_home_away_on_repeat": True,
                }
            ],
            dry_run=True,
        )
        rows = res["builds"][0]["rows"]
        first, second = rows[:15], rows[15:]
        self.assertEqual(
            [(r["away"]["team_id"], r["home"]["team_id"]) for r in second],
            [(r["home"]["team_id"], r["away"]["team_id"]) for r in first],
        )
        plain = self.admin_tools.build_draw(
            [
                dict(res_spec, alternate_home_away_on_repeat=False)
                for res_spec in [
                    {
                        "stage_id": division.regular.pk,
                        "draw_format_id": draw_format.pk,
                        "start_date": WEDNESDAYS[0],
                        "rounds": 10,
                    }
                ]
            ],
            dry_run=True,
        )["builds"][0]["rows"]
        self.assertEqual(
            [(r["home"]["team_id"], r["away"]["team_id"]) for r in plain[15:]],
            [(r["home"]["team_id"], r["away"]["team_id"]) for r in first],
        )

    def test_repeats_keep_winner_references_on_their_side(self):
        """
        Swapping home and away on a repeat swaps W/L references whole: the
        reference is resolved after the swap, so each side still points at
        the match it names.
        """
        division = self.season.divisions_by_title["Women's"]
        rows = self.admin_tools.build_draw(
            [
                {
                    "stage_id": division.regular.pk,
                    "draw_format_text": "ROUND\n1: 1 vs 2\n2: 3 vs 4\nROUND\n3: W1 vs L2",
                    "start_date": WEDNESDAYS[0],
                    "rounds": 4,
                    "alternate_home_away_on_repeat": True,
                }
            ],
            dry_run=True,
        )["builds"][0]["rows"]
        self.assertEqual(
            [
                (
                    r["ref"],
                    r["home"].get("eval"),
                    r["home"].get("eval_ref"),
                    r["away"].get("eval"),
                    r["away"].get("eval_ref"),
                )
                for r in rows
                if r["home"].get("eval")
            ],
            [
                ("2.3", "W", "1.1", "L", "1.2"),
                ("4.3", "L", "3.2", "W", "3.1"),
            ],
        )

    def test_pool_and_tournament_builds(self):
        division = self.season.divisions_by_title["Mixed"]
        pool = factories.StageGroupFactory.create(
            stage=division.regular, title="Pool A", order=1
        )
        for team in division.team_list[:5]:
            team.stage_group = pool
            team.save()
        self.season.mode = DAILY
        self.season.save()
        division.games_per_day = 2
        division.save()
        res = self.admin_tools.build_draw(
            [
                {
                    "pool_id": pool.pk,
                    "draw_format_text": round_robin_format(5),
                    "start_date": datetime.date(2027, 3, 6),
                }
            ],
            dry_run=True,
        )
        build = res["builds"][0]
        self.assertEqual(build["pool"]["id"], pool.pk)
        self.assertEqual(build["matches"], 15)
        self.assertEqual(build["byes"], 5)
        # Two rounds a day.
        self.assertEqual(
            [(r["round"], r["date"]) for r in build["rows"][::3]],
            [
                (1, "2027-03-06"),
                (2, "2027-03-06"),
                (3, "2027-03-07"),
                (4, "2027-03-07"),
                (5, "2027-03-08"),
            ],
        )
        self.assertEqual({r["pool_id"] for r in build["rows"]}, {pool.pk})
        self.assertToolError(
            "build 0: stage Regular Season has pools; build each of its pools "
            "(pool_id) instead.",
            self.admin_tools.build_draw,
            [
                {
                    "stage_id": division.regular.pk,
                    "draw_format_text": round_robin_format(5),
                }
            ],
        )

    def test_existing_matches(self):
        division = self.season.divisions_by_title["Women's"]
        draw_format = self.round_robin(6)
        build = {
            "stage_id": division.regular.pk,
            "draw_format_id": draw_format.pk,
            "start_date": WEDNESDAYS[0],
        }
        first = self.admin_tools.build_draw([build])["builds"][0]["match_ids"]
        self.assertToolError(
            "build 0: Regular Season already has 15 matches; pass "
            "replace_existing=true to replace those without results.",
            self.admin_tools.build_draw,
            [build],
        )
        played = Match.objects.get(pk=first[0])
        self.admin_tools.record_match_result(
            played.pk, home_team_score=2, away_team_score=1
        )
        res = self.admin_tools.build_draw([build], replace_existing=True)
        self.assertEqual(
            res["builds"][0]["replaced"],
            {"deleted": 14, "kept_with_results": [played.pk]},
        )
        self.assertEqual(division.regular.matches.count(), 16)
        self.assertEqual(Match.objects.filter(pk__in=first[1:]).count(), 0)
        played.refresh_from_db()
        self.assertEqual(played.home_team_score, 2)

        # Replacing finals whose matches refer to each other.
        finals = self.finals_format()
        finals_build = {
            "stage_id": division.finals.pk,
            "draw_format_id": finals.pk,
            "start_date": datetime.date(2027, 1, 20),
        }
        self.admin_tools.build_draw([finals_build])
        res = self.admin_tools.build_draw([finals_build], replace_existing=True)
        self.assertEqual(
            res["builds"][0]["replaced"], {"deleted": 3, "kept_with_results": []}
        )
        self.assertEqual(division.finals.matches.count(), 3)

    def test_validation(self):
        division = self.season.divisions_by_title["Women's"]
        stage = division.regular.pk
        draw_format = self.round_robin(6)
        cases = [
            (
                [{"draw_format_id": draw_format.pk}],
                "build 0: give exactly one of stage_id or pool_id.",
            ),
            (
                [
                    {
                        "stage_id": stage,
                        "draw_format_id": draw_format.pk,
                        "draw_format_text": "ROUND",
                    }
                ],
                "build 0: give exactly one of draw_format_id or draw_format_text.",
            ),
            (
                [{"stage_id": stage, "draw_format_text": "ROUND\n1: 1 v 2"}],
                "build 0: Validation failed: text: Draw formula is invalid: "
                "line(s) '1' are not in the correct format.",
            ),
            (
                [
                    {
                        "stage_id": stage,
                        "draw_format_text": "ROUND\n1: W2 vs 1\n2: 3 vs 4",
                    }
                ],
                "build 0: Match 1 refers to W2, but match 2 is not in an earlier round.",
            ),
            (
                [{"stage_id": stage, "draw_format_id": draw_format.pk, "rounds": 0}],
                "build 0: rounds: Input should be greater than or equal to 1",
            ),
            (
                [
                    {"stage_id": stage, "draw_format_id": draw_format.pk},
                    {"stage_id": stage, "draw_format_id": draw_format.pk},
                ],
                "builds 0 and 1 build the same stage.",
            ),
            (
                [
                    {
                        "stage_id": stage,
                        "draw_format_id": draw_format.pk,
                        "start_date": datetime.date(2026, 9, 30),
                    }
                ],
                "build 0: round 1 on 2026-09-30: Validation failed: date: This "
                "date is before the start of the season.",
            ),
        ]
        for builds, message in cases:
            with self.subTest(message=message):
                self.assertToolError(message, self.admin_tools.build_draw, builds)
        self.assertEqual(Match.objects.count(), 0)

        self.season.start_date = None
        self.season.save()
        self.assertToolError(
            "build 0: give a start_date; the season has no start date.",
            self.admin_tools.build_draw,
            [{"stage_id": stage, "draw_format_id": draw_format.pk}],
        )

    def test_warns_when_the_format_does_not_suit(self):
        division = self.season.divisions_by_title["Women's"]
        res = self.admin_tools.build_draw(
            [
                {
                    "stage_id": division.regular.pk,
                    "draw_format_id": self.round_robin(8).pk,
                    "start_date": WEDNESDAYS[0],
                }
            ],
            dry_run=True,
        )
        self.assertEqual(
            res["builds"][0]["warnings"],
            ["Draw format Round Robin (8 teams) is for 8 teams; Regular Season has 6."],
        )
        # Teams 7 and 8 play 7 matches each, one of them against each other.
        self.assertEqual(res["builds"][0]["byes"], 13)

    def test_permissions(self):
        builds = self.regular_builds(self.season)
        self.assertToolError(
            "Permission denied: add match requires the competition.add_match "
            "permission.",
            self.admin(self.staff).build_draw,
            builds,
        )
        assign_perm("competition.add_match", self.staff)
        staff = self.admin(self.fresh(self.staff))
        self.assertEqual(staff.build_draw(builds)["matches"], 144)
        self.assertToolError(
            "Permission denied: delete match requires the competition.delete_match "
            "permission.",
            staff.build_draw,
            builds,
            replace_existing=True,
        )


class DrawGenerationWizardRegressionTests(DemoMixin, TestCase):
    """The wizard's form builds what the shared service builds."""

    def test_form_uses_the_service(self):
        division = self.season.divisions_by_title["Men's"]
        draw_format = self.round_robin(8)
        self.round_robin(6)
        form = DrawGenerationForm(
            initial=division.regular,
            data={
                "start_date": "2026-10-07",
                "format": draw_format.pk,
                "rounds": "9",
                "offset": "2",
            },
        )
        self.assertEqual(list(form.fields["format"].queryset), [draw_format])
        self.assertEqual(form.is_valid(), True)

        def describe(matches):
            return [
                (m.round, m.date, m.home_team_id, m.away_team_id, m.label)
                for m in matches
            ]

        self.assertEqual(
            describe(form.cleaned_data["matches"]),
            describe(
                generate_stage_draw(
                    division.regular, draw_format, datetime.date(2026, 10, 7), 9, 2
                )
            ),
        )
        self.assertEqual(
            [m.round for m in form.cleaned_data["matches"]][::4],
            list(range(3, 12)),
        )
        # Rounds default to one pass of the format.
        form = DrawGenerationForm(
            initial=division.regular,
            data={"start_date": "2026-10-07", "format": draw_format.pk},
        )
        self.assertEqual(form.is_valid(), True)
        self.assertEqual(form.cleaned_data["rounds"], 7)
        self.assertEqual(len(form.cleaned_data["matches"]), 28)

    def test_wizard_saves_the_same_draw(self):
        division = self.season.divisions_by_title["Women's"]
        draw_format = self.round_robin(6)
        plan = self.admin().build_draw(
            [
                {
                    "stage_id": division.regular.pk,
                    "draw_format_id": draw_format.pk,
                    "start_date": datetime.date(2026, 10, 7),
                }
            ],
            dry_run=True,
        )["builds"][0]["rows"]
        build_url = division.regular.url_names["build"]
        with self.login(self.superuser):
            self.get(build_url.url_name, *build_url.args)
            self.response_200()
            self.post(
                build_url.url_name,
                *build_url.args,
                data={
                    "draw_generation_wizard-current_step": "0",
                    "0-TOTAL_FORMS": "1",
                    "0-INITIAL_FORMS": "1",
                    "0-MIN_NUM_FORMS": "0",
                    "0-MAX_NUM_FORMS": "1000",
                    "0-0-start_date": "2026-10-07",
                    "0-0-format": draw_format.pk,
                    "0-0-rounds": "",
                    "0-0-offset": "",
                },
            )
            self.response_200()
            formset = self.get_context("form")
            data = {
                "draw_generation_wizard-current_step": "1",
                "1-TOTAL_FORMS": str(formset.total_form_count()),
                "1-INITIAL_FORMS": str(formset.initial_form_count()),
                "1-MIN_NUM_FORMS": "0",
                "1-MAX_NUM_FORMS": "1000",
            }
            for index, form in enumerate(formset.forms):
                for name, field in form.fields.items():
                    value = form.initial.get(name)
                    if hasattr(value, "pk"):
                        value = value.pk
                    if isinstance(value, datetime.datetime):
                        value = value.date()
                    data[f"1-{index}-{name}"] = "" if value is None else str(value)
            self.post(build_url.url_name, *build_url.args, data=data)
            self.response_302()
        saved = division.regular.matches.order_by("round", "pk")
        self.assertEqual(
            [
                (m.round, m.date.isoformat(), m.home_team_id, m.away_team_id)
                for m in saved
            ],
            [
                (r["round"], r["date"], r["home"]["team_id"], r["away"]["team_id"])
                for r in plan
            ],
        )


class MatchEvalTests(DemoMixin, TestCase):
    """Item 6: hand-built finals with evals."""

    def setUp(self):
        super().setUp()
        self.division = self.season.divisions_by_title["Men's"]
        self.admin_tools = self.admin()
        self.admin_tools.build_draw(
            [
                {
                    "stage_id": self.division.regular.pk,
                    "draw_format_id": self.round_robin(8).pk,
                    "start_date": WEDNESDAYS[0],
                }
            ]
        )

    def create(self, **kwargs):
        kwargs.setdefault("stage_id", self.division.finals.pk)
        return self.admin_tools.create_match(**kwargs)["match"]

    def test_hand_built_finals_resolve(self):
        semi_1 = self.create(
            round=8,
            label="Semi 1",
            home_team_eval="P1",
            away_team_eval="p4",
            date=datetime.date(2026, 11, 25),
        )
        semi_2 = self.create(
            round=8,
            label="Semi 2",
            home_team_eval="P2",
            away_team_eval="P3",
            date=datetime.date(2026, 11, 25),
        )
        final = self.create(
            round=9,
            label="Final",
            home_team_eval="W",
            home_team_eval_related_id=semi_1["id"],
            away_team_eval="W",
            away_team_eval_related_id=semi_2["id"],
            date=datetime.date(2026, 12, 2),
        )
        self.assertEqual(
            semi_1["away_team"],
            {
                "id": None,
                "title": "4th",
                "slug": None,
                "club": None,
                "eval": "P4",
                "eval_related_id": None,
            },
        )
        self.assertEqual(
            final["home_team"],
            {
                "id": None,
                "title": "Winner Semi 1",
                "slug": None,
                "club": None,
                "eval": "W",
                "eval_related_id": semi_1["id"],
            },
        )
        listed = self.admin_tools.list_matches(stage_id=self.division.finals.pk)
        self.assertEqual(
            [m["home_team"]["title"] for m in listed["matches"]],
            ["1st", "2nd", "Winner Semi 1"],
        )

        order = {team.pk: n for n, team in enumerate(self.division.team_list)}
        for match in self.division.regular.matches.all():
            home_wins = order[match.home_team_id] < order[match.away_team_id]
            self.admin_tools.record_match_result(
                match.pk,
                home_team_score=5 if home_wins else 1,
                away_team_score=1 if home_wins else 5,
            )
        team = self.division.team_list
        self.assertEqual(
            Match.objects.get(pk=semi_1["id"]).eval(lazy=True), (team[0].pk, team[3].pk)
        )
        self.assertEqual(
            Match.objects.get(pk=semi_2["id"]).eval(lazy=True), (team[1].pk, team[2].pk)
        )
        self.admin_tools.update_match(
            semi_1["id"], home_team_id=team[0].pk, away_team_id=team[3].pk
        )
        self.admin_tools.record_match_result(
            semi_1["id"], home_team_score=1, away_team_score=2
        )
        self.assertEqual(Match.objects.get(pk=final["id"]).eval(lazy=True)[0], team[3])
        # Setting a team replaced the eval on that side.
        semi = Match.objects.get(pk=semi_1["id"])
        self.assertEqual((semi.home_team_id, semi.home_team_eval), (team[0].pk, None))

    def test_invalid_evals(self):
        semi = self.create(round=8, home_team_eval="P1", away_team_eval="P4")
        pooled = self.season.divisions_by_title["Women's"]
        other = Match.objects.filter(
            stage__division=self.season.divisions_by_title["Mixed"]
        )
        other_match = factories.MatchFactory.create(
            stage=self.season.divisions_by_title["Mixed"].regular,
            home_team=self.season.divisions_by_title["Mixed"].team_list[0],
            away_team=self.season.divisions_by_title["Mixed"].team_list[1],
            date=None,
            time=None,
            datetime=None,
        )
        self.assertEqual(other.count(), 1)
        cases = [
            (
                {"home_team_eval": "P9"},
                "Validation failed: home_team_eval: P9 refers to position 9, but "
                "Regular Season has 8 teams.",
            ),
            (
                {"home_team_eval": "G1P1"},
                "Validation failed: home_team_eval: G1P1: Regular Season has no "
                "pool 1 (it has 0).",
            ),
            (
                {"home_team_eval": "S3P1"},
                "Validation failed: home_team_eval: S3P1: the division has no stage 3.",
            ),
            (
                {"home_team_eval": "S2P1"},
                "Validation failed: home_team_eval: S2P1 must refer to an earlier "
                "stage than Finals.",
            ),
            (
                {"home_team_eval": "P0"},
                "Validation failed: home_team_eval: P0: stage, pool and position "
                "numbers start at 1.",
            ),
            (
                {"home_team_eval": "X1"},
                "Validation failed: home_team_eval: X1 is not an eval: use P1 "
                "(position on the ladder of the previous stage), G2P3 (position 3 "
                "in its pool 2), S1G1P2 (stage 1, pool 1, position 2), W or L.",
            ),
            (
                {"round": 9, "home_team_eval": "W"},
                "Validation failed: home_team_eval: A W or L eval needs the match it "
                "refers to (home_team_eval_related_id).",
            ),
            (
                {
                    "round": 8,
                    "home_team_eval": "W",
                    "home_team_eval_related_id": semi["id"],
                },
                f"Validation failed: home_team_eval: Match {semi['id']} is in round 8 "
                "of this stage; a W or L eval must refer to a match in an earlier "
                "stage or an earlier round of this stage.",
            ),
            (
                {
                    "round": 9,
                    "home_team_eval": "W",
                    "home_team_eval_related_id": other_match.pk,
                },
                "Validation failed: home_team_eval_related: The related match must be "
                "another match of this division.",
            ),
            (
                {"home_team_eval_related_id": semi["id"]},
                "Validation failed: home_team_eval_related: A related match is only "
                "used with a W (winner) or L (loser) eval.",
            ),
            (
                {"home_team_id": self.division.team_list[0].pk, "home_team_eval": "P1"},
                "Give the home side one of home_team_id or home_team_eval, not more "
                "than one.",
            ),
        ]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs):
                self.assertToolError(message, self.create, **kwargs)
        self.assertToolError(
            "Validation failed: home_team_eval: P1 refers to the stage before this "
            "one, but Regular Season is the first stage of the division.",
            self.create,
            stage_id=pooled.regular.pk,
            home_team_eval="P1",
        )
        self.assertEqual(self.division.finals.matches.count(), 1)

    def test_winner_eval_replaced_by_a_position(self):
        semi = self.create(round=8, home_team_eval="P1", away_team_eval="P4")
        final = self.create(
            round=9,
            home_team_eval="W",
            home_team_eval_related_id=semi["id"],
            away_team_eval="P2",
        )
        res = self.admin_tools.update_match(final["id"], home_team_eval="P1")["match"]
        self.assertEqual(
            res["home_team"],
            {
                "id": None,
                "title": "1st",
                "slug": None,
                "club": None,
                "eval": "P1",
                "eval_related_id": None,
            },
        )
        res = self.admin_tools.update_match(
            final["id"], home_team_eval="L", home_team_eval_related_id=semi["id"]
        )["match"]
        self.assertEqual(
            (res["home_team"]["eval"], res["home_team"]["eval_related_id"]),
            ("L", semi["id"]),
        )

    def test_update_and_clear(self):
        semi = self.create(round=8, home_team_eval="P1", away_team_eval="P4")
        res = self.admin_tools.update_match(semi["id"], away_team_eval="P3")["match"]
        self.assertEqual(res["away_team"]["eval"], "P3")
        res = self.admin_tools.update_match(semi["id"], away_team_eval="")["match"]
        self.assertEqual(
            res["away_team"], {"id": None, "title": "TBA", "slug": None, "club": None}
        )


class ScheduleMatchesTests(DemoMixin, TestCase):
    """Item 7: batch scheduling."""

    def setUp(self):
        super().setUp()
        self.admin_tools = self.admin()
        self.admin_tools.create_timeslot(
            self.season.pk, start=datetime.time(18, 40), interval=50, count=3
        )
        self.admin_tools.build_draw(self.regular_builds(self.season))
        self.night = list(
            Match.objects.filter(
                stage__division__season=self.season, date=WEDNESDAYS[0]
            ).order_by("stage__division__order", "pk")
        )
        self.cells = list(
            itertools.product(
                [datetime.time(18, 40), datetime.time(19, 30), datetime.time(20, 20)],
                self.season.grounds,
            )
        )

    def test_a_full_night_in_one_call(self):
        self.assertEqual(len(self.night), 12)
        items = [
            {"match_id": match.pk, "time": time, "place_id": ground.pk}
            for match, (time, ground) in zip(self.night, self.cells)
        ]
        res = self.admin_tools.schedule_matches(items)
        self.assertEqual(res["saved"], 12)
        self.assertEqual(res["failed"], [])
        self.assertEqual(
            res["matches"][0],
            {
                "id": self.night[0].pk,
                "round": 1,
                "date": "2026-10-07",
                "time": "18:40",
                "place_id": self.season.grounds[0].pk,
                "home_team_id": self.night[0].home_team_id,
                "away_team_id": self.night[0].away_team_id,
                "status": "upcoming",
            },
        )
        scheduled = Match.objects.filter(pk__in=[m.pk for m in self.night])
        self.assertEqual(len({(m.time, m.play_at_id) for m in scheduled}), 12)
        self.assertEqual(
            scheduled.get(pk=self.night[11].pk).datetime.isoformat(),
            "2026-10-07T09:20:00+00:00",
        )

    def test_intra_batch_clash_is_refused_by_index(self):
        time, ground = self.cells[0]
        items = [
            {"match_id": self.night[0].pk, "time": time, "place_id": ground.pk},
            {
                "match_id": self.night[1].pk,
                "time": self.cells[1][0],
                "place_id": self.cells[1][1].pk,
            },
            {"match_id": self.night[2].pk, "time": time, "place_id": ground.pk},
            {
                "match_id": self.night[3].pk,
                "time": datetime.time(19, 0),
                "place_id": ground.pk,
            },
        ]
        self.assertToolError(
            "Nothing was scheduled: 2 of 4 items failed.\n"
            f"item 2 (match {self.night[2].pk}): Item 0 (match {self.night[0].pk}) "
            "is already scheduled for this time & place.\n"
            f"item 3 (match {self.night[3].pk}): Validation failed: time: 19:00 is "
            "not a time slot on 2026-10-07; valid: 18:40, 19:30, 20:20.",
            self.admin_tools.schedule_matches,
            items,
        )
        self.assertEqual(
            Match.objects.filter(
                pk__in=[m.pk for m in self.night], time__isnull=False
            ).count(),
            0,
        )
        # Not atomic: the valid items are saved and the others reported.
        res = self.admin_tools.schedule_matches(items, atomic=False)
        self.assertEqual(res["saved"], 2)
        self.assertEqual([f["index"] for f in res["failed"]], [2, 3])
        # With ignore_clashes the double booking is allowed, never the slot.
        res = self.admin_tools.schedule_matches(
            items[2:], atomic=False, ignore_clashes=True
        )
        self.assertEqual(res["saved"], 1)
        self.assertEqual([f["index"] for f in res["failed"]], [1])

    def test_the_same_team_twice_at_once(self):
        mens = self.season.divisions_by_title["Men's"]
        extra = factories.MatchFactory.create(
            stage=mens.regular,
            home_team=self.night[0].home_team,
            away_team=self.night[1].home_team,
            date=WEDNESDAYS[0],
            time=None,
            datetime=None,
            round=1,
        )
        time = datetime.time(18, 40)
        self.assertToolError(
            "Nothing was scheduled: 1 of 2 items failed.\n"
            f"item 1 (match {extra.pk}): {self.night[0].home_team.title} are "
            f"already playing at 18:40 on 2026-10-07 (item 0 (match {self.night[0].pk})).",
            self.admin_tools.schedule_matches,
            [
                {
                    "match_id": self.night[0].pk,
                    "time": time,
                    "place_id": self.season.grounds[0].pk,
                },
                {
                    "match_id": extra.pk,
                    "time": time,
                    "place_id": self.season.grounds[1].pk,
                },
            ],
        )

    def test_swap_checks_clashes_with_other_matches(self):
        first, second = self.night[0], self.night[1]
        early, late = datetime.time(18, 40), datetime.time(19, 30)
        field_1, field_2 = self.season.grounds[:2]
        self.admin_tools.schedule_matches(
            [
                {"match_id": first.pk, "time": early, "place_id": field_1.pk},
                {"match_id": second.pk, "time": late, "place_id": field_1.pk},
            ]
        )
        # Another match already has one of the second match's teams at 18:40.
        busy = second.home_team
        factories.MatchFactory.create(
            stage=self.season.divisions_by_title["Men's"].regular,
            home_team=busy,
            away_team=self.night[2].home_team,
            date=WEDNESDAYS[0],
            time=early,
            datetime=None,
            play_at=field_2,
            round=1,
        )
        self.assertToolError(
            f"Match {second.pk}: {busy.title} are already playing at 18:40 on "
            "2026-10-07.",
            self.admin_tools.swap_match_allocations,
            first.pk,
            second.pk,
        )
        second.refresh_from_db()
        self.assertEqual((second.time, second.play_at_id), (late, field_1.pk))
        res = self.admin_tools.swap_match_allocations(
            first.pk, second.pk, ignore_clashes=True
        )
        self.assertEqual(
            [(m["id"], m["time"]) for m in res["matches"]],
            [(first.pk, "19:30"), (second.pk, "18:40")],
        )

    def test_rescheduling_starts_from_the_saved_match(self):
        """
        A match read before another call moved it is re-read under the lock,
        so changing only its time keeps the other call's new date.
        """
        stale = Match.objects.get(pk=self.night[0].pk)
        Match.objects.filter(pk=stale.pk).update(date=WEDNESDAYS[1])
        match = self.admin_tools._reschedule(stale, time=datetime.time(19, 30))
        self.assertEqual(
            (match.date, match.time), (WEDNESDAYS[1], datetime.time(19, 30))
        )
        self.assertEqual(
            Match.objects.filter(pk=stale.pk).values_list("date", "time").get(),
            (WEDNESDAYS[1], datetime.time(19, 30)),
        )

    def test_scheduling_locks_the_season(self):
        """
        Clash checks and the writes they guard run under a row lock on the
        season, so concurrent schedulers cannot book the same slot (nor two
        builds fill the same stage).
        """
        item = {
            "match_id": self.night[0].pk,
            "time": datetime.time(18, 40),
            "place_id": self.season.grounds[0].pk,
        }
        calls = [
            (self.admin_tools.schedule_matches, ([item],), {}),
            (
                self.admin_tools.reschedule_match,
                (self.night[1].pk,),
                {"time": datetime.time(19, 30)},
            ),
            (
                self.admin_tools.auto_schedule,
                (self.season.pk, WEDNESDAYS[0], [g.pk for g in self.season.grounds]),
                {},
            ),
            (
                self.admin_tools.swap_match_allocations,
                (self.night[0].pk, self.night[1].pk),
                {},
            ),
            (
                self.admin_tools.create_match,
                (self.season.divisions_by_title["Women's"].finals.pk,),
                {"home_team_eval": "P1", "away_team_eval": "P2", "date": WEDNESDAYS[5]},
            ),
            (
                self.admin_tools.create_timeslot,
                (self.season.pk,),
                {"start": datetime.time(21, 10), "interval": 50, "count": 1},
            ),
            (
                self.admin_tools.update_timeslot,
                (self.season.timeslots.get().pk,),
                {"count": 2},
            ),
            (
                self.admin_tools.build_draw,
                (
                    [
                        {
                            "stage_id": self.season.divisions_by_title[
                                "Men's"
                            ].finals.pk,
                            "draw_format_text": FINALS_TEXT,
                            "start_date": datetime.date(2027, 1, 20),
                        }
                    ],
                ),
                {"dry_run": True},
            ),
        ]
        for tool, args, kwargs in calls:
            with self.subTest(tool=tool.__name__):
                with CaptureQueriesContext(connection) as queries:
                    tool(*args, **kwargs)
                self.assertEqual(
                    [
                        q["sql"].startswith('SELECT "competition_season"."id"')
                        for q in queries.captured_queries
                        if q["sql"].endswith("FOR UPDATE")
                    ],
                    [True],
                )

    def test_batch_clash_checks_do_not_query_per_match(self):
        """
        The clash checks of a batch read the date's existing bookings once
        and every team's declared clashes in one query: a whole night costs
        the same two queries as a single match.
        """
        mens = self.season.divisions_by_title["Men's"]
        mens.team_list[0].team_clashes.add(
            self.season.divisions_by_title["Women's"].team_list[0]
        )

        def queries_for(count):
            matches = list(
                Match.objects.select_related("home_team", "away_team").filter(
                    pk__in=[m.pk for m in self.night[:count]]
                )
            )
            for match, (time, ground) in zip(matches, self.cells):
                match.time, match.play_at_id = time, ground.pk
            validator = ScheduleValidator(moving={m.pk for m in matches})
            with CaptureQueriesContext(connection) as queries:
                validator.prefetch_clashes(
                    t for m in matches for t in (m.home_team_id, m.away_team_id)
                )
                for match in matches:
                    self.assertEqual(validator.clash_errors(match), [])
                    validator.claim(match, f"match {match.pk}")
            return len(queries.captured_queries)

        self.assertEqual((queries_for(1), queries_for(12)), (2, 2))

    def test_limits_and_shape(self):
        self.assertToolError(
            "Give at most 500 items at once; split the batch.",
            self.admin_tools.schedule_matches,
            [{"match_id": 1, "time": datetime.time(18, 40)}] * 501,
        )
        self.assertToolError(
            "Nothing was scheduled: 2 of 2 items failed.\n"
            f"item 0 (match {self.night[0].pk}): give a date, time or place_id to change.\n"
            "item 1 (match 0): Match 0 was not found.",
            self.admin_tools.schedule_matches,
            [
                {"match_id": self.night[0].pk},
                {"match_id": 0, "time": datetime.time(18, 40)},
            ],
        )
        self.assertToolError(
            "Permission denied: change match requires the competition.change_match "
            "permission for this match.",
            self.admin(self.staff).reschedule_match,
            self.night[0].pk,
            time=datetime.time(18, 40),
        )

    def test_auto_schedule(self):
        grounds = [g.pk for g in self.season.grounds]
        plan = self.admin_tools.auto_schedule(
            self.season.pk, WEDNESDAYS[0], grounds, dry_run=True
        )
        self.assertEqual(plan["scheduled"], 12)
        self.assertEqual(plan["unscheduled"], [])
        self.assertEqual(
            [(m["id"], m["time"], m["place_id"]) for m in plan["matches"]],
            [
                (match.pk, time.strftime("%H:%M"), ground.pk)
                for match, (time, ground) in zip(self.night, self.cells)
            ],
        )
        self.assertEqual(
            Match.objects.filter(date=WEDNESDAYS[0], time__isnull=False).count(), 0
        )
        res = self.admin_tools.auto_schedule(self.season.pk, WEDNESDAYS[0], grounds)
        self.assertEqual(res["matches"], plan["matches"])
        # Nothing is left to schedule that night.
        again = self.admin_tools.auto_schedule(self.season.pk, WEDNESDAYS[0], grounds)
        self.assertEqual((again["scheduled"], again["unscheduled"]), (0, []))
        # Too few cells: the rest are reported.
        res = self.admin_tools.auto_schedule(self.season.pk, WEDNESDAYS[1], grounds[:3])
        self.assertEqual(res["scheduled"], 9)
        self.assertEqual(
            [u["reason"] for u in res["unscheduled"]],
            ["every time slot and place is taken."] * 3,
        )


class CompactResponseTests(DemoMixin, TestCase):
    def test_verbose_false(self):
        admin = self.admin()
        division = self.season.divisions_by_title["Women's"]
        home, away = division.team_list[:2]
        match = admin.create_match(
            division.regular.pk,
            home_team_id=home.pk,
            away_team_id=away.pk,
            round=1,
            date=WEDNESDAYS[0],
            time=datetime.time(18, 40),
            place_id=self.season.grounds[0].pk,
            verbose=False,
        )
        expected = {
            "id": match["match"]["id"],
            "round": 1,
            "date": "2026-10-07",
            "time": "18:40",
            "place_id": self.season.grounds[0].pk,
            "home_team_id": home.pk,
            "away_team_id": away.pk,
            "status": "upcoming",
        }
        self.assertEqual(match, {"saved": True, "match": expected})
        res = admin.reschedule_match(
            expected["id"], time=datetime.time(19, 30), verbose=False
        )
        self.assertEqual(res["match"], dict(expected, time="19:30"))
        res = admin.update_match(expected["id"], label="Opener", verbose=False)
        self.assertEqual(res["match"], dict(expected, time="19:30"))
        res = admin.record_match_result(
            expected["id"], home_team_score=3, away_team_score=1, verbose=False
        )
        self.assertEqual(
            res["match"],
            dict(
                expected,
                time="19:30",
                status="completed",
                home_team_score=3,
                away_team_score=1,
            ),
        )
        team = admin.create_team(division.pk, title="Late Entry", verbose=False)
        self.assertEqual(
            team,
            {
                "saved": True,
                "team": {
                    "id": team["team"]["id"],
                    "title": "Late Entry",
                    "slug": "late-entry",
                },
            },
        )
        # The full description stays the default.
        res = admin.reschedule_match(expected["id"], time=datetime.time(20, 20))
        self.assertEqual(res["match"]["datetime"], "2026-10-07T20:20:00+11:00")
        self.assertEqual(res["match"]["venue"]["title"], "Park")


class TitleTests(DemoMixin, TestCase):
    def test_titles_round_trip(self):
        admin = self.admin()
        division = self.season.divisions_by_title["Women's"]
        for title, slug in (
            ("Hit & Run", "hit-run"),
            ("<b>Bold</b>", "bboldb"),
            ("O'Brien's", "obriens"),
        ):
            with self.subTest(title=title):
                team = admin.create_team(division.pk, title=title)["team"]
                self.assertEqual((team["title"], team["slug"]), (title, slug))
                self.assertEqual(admin.get_team(team["id"])["team"]["title"], title)
        # A client that HTML-escapes its arguments still stores plain text.
        team = admin.create_team(division.pk, title="Smash &amp; Grab")["team"]
        self.assertEqual((team["title"], team["slug"]), ("Smash & Grab", "smash-grab"))

    def test_placeholder_titles(self):
        division = self.season.divisions_by_title["Women's"]
        match = factories.MatchFactory.create(
            stage=division.finals,
            home_team=None,
            away_team=None,
            date=WEDNESDAYS[3],
            time=None,
            datetime=None,
        )
        self.assertEqual(match.get_home_team(), {"title": "TBA"})
        self.assertEqual(match.get_away_team_plain(), "TBA")
        self.assertEqual(match.title, "TBA vs TBA")
        res = self.admin().get_match(match.pk)
        self.assertEqual(
            (res["home_team"], res["away_team"]),
            (
                {"id": None, "title": "TBA", "slug": None, "club": None},
                {"id": None, "title": "TBA", "slug": None, "club": None},
            ),
        )
        listed = self.admin().list_matches(stage_id=division.finals.pk)["matches"]
        self.assertEqual(listed[0]["home_team"]["title"], "TBA")
