import base64
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.urls import reverse
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.tasks import generate_pdf_scorecards
from tournamentcontrol.competition.tests import factories

FAKE_PDF = b"%PDF-1.4 fake scorecards"
UTC = ZoneInfo("UTC")


class ScorecardTestCase(TestCase):
    """
    Exercise the real keyword argument plumbing from the admin views, through
    the celery task (executed eagerly, and serialized, in the test settings)
    and into the ``prince`` PDF renderer. Refs #42.
    """

    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.stage = factories.StageFactory.create()
        self.season = self.stage.division.season
        self.competition = self.season.competition
        self.matches = [
            factories.MatchFactory.create(
                stage=self.stage, datetime=datetime(2017, 2, 13, 10, 0, tzinfo=UTC)
            ),
            factories.MatchFactory.create(
                stage=self.stage, datetime=datetime(2017, 2, 13, 11, 0, tzinfo=UTC)
            ),
            factories.MatchFactory.create(
                stage=self.stage, datetime=datetime(2017, 2, 14, 10, 0, tzinfo=UTC)
            ),
        ]
        self.patcher = patch(
            "tournamentcontrol.competition.utils.prince", return_value=FAKE_PDF
        )
        self.prince = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def assertRenderedPdf(self, **kwargs):
        """
        The HTML rendered from the scorecard template was handed to prince
        with exactly the given keyword arguments.
        """
        self.prince.assert_called_once()
        self.assertIn("<html>", self.prince.call_args.args[0])
        self.assertEqual(self.prince.call_args.kwargs, kwargs)

    def assertRedirectsToAsyncResult(self):
        self.response_302()
        prefix = reverse(
            "admin:fixja:competition:season:scorecards-async",
            kwargs={
                "competition_id": self.competition.pk,
                "season_id": self.season.pk,
                "result_id": "result",
            },
        ).replace("result.pdf", "")
        self.assertTrue(self.last_response["Location"].startswith(prefix))

    def capture_context(self):
        """
        Replace the template lookup so the context handed to the scorecard
        template can be inspected by the test.
        """
        patcher = patch("tournamentcontrol.competition.utils.select_template")
        select_template = patcher.start()
        self.addCleanup(patcher.stop)
        select_template.return_value.render.return_value = "<html>captured</html>"
        return select_template.return_value.render


class DateScorecardTests(ScorecardTestCase):
    def test_pdf(self):
        render = self.capture_context()
        with self.login(self.superuser):
            self.get(
                "admin:fixja:scorecards",
                self.competition.pk,
                self.season.pk,
                "20170213",
                "pdf",
            )
        self.assertRedirectsToAsyncResult()
        self.assertRenderedPdf()
        context = render.call_args.args[0]
        self.assertCountEqual(context["matches"], self.matches[:2])
        self.assertEqual(context["competition"], self.competition)
        self.assertEqual(context["season"], self.season)
        self.assertEqual(context["date"], date(2017, 2, 13))
        self.assertIsNone(context["time"])
        self.assertIsNone(context.get("stage"))

    def test_pdf_with_time(self):
        render = self.capture_context()
        with self.login(self.superuser):
            self.get(
                "admin:fixja:scorecards",
                self.competition.pk,
                self.season.pk,
                "1100",
                "20170213",
                "pdf",
            )
        self.assertRedirectsToAsyncResult()
        self.assertRenderedPdf()
        context = render.call_args.args[0]
        self.assertCountEqual(context["matches"], self.matches[1:2])
        self.assertEqual(context["date"], date(2017, 2, 13))
        self.assertEqual(context["time"], time(11, 0))

    def test_html(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:scorecards",
                self.competition.pk,
                self.season.pk,
                "20170213",
                "html",
            )
        self.response_200()
        self.assertIn("<html>", self.last_response.content.decode("utf8"))
        self.prince.assert_not_called()

    def test_login_required(self):
        self.assertLoginRequired(
            "admin:fixja:scorecards",
            self.competition.pk,
            self.season.pk,
            "20170213",
            "pdf",
        )
        self.prince.assert_not_called()


class StageScorecardTests(ScorecardTestCase):
    url = "admin:fixja:competition:season:division:stage:scorecards"

    def test_pdf_clears_matches_needing_printing(self):
        render = self.capture_context()
        self.stage.matches_needing_printing.set(self.matches[:2])
        with self.login(self.superuser):
            self.get(
                self.url,
                self.competition.pk,
                self.season.pk,
                self.stage.division.pk,
                self.stage.pk,
                "pdf",
            )
        self.assertRedirectsToAsyncResult()
        self.assertRenderedPdf()
        context = render.call_args.args[0]
        self.assertCountEqual(context["matches"], self.matches[:2])
        self.assertEqual(context["competition"], self.competition)
        self.assertEqual(context["season"], self.season)
        self.assertEqual(context["stage"], self.stage)
        self.assertEqual(self.stage.matches_needing_printing.count(), 0)

    def test_html(self):
        with self.login(self.superuser):
            self.get(
                self.url,
                self.competition.pk,
                self.season.pk,
                self.stage.division.pk,
                self.stage.pk,
                "html",
            )
        self.response_200()
        self.assertIn("<html>", self.last_response.content.decode("utf8"))
        self.prince.assert_not_called()

    def test_login_required(self):
        self.assertLoginRequired(
            self.url,
            self.competition.pk,
            self.season.pk,
            self.stage.division.pk,
            self.stage.pk,
            "pdf",
        )
        self.prince.assert_not_called()


class AsyncResultViewTests(ScorecardTestCase):
    url = "admin:fixja:competition:season:scorecards-async"

    def test_ready(self):
        with patch(
            "tournamentcontrol.competition.admin.generate_pdf_scorecards.AsyncResult"
        ) as AsyncResult:
            AsyncResult.return_value.ready.return_value = True
            AsyncResult.return_value.wait.return_value = base64.b64encode(
                FAKE_PDF
            ).decode("utf8")
            with self.login(self.superuser):
                self.get(self.url, self.competition.pk, self.season.pk, "abc-123")
        self.response_200()
        AsyncResult.assert_called_once_with("abc-123")
        self.assertEqual(self.last_response["Content-Type"], "application/pdf")
        self.assertEqual(self.last_response.content, FAKE_PDF)

    def test_pending(self):
        with patch(
            "tournamentcontrol.competition.admin.generate_pdf_scorecards.AsyncResult"
        ) as AsyncResult:
            AsyncResult.return_value.ready.return_value = False
            with self.login(self.superuser):
                self.get(self.url, self.competition.pk, self.season.pk, "abc-123")
        self.response_200()
        self.assertTrue(self.last_response.has_header("Refresh"))

    def test_login_required(self):
        self.assertLoginRequired(self.url, self.competition.pk, self.season.pk, "abc")


class GeneratePdfScorecardsTaskTests(ScorecardTestCase):
    """
    Call the task with exactly the keyword arguments the admin view builds
    (including the tenant specific ones) so a signature change is caught.
    """

    templates = ("tournamentcontrol/competition/admin/scorecards.html",)

    def test_stage_keyword_arguments(self):
        render = self.capture_context()
        self.stage.matches_needing_printing.set(self.matches)
        result = generate_pdf_scorecards.delay(
            match_pks=[m.pk for m in self.matches],
            templates=self.templates,
            extra_context={"date": date(2017, 2, 13), "time": None},
            season_pk=self.season.pk,
            stage_pk=self.stage.pk,
            _schema_name="tenant",
            base_url="http://tenant.example.com/",
        )
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertRenderedPdf(
            _schema_name="tenant", base_url="http://tenant.example.com/"
        )
        context = render.call_args.args[0]
        self.assertCountEqual(context["matches"], self.matches)
        self.assertEqual(context["competition"], self.competition)
        self.assertEqual(context["season"], self.season)
        self.assertEqual(context["stage"], self.stage)
        self.assertEqual(context["date"], date(2017, 2, 13))
        self.assertIsNone(context["time"])
        self.assertEqual(self.stage.matches_needing_printing.count(), 0)

    def test_season_keyword_arguments(self):
        render = self.capture_context()
        result = generate_pdf_scorecards.delay(
            match_pks=[m.pk for m in self.matches],
            templates=self.templates,
            extra_context={},
            season_pk=self.season.pk,
        )
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertRenderedPdf()
        context = render.call_args.args[0]
        self.assertEqual(context["competition"], self.competition)
        self.assertEqual(context["season"], self.season)
        self.assertNotIn("stage", context)

    def test_positional_arguments(self):
        result = generate_pdf_scorecards.delay(
            [m.pk for m in self.matches], self.templates, {}
        )
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertRenderedPdf()


class ScorecardReportWizardTests(ScorecardTestCase):
    """
    The "Reports" wizard reaches the same task and HTML generator through a
    different call path.
    """

    url = "admin:fixja:scorecard-report"

    def run_wizard(self, mode):
        with self.login(self.superuser):
            self.get(self.url)
            self.response_200()
            self.post(
                self.url,
                data={
                    "scorecard_wizard-current_step": "0",
                    "0-season": self.season.pk,
                },
            )
            self.response_200()
            self.post(
                self.url,
                data={
                    "scorecard_wizard-current_step": "1",
                    "1-template": "scorecards.html",
                    "1-format": mode,
                },
            )

    def test_pdf(self):
        render = self.capture_context()
        self.run_wizard("pdf")
        self.assertRedirectsToAsyncResult()
        self.assertRenderedPdf()
        context = render.call_args.args[0]
        self.assertCountEqual(context["matches"], self.matches)
        self.assertEqual(context["competition"], self.competition)
        self.assertEqual(context["season"], self.season)

    def test_html(self):
        render = self.capture_context()
        self.run_wizard("html")
        self.response_200()
        self.assertEqual(self.last_response.content, b"<html>captured</html>")
        self.prince.assert_not_called()
        context = render.call_args.args[0]
        self.assertCountEqual(context["matches"], self.matches)
        self.assertEqual(context["competition"], self.competition)
        self.assertEqual(context["season"], self.season)

    def test_login_required(self):
        self.assertLoginRequired(self.url)
