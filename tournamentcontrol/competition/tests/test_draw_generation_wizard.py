"""
The Draw Generation wizard: a match marked Skip on its last step is not
created (#630), and each step but the last moves on with Next (#631).
"""

import datetime

from django.utils.translation import gettext as _
from test_plus import TestCase

from touchtechnology.admin.tests.shells import IconMixin, per_shell
from touchtechnology.common.tests.factories import SuperUserFactory
from tournamentcontrol.competition.tests import factories

FINALS = (
    "ROUND\n"
    "1: P1 vs P4 Semi 1\n"
    "2: P2 vs P3 Semi 2\n"
    "3: P5 vs P6 5th/6th Playoff\n"
    "ROUND\n"
    "4: L1 vs L2 3rd/4th Playoff\n"
    "5: W1 vs W2 Final"
)

# The playoff of match 3 is played off again: it depends on match 3.
REPLAYED = f"{FINALS}\nROUND\n6: W3 vs L3 Replay"


@per_shell
class DrawGenerationWizardTests(IconMixin, TestCase):
    """A five team round robin, then finals that name a sixth team."""

    user_factory = SuperUserFactory

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.division = factories.DivisionFactory.create()
        cls.round_robin = factories.StageFactory.create(
            division=cls.division, title="Round Robin", order=1
        )
        factories.TeamFactory.create_batch(5, division=cls.division)
        cls.finals = factories.StageFactory.create(
            division=cls.division, title="Finals", order=2
        )
        cls.finals_format = factories.DrawFormatFactory.create(
            name="Finals", teams=6, text=FINALS
        )
        cls.replayed_format = factories.DrawFormatFactory.create(
            name="Finals and a replay", teams=6, text=REPLAYED
        )
        cls.playoffs = factories.StageFactory.create(
            division=cls.division, title="Playoffs", order=3
        )
        factories.StageGroupFactory.create(stage=cls.playoffs, title="Pool A", order=1)
        factories.StageGroupFactory.create(stage=cls.playoffs, title="Pool B", order=2)

    def setUp(self):
        super().setUp()
        self.login(self.make_user("superuser"))

    def post_draw_formats(self, stage, *forms):
        """The first step: one ``(format, skipped)`` per stage or pool."""
        data = {
            "draw_generation_wizard-current_step": "0",
            "0-TOTAL_FORMS": str(len(forms)),
            "0-INITIAL_FORMS": str(len(forms)),
            "0-MIN_NUM_FORMS": "0",
            "0-MAX_NUM_FORMS": "1000",
        }
        for index, (format, skipped) in enumerate(forms):
            data.update(
                {
                    f"0-{index}-start_date": "2026-10-31",
                    f"0-{index}-format": format.pk,
                    f"0-{index}-rounds": "",
                    f"0-{index}-offset": "",
                }
            )
            if skipped:
                data[f"0-{index}-DELETE"] = "on"
        url = stage.url_names["build"]
        self.post(url.url_name, *url.args, data=data)

    def post_draw_format(self, format):
        self.post_draw_formats(self.finals, (format, False))

    def post_draw_matches(self, *skipped, stage=None):
        """The last step as the first filled it in, with ``skipped`` labels skipped."""
        stage = stage or self.finals
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
            # Skip is a checkbox: ticked, it is posted; clear, it is not.
            if form.instance.label in skipped:
                data[f"1-{index}-DELETE"] = "on"
            else:
                del data[f"1-{index}-DELETE"]
        url = stage.url_names["build"]
        self.post(url.url_name, *url.args, data=data)

    def labels(self):
        return self.finals.matches.values_list("label", flat=True)

    def button(self, label):
        """The shell's primary submit button, reading ``label``."""
        return self.by_shell(
            workbook=(
                f'<button type="submit" class="wb-button wb-button-primary">'
                f"{label}</button>"
            ),
            explorer=(
                '<button type="submit" form="edit-form" class="button primary">'
                f"{self.icon('check')}<span>{label}</span></button>"
            ),
        )

    def problems(self, error):
        """The shell's list of what is wrong with the whole step."""
        return self.by_shell(
            workbook=(
                '<div class="wb-problems" role="alert" tabindex="-1">'
                f"<h2>{_('Please check the form')}</h2>"
                f"<ul><li>{error}</li></ul></div>"
            ),
            explorer=(
                '<div class="form-errors" role="alert">'
                f"{self.icon('alert')}<ul><li>{error}</li></ul></div>"
            ),
        )

    # Skip (#630).

    def test_skipped_match_is_not_created(self):
        self.post_draw_format(self.finals_format)
        self.assertEqual(self.get_context("wizard")["steps"].current, "1")
        self.post_draw_matches("5th/6th Playoff")
        self.assert_http_302_found(url=str(self.division.urls["edit"]))
        self.assertCountEqual(
            self.labels(), ["Semi 1", "Semi 2", "3rd/4th Playoff", "Final"]
        )

    def test_match_not_skipped_is_created(self):
        self.post_draw_format(self.finals_format)
        self.post_draw_matches()
        self.assert_http_302_found(url=str(self.division.urls["edit"]))
        self.assertCountEqual(
            self.labels(),
            ["Semi 1", "Semi 2", "5th/6th Playoff", "3rd/4th Playoff", "Final"],
        )

    def test_skipping_a_match_another_depends_on_is_refused(self):
        self.post_draw_format(self.replayed_format)
        self.post_draw_matches("5th/6th Playoff")
        self.assert_http_200_ok()
        self.assertEqual(self.get_context("wizard")["steps"].current, "1")
        self.assertEqual(
            self.get_context("form").non_form_errors(),
            ["Replay depends on 5th/6th Playoff, which is skipped."],
        )
        self.assertResponseContains(
            self.problems("Replay depends on 5th/6th Playoff, which is skipped.")
        )
        self.assertCountEqual(self.labels(), [])

    def test_skipping_a_match_and_those_depending_on_it(self):
        self.post_draw_format(self.replayed_format)
        self.post_draw_matches("5th/6th Playoff", "Replay")
        self.assert_http_302_found(url=str(self.division.urls["edit"]))
        self.assertCountEqual(
            self.labels(), ["Semi 1", "Semi 2", "3rd/4th Playoff", "Final"]
        )

    # Skip on the first step (#633).

    def test_skipped_pool_is_not_offered_or_created(self):
        self.post_draw_formats(
            self.playoffs, (self.finals_format, True), (self.finals_format, False)
        )
        self.assertEqual(self.get_context("wizard")["steps"].current, "1")
        self.assertCountEqual(
            [form.instance.stage_group.title for form in self.get_context("form")],
            ["Pool B"] * 5,
        )
        self.post_draw_matches(stage=self.playoffs)
        self.assert_http_302_found(url=str(self.division.urls["edit"]))
        self.assertCountEqual(
            self.playoffs.matches.values_list("stage_group__title", "label"),
            [
                ("Pool B", "Semi 1"),
                ("Pool B", "Semi 2"),
                ("Pool B", "5th/6th Playoff"),
                ("Pool B", "3rd/4th Playoff"),
                ("Pool B", "Final"),
            ],
        )

    def test_skipping_every_pool_is_refused(self):
        self.post_draw_formats(
            self.playoffs, (self.finals_format, True), (self.finals_format, True)
        )
        self.assert_http_200_ok()
        self.assertEqual(self.get_context("wizard")["steps"].current, "0")
        error = _("Choose at least one stage or pool to build.")
        self.assertEqual(self.get_context("form").non_form_errors(), [error])
        self.assertResponseContains(self.problems(error))
        self.assertCountEqual(self.playoffs.matches.all(), [])

    def test_skipping_the_only_stage_is_refused(self):
        self.post_draw_formats(self.finals, (self.finals_format, True))
        self.assert_http_200_ok()
        error = _("Choose at least one stage or pool to build.")
        self.assertEqual(self.get_context("form").non_form_errors(), [error])
        self.assertCountEqual(self.labels(), [])

    # Start date (#634).

    def test_start_date_is_required(self):
        url = self.finals.url_names["build"]
        self.post(
            url.url_name,
            *url.args,
            data={
                "draw_generation_wizard-current_step": "0",
                "0-TOTAL_FORMS": "1",
                "0-INITIAL_FORMS": "1",
                "0-MIN_NUM_FORMS": "0",
                "0-MAX_NUM_FORMS": "1000",
                "0-0-start_date": "",
                "0-0-format": self.finals_format.pk,
            },
        )
        self.assert_http_200_ok()
        self.assertEqual(
            self.get_context("form").errors,
            [{"start_date": [_("This field is required.")]}],
        )

    # Next, then Save (#631).

    def test_first_step_moves_on_with_next(self):
        url = self.finals.url_names["build"]
        self.get(url.url_name, *url.args)
        self.assert_http_200_ok()
        self.assertResponseContains(self.button(_("Next")))
        self.assertResponseNotContains(self.button(_("Save")))

    def test_last_step_saves(self):
        self.post_draw_format(self.finals_format)
        self.assertEqual(self.get_context("wizard")["steps"].current, "1")
        self.assertResponseContains(self.button(_("Save")))
        self.assertResponseNotContains(self.button(_("Next")))
