"""[User Facing] Core definitions for the competition app.

This module exposes app metadata and is tightly coupled to the
tournamentcontrol project.
"""

import logging

logger = logging.getLogger(__name__)

NAME = "Competitions"
INSTALL = (
    "CompetitionSite",
    "MultiCompetitionSite",
    "RegistrationSite",
    "TournamentCalculatorSite",
    "RankingSite",
)

__version__ = "2.4.14"

logger.debug('"%s"/"%s"' % (NAME, __version__))

default_app_config = "tournamentcontrol.competition.apps.CompetitionConfig"
