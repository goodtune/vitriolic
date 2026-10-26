"""
A position with no stage in it (P1, G1P2) is a place on the ladder of the
stage before. The first stage of a division has no stage before it, so such a
position names nothing there and the admin refuses it (#473). A position that
names its stage (S1G1P1) is not refused.
"""

import datetime

from test_plus import TestCase

from touchtechnology.admin.tests.shells import IconMixin, per_shell
from touchtechnology.common.tests.factories import SuperUserFactory
from tournamentcontrol.competition.forms import (
    DrawGenerationForm,
    UndecidedTeamForm,
)
from tournamentcontrol.competition.models import UndecidedTeam
from tournamentcontrol.competition.tests import factories


class FirstStageMixin:
    """
    A division of two teams whose first stage is Pools and whose second is
    Finals, and a draw format of positions on the ladder of the stage before.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.division = factories.DivisionFactory.create()
        factories.TeamFactory.create_batch(2, division=cls.division)
        cls.pools = factories.StageFactory.create(
            division=cls.division, title="Pools", order=1
        )
        cls.finals = factories.StageFactory.create(
            division=cls.division, title="Finals", order=2
        )
        cls.final = factories.DrawFormatFactory.create(
            name="Final", teams=2, text="ROUND\n1: P1 vs P2 Final"
        )

    def first_stage_error(self, formula):
        return (
            f"{formula} refers to the stage before this one, but Pools is the "
            "first stage of the division."
        )


class UndecidedTeamFormTests(FirstStageMixin, TestCase):
    def form(self, stage, formula):
        return UndecidedTeamForm(
            data={"formula": formula, "label": ""},
            instance=UndecidedTeam(stage=stage),
        )

    def test_position_on_the_first_stage_is_refused(self):
        for formula in ("P1", "G1P2"):
            with self.subTest(formula=formula):
                form = self.form(self.pools, formula)
                self.assertEqual(form.is_valid(), False)
                self.assertEqual(
                    form.errors["formula"], [self.first_stage_error(formula)]
                )

    def test_position_on_a_later_stage_is_accepted(self):
        form = self.form(self.finals, "G1P2")
        self.assertEqual(form.is_valid(), True)
        self.assertEqual(form.cleaned_data["formula"], "G1P2")

    def test_position_naming_its_stage_is_accepted(self):
        form = self.form(self.pools, "S1G1P1")
        self.assertEqual(form.is_valid(), True)
        self.assertEqual(form.cleaned_data["formula"], "S1G1P1")


class DrawGenerationFormTests(FirstStageMixin, TestCase):
    def form(self, stage):
        return DrawGenerationForm(
            initial=stage,
            data={"start_date": "2026-10-07", "format": self.final.pk},
        )

    def test_positions_on_the_first_stage_are_refused(self):
        form = self.form(self.pools)
        self.assertEqual(form.is_valid(), False)
        self.assertEqual(
            form.errors["format"],
            [self.first_stage_error("P1"), self.first_stage_error("P2")],
        )

    def test_positions_on_a_later_stage_are_accepted(self):
        form = self.form(self.finals)
        self.assertEqual(form.is_valid(), True)
        self.assertEqual(
            [
                (m.home_team_eval, m.away_team_eval)
                for m in form.cleaned_data["matches"]
            ],
            [("P1", "P2")],
        )


class MatchFormTests(FirstStageMixin, TestCase):
    """
    The admin's match form does not offer the evals, so it cannot save a
    position on a first stage: the administration MCP tools offer them and
    refuse one (``mcp.admin.forms.position_eval_error``).
    """

    user_factory = SuperUserFactory

    def test_eval_is_not_saved(self):
        match = factories.MatchFactory.create(stage=self.pools)
        url = match.url_names["edit"]
        self.login(self.make_user("superuser"))
        self.post(
            url.url_name,
            *url.args,
            data={
                "home_team": match.home_team.pk,
                "away_team": match.away_team.pk,
                "label": "Final",
                "round": "1",
                "date": "2026-10-07",
                "include_in_ladder": "0",
                "home_team_eval": "P1",
            },
        )
        self.assert_http_302_found(url=str(self.pools.urls["edit"]))
        match.refresh_from_db()
        self.assertEqual((match.label, match.home_team_eval), ("Final", None))


@per_shell
class FirstStagePositionAdminTests(IconMixin, FirstStageMixin, TestCase):
    user_factory = SuperUserFactory

    def setUp(self):
        super().setUp()
        self.login(self.make_user("superuser"))

    def field_error(self, name, *errors):
        """A field's errors as the shell draws them."""
        return self.by_shell(
            workbook=(
                f'<p class="wb-error" id="id_{name}_error">'
                f'{self.icon("circle-alert")}<span>{" ".join(errors)}</span></p>'
            ),
            explorer=(
                f'<ul class="field-errors" id="id_{name}-errors">'
                f'{"".join(f"<li>{error}</li>" for error in errors)}</ul>'
            ),
        )

    # The undecided team form.

    def post_undecided_team(self, stage, formula):
        url = UndecidedTeam(stage=stage).url_names["add"]
        self.post(url.url_name, *url.args, data={"formula": formula, "label": ""})

    def test_undecided_team_position_on_the_first_stage_is_refused(self):
        for formula in ("P1", "G1P2"):
            with self.subTest(formula=formula):
                self.post_undecided_team(self.pools, formula)
                self.assert_http_200_ok()
                self.assertResponseContains(
                    self.field_error("formula", self.first_stage_error(formula))
                )
                self.assertCountEqual(self.pools.undecided_teams.all(), [])

    def test_undecided_team_position_on_a_later_stage_is_saved(self):
        self.post_undecided_team(self.finals, "G1P2")
        self.assert_http_302_found(url=str(self.finals.urls["edit"]))
        self.assertCountEqual(
            self.finals.undecided_teams.values_list("formula", flat=True), ["G1P2"]
        )

    def test_undecided_team_position_naming_its_stage_is_saved(self):
        self.post_undecided_team(self.pools, "S1G1P1")
        self.assert_http_302_found(url=str(self.pools.urls["edit"]))
        self.assertCountEqual(
            self.pools.undecided_teams.values_list("formula", flat=True), ["S1G1P1"]
        )

    # The draw wizard.

    def post_draw_format(self, stage):
        url = stage.url_names["build"]
        self.post(
            url.url_name,
            *url.args,
            data={
                "draw_generation_wizard-current_step": "0",
                "0-TOTAL_FORMS": "1",
                "0-INITIAL_FORMS": "1",
                "0-MIN_NUM_FORMS": "0",
                "0-MAX_NUM_FORMS": "1000",
                "0-0-start_date": "2026-10-07",
                "0-0-format": self.final.pk,
                "0-0-rounds": "",
                "0-0-offset": "",
            },
        )

    def test_draw_of_positions_on_the_first_stage_is_refused(self):
        self.post_draw_format(self.pools)
        self.assert_http_200_ok()
        self.assertEqual(self.get_context("wizard")["steps"].current, "0")
        self.assertResponseContains(
            self.field_error(
                "0-0-format",
                self.first_stage_error("P1"),
                self.first_stage_error("P2"),
            )
        )

    def test_draw_of_positions_on_a_later_stage_is_saved(self):
        self.post_draw_format(self.finals)
        self.assert_http_200_ok()
        self.assertEqual(self.get_context("wizard")["steps"].current, "1")
        formset = self.get_context("form")
        data = {
            "draw_generation_wizard-current_step": "1",
            "1-TOTAL_FORMS": str(formset.total_form_count()),
            "1-INITIAL_FORMS": str(formset.initial_form_count()),
            "1-MIN_NUM_FORMS": "0",
            "1-MAX_NUM_FORMS": "1000",
        }
        for index, form in enumerate(formset.forms):
            for name in form.fields:
                value = form.initial.get(name)
                if isinstance(value, datetime.datetime):
                    value = value.date()
                data[f"1-{index}-{name}"] = "" if value is None else str(value)
        url = self.finals.url_names["build"]
        self.post(url.url_name, *url.args, data=data)
        self.assert_http_302_found(url=str(self.division.urls["edit"]))
        self.assertCountEqual(
            self.finals.matches.values_list("home_team_eval", "away_team_eval"),
            [("P1", "P2")],
        )
