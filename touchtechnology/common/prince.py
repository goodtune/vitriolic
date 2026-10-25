import logging
import subprocess

import requests
from django.conf import settings
from django.utils.html import strip_spaces_between_tags

logger = logging.getLogger(__name__)


class PrinceError(Exception):
    """
    The PDF server did not make the PDF: it could not be reached, it did not
    answer within ``PRINCE_TIMEOUT``, or it answered with an error status.
    The ``requests`` exception is the ``__cause__``.
    """


def prince(html, base_url=None, ttl=300, **kwargs):
    SERVER = getattr(settings, "PRINCE_SERVER", None)
    BINARY = getattr(settings, "PRINCE_BINARY", "/usr/local/bin/prince")
    # Seconds to wait for the PDF server: (connect, read). Without a timeout
    # requests waits for ever, and so does the worker that called us.
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

        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        out, err = p.communicate(html.encode("utf8"))
        logger.info("Local PDF generation complete.")

        if err:
            logger.error(err)

    return out
