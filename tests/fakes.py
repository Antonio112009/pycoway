"""Minimal stand-ins for aiohttp's ``ClientSession`` and ``ClientResponse``.

They let the real client code run end to end (OAuth login, token refresh,
request wrapper, control commands) without a network. Third-party mocking
libraries keep breaking on aiohttp's private response constructor, so the
fakes only implement the handful of attributes pycoway actually touches.
"""

import asyncio
import inspect
import json
from http.cookies import SimpleCookie
from typing import Any
from unittest.mock import MagicMock

from yarl import URL

from pycoway.constants import Endpoint

LOGIN_ACTION_URL = "https://id.coway.com/login-actions/authenticate"
PASSWORD_CHANGE_URL = "https://id.coway.com/login-actions/required-action"
TOKEN_URL = f"{Endpoint.BASE_URI}{Endpoint.GET_TOKEN}"
REFRESH_URL = f"{Endpoint.BASE_URI}{Endpoint.TOKEN_REFRESH}"
USER_INFO_URL = f"{Endpoint.BASE_URI}{Endpoint.USER_INFO}"
PLACES_URL = f"{Endpoint.BASE_URI}{Endpoint.PLACES}"

DEFAULT_PLACE = {"placeId": "p1", "placeName": "Home", "deviceCnt": 1}


def _route_key(method: str, url: str) -> tuple[str, str]:
    return method.lower(), str(URL(str(url)).with_query(None))


class FakeResponse:
    """Just enough of ``aiohttp.ClientResponse`` for pycoway's code paths."""

    def __init__(
        self,
        *,
        status: int = 200,
        json_data: Any = None,
        text: str = "",
        content_type: str = "application/json",
        url: str = "",
        reason: str = "OK",
        read_error: BaseException | None = None,
    ) -> None:
        self.status = status
        self.reason = reason
        self.content_type = content_type
        self.url = URL(url)
        self.cookies = SimpleCookie()
        self._json = json_data
        self._text = text if text or json_data is None else json.dumps(json_data)
        self._read_error = read_error

    async def text(self) -> str:
        if self._read_error is not None:
            raise self._read_error
        return self._text

    async def json(self) -> Any:
        if self._read_error is not None:
            raise self._read_error
        if self._json is None:
            raise ValueError("response body is not JSON")
        return self._json


class _FakeRequestContext:
    """Mimics the ``async with session.get(...) as resp`` context manager."""

    def __init__(self, session: "FakeSession", method: str, url: str, kwargs: dict) -> None:
        self._session = session
        self._method = method
        self._url = url
        self._kwargs = kwargs

    async def __aenter__(self) -> FakeResponse:
        outcome = self._session._resolve(self._method, self._url)
        if callable(outcome) and not isinstance(outcome, BaseException):
            outcome = outcome(**self._kwargs)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def __aexit__(self, *exc: Any) -> None:
        return None


class FakeSession:
    """Routes ``get``/``post`` calls to canned outcomes and records every call.

    An outcome is a :class:`FakeResponse`, an exception instance (raised
    when the request is entered, like a connection failure), or a callable
    taking the request kwargs and returning either of those, optionally
    asynchronously. A queue of outcomes is consumed in order; the last one
    is reused once the queue is drained.
    """

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], list[Any]] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.cookie_jar = MagicMock()
        self.closed = False

    def add(self, method: str, url: str, *outcomes: Any) -> None:
        """Set the outcome queue for a route, replacing any previous one."""
        self._routes[_route_key(method, url)] = list(outcomes)

    def requests(self, method: str, url: str) -> list[dict[str, Any]]:
        """Return the kwargs of every recorded call to a route, in order."""
        key = _route_key(method, url)
        return [kwargs for m, u, kwargs in self.calls if _route_key(m, u) == key]

    def _resolve(self, method: str, url: str) -> Any:
        queue = self._routes.get(_route_key(method, url))
        if not queue:
            raise AssertionError(f"unexpected {method.upper()} {url}")
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def _start(self, method: str, url: str, kwargs: dict[str, Any]) -> _FakeRequestContext:
        self.calls.append((method, str(url), kwargs))
        return _FakeRequestContext(self, method, str(url), kwargs)

    def get(self, url: str, **kwargs: Any) -> _FakeRequestContext:
        return self._start("get", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> _FakeRequestContext:
        return self._start("post", url, kwargs)

    async def close(self) -> None:
        self.closed = True


def html_page(body: str, title: str | None = None) -> FakeResponse:
    """A text/html response, optionally with a ``<title>``."""
    head = f"<head><title>{title}</title></head>" if title else ""
    return FakeResponse(content_type="text/html", text=f"<html>{head}<body>{body}</body></html>")


def redirect_bridge(code: str = "auth-code-1") -> FakeResponse:
    """The empty redirect-bridge page Keycloak lands on after a successful login."""
    return FakeResponse(
        content_type="text/html",
        text="<html><body></body></html>",
        url=f"{Endpoint.REDIRECT_URL}?code={code}&session_state=s",
    )


def token_response(
    access_token: str = "acc-1", refresh_token: str = "ref-1", expires_in: int = 3600
) -> FakeResponse:
    return FakeResponse(
        json_data={
            "data": {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresIn": expires_in,
            }
        }
    )


def add_login_routes(
    session: FakeSession,
    *,
    places: list[dict[str, Any]] | None = None,
    oauth_page_delay: float = 0.0,
) -> None:
    """Register the happy-path login flow on ``session``.

    ``oauth_page_delay`` makes the first request of the flow yield to the
    event loop, which is what lets concurrency tests observe other callers
    queueing behind the token lock.
    """
    login_form = html_page(f'<form id="kc-form-login" action="{LOGIN_ACTION_URL}"></form>')
    if oauth_page_delay:

        async def slow_login_form(**_: Any) -> FakeResponse:
            await asyncio.sleep(oauth_page_delay)
            return login_form

        session.add("get", Endpoint.OAUTH_URL, slow_login_form)
    else:
        session.add("get", Endpoint.OAUTH_URL, login_form)
    session.add("post", LOGIN_ACTION_URL, redirect_bridge())
    session.add("post", TOKEN_URL, token_response())
    session.add(
        "get",
        USER_INFO_URL,
        FakeResponse(json_data={"data": {"memberInfo": {"countryCode": "US"}}}),
    )
    session.add(
        "get",
        PLACES_URL,
        FakeResponse(
            json_data={"data": {"content": [DEFAULT_PLACE] if places is None else places}}
        ),
    )
