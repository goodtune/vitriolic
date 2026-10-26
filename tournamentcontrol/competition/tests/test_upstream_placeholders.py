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
whatever team was chosen for it. For the same reason it is not an undecided
team anywhere a person chooses one: it does not make a match of our own
progressable, the match and pool forms do not offer it, and a draw is built
for the undecided teams of our own without it.
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
from tournamentcontrol.competition.draw.services import (
    draw_generator,
    draw_target_team_count,
    generate_stage_draw,
)
from tournamentcontrol.competition.forms import MatchEditForm
from tournamentcontrol.competition.mcp.admin.forms import position_eval_error
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests.factories import (
    DrawFormatFactory,
    MatchFactory,
    SeasonFactory,
    StageFactory,
    StageGroupFactory,
    TeamFactory,
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
from tournamentcontrol.competition.utils import round_robin_format

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


def unresolved_final(stage):
    """
    A final of our own, between the winner of a semi final of ours which is
    yet to be played and a team: it waits on progression, and nothing can
    resolve it until the semi final has a result.
    """
    semi = MatchFactory.create(stage=stage, datetime=KICK_OFF, label="Semi")
    return MatchFactory.create(
        stage=stage,
        home_team=None,
        home_team_eval="W",
        home_team_eval_related=semi,
        datetime=KICK_OFF,
        label="Final",
    )


def finals_after(first):
    """
    A finals stage after ``first``, holding the sync's placeholder beside
    four undecided teams of our own, the top four of the stage before.
    """
    finals = StageFactory.create(division=first.division, title="Finals", order=2)
    finals.placeholder = synced_placeholder(finals, "mysideline:2").home_team_undecided
    finals.places = [
        UndecidedTeamFactory.create(stage=finals, formula=f"P{position}", label="")
        for position in range(1, 5)
    ]
    return finals


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

    def test_a_final_of_our_own_is_not_progressable_for_the_placeholder(self):
        """
        A final of our own whose semi final is unplayed, on a stage whose only
        undecided team is the placeholder: it waits on progression, but the
        placeholder is not a place a person can fill, so there is nothing to
        progress on the stage yet.
        """
        stage = StageFactory.create(division__season__timezone="UTC", order=1)
        synced_placeholder(stage, "mysideline:1")
        final = unresolved_final(stage)
        self.assertCountEqual(matches_require_progression(), [final])
        self.assertCountEqual(matches_progression_possible(), [])
        self.assertEqual(stages_require_progression(), {})

    def test_a_place_of_our_own_makes_the_stage_progressable(self):
        """
        Beside a place of our own the stage is progressable, as before: the
        page which fills the place can be opened, and it lists the final too.
        """
        stage = StageFactory.create(division__season__timezone="UTC", order=1)
        synced_placeholder(stage, "mysideline:1")
        final = unresolved_final(stage)
        host = place_to_fill(stage, label="Host", formula="")
        self.assertCountEqual(
            matches_progression_possible(),
            [final, stage.matches.get(home_team_undecided=host)],
        )

    def assertProgressionQueries(self, finals, queries):
        """
        Work out what can be progressed, with ``finals`` finals of our own
        beside the placeholder, in ``queries``: whether a stage holds a place
        to fill is asked once for each stage, not once for each match. Each
        final still costs the evaluation of its own sides.
        """
        stage = StageFactory.create(division__season__timezone="UTC", order=1)
        synced_placeholder(stage, "mysideline:1")
        for __ in range(finals):
            unresolved_final(stage)
        with self.assertNumQueries(queries):
            possible = matches_progression_possible()
        self.assertCountEqual(possible, [])

    def test_queries_for_one_final(self):
        self.assertProgressionQueries(1, 6)

    def test_queries_for_four_finals(self):
        self.assertProgressionQueries(4, 12)


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

    def assertHomePageHasNoStageToProgress(self):
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

    def test_home_page_has_no_stage_to_progress(self):
        self.assertHomePageHasNoStageToProgress()

    def test_home_page_has_no_stage_to_progress_for_a_final_of_our_own(self):
        """
        A final of our own whose semi final is unplayed does not make the stage
        one to progress: the placeholder is not a place a person can fill.
        """
        unresolved_final(self.stage)
        self.assertHomePageHasNoStageToProgress()

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


@per_shell
@freeze_time(NOW)
class UpstreamPlaceholderMatchFormTests(TestCase):
    """
    The match pages of a stage holding the sync's placeholder. It is not an
    undecided team a person can choose for a match: on a division synced from
    the provider (one stage, whose only undecided team is the placeholder) a
    match of our own is between teams of the division, and beside an undecided
    team of our own the placeholder is never among the undecided choices.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        cls.stage = StageFactory.create(division__season__timezone="UTC", order=1)
        cls.placeholder = synced_placeholder(
            cls.stage, "mysideline:1"
        ).home_team_undecided
        cls.teams = TeamFactory.create_batch(2, division=cls.stage.division)

    def get_form(self, match, view):
        """Open the ``view`` page of ``match``: the form it offers."""
        lookup = match.url_names[view]
        with self.login(self.superuser):
            self.get_check_200(lookup.url_name, *lookup.args)
        return self.get_context("form")

    def assertTeamFields(self, form):
        """``form`` offers the teams of the division, and no undecided team."""
        self.assertCountEqual(form.fields["home_team"].queryset, self.teams)
        self.assertCountEqual(form.fields["away_team"].queryset, self.teams)
        self.assertEqual(
            [name for name in form.fields if name.endswith("_undecided")], []
        )

    def test_adding_a_match_of_our_own_offers_the_teams(self):
        self.assertTeamFields(self.get_form(Match(stage=self.stage), "add"))

    def test_editing_a_match_of_our_own_offers_the_teams(self):
        home, away = self.teams
        match = MatchFactory.create(
            stage=self.stage, home_team=home, away_team=away, datetime=KICK_OFF
        )
        self.assertTeamFields(self.get_form(match, "edit"))
        self.assertResponseContains(
            f'<option value="{home.pk}" selected>{home.title}</option>'
        )

    def test_the_placeholder_is_not_an_undecided_choice(self):
        """
        Beside a place of our own the undecided fields are offered, and ours
        is their only choice.
        """
        host = place_to_fill(self.stage, label="Host", formula="")
        form = self.get_form(self.stage.matches.get(home_team_undecided=host), "edit")
        self.assertCountEqual(form.fields["home_team_undecided"].queryset, [host])
        self.assertCountEqual(form.fields["away_team_undecided"].queryset, [host])
        self.assertResponseContains(
            f'<option value="{host.pk}" selected>{host.title}</option>'
        )
        self.assertResponseNotContains(
            f'<option value="{self.placeholder.pk}">{TBA_LABEL}</option>'
        )

    def test_queries(self):
        """
        Building the form asks whether the stage has pools, and once whether
        it holds an undecided team of our own. The teams and undecided teams
        each field offers are queried as the form is rendered, not here.
        """
        host = place_to_fill(self.stage, label="Host", formula="")
        match = self.stage.matches.select_related(
            "home_team_undecided", "away_team"
        ).get(home_team_undecided=host)
        with self.assertNumQueries(2):
            MatchEditForm(instance=match)


@per_shell
@freeze_time(NOW)
class UpstreamPlaceholderPoolFormTests(TestCase):
    """
    The pool page of a finals stage holding the sync's placeholder beside
    undecided teams of our own: the placeholder cannot be put in a pool, as
    the provider will never name its team.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        first = StageFactory.create(division__season__timezone="UTC", order=1)
        cls.finals = finals_after(first)
        cls.pool = StageGroupFactory.create(stage=cls.finals, title="Pool A")

    def test_the_placeholder_is_not_offered_to_a_pool(self):
        edit = self.pool.url_names["edit"]
        with self.login(self.superuser):
            self.get_check_200(edit.url_name, *edit.args)
        self.assertCountEqual(
            self.get_context("form").fields["teams"].queryset, self.finals.places
        )


@freeze_time(NOW)
class UpstreamPlaceholderDrawTests(TestCase):
    """
    A draw for a finals stage holding the sync's placeholder beside undecided
    teams of our own is built for ours alone: the format's numbered teams map
    onto them, the count the draw is built for is theirs, and a position past
    them is refused.
    """

    @classmethod
    def setUpTestData(cls):
        cls.first = StageFactory.create(division__season__timezone="UTC", order=1)
        cls.finals = finals_after(cls.first)

    def test_numbered_teams_map_onto_our_undecided_teams(self):
        generator = draw_generator(self.finals, round_robin_format(4))
        self.assertEqual(dict(generator.teams), dict(enumerate(self.finals.places)))

    def test_a_draw_stands_on_our_undecided_teams_only(self):
        matches = generate_stage_draw(
            self.finals, round_robin_format(4), datetime.date(2019, 7, 20)
        )
        self.assertEqual(len(matches), 6)
        self.assertCountEqual(
            {match.home_team_undecided for match in matches}
            | {match.away_team_undecided for match in matches},
            self.finals.places,
        )

    def test_a_pool_draw_stands_on_our_undecided_teams_only(self):
        """
        The placeholder, were it in a pool, is not a team of the pool's draw.
        """
        pool = StageGroupFactory.create(stage=self.finals, title="Pool A")
        top_two = self.finals.places[:2]
        pool.undecided_teams.set([self.finals.placeholder, *top_two])
        generator = draw_generator(pool, round_robin_format(2))
        self.assertEqual(dict(generator.teams), dict(enumerate(top_two)))
        self.assertEqual(draw_target_team_count(pool), 2)

    def test_the_draw_is_built_for_our_undecided_teams(self):
        self.assertEqual(draw_target_team_count(self.finals), 4)

    def test_a_position_past_our_undecided_teams_is_refused(self):
        after = StageFactory.create(division=self.first.division, order=3)
        self.assertEqual(position_eval_error(after, "P4"), None)
        self.assertEqual(
            position_eval_error(after, "P5"),
            "P5 refers to position 5, but Finals has 4 teams.",
        )


@per_shell
@freeze_time(NOW)
class UpstreamPlaceholderDrawWizardTests(TestCase):
    """
    The draw generation page of a finals stage holding the sync's placeholder
    beside four undecided teams of our own offers the formats for four teams.
    """

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        cls.superuser = cls.make_user("superuser")
        first = StageFactory.create(division__season__timezone="UTC", order=1)
        cls.finals = finals_after(first)
        cls.four = DrawFormatFactory.create(teams=4)
        DrawFormatFactory.create(teams=6)

    def test_formats_for_our_undecided_teams_are_offered(self):
        build = self.finals.url_names["build"]
        with self.login(self.superuser):
            self.get_check_200(build.url_name, *build.args)
        (form,) = self.get_context("form").forms
        self.assertCountEqual(form.fields["format"].queryset, [self.four])
