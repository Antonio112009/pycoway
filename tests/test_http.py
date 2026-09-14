"""Tests for HTTP response handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientConnectionError, ClientPayloadError

from pycoway.constants import ErrorMessages
from pycoway.exceptions import AuthError, CowayConnectionError, CowayError, ServerMaintenance
from pycoway.transport.http import CowayHttpClient
from tests.fakes import FakeResponse


def _mock_response(
    status: int = 200,
    json_data: dict | None = None,
    text_data: str = "",
    *,
    json_raises: Exception | None = None,
) -> MagicMock:
    """Create a mock ClientResponse."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text_data)
    if json_raises:
        resp.json = AsyncMock(side_effect=json_raises)
    else:
        resp.json = AsyncMock(return_value=json_data or {})
    return resp


class TestResponse:
    async def test_success(self):
        resp = _mock_response(json_data={"result": "ok"})
        result = await CowayHttpClient._response(resp)
        assert result == {"result": "ok"}

    async def test_maintenance_raises(self):
        resp = _mock_response(json_data={"data": {"maintainInfos": []}})
        with pytest.raises(ServerMaintenance):
            await CowayHttpClient._response(resp)

    async def test_error_key_invalid_refresh(self):
        resp = _mock_response(json_data={"error": {"message": ErrorMessages.INVALID_REFRESH_TOKEN}})
        with pytest.raises(AuthError):
            await CowayHttpClient._response(resp)

    async def test_error_key_generic(self):
        resp = _mock_response(json_data={"error": {"message": "some error"}})
        with pytest.raises(CowayError, match="some error"):
            await CowayHttpClient._response(resp)

    async def test_error_key_string_value(self):
        resp = _mock_response(json_data={"error": "plain string error"})
        with pytest.raises(CowayError, match="plain string error"):
            await CowayHttpClient._response(resp)

    async def test_non_200_bad_token(self):
        resp = _mock_response(
            status=401,
            json_data={"message": str(ErrorMessages.BAD_TOKEN)},
            text_data="Unauthorized",
        )
        with pytest.raises(AuthError):
            await CowayHttpClient._response(resp)

    async def test_non_200_expired_token(self):
        resp = _mock_response(
            status=401,
            json_data={"message": str(ErrorMessages.EXPIRED_TOKEN)},
            text_data="Unauthorized",
        )
        with pytest.raises(AuthError):
            await CowayHttpClient._response(resp)

    async def test_non_200_non_dict_json(self):
        resp = _mock_response(
            status=500,
            text_data="Server Error",
        )
        resp.json = AsyncMock(return_value=["unexpected", "list"])
        result = await CowayHttpClient._response(resp)
        assert result == {"error": ["unexpected", "list"]}

    async def test_non_200_json_error_key(self):
        resp = _mock_response(
            status=500,
            json_data={"error": "internal"},
            text_data="Server Error",
        )
        result = await CowayHttpClient._response(resp)
        assert "error" in result

    async def test_non_200_unparseable_json(self):
        resp = _mock_response(
            status=500,
            text_data="Bad Gateway",
            json_raises=ValueError("No JSON"),
        )
        with pytest.raises(CowayError, match="Could not return json"):
            await CowayHttpClient._response(resp)

    async def test_200_unparseable_json(self):
        resp = _mock_response(json_raises=ValueError("No JSON"))
        with pytest.raises(CowayError, match="Could not return json"):
            await CowayHttpClient._response(resp)


class TestControlCommandResponse:
    async def test_success(self):
        resp = _mock_response(json_data={"result": "ok"})
        result = await CowayHttpClient._control_command_response(resp)
        assert result == {"result": "ok"}

    async def test_maintenance_raises(self):
        resp = _mock_response(json_data={"data": {"maintainInfos": []}})
        with pytest.raises(ServerMaintenance):
            await CowayHttpClient._control_command_response(resp)

    async def test_non_200_returns_text(self):
        resp = _mock_response(
            status=500,
            json_data={"detail": "error"},
            text_data="Server Error",
        )
        result = await CowayHttpClient._control_command_response(resp)
        assert result == "Server Error"

    async def test_unparseable_returns_text(self):
        resp = _mock_response(
            text_data="raw text",
            json_raises=ValueError("No JSON"),
        )
        result = await CowayHttpClient._control_command_response(resp)
        assert result == "raw text"


class TestContextManager:
    async def test_session_created_lazily_and_closed(self):
        async with CowayHttpClient() as client:
            # No request made yet — the session must not exist.
            assert client._session is None
            session = client._ensure_session()
            assert client._session is session
            assert client._ensure_session() is session
        assert session.closed

    async def test_close_without_session_is_noop(self):
        async with CowayHttpClient() as client:
            pass
        assert client._session is None

    async def test_external_session_not_closed(self):
        from aiohttp import ClientSession

        session = ClientSession()
        try:
            async with CowayHttpClient(session=session) as client:
                assert client._owns_session is False
                assert client._ensure_session() is session
            # External session should NOT be closed
            assert not session.closed
        finally:
            await session.close()


class TestConnectionErrors:
    """aiohttp transport failures surface as CowayConnectionError (a CowayError)."""

    URL = "https://iocare.iotsvc.coway.com/api/v1/com/places"

    async def test_connection_failure_is_wrapped(self, fake_session):
        fake_session.add("get", self.URL, ClientConnectionError("boom"))
        client = CowayHttpClient(session=fake_session)

        with pytest.raises(
            CowayConnectionError, match=r"GET .*ClientConnectionError: boom"
        ) as info:
            await client._get_endpoint(self.URL, {}, None)

        assert isinstance(info.value, CowayError)
        assert isinstance(info.value.__cause__, ClientConnectionError)

    async def test_timeout_is_wrapped(self, fake_session):
        fake_session.add("post", f"{self.URL}/token", TimeoutError())
        client = CowayHttpClient(session=fake_session)

        with pytest.raises(CowayConnectionError, match="TimeoutError"):
            async with client._request("post", f"{self.URL}/token"):
                pass

    async def test_body_read_failure_is_wrapped(self, fake_session):
        html_url = "https://iocare2.coway.com/en/p1/product/MODEL"
        fake_session.add(
            "get",
            html_url,
            FakeResponse(content_type="text/html", read_error=ClientPayloadError("truncated")),
        )
        client = CowayHttpClient(session=fake_session)

        with pytest.raises(CowayConnectionError, match="truncated"):
            await client._get_purifier_html("nick", "serial", "MODEL", "p1")

    async def test_api_errors_are_not_reclassified(self, fake_session):
        fake_session.add("get", self.URL, FakeResponse(json_data={"error": {"message": "nope"}}))
        client = CowayHttpClient(session=fake_session)

        with pytest.raises(CowayError, match="nope") as info:
            await client._get_endpoint(self.URL, {}, None)

        assert type(info.value) is CowayError

    async def test_request_passes_timeout_and_kwargs(self, fake_session):
        fake_session.add("get", self.URL, FakeResponse(json_data={"data": {}}))
        client = CowayHttpClient(session=fake_session, timeout=7)

        assert await client._get_endpoint(self.URL, {"x": "y"}, {"a": "b"}) == {"data": {}}

        (call,) = fake_session.requests("get", self.URL)
        assert call["timeout"].total == 7
        assert call["headers"] == {"x": "y"}
        assert call["params"] == {"a": "b"}
