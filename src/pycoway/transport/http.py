"""HTTP base client for Coway IoCare API."""

import json
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Literal, Self

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout, ContentTypeError

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
    CowayConnectionError,
    CowayError,
    ServerMaintenance,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

LOGGER = logging.getLogger(__name__)


class CowayHttpClient:
    """Low-level HTTP transport for Coway API."""

    def __init__(self, session: ClientSession | None = None, timeout: int = TIMEOUT) -> None:
        self._session: ClientSession | None = session
        self._owns_session: bool = session is None
        self.timeout: ClientTimeout = ClientTimeout(total=timeout)
        self.access_token: str | None = None

    def _ensure_session(self) -> ClientSession:
        """Return the HTTP session, creating it lazily on first use.

        Deferring creation to the first request means the session is
        always created inside a running event loop, even when the client
        itself was instantiated in synchronous code.
        """
        if self._session is None:
            self._session = ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session if we created it."""
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    @asynccontextmanager
    async def _request(
        self, method: Literal["get", "post"], url: str, **kwargs: Any
    ) -> AsyncIterator[ClientResponse]:
        """Issue a request, translating transport failures into ``CowayConnectionError``.

        Every HTTP call goes through here so callers only ever see the
        ``CowayError`` hierarchy: connection failures, timeouts and
        truncated payloads from aiohttp are re-raised as
        :class:`~pycoway.exceptions.CowayConnectionError`. Failures while
        reading the body inside the ``with`` block are covered as well.
        """

        session = self._ensure_session()
        requester = session.get if method == "get" else session.post
        try:
            async with requester(url, timeout=self.timeout, **kwargs) as resp:
                yield resp
        except (ClientError, TimeoutError) as exc:
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            raise CowayConnectionError(
                f"Connection error during {method.upper()} {url}: {detail}"
            ) from exc

    async def _post_endpoint(self, data: dict[str, str]) -> dict[str, Any]:
        """POST to the token endpoint."""

        url = f"{Endpoint.BASE_URI}{Endpoint.GET_TOKEN}"
        headers = {
            "content-type": Header.CONTENT_JSON,
            "user-agent": Header.USER_AGENT,
            "accept-language": Header.COWAY_LANGUAGE,
        }
        async with self._request("post", url, headers=headers, data=json.dumps(data)) as resp:
            return await self._response(resp)

    async def _get_endpoint(
        self,
        endpoint: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """GET an authorized API endpoint."""

        async with self._request("get", endpoint, headers=headers, params=params) as resp:
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
        async with self._request("get", endpoint, headers=headers, params=params) as resp:
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
            "timezoneid": get_timezone(),
            "appversion": Parameter.APP_VERSION,
            "accesstoken": self.access_token or "",
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
        async with self._request("get", url, headers=headers, params=params) as resp:
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

            if not isinstance(error_json, dict) or "error" in error_json:
                return {"error": error_json}

            message = error_json.get("message")
            if message in (ErrorMessages.BAD_TOKEN, ErrorMessages.EXPIRED_TOKEN):
                raise AuthError(f"Coway Auth error: Coway IoCare authentication failed; {message}")
            return {"error": error_json}

        try:
            response = await resp.json()
        except (ValueError, ContentTypeError) as exc:
            raise CowayError(f"Could not return json {exc}") from exc

        if "data" in response and "maintainInfos" in response["data"]:
            raise ServerMaintenance("Coway Servers are undergoing maintenance.")

        # Sometimes an unauthorized message comes back with a 200 status.
        if "error" in response:
            error = response["error"]
            message = error.get("message") if isinstance(error, dict) else error
            if message == ErrorMessages.INVALID_REFRESH_TOKEN:
                raise AuthError(f"Coway Auth error: Coway IoCare authentication failed: {message}")
            raise CowayError(f"Coway error message: {message}")
        return response

    @staticmethod
    async def _control_command_response(resp: ClientResponse) -> dict[str, Any] | str:
        """Parse a control-command response."""

        try:
            response = await resp.json()
        except ValueError, ContentTypeError:
            return await resp.text()

        if resp.status != 200:
            return await resp.text()

        if "data" in response and "maintainInfos" in response["data"]:
            raise ServerMaintenance("Coway Servers are undergoing maintenance.")

        return response
