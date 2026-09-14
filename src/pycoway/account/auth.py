"""Authentication layer for Coway IoCare API."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from pycoway.constants import (
    TIMEOUT,
    Endpoint,
    ErrorMessages,
    Header,
    Parameter,
    get_timezone,
)
from pycoway.exceptions import (
    AuthError,
    CowayError,
    NoPlaces,
    PasswordExpired,
    RateLimited,
    ServerMaintenance,
)
from pycoway.transport.http import CowayHttpClient

if TYPE_CHECKING:
    from http.cookies import SimpleCookie

    from aiohttp import ClientResponse, ClientSession

LOGGER = logging.getLogger(__name__)

DEFAULT_TOKEN_LIFETIME = 3600  # seconds, used when the API omits expiresIn
TOKEN_REFRESH_MARGIN = 300  # seconds before expiry at which the token is refreshed


def _token_lifetime(token_data: dict[str, Any]) -> int:
    """Extract the token lifetime in seconds, falling back to the default."""
    expires_in = token_data.get("expiresIn", token_data.get("expires_in"))
    try:
        lifetime = int(expires_in)
    except TypeError, ValueError:
        return DEFAULT_TOKEN_LIFETIME
    return lifetime if lifetime > 0 else DEFAULT_TOKEN_LIFETIME


class CowayAuthClient(CowayHttpClient):
    """Coway client with authentication and account setup."""

    def __init__(
        self,
        username: str,
        password: str,
        session: ClientSession | None = None,
        timeout: int = TIMEOUT,
        skip_password_change: bool = False,
    ) -> None:
        super().__init__(session=session, timeout=timeout)
        self.username: str = username
        self.password: str = password
        self.skip_password_change: bool = skip_password_change
        self.refresh_token: str | None = None
        self.token_expiration: datetime | None = None
        self.country_code: str | None = None
        self.places: list[dict[str, Any]] | None = None
        # Set to False to disable the automatic refresh / re-login that
        # normally runs before every authenticated request.
        self.check_token: bool = True
        # Serialises login and token refresh so concurrent callers (a poll
        # and a control command, say) share one refresh instead of each
        # performing their own and tripping Coway's rate limiter.
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # OAuth / login helpers
    # ------------------------------------------------------------------

    async def _get_oauth_page(self, url: str) -> tuple[ClientResponse, str]:
        """GET the OAuth login page and return response + HTML body."""

        headers = {
            "user-agent": Header.USER_AGENT,
            "accept": Header.ACCEPT,
            "accept-language": Header.ACCEPT_LANG,
        }
        params = {
            "auth_type": 0,
            "response_type": "code",
            "client_id": Parameter.CLIENT_ID,
            "redirect_uri": Endpoint.REDIRECT_URL,
            "ui_locales": "en",
        }
        session = self._ensure_session()
        # Clear only Coway/keycloak cookies so we don't wipe unrelated cookies
        # when the caller passed in a shared ClientSession.
        for domain in ("id.coway.com", "iocare.iotsvc.coway.com", "iocareapi.iot.coway.com"):
            session.cookie_jar.clear_domain(domain)
        LOGGER.debug(f"Sending request to endpoint {url}")
        async with self._request("get", url, headers=headers, params=params) as resp:
            html_page = await resp.text()
            return resp, html_page

    async def _post_auth(
        self,
        url: str,
        cookies: SimpleCookie,
        headers: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[str | ClientResponse, bool]:
        """POST credentials / password-skip to the authentication endpoint."""

        async with self._request("post", url, cookies=cookies, headers=headers, data=data) as resp:
            if resp.content_type != "text/html":
                return resp, False

            html_page = await resp.text()
            soup = BeautifulSoup(html_page, "html.parser")
            title_tag = soup.find("title")

            if title_tag is None or title_tag.string is None:
                return resp, False

            page_title = title_tag.string

            if page_title == "Coway - Password change message":
                if self.skip_password_change:
                    form = soup.find("form", id="kc-password-change-form")
                    if form is None or not form.get("action"):
                        raise CowayError(
                            "Coway servers returned the password change page but no "
                            "'kc-password-change-form' form was found to skip it."
                        )
                    return form.get("action"), True
                raise PasswordExpired(
                    "Coway servers are requesting a password change as the "
                    "password on this account hasn't been changed for 60 days or more."
                )

            error_message = soup.find("p", class_="member_error_msg")
            if error_message and error_message.text == "Your ID or password is incorrect.":
                raise AuthError("Coway API authentication error: Invalid username/password.")
            return resp, False

    async def _create_endpoint_header(self) -> dict[str, str]:
        """Build the common header for authorized endpoints."""

        await self._check_token()
        return self._build_auth_header(region="NUS")

    # ------------------------------------------------------------------
    # Login flow
    # ------------------------------------------------------------------

    async def login(self) -> None:
        """Full login flow: cookies -> auth code -> tokens -> country -> places."""

        async with self._token_lock:
            await self._do_login()

    async def _do_login(self) -> None:
        """Run the login flow. The caller must hold ``_token_lock``."""

        login_url, cookies = await self._get_login_cookies()
        auth_code = await self._get_auth_code(login_url, cookies)
        self.access_token, self.refresh_token, lifetime = await self._get_token(auth_code)
        self.token_expiration = datetime.now() + timedelta(seconds=lifetime)
        LOGGER.debug(f"Token expiration set to {self.token_expiration}.")
        self.country_code = await self._get_country_code()
        self.places = await self._get_places()

    async def _get_login_cookies(self) -> tuple[str, Any]:
        """Get the openid-connect login URL and associated cookies."""

        LOGGER.debug(f"Getting Coway login cookies for {self.username}")
        response, html_page = await self._get_oauth_page(Endpoint.OAUTH_URL)
        LOGGER.debug(f"Login cookies response: {response}")

        status = response.status
        if status != 200:
            error = response.reason
            if status == 503:
                raise ServerMaintenance(
                    f"Coway Servers are undergoing maintenance. Response: {error}"
                )
            raise CowayError(
                f"Coway API error while fetching login page. Status: {status}, Reason: {error}"
            )

        cookies = response.cookies
        soup = BeautifulSoup(html_page, "html.parser")
        try:
            login_url = soup.find("form", id="kc-form-login").get("action")
            LOGGER.debug(f"Login URL obtained: {login_url}")
        except AttributeError:
            raise CowayError(
                "Coway API error: Coway servers did not return a valid Login URL."
            ) from None
        return login_url, cookies

    async def _get_auth_code(self, login_url: str, cookies: Any) -> str:
        """Exchange credentials for an OAuth auth code."""

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": Header.USER_AGENT,
        }
        data = {
            "clientName": Parameter.CLIENT_NAME,
            "termAgreementStatus": "",
            "idp": "",
            "username": self.username,
            "password": self.password,
            "rememberMe": "on",
        }
        password_skip_data = {
            "cmd": "change_next_time",
            "checkPasswordNeededYn": "Y",
            "current_password": "",
            "new_password": "",
            "new_password_confirm": "",
        }

        LOGGER.debug(f"Obtaining auth code for {self.username}")
        response, password_skip_init = await self._post_auth(login_url, cookies, headers, data)
        LOGGER.debug(f"Auth code response: {response}")

        if password_skip_init:
            response, password_skip_init = await self._post_auth(
                response, cookies, headers, password_skip_data
            )
            LOGGER.debug(f"Auth code skip password response: {response}")

        code = response.url.query.get("code")
        if not code:
            raise AuthError(
                "Coway authentication did not return an auth code. "
                "This usually means the credentials were rejected silently "
                "or the OAuth flow changed."
            )
        return code

    async def _get_token(self, auth_code: str) -> tuple[str, str, int]:
        """Exchange auth code for access + refresh tokens and their lifetime."""

        data = {
            "authCode": auth_code,
            "redirectUrl": Endpoint.REDIRECT_URL,
        }
        LOGGER.debug(f"Obtaining access/refresh token for {self.username}")
        response = await self._post_endpoint(data)

        if "error" in response:
            LOGGER.debug(
                f"Error obtaining access/refresh token for {self.username}. Response: {response}"
            )
            if response["error"].get("message") == ErrorMessages.INVALID_GRANT:
                raise RateLimited(
                    "Failed fetching Coway access token. The account has likely "
                    "been rate-limited (blocked). Please wait 24 hours before trying again. "
                    "If, after 24 hours, you're unable to log in even with the mobile "
                    "IoCare+ app, please contact Coway support."
                )
            raise CowayError(
                f"Failed fetching Coway access token: {response['error'].get('message')}"
            )

        token_data = response.get("data", {})
        access_token = token_data.get("accessToken")
        refresh_token = token_data.get("refreshToken")
        if access_token and refresh_token:
            return access_token, refresh_token, _token_lifetime(token_data)

        raise CowayError(
            f"Failed fetching Coway access/refresh token for {self.username}. Response: {response}"
        )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _check_token(self) -> None:
        """Refresh or re-login if the token is missing or about to expire.

        Serialised through ``_token_lock``: concurrent callers wait for the
        refresh (or login) already in flight and then reuse its result
        instead of each starting their own.
        """

        if not self.check_token:
            LOGGER.debug(f"Token check is set to False. Skipping for {self.username}")
            return

        async with self._token_lock:
            LOGGER.debug(f"Checking token for {self.username}")

            if (
                self.access_token is None
                or self.refresh_token is None
                or self.token_expiration is None
            ):
                LOGGER.debug(
                    f"One of access_token, refresh_token, or token_expiration is None. "
                    f"Logging in for {self.username}"
                )
                await self._do_login()
                return

            remaining = (self.token_expiration - datetime.now()).total_seconds()
            if remaining < TOKEN_REFRESH_MARGIN:
                LOGGER.debug(
                    f"Access token expires at {self.token_expiration}. "
                    f"Refreshing token for {self.username}"
                )
                await self._refresh_token()

    async def _refresh_token(self) -> None:
        """Obtain a new access token using the refresh token.

        Falls back to a full credential login when Coway rejects the
        refresh token. The caller must hold ``_token_lock``.
        """

        headers = {
            "content-type": "application/json",
            "accept": "*/*",
            "accept-language": Header.COWAY_LANGUAGE,
            "user-agent": Header.USER_AGENT,
        }
        data = {"refreshToken": self.refresh_token}
        url = f"{Endpoint.BASE_URI}{Endpoint.TOKEN_REFRESH}"

        LOGGER.debug(f"Refreshing tokens for {self.username} at {url}")
        try:
            async with self._request("post", url, headers=headers, data=json.dumps(data)) as resp:
                response = await self._response(resp)
        except AuthError as exc:
            LOGGER.warning(
                f"Token refresh rejected for {self.username}, falling back to full login: {exc}"
            )
            await self._do_login()
            return

        if "error" in response:
            LOGGER.warning(
                f"Token refresh failed for {self.username}, falling back to full login. "
                f"Response: {response}"
            )
            await self._do_login()
            return

        token_data = response.get("data") or {}
        self.access_token = token_data.get("accessToken")
        self.refresh_token = token_data.get("refreshToken")
        if self.access_token is None or self.refresh_token is None:
            raise CowayError(f"Failed to refresh tokens for {self.username}. Response: {response}")

        self.token_expiration = datetime.now() + timedelta(seconds=_token_lifetime(token_data))
        LOGGER.debug(
            f"Tokens refreshed for {self.username}. New expiration: {self.token_expiration}"
        )

    # ------------------------------------------------------------------
    # Account data
    # ------------------------------------------------------------------

    async def _get_country_code(self) -> str:
        """Fetch the country code associated with the account."""

        endpoint = f"{Endpoint.BASE_URI}{Endpoint.USER_INFO}"
        # Part of the login flow, which runs with the token lock held and
        # a freshly issued token: build the header without a token check.
        headers = self._build_auth_header(region="NUS")
        LOGGER.debug(f"Getting country code for {self.username}")
        response = await self._get_endpoint(endpoint=endpoint, headers=headers, params=None)

        if "data" in response:
            if LOGGER.isEnabledFor(logging.DEBUG):
                LOGGER.debug(
                    "Country code response for %s: %s",
                    self.username,
                    json.dumps(response["data"], indent=4),
                )
            if "maintainInfos" in response["data"]:
                raise ServerMaintenance("Coway Servers are undergoing maintenance.")
            member_info = response["data"].get("memberInfo", {})
            country_code = member_info.get("countryCode")
            if country_code is not None:
                return country_code
            raise CowayError(
                f"Failed to get country code for {self.username}. Response: {response}"
            )

        if "error" in response:
            raise CowayError(
                f"Failed to get country code associated with account. {response['error']}"
            )

        raise CowayError(
            f"Unexpected response getting country code for {self.username}. Response: {response}"
        )

    async def _get_places(self) -> list[dict[str, Any]]:
        """Fetch all places (homes) associated with the account."""

        endpoint = f"{Endpoint.BASE_URI}{Endpoint.PLACES}"
        params = {
            "countryCode": self.country_code,
            "langCd": Header.ACCEPT_LANG,
            "pageIndex": "1",
            "pageSize": "20",
            "timezoneId": get_timezone(),
        }
        # Same as _get_country_code: called from the login flow, no token check.
        headers = self._build_auth_header(region="NUS")
        LOGGER.debug(f"Getting places for {self.username}")
        response = await self._get_endpoint(endpoint=endpoint, headers=headers, params=params)

        if "error" in response:
            raise CowayError(f"Failed to get places associated with account. {response['error']}")

        places = response.get("data", {}).get("content")
        if places is not None:
            return places

        raise NoPlaces(f"No places found associated with {self.username}. Response: {response}")
