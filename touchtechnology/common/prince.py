import logging
import subprocess

import requests
from django.conf import settings
from django.utils.html import strip_spaces_between_tags

logger = logging.getLogger(__name__)


class PrinceError(Exception):
    """
    The PDF was not made.

    With ``PRINCE_SERVER``, the server could not be reached, it did not
    answer within ``PRINCE_TIMEOUT``, or it answered with an error status.
    The ``requests`` exception is the ``__cause__``.

    Without it, ``PRINCE_BINARY`` did not finish within the read timeout, or
    it exited with an error status. The ``subprocess`` exception is the
    ``__cause__``. If the binary could not be run at all, the error is a
    ``PrinceUnavailable``.
    """


class PrinceUnavailable(PrinceError):
    """
    ``PRINCE_BINARY`` could not be run: it is missing, or it is not
    executable. The ``OSError`` is the ``__cause__``. Trying again will not
    help; the site's setup must change.
    """


def prince(html, base_url=None, ttl=300, **kwargs):
    SERVER = getattr(settings, "PRINCE_SERVER", None)
    BINARY = getattr(settings, "PRINCE_BINARY", "/usr/local/bin/prince")
    # Seconds to wait for the PDF server: (connect, read). Without a timeout
    # requests waits for ever, and so does the worker that called us. The
    # binary has nothing to connect to, so it gets the read timeout.
    TIMEOUT = getattr(settings, "PRINCE_TIMEOUT", (5, 60))

    if base_url is None:
        base_url = getattr(settings, "PRINCE_BASE_URL", None)

    # When celery and django-tenant-schemas are involved, this get's a bit
    # weird. This has bitten once in production so lets log it and see else
    # might cause grief.
    for kw, arg in kwargs.items():
        logger.warning("Unexpected keyword argument: %s=%r", kw, arg)

    logger.debug("base_url: %s", base_url)
    logger.debug("ttl: %s", ttl)

    logger.debug("content-length: %s", len(html))
    html = strip_spaces_between_tags(html)
    logger.debug("content-length-stripped: %s", len(html))

    if SERVER:
        logger.debug("server: %s", SERVER)
        html = html.encode("utf8")

        headers = {}
        if base_url:
            headers["base_url"] = base_url
        for key, value in headers.items():
            logger.debug("header: %s=%s", key, value)

        try:
            res = requests.post(
                f"https://{SERVER}/", data=html, headers=headers, timeout=TIMEOUT
            )
            res.raise_for_status()
        except requests.RequestException as exc:
            raise PrinceError(
                f"Remote PDF generation via {SERVER} failed: {exc}"
            ) from exc

        out = res.content
        logger.info("Remote PDF generation via %s complete.", SERVER)

    else:
        command = [BINARY, "--input=html"]
        if base_url:
            command += [f"--baseurl={base_url}"]
        command += ["-"]
        logger.debug("command: %s", " ".join(command))

        # A single number is the whole timeout, as it is for requests.
        timeout = TIMEOUT[1] if isinstance(TIMEOUT, tuple) else TIMEOUT
        try:
            # On a timeout, run() kills the binary and waits for it to exit.
            out = subprocess.run(
                command,
                input=html.encode("utf8"),
                stdout=subprocess.PIPE,
                timeout=timeout,
                check=True,
            ).stdout
        except OSError as exc:
            logger.error("PDF binary %s cannot be run: %s", BINARY, exc.strerror)
            raise PrinceUnavailable(f"Local PDF generation failed: {exc}") from exc
        except subprocess.SubprocessError as exc:
            raise PrinceError(f"Local PDF generation failed: {exc}") from exc
        logger.info("Local PDF generation complete.")

    return out
