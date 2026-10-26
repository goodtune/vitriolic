"""
A match mirrored from an upstream provider which has yet to name its teams is
not waiting on progression.

The sync saves such a match with its "TBA" undecided team, which has no
formula, on each side still to be named, and fills the team in on a later
sync. Nothing here can progress it, so ``matches_require_progression()`` (the
home page's Progress Teams widget) and the stage's progression page leave it
out, by ``team_awaits_upstream`` in ``utils``. Only that placeholder is left
out: an undecided team with a formula on a synced match, and a placeholder
shaped undecided team on a match of our own, still need progressing.

Nor is the placeholder a place to fill on the progression page of a stage
which also holds undecided teams of our own: the next sync would write over
whatever team was chosen for it.
"""

import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import SuperUserFactory, UserFactory
from tournamentcontrol.competition.dashboard import (
    matches_progression_possible,
    matches_require_progression,
    stages_require_progression,
)
from tournamentcontrol.competition.tests.factories import (
    MatchFactory,
    SeasonFactory,
    StageFactory,
    UndecidedTeamFactory,
)
from tournamentcontrol.competition.tests.upstream import (
    STATE_CUP_SEASON_URL,
    STATE_CUP_URL,
)
from tournamentcontrol.competition.upstream.sync import TBA_LABEL, apply_snapshot
from tournamentcontrol.competition.upstream.types import (
    ROUND_REGULAR,
    RemoteCompetition,
    RemoteMatch,
    RemoteTeam,
)

PROGRESS = "admin:fixja:competition:season:division:stage:progress"

# The clock these tests freeze at, and an hour either side of it.
NOW = "2019-07-15 09:30 UTC"
PLAYED = datetime.datetime(2019, 7, 15, 8, 30, tzinfo=ZoneInfo("UTC"))
KICK_OFF = datetime.datetime(2019, 7, 15, 10, 30, tzinfo=ZoneInfo("UTC"))


def synced_placeholder(stage, upstream_id):
    """
    A match mirrored from an upstream provider which has yet to name its
    teams, as the sync saves one: its "TBA" undecided team, which has no
    formula, stands in on both sides.
    """
    tba = UndecidedTeamFactory.create(stage=stage, label=TBA_LABEL, formula="")
    return MatchFactory.create(
        stage=stage,
        home_team=None,
        away_team=None,
        home_team_undecided=tba,
        away_team_undecided=tba,
        upstream_id=upstream_id,
        datetime=KICK_OFF,
    )


def place_to_fill(stage, **kwargs):
    """An undecided team of our own, on the home side of a match of our own."""
    undecided = UndecidedTeamFactory.create(stage=stage, **kwargs)
    MatchFactory.create(
        stage=stage, home_team=None, home_team_undecided=undecided, datetime=KICK_OFF
    )
    return undecided


@freeze_time(NOW)
class UpstreamPlaceholderTests(TestCase):
    """The progression work behind the home page, with a synced placeholder."""

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def assertNothingToProgress(self):
        """Nothing waits on progression, and the home page stands."""
        self.assertCountEqual(matches_require_progression(), [])
        self.assertCountEqual(matches_progression_possible(), [])
        self.assertEqual(stages_require_progression(), {})
        with self.login(self.superuser):
            self.get_check_200("admin:index")

    def test_synced_placeholder(self):
        """
        A synced placeholder in the first stage of its division: only the
        provider can fill its teams in, so it is not waiting on progression,
        and the stage is never asked about the stage before it.
        """
        stage = StageFactory.create(division__season__timezone="UTC", order=1)
        synced_placeholder(stage, "mysideline:1")
        self.assertNothingToProgress()

    def test_only_the_synced_placeholder_is_left_out(self):
        """
        An undecided team with a formula on a synced match, and a placeholder
        shaped undecided team (no formula) on a match of our own, both still
        need progressing: only the provider's own placeholder is left out.
        """
        stage = StageFactory.create(division__season__timezone="UTC", order=1)
        synced_placeholder(stage, "mysideline:1")
        synced_with_formula = MatchFactory.create(
            stage=stage,
            home_team=None,
            home_team_undecided=UndecidedTeamFactory.create(
                stage=stage, label="", formula="P1"
            ),
            upstream_id="mysideline:2",
            datetime=KICK_OFF,
        )
        shaped_like_one = UndecidedTeamFactory.create(
            stage=stage, label=TBA_LABEL, formula=""
        )
        our_own = MatchFactory.create(
            stage=stage,
            home_team=None,
            away_team=None,
            home_team_undecided=shaped_like_one,
            away_team_undecided=shaped_like_one,
            datetime=KICK_OFF,
        )
        with self.assertNumQueries(1):
            self.assertCountEqual(
                matches_require_progression(), [synced_with_formula, our_own]
            )

    def test_synced_fixture_without_teams(self):
        """
        The sync, given a regular-round fixture the provider publishes without
        its teams, saves it with its placeholder; the match is not waiting on
        progression and the home page stands.
        """
        season = SeasonFactory.create(
            timezone="UTC",
            competition__upstream_url=STATE_CUP_URL,
            upstream_url=STATE_CUP_SEASON_URL,
        )
        reds = RemoteTeam(id="1", name="Reds")
        blues = RemoteTeam(id="2", name="Blues")
        apply_snapshot(
            season,
            [
                RemoteCompetition(
                    id="1",
                    name="Division One",
                    teams=(reds, blues),
                    matches=(
                        RemoteMatch(
                            id="10",
                            round_number=1,
                            round_type=ROUND_REGULAR,
                            round_name="Round 1",
                            start=KICK_OFF,
                            home_team_id=reds.id,
                            away_team_id=blues.id,
                        ),
                        RemoteMatch(
                            id="11",
                            round_number=2,
                            round_type=ROUND_REGULAR,
                            round_name="Round 2",
                            start=KICK_OFF,
                            is_tba=True,
                        ),
                    ),
                )
            ],
        )
        placeholder = season.divisions.get().matches.get(upstream_id="mysideline:11")
        self.assertEqual(
            (
                placeholder.home_team_undecided.label,
                placeholder.home_team_undecided.formula,
            ),
            (TBA_LABEL, ""),
        )
        self.assertEqual(
            placeholder.away_team_undecided, placeholder.home_team_undecided
        )
        self.assertNothingToProgress()


@per_shell
@freeze_time(NOW)
class UpstreamPlaceholderPageTests(TestCase):
    """
    The admin's home page, and the progression page, for a stage holding a
    match mirrored from an upstream provider which has yet to name its teams.
    Only the provider can fill them in, so neither page offers the match.
    """

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.stage = StageFactory.create(division__season__timezone="UTC", order=1)
        self.placeholder = synced_placeholder(self.stage, "mysideline:1")

    @property
    def progress_args(self):
        division = self.stage.division
        return (
            division.season.competition_id,
            division.season_id,
            division.pk,
            self.stage.pk,
        )

    def test_home_page_has_no_stage_to_progress(self):
        with self.login(self.superuser):
            self.get_check_200("admin:index")
        self.assertResponseContains(
            self.by_shell(
                workbook=(
                    '<p class="wb-muted">'
                    '<svg class="wb-icon" aria-hidden="true" focusable="false">'
                    '<use href="/static/touchtechnology/admin/workbook/icons.svg'
                    '#circle-check"></use></svg> No stages require progression.</p>'
                ),
                explorer=(
                    '<tr><td colspan="2" class="empty-state">'
                    "No stage is waiting for its teams.</td></tr>"
                ),
            )
        )

    def test_progression_page_has_nothing_to_progress(self):
        """
        Nothing on the stage can be progressed here, which the page answers as
        it does for any stage with nothing to progress: 410 Gone.
        """
        with self.login(self.superuser):
            self.get(PROGRESS, *self.progress_args)
        self.response_410()

    def test_progression_page_lists_only_what_can_be_progressed(self):
        """
        A match of our own on the same stage is still offered for progression,
        on its own: the provider's placeholder is not listed beside it.
        """
        semi = MatchFactory.create(
            stage=self.stage,
            datetime=PLAYED,
            home_team_score=4,
            away_team_score=3,
            label="Semi",
        )
        final = MatchFactory.create(
            stage=self.stage,
            home_team=None,
            home_team_eval="W",
            home_team_eval_related=semi,
            datetime=KICK_OFF,
            label="Final",
        )
        with self.login(self.superuser):
            self.get_check_200(PROGRESS, *self.progress_args)
        self.assertResponseContains(
            '<input type="hidden" name="form-TOTAL_FORMS" value="1" '
            'id="id_form-TOTAL_FORMS">'
        )
        self.assertResponseContains(
            f'<input type="hidden" name="form-0-id" value="{final.pk}" '
            'id="id_form-0-id">'
        )


@per_shell
@freeze_time(NOW)
class UpstreamPlaceholderPlacesTests(TestCase):
    """
    The places to fill on the progression page of a stage which holds the
    sync's placeholder beside undecided teams of our own. The next sync would
    write over whatever team was chosen for the placeholder, so it is not
    offered; every undecided team of our own still is.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        cls.stage = StageFactory.create(division__season__timezone="UTC", order=1)
        cls.placeholder = synced_placeholder(
            cls.stage, "mysideline:1"
        ).home_team_undecided

    def get_places(self, stage):
        """Open the progression page of ``stage``: the places it offers."""
        progress = stage.url_names["progress"]
        with self.login(self.superuser):
            self.get_check_200(progress.url_name, *progress.args)
        return [form.instance for form in self.get_context("formset").forms]

    def label(self, row, title):
        """The label of the place in ``row`` of the page."""
        return self.by_shell(
            workbook=(
                f'<label for="id_form-{row}-team" class="field_name">{title}</label>'
            ),
            explorer=(
                f'<label class="field-label" for="id_form-{row}-team">{title}</label>'
            ),
        )

    def assertPlacesQueries(self, places, queries):
        """
        Open the progression page of a stage with ``places`` of our own beside
        the placeholder, in ``queries``. The places are one query, whatever
        their number; each place still costs the evaluation of its match and
        the teams it may be filled with.
        """
        for number in range(1, places + 1):
            place_to_fill(self.stage, label=f"Place {number}", formula="")
        progress = self.stage.url_names["progress"]
        with self.login(self.superuser), self.assertNumQueries(queries):
            self.get(progress.url_name, *progress.args)
        self.assert_http_200_ok()
        self.assertResponseContains(
            '<input type="hidden" name="form-TOTAL_FORMS" '
            f'value="{places}" id="id_form-TOTAL_FORMS">'
        )

    def test_the_placeholder_is_not_a_place_to_fill(self):
        """
        Beside a place of our own, the sync's placeholder is not offered. Its
        formula is empty, so had it been offered it would be the first row.
        """
        ours = place_to_fill(self.stage, label="", formula="G1P2")
        self.assertEqual(self.get_places(self.stage), [ours])
        self.assertResponseContains(self.label(0, "G1P2"))
        self.assertResponseNotContains(self.label(0, TBA_LABEL))

    def test_places_of_our_own_are_all_offered(self):
        """A stage without the placeholder offers every undecided team."""
        stage = StageFactory.create(division__season__timezone="UTC", order=1)
        host = place_to_fill(stage, label="Host", formula="")
        position = place_to_fill(stage, label="", formula="G1P2")
        self.assertCountEqual(self.get_places(stage), [host, position])
        self.assertResponseContains(self.label(0, "Host"))
        self.assertResponseContains(self.label(1, "G1P2"))

    def test_a_tba_of_our_own_is_a_place_to_fill(self):
        """
        An undecided team of our own shaped like the placeholder (labelled
        "TBA", no formula) is offered: a match of our own stands on it.
        """
        ours = place_to_fill(self.stage, label=TBA_LABEL, formula="")
        self.assertEqual(self.get_places(self.stage), [ours])
        self.assertResponseContains(
            '<input type="hidden" name="form-TOTAL_FORMS" value="1" '
            'id="id_form-TOTAL_FORMS">'
        )
        self.assertResponseContains(
            f'<input type="hidden" name="form-0-id" value="{ours.pk}" '
            'id="id_form-0-id">'
        )

    def test_the_placeholder_on_a_match_of_our_own_is_a_place_to_fill(self):
        """
        Once a match of our own stands on the sync's placeholder as well,
        filling it is ours to do, and it is offered.
        """
        MatchFactory.create(
            stage=self.stage,
            home_team=None,
            home_team_undecided=self.placeholder,
            datetime=KICK_OFF,
        )
        self.assertEqual(self.get_places(self.stage), [self.placeholder])
        self.assertResponseContains(self.label(0, TBA_LABEL))

    def test_an_undecided_team_on_no_match_is_offered(self):
        """
        An undecided team which no match stands on is offered, as before: no
        match of the provider's says the sync owns it.
        """
        unused = UndecidedTeamFactory.create(stage=self.stage, label="Host")
        ours = place_to_fill(self.stage, label="", formula="G1P2")
        self.assertCountEqual(self.get_places(self.stage), [unused, ours])

    def test_queries_for_one_place(self):
        self.assertPlacesQueries(1, self.by_shell(workbook=24, explorer=23))

    def test_queries_for_six_places(self):
        self.assertPlacesQueries(6, self.by_shell(workbook=44, explorer=38))
