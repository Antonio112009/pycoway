"""Exceptions for Coway IoCare."""


class CowayError(Exception):
    """Error from Coway api."""


class CowayConnectionError(CowayError):
    """Network-level failure while talking to the Coway API.

    Wraps aiohttp connection errors, timeouts and truncated payloads so
    callers only need to handle the ``CowayError`` hierarchy. The
    original aiohttp exception is available as ``__cause__``.
    """


class AuthError(CowayError):
    """Authentication issue from Coway api."""


class PasswordExpired(CowayError):
    """Coway API indicating password has expired."""


class ServerMaintenance(CowayError):
    """Coway API indicating servers are undergoing maintenance."""


class RateLimited(CowayError):
    """Coway API indicating account has been rate-limited."""


class NoPlaces(CowayError):
    """Coway API indicating account has no places defined."""


class NoPurifiers(CowayError):
    """Coway API indicating account has no purifiers."""
