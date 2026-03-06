"""Init file for pycoway."""

from .__version__ import __version__
from .client import CowayClient
from .constants import CommandCode, LightMode
from .devices.models import CowayPurifier, DeviceAttributes, FilterInfo, PurifierData
from .exceptions import (
    AuthError,
    CowayError,
    NoPlaces,
    NoPurifiers,
    PasswordExpired,
    RateLimited,
    ServerMaintenance,
)

__all__ = [
    "AuthError",
    "CommandCode",
    "CowayClient",
    "CowayError",
    "CowayPurifier",
    "DeviceAttributes",
    "FilterInfo",
    "LightMode",
    "NoPlaces",
    "NoPurifiers",
    "PasswordExpired",
    "PurifierData",
    "RateLimited",
    "ServerMaintenance",
    "__version__",
]
