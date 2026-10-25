import requests
import responses
from django.test import SimpleTestCase, override_settings

from touchtechnology.common.prince import PrinceError, prince

FAKE_PDF = b"%PDF-1.4 fake"
PDF_SERVICE = "https://pdf.example.com/"


@override_settings(PRINCE_SERVER="pdf.example.com")
class PrinceServerTests(SimpleTestCase):
    """
    ``prince`` posts the HTML to the PDF server named by ``PRINCE_SERVER``.
    It must not wait for ever on a server that never answers (#427), and a
    failure must reach the caller as a ``PrinceError``.
    """

    def setUp(self):
        super().setUp()
        self.pdf_service = responses.RequestsMock()
        self.pdf_service.start()
        self.addCleanup(self.pdf_service.reset)
        self.addCleanup(self.pdf_service.stop)

    def assertPrinceError(self, cause, message):
        with self.assertRaises(PrinceError) as raised:
            prince("<html></html>")
        self.assertEqual(str(raised.exception), message)
        self.assertIs(raised.exception.__cause__, cause)

    def test_pdf(self):
        self.pdf_service.post(PDF_SERVICE, body=FAKE_PDF)
        self.assertEqual(prince("<html></html>"), FAKE_PDF)
        self.assertEqual(
            self.pdf_service.calls[0].request.req_kwargs["timeout"], (5, 60)
        )

    @override_settings(PRINCE_TIMEOUT=(1, 2))
    def test_timeout_setting(self):
        self.pdf_service.post(PDF_SERVICE, body=FAKE_PDF)
        self.assertEqual(prince("<html></html>"), FAKE_PDF)
        self.assertEqual(
            self.pdf_service.calls[0].request.req_kwargs["timeout"], (1, 2)
        )

    def test_read_timeout(self):
        timeout = requests.ReadTimeout("read timed out")
        self.pdf_service.post(PDF_SERVICE, body=timeout)
        self.assertPrinceError(
            timeout, "Remote PDF generation via pdf.example.com failed: read timed out"
        )

    def test_connect_timeout(self):
        timeout = requests.ConnectTimeout("connect timed out")
        self.pdf_service.post(PDF_SERVICE, body=timeout)
        self.assertPrinceError(
            timeout,
            "Remote PDF generation via pdf.example.com failed: connect timed out",
        )

    def test_connection_error(self):
        refused = requests.ConnectionError("connection refused")
        self.pdf_service.post(PDF_SERVICE, body=refused)
        self.assertPrinceError(
            refused,
            "Remote PDF generation via pdf.example.com failed: connection refused",
        )

    def test_server_error(self):
        self.pdf_service.post(PDF_SERVICE, status=502)
        with self.assertRaises(PrinceError) as raised:
            prince("<html></html>")
        self.assertEqual(
            str(raised.exception),
            "Remote PDF generation via pdf.example.com failed: "
            "502 Server Error: Bad Gateway for url: https://pdf.example.com/",
        )
        self.assertEqual(raised.exception.__cause__.response.status_code, 502)
