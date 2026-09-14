"""Init file for pycoway."""

from .__version__ import __version__
from .client import CowayClient
from .constants import CommandCode, LightMode, SensorCode, SensorKey
from .devices.models import CowayPurifier, DeviceAttributes, FilterInfo, PurifierData
from .exceptions import (
    AuthError,
    CowayConnectionError,
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
    "CowayConnectionError",
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
    "SensorCode",
    "SensorKey",
    "ServerMaintenance",
    "__version__",
]
