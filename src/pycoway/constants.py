"""Constants for pycoway."""

import os
import subprocess

from .__version__ import __version__ as version
from .enums import StrEnum

DEFAULT_TIMEZONE = "America/Kentucky/Louisville"


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

    # 4. timedatectl (systemd-based Linux)
    try:
        out = subprocess.check_output(
            ["timedatectl", "show", "-p", "Timezone", "--value"],
            text=True,
            timeout=2,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out and "/" in out:
            return out
    except (OSError, subprocess.SubprocessError):
        pass

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
    AIR = "/air/devices"
    PURIFIER_HTML_BASE = "https://iocare2.coway.com/en"
    SECONDARY_BASE = "https://iocare2.coway.com/api/proxy/api/v1"


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
    COWAY_USER_AGENT = f"pycoway/{version}"
    HTML_USER_AGENT = f"pycoway/{version}"
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
