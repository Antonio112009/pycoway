"""Constants for pycoway."""

import logging
import os
from enum import StrEnum

from .__version__ import __version__ as version

DEFAULT_TIMEZONE = "America/Kentucky/Louisville"

_LOGGER = logging.getLogger(__name__)


def _detect_timezone() -> str:
    """Detect the system IANA timezone, falling back to the default."""

    # 1. TZ env var (Docker, Home Assistant, explicit config)
    tz = os.environ.get("TZ", "").strip()
    if tz and "/" in tz:
        return tz

    # 2. /etc/timezone (Debian/Ubuntu, many HA containers)
    try:
        with open("/etc/timezone") as f:
            tz = f.read().strip()
            if tz and "/" in tz:
                return tz
    except OSError:
        pass

    # 3. /etc/localtime symlink (macOS, most Linux)
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/")[-1]
    except OSError:
        pass

    _LOGGER.warning(
        "Could not detect system timezone; falling back to '%s'. "
        "Set the TZ environment variable to override.",
        DEFAULT_TIMEZONE,
    )
    return DEFAULT_TIMEZONE


class Endpoint(StrEnum):
    BASE_URI = "https://iocare.iotsvc.coway.com/api/v1"
    GET_TOKEN = "/com/token"
    NOTICES = "/com/notices"
    OAUTH_URL = "https://id.coway.com/auth/realms/cw-account/protocol/openid-connect/auth"
    REDIRECT_URL = "https://iocare-redirect.iotsvc.coway.com/redirect_bridge_empty.html"
    TOKEN_REFRESH = "/com/refresh-token"
    USER_INFO = "/com/my-info"
    PLACES = "/com/places"
    PURIFIER_HTML_BASE = "https://iocare2.coway.com/en"
    SECONDARY_BASE = "https://iocare2.coway.com/api/proxy/api/v1"

    # IoCare IoT JSON API (no HTML scraping needed)
    IOT_BASE_URI = "https://iocareapi.iot.coway.com/api/v1"
    IOT_USER_DEVICES = "/com/user-devices"
    IOT_DEVICE_CONTROL = "/com/devices"  # /{id}/control
    IOT_DEVICE_CONN = "/com/devices-conn"
    IOT_AIR_HOME = "/air/devices"  # /{id}/home or /{id}/filter-info


class TrCode(StrEnum):
    """IoT API transaction codes sent in the trcode request header."""

    USER_DEVICES = "CWIG0304"
    DEVICE_CONTROL = "CWIG0602"
    DEVICE_CONN = "CWIG0607"
    AIR_HOME = "CWIA0120"
    CONTROL_DEVICE = "CWIG0603"


class Parameter(StrEnum):
    APP_VERSION = "2.15.0"
    CLIENT_ID = "cwid-prd-iocare-plus-25MJGcYX"
    CLIENT_NAME = "IOCARE"
    TIMEZONE = _detect_timezone()


class Header(StrEnum):
    ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ACCEPT_LANG = "en"
    CALLING_PAGE = "product"
    CONTENT_JSON = "application/json"
    COWAY_LANGUAGE = "en-US,en;q=0.9"
    SOURCE_PATH = "iOS"
    THEME = "light"
    USER_AGENT = f"pycoway/{version}"


class ErrorMessages(StrEnum):
    BAD_TOKEN = "Unauthenticated (crypto/rsa: verification error)"
    EXPIRED_TOKEN = "Unauthenticated (Token is expired)"
    INVALID_REFRESH_TOKEN = (
        "통합회원 토큰 갱신 오류 (error: invalid_grant)(error_desc: Invalid refresh token)"
    )
    INVALID_GRANT = "통합회원 토큰 발급 오류 (error: invalid_grant)(error_desc: Code not valid)"


class LightMode(StrEnum):
    AQI_OFF = "1"
    OFF = "2"
    HALF_OFF = "3"  # For IconS only
    ON = "0"


CATEGORY_NAME = "청정기"  # Translates to purifier
PREFILTER_CYCLE = {2: "112", 3: "168", 4: "224"}
TIMEOUT = 5 * 60


class CommandCode(StrEnum):
    POWER = "0001"
    MODE = "0002"
    FAN_SPEED = "0003"
    LIGHT = "0007"
    TIMER = "0008"
    SMART_SENSITIVITY = "000A"
    BUTTON_LOCK = "0024"
    PREFILTER = "0001"


class SensorCode(StrEnum):
    """Sensor-data attribute codes from the purifier."""

    PM25 = "0001"
    PM10 = "0002"
    LUX = "0007"
    PRE_FILTER_USAGE = "0011"
    MAX2_FILTER_USAGE = "0012"
    ODOR_FILTER_USAGE = "0013"


class SensorKey(StrEnum):
    """Named sensor keys used by the HTML-parsed sensor data."""

    PM25 = "PM25_IDX"
    PM10 = "PM10_IDX"
    CO2 = "CO2_IDX"
    VOCS = "VOCs_IDX"
    IAQ = "IAQ"


# Map IoT JSON API "IAQ" field names → internal sensor keys for build_purifier.
IAQ_FIELD_MAP: dict[str, str] = {
    "dustpm25": SensorKey.PM25,
    "dustpm10": SensorKey.PM10,
    "co2": SensorKey.CO2,
    "vocs": SensorKey.VOCS,
    "inairquality": SensorKey.IAQ,
}
