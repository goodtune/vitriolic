"""
Competition-specific exceptions for Tournament Control.
"""


class LiveStreamError(Exception):
    """Base exception for live streaming operations."""
    pass


class LiveStreamIdentifierMissing(LiveStreamError):
    """Raised when trying to transition a match without a live stream identifier."""
    pass


class LiveStreamTransitionWarning(Warning):
    """Raised when attempting an invalid live stream transition."""
    pass


class InvalidLiveStreamTransition(LiveStreamError):
    """Raised when attempting an invalid live stream transition as an error."""
    pass