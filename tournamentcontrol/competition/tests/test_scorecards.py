import base64
from datetime import date, datetime, time
from unittest.mock import ANY, patch
from zoneinfo import ZoneInfo

import requests
import responses
from celery import states
from celery.exceptions import TaskRevokedError
from celery.result import AsyncResult
from django.test import override_settings
from django.urls import reverse
from test_plus import TestCase

from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.admin import SCORECARD_PDF_WAIT
from tournamentcontrol.competition.tasks import (
    generate_pdf_grid,
    generate_pdf_scorecards,
)
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

    def start_patch(self, patcher):
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

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
    """
    The polling views read the task state straight from the result backend.
    They must never build an ``AsyncResult``: when one is ready, or garbage
    collected, it unsubscribes from the Redis result channel, and if that
    needs a reconnect redis-py deadlocks on its own pub/sub lock, hanging the
    request until gunicorn kills the worker.
    """

    url = "admin:fixja:competition:season:scorecards-async"

    def setUp(self):
        super().setUp()
        backend = generate_pdf_scorecards.backend
        self.get_task_meta = self.start_patch(patch.object(backend, "get_task_meta"))
        self.remove_pending_result = self.start_patch(
            patch.object(backend, "remove_pending_result")
        )
        self.async_result_init = self.start_patch(
            patch.object(AsyncResult, "__init__", autospec=True, return_value=None)
        )

    def poll(self, status, result=None):
        self.get_task_meta.return_value = {"status": status, "result": result}
        with self.login(self.superuser):
            self.get(self.url, self.competition.pk, self.season.pk, "abc-123")

    def assertNoAsyncResult(self):
        self.get_task_meta.assert_called_once_with("abc-123")
        self.async_result_init.assert_not_called()
        self.remove_pending_result.assert_not_called()

    def assertWaiting(self):
        self.response_200()
        self.assertResponseHeaders({"Refresh": str(SCORECARD_PDF_WAIT)})
        self.assertResponseContains(
            "<p>Your scorecards will finish generating shortly.</p>"
        )
        self.assertNoAsyncResult()

    def test_ready(self):
        self.poll(states.SUCCESS, base64.b64encode(FAKE_PDF).decode("utf8"))
        self.response_200()
        self.assertEqual(self.last_response["Content-Type"], "application/pdf")
        self.assertEqual(self.last_response.content, FAKE_PDF)
        self.assertNoAsyncResult()

    def test_pending(self):
        self.poll(states.PENDING)
        self.assertWaiting()

    def test_started(self):
        self.poll(states.STARTED)
        self.assertWaiting()

    def test_retry(self):
        """
        A task waiting to retry a failed render is still in progress.
        """
        self.poll(states.RETRY, requests.Timeout("timed out"))
        self.assertWaiting()

    def test_failed(self):
        """
        A render that failed for good shows a plain message and a way to start
        again, rather than re-raising the background error as a server error.
        """
        self.poll(states.FAILURE, requests.HTTPError("504 Server Error"))
        self.response_200()
        self.assertResponseHeaders({"Refresh": None})
        self.assertResponseContains(
            '<div class="alert alert-danger alert-dismissable">'
            '<button type="button" class="close" data-dismiss="alert" '
            'aria-hidden="true">&#215;</button>'
            "The PDF service didn&#x27;t respond, so your PDF could not be "
            "generated. Please try again.</div>"
        )
        self.assertResponseContains(f'<a href="{self.start_again()}">Start again</a>')
        self.assertNoAsyncResult()

    def test_revoked(self):
        with self.assertRaises(TaskRevokedError):
            self.poll(states.REVOKED, TaskRevokedError("revoked"))
        self.assertNoAsyncResult()

    def test_login_required(self):
        self.assertLoginRequired(self.url, self.competition.pk, self.season.pk, "abc")
        self.get_task_meta.assert_not_called()

    def start_again(self):
        return reverse("admin:fixja:scorecard-report")


class GridAsyncResultViewTests(AsyncResultViewTests):
    url = "admin:fixja:competition:season:grid-async"

    def start_again(self):
        return self.season.urls["edit"]


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=False, TOURNAMENTCONTROL_ASYNC_PDF_GRID=True
)
class QueuePdfTaskTests(ScorecardTestCase):
    """
    Queueing a PDF task from a request must not subscribe the web process to
    the task's Redis result channel (``RedisBackend.on_task_call``), so that
    nothing in the web process ever needs to unsubscribe from it again.

    Running eagerly skips publishing altogether, so eager mode is turned off
    and the publish itself is replaced.
    """

    def setUp(self):
        super().setUp()
        app = generate_pdf_scorecards.app
        self.send_task_message = self.start_patch(
            patch.object(app.amqp, "send_task_message")
        )
        self.on_task_call = self.start_patch(patch.object(app.backend, "on_task_call"))

    def assertQueuedWithoutSubscribing(self, task):
        self.response_302()
        self.send_task_message.assert_called_once()
        self.assertEqual(self.send_task_message.call_args.args[1], task.name)
        self.on_task_call.assert_not_called()

    def test_scorecards(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:scorecards",
                self.competition.pk,
                self.season.pk,
                "20170213",
                "pdf",
            )
        self.assertRedirectsToAsyncResult()
        self.assertQueuedWithoutSubscribing(generate_pdf_scorecards)

    def test_scorecard_report_wizard(self):
        with self.login(self.superuser):
            self.get("admin:fixja:scorecard-report")
            self.response_200()
            self.post(
                "admin:fixja:scorecard-report",
                data={
                    "scorecard_wizard-current_step": "0",
                    "0-season": self.season.pk,
                },
            )
            self.response_200()
            self.post(
                "admin:fixja:scorecard-report",
                data={
                    "scorecard_wizard-current_step": "1",
                    "1-template": "scorecards.html",
                    "1-format": "pdf",
                },
            )
        self.assertRedirectsToAsyncResult()
        self.assertQueuedWithoutSubscribing(generate_pdf_scorecards)

    def test_season_grid(self):
        with self.login(self.superuser):
            self.get(
                "admin:fixja:competition:season:match-grid",
                self.competition.pk,
                self.season.pk,
                "pdf",
            )
        self.assertQueuedWithoutSubscribing(generate_pdf_grid)


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

    def test_stores_result(self):
        """
        The task is queued with ``ignore_result=True``, so it stores its own
        result for the admin to poll. ``apply_async`` runs eagerly here but
        carries the same options as a queued message.
        """
        with patch.object(generate_pdf_scorecards.backend, "store_result") as store:
            generate_pdf_scorecards.apply_async(
                ([m.pk for m in self.matches], self.templates, {}),
                task_id="abc-123",
            )
        store.assert_called_once_with(
            "abc-123",
            base64.b64encode(FAKE_PDF).decode("utf8"),
            states.SUCCESS,
            request=ANY,
        )

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
    def test_stores_failure(self):
        """
        A worker does not propagate the exception, it stores it as the result
        so the admin can raise it.
        """
        self.prince.side_effect = ValueError("prince failed")
        with patch.object(generate_pdf_scorecards.backend, "store_result") as store:
            result = generate_pdf_scorecards.apply_async(
                ([m.pk for m in self.matches], self.templates, {}),
                task_id="abc-123",
            )
        self.assertEqual(result.state, states.FAILURE)
        store.assert_called_once()
        task_id, exc, state = store.call_args.args
        self.assertEqual(task_id, "abc-123")
        self.assertEqual(str(exc), "prince failed")
        self.assertEqual(state, states.FAILURE)


PDF_SERVICE = "https://pdf.example.com/"


@override_settings(PRINCE_SERVER="pdf.example.com", CELERY_TASK_EAGER_PROPAGATES=False)
class PdfServiceRetryTests(TestCase):
    """
    The PDF tasks retry a render that the remote PDF service failed with a
    timeout, a connection error or a 5xx, but not a 4xx.

    Eager tasks retry inline, without waiting for the countdown, but only when
    eager errors are not propagated; otherwise ``Retry`` itself is raised. So
    these tests turn propagation off and inspect the final result instead.
    """

    templates = ("tournamentcontrol/competition/admin/scorecards.html",)

    def setUp(self):
        super().setUp()
        self.stage = factories.StageFactory.create()
        self.season = self.stage.division.season
        self.match = factories.MatchFactory.create(
            stage=self.stage, datetime=datetime(2017, 2, 13, 10, 0, tzinfo=UTC)
        )
        self.pdf_service = responses.RequestsMock()
        self.pdf_service.start()
        self.addCleanup(self.pdf_service.reset)
        self.addCleanup(self.pdf_service.stop)

    def reply(self, *replies):
        """
        Queue the PDF service's answers to successive renders: an exception to
        raise, or a status code (a 200 carries the PDF). The last one repeats.
        """
        for reply in replies:
            if isinstance(reply, Exception):
                self.pdf_service.post(PDF_SERVICE, body=reply)
            else:
                body = FAKE_PDF if reply == 200 else b""
                self.pdf_service.post(PDF_SERVICE, status=reply, body=body)

    def generate_scorecards(self):
        return generate_pdf_scorecards.delay(
            match_pks=[self.match.pk],
            templates=self.templates,
            extra_context={},
            season_pk=self.season.pk,
        )

    def test_timeout_then_success(self):
        self.reply(requests.Timeout("timed out"), 200)
        result = self.generate_scorecards()
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertEqual(len(self.pdf_service.calls), 2)

    def test_connection_error_then_success(self):
        self.reply(requests.ConnectionError("connection refused"), 200)
        result = self.generate_scorecards()
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertEqual(len(self.pdf_service.calls), 2)

    def test_server_error_then_success(self):
        self.reply(504, 200)
        result = self.generate_scorecards()
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertEqual(len(self.pdf_service.calls), 2)

    def test_server_error_gives_up_after_two_retries(self):
        self.reply(504)
        result = self.generate_scorecards()
        self.assertEqual(result.state, "FAILURE")
        self.assertIsInstance(result.result, requests.HTTPError)
        self.assertEqual(len(self.pdf_service.calls), 3)

    def test_client_error_not_retried(self):
        self.reply(400)
        result = self.generate_scorecards()
        self.assertEqual(result.state, "FAILURE")
        self.assertIsInstance(result.result, requests.HTTPError)
        self.assertEqual(len(self.pdf_service.calls), 1)

    # The grid task takes a Season instance, which the eager ``delay`` would
    # reject as not JSON serializable, so these call ``apply`` directly.

    def test_grid_server_error_then_success(self):
        self.reply(503, 200)
        result = generate_pdf_grid.apply(args=(self.season, {}))
        self.assertEqual(base64.b64decode(result.get()), FAKE_PDF)
        self.assertEqual(len(self.pdf_service.calls), 2)

    def test_grid_client_error_not_retried(self):
        self.reply(404)
        result = generate_pdf_grid.apply(args=(self.season, {}))
        self.assertEqual(result.state, "FAILURE")
        self.assertIsInstance(result.result, requests.HTTPError)
        self.assertEqual(len(self.pdf_service.calls), 1)


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
