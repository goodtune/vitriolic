import logging
import subprocess

import requests
from django.conf import settings
from django.utils.html import strip_spaces_between_tags

SERVER = getattr(settings, 'PRINCE_SERVER', None)
BINARY = getattr(settings, 'PRINCE_BINARY', '/usr/local/bin/prince')
BASE_URL = getattr(settings, 'PRINCE_BASE_URL', None)

logger = logging.getLogger(__name__)


def prince(html, base_url=BASE_URL, ttl=300, **kwargs):
    # When celery and django-tenant-schemas are involved, this get's a bit
    # weird. This has bitten once in production so lets log it and see else
    # might cause grief.
    for kw, arg in kwargs.items():
        logger.warn('Unexpected keyword argument: %s=%r', kw, arg)

    logger.debug('base_url: %s', base_url)
    logger.debug('ttl: %s', ttl)

    logger.debug('content-length: %s', len(html))
    html = strip_spaces_between_tags(html)
    logger.debug('content-length-stripped: %s', len(html))

    if SERVER:
        logger.debug('server: %s', SERVER)
        if isinstance(html, unicode):
            html = html.encode('utf8')

        headers = {}
        if base_url:
            headers['base_url'] = base_url
        for key, value in headers.items():
            logger.debug('header: %s=%s', key, value)

        res = requests.post(
            "http://%s/" % settings.PRINCE_SERVER,
            data=html,
            headers=headers)
        res.raise_for_status()

        out = res.content
        logger.info('Remote PDF generation via %s complete.', SERVER)

    else:
        command = [BINARY, '--input=html']
        if base_url:
            command += ['--baseurl=%s' % base_url]
        command += ['-']
        logger.debug('command: %s', ' '.join(command))

        p = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        out, err = p.communicate(html.encode('utf8'))
        logger.info('Local PDF generation complete.')

        if err:
            logger.error(err)

    return out
