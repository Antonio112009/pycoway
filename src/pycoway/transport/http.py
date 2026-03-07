"""HTTP base client for Coway IoCare API."""

import json
import logging
from typing import Any

from aiohttp import ClientResponse, ClientSession, ClientTimeout, ContentTypeError

from pycoway.constants import (
    TIMEOUT,
    Endpoint,
    ErrorMessages,
    Header,
    Parameter,
)
from pycoway.exceptions import (
    AuthError,
    CowayError,
    ServerMaintenance,
)

LOGGER = logging.getLogger(__name__)


class CowayHttpClient:
    """Low-level HTTP transport for Coway API."""

    def __init__(self, session: ClientSession | None = None, timeout: int = TIMEOUT) -> None:
        self._session: ClientSession = session if session else ClientSession()
        self._owns_session: bool = session is None
        self.timeout: ClientTimeout = ClientTimeout(total=timeout)
        self.access_token: str | None = None

    async def close(self) -> None:
        """Close the underlying HTTP session if we created it."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "CowayHttpClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _post_endpoint(self, data: dict[str, str]) -> dict[str, Any]:
        """POST to the token endpoint."""

        url = f"{Endpoint.BASE_URI}{Endpoint.GET_TOKEN}"
        headers = {
            "content-type": Header.CONTENT_JSON,
            "user-agent": Header.USER_AGENT,
            "accept-language": Header.COWAY_LANGUAGE,
        }
        async with self._session.post(
            url, headers=headers, data=json.dumps(data), timeout=self.timeout
        ) as resp:
            return await self._response(resp)

    async def _get_endpoint(
        self,
        endpoint: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """GET an authorized API endpoint."""

        async with self._session.get(
            endpoint, headers=headers, params=params, timeout=self.timeout
        ) as resp:
            return await self._response(resp)

    def _build_auth_header(self, **extra: str) -> dict[str, str]:
        """Build an authenticated header with optional extras."""

        headers = {
            "Content-Type": Header.CONTENT_JSON,
            "Accept": "*/*",
            "accept-language": Header.COWAY_LANGUAGE,
            "User-Agent": Header.USER_AGENT,
            "authorization": f"Bearer {self.access_token}",
        }
        headers.update(extra)
        return headers

    def _construct_control_header(self) -> dict[str, str]:
        """Build header for purifier control commands."""
        return self._build_auth_header(region="NUS")

    def _construct_iot_header(self, trcode: str = "") -> dict[str, str]:
        """Build header for the IoT JSON API calls."""
        headers = self._build_auth_header(profile="prod")
        if trcode:
            headers["trcode"] = trcode
        return headers

    async def _get_iot_endpoint(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        trcode: str = "",
    ) -> dict[str, Any]:
        """GET an IoT JSON API endpoint."""

        headers = self._construct_iot_header(trcode)
        async with self._session.get(
            endpoint, headers=headers, params=params, timeout=self.timeout
        ) as resp:
            return await self._response(resp)

    async def _get_purifier_html(
        self, nick_name: str, serial: str, model_code: str, place_id: str
    ) -> str:
        """Fetch the HTML page shown in the iOS app for an individual purifier."""

        url = f"{Endpoint.PURIFIER_HTML_BASE}/{place_id}/product/{model_code}"
        headers = {
            "theme": Header.THEME,
            "callingpage": Header.CALLING_PAGE,
            "accept": Header.ACCEPT,
            "dvcnick": nick_name,
            "timezoneid": Parameter.TIMEZONE,
            "appversion": Parameter.APP_VERSION,
            "accesstoken": self.access_token,
            "accept-language": Header.COWAY_LANGUAGE,
            "region": "NUS",
            "user-agent": Header.USER_AGENT,
            "srcpath": Header.SOURCE_PATH,
            "deviceserial": serial,
        }
        params = {
            "bottomSlide": "false",
            "tab": "0",
            "temperatureUnit": "F",
            "weightUnit": "oz",
            "gravityUnit": "lb",
        }
        LOGGER.debug(f"Fetching purifier HTML page at {url}")
        async with self._session.get(
            url, headers=headers, params=params, timeout=self.timeout
        ) as resp:
            return await resp.text()

    @staticmethod
    async def _response(resp: ClientResponse) -> dict[str, Any]:
        """Parse a JSON API response, handling errors and maintenance."""

        if resp.status != 200:
            error = await resp.text()
            try:
                error_json = await resp.json()
            except (ValueError, ContentTypeError) as exc:
                raise CowayError(f"Could not return json: {error}") from exc

            if "error" in error_json:
                return {"error": error_json}

            message = error_json.get("message")
            if message == ErrorMessages.BAD_TOKEN:
                raise AuthError(
                    f"Coway Auth error: Coway IoCare authentication failed; "
                    f"{ErrorMessages.BAD_TOKEN}"
                )
            if message == ErrorMessages.EXPIRED_TOKEN:
                LOGGER.debug(
                    f"Current access token has expired. Error: {ErrorMessages.EXPIRED_TOKEN}"
                )
                return {"error": ErrorMessages.EXPIRED_TOKEN}
            return {"error": error_json}

        try:
            response = await resp.json()
        except (ValueError, ContentTypeError) as exc:
            raise CowayError(f"Could not return json {exc}") from exc

        if "data" in response and "maintainInfos" in response["data"]:
            raise ServerMaintenance("Coway Servers are undergoing maintenance.")

        # Sometimes an unauthorized message comes back with a 200 status.
        if "error" in response:
            if response["error"]["message"] == ErrorMessages.INVALID_REFRESH_TOKEN:
                raise AuthError(
                    f"Coway Auth error: Coway IoCare authentication failed: "
                    f"{ErrorMessages.INVALID_REFRESH_TOKEN}"
                )
            raise CowayError(f"Coway error message: {response['error']['message']}")
        return response

    @staticmethod
    async def _control_command_response(resp: ClientResponse) -> dict[str, Any] | str:
        """Parse a control-command response."""

        try:
            response = await resp.json()
        except (ValueError, ContentTypeError):
            return await resp.text()

        if resp.status != 200:
            return await resp.text()

        if "data" in response and "maintainInfos" in response["data"]:
            raise ServerMaintenance("Coway Servers are undergoing maintenance.")

        return response
