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
"""

import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time
from test_plus import TestCase

from touchtechnology.admin.tests.shells import per_shell
from touchtechnology.common.tests.factories import UserFactory
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
