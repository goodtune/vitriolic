"""[Developer API] Shared utilities for touchtechnology apps.

This package contains common models and helpers intended for reuse.
"""

import logging

logger = logging.getLogger(__name__)

NAME = "Common Components"
INSTALL = ("AccountsSite",)

__version__ = "3.5.5"

logger.debug('"%s"/"%s"' % (NAME, __version__))

default_app_config = "touchtechnology.common.apps.CommonConfig"
