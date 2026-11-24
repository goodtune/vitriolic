import os
import subprocess
import tempfile
import time
from pathlib import Path

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

    def test_html(self):
        """
        The HTML is posted as UTF-8, with the spaces between tags stripped.
        """
        self.pdf_service.post(PDF_SERVICE, body=FAKE_PDF)
        self.assertEqual(prince("<html>\n  <p>Chéese</p>\n</html>"), FAKE_PDF)
        self.assertEqual(
            self.pdf_service.calls[0].request.body,
            "<html><p>Chéese</p></html>".encode(),
        )

    def test_html_bytes(self):
        """
        A rendered response's content is bytes. The server gets the HTML they
        hold, not their repr (#438).
        """
        self.pdf_service.post(PDF_SERVICE, body=FAKE_PDF)
        self.assertEqual(prince("<html>\n  <p>Chéese</p>\n</html>".encode()), FAKE_PDF)
        self.assertEqual(
            self.pdf_service.calls[0].request.body,
            "<html><p>Chéese</p></html>".encode(),
        )

    @override_settings(DEFAULT_CHARSET="iso-8859-1")
    def test_html_bytes_default_charset(self):
        """
        Bytes are decoded with ``DEFAULT_CHARSET``, the charset Django encodes
        a response with, and posted as UTF-8.
        """
        self.pdf_service.post(PDF_SERVICE, body=FAKE_PDF)
        self.assertEqual(prince("<p>Chéese</p>".encode("iso-8859-1")), FAKE_PDF)
        self.assertEqual(
            self.pdf_service.calls[0].request.body, "<p>Chéese</p>".encode()
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


@override_settings(PRINCE_TIMEOUT=(5, 1))
class PrinceBinaryTests(SimpleTestCase):
    """
    Without ``PRINCE_SERVER``, ``prince`` pipes the HTML through the binary
    named by ``PRINCE_BINARY``. It must not wait for ever on a binary that
    never finishes (#440), and a failure must reach the caller as a
    ``PrinceError``, the same as a failure of the PDF server. So must a
    binary that is missing or cannot be run.

    Each test makes ``PRINCE_BINARY`` a shell script, or leaves the path empty.
    """

    #: Longer than any timeout these tests set.
    HANG = 10

    def setUp(self):
        super().setUp()
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.binary = Path(directory, "prince")
        self.pid = Path(directory, "pid")
        self.command = [str(self.binary), "--input=html", "-"]
        self.enterContext(self.settings(PRINCE_BINARY=str(self.binary)))

    def install(self, script):
        self.binary.write_text(f"#!/bin/sh\n{script}\n")
        self.binary.chmod(0o755)

    def install_hang(self):
        """
        A binary that never finishes in time. It writes its process ID first;
        ``exec`` keeps that ID for ``sleep``, so the process to kill is the
        one that was started.
        """
        self.install(f'echo $$ > "{self.pid}"\nexec sleep {self.HANG}')

    def assertKilled(self):
        """The hung binary was killed and reaped: its process is gone."""
        with self.assertRaises(ProcessLookupError):
            os.kill(int(self.pid.read_text()), 0)

    def assertCannotRun(self, cause, errno, reason):
        """
        The binary could not be run at all. Only a change to the site's setup
        will fix that, so the error names the path and is logged.
        """
        with (
            self.assertLogs("touchtechnology.common.prince", "ERROR") as logs,
            self.assertRaises(PrinceError) as raised,
        ):
            prince("<html></html>")
        self.assertEqual(
            str(raised.exception),
            f"Local PDF generation failed: [Errno {errno}] {reason}: '{self.binary}'",
        )
        self.assertIsInstance(raised.exception.__cause__, cause)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [f"PDF binary {self.binary} cannot be run: {reason}"],
        )

    def test_pdf(self):
        self.install("exec cat")
        self.assertEqual(
            prince("<html>\n  <p>Chéese</p>\n</html>"),
            "<html><p>Chéese</p></html>".encode(),
        )

    def test_timeout(self):
        """
        The binary has nothing to connect to, so it gets the read timeout,
        the second of the ``(connect, read)`` pair.
        """
        self.install_hang()
        started = time.monotonic()
        with self.assertRaises(PrinceError) as raised:
            prince("<html></html>")
        self.assertLess(time.monotonic() - started, self.HANG)
        self.assertEqual(
            str(raised.exception),
            f"Local PDF generation failed: Command '{self.command}' "
            "timed out after 1 seconds",
        )
        self.assertIsInstance(raised.exception.__cause__, subprocess.TimeoutExpired)
        self.assertKilled()

    @override_settings(PRINCE_TIMEOUT=2)
    def test_timeout_single_number(self):
        """A single number is the whole timeout, as it is for ``requests``."""
        self.install_hang()
        with self.assertRaises(PrinceError) as raised:
            prince("<html></html>")
        self.assertEqual(
            str(raised.exception),
            f"Local PDF generation failed: Command '{self.command}' "
            "timed out after 2 seconds",
        )
        self.assertKilled()

    def test_exit_status(self):
        self.install("exit 3")
        with self.assertRaises(PrinceError) as raised:
            prince("<html></html>")
        self.assertEqual(
            str(raised.exception),
            f"Local PDF generation failed: Command '{self.command}' "
            "returned non-zero exit status 3.",
        )
        self.assertEqual(raised.exception.__cause__.returncode, 3)

    def test_missing(self):
        """Nothing was installed at ``PRINCE_BINARY``."""
        self.assertCannotRun(FileNotFoundError, 2, "No such file or directory")

    def test_not_executable(self):
        self.install("exec cat")
        self.binary.chmod(0o644)
        self.assertCannotRun(PermissionError, 13, "Permission denied")
