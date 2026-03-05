"""Init file for CowayAIO"""

from .client import CowayClient
from .exceptions import (
    AuthError,
    CowayError,
    NoPlaces,
    NoPurifiers,
    PasswordExpired,
    RateLimited,
    ServerMaintenance,
)
from .constants import LightMode
from .devices.models import CowayPurifier, DeviceAttributes, PurifierData
from .__version__ import __version__

__all__ = [
    "AuthError",
    "CowayClient",
    "CowayError",
    "CowayPurifier",
    "DeviceAttributes",
    "LightMode",
    "NoPlaces",
    "NoPurifiers",
    "PasswordExpired",
    "PurifierData",
    "RateLimited",
    "ServerMaintenance",
    "__version__",
]
