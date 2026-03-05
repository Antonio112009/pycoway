"""Tests for HTTP response handling."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from cowayaio.constants import ErrorMessages
from cowayaio.exceptions import AuthError, CowayError, ServerMaintenance
from cowayaio.http import CowayHttpClient


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
        resp = _mock_response(
            json_data={
                "error": {"message": ErrorMessages.INVALID_REFRESH_TOKEN}
            }
        )
        with pytest.raises(AuthError):
            await CowayHttpClient._response(resp)

    async def test_error_key_generic(self):
        resp = _mock_response(
            json_data={"error": {"message": "some error"}}
        )
        with pytest.raises(CowayError, match="some error"):
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
        result = await CowayHttpClient._response(resp)
        assert result == {"error": str(ErrorMessages.EXPIRED_TOKEN)}

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
    async def test_async_context_manager(self):
        async with CowayHttpClient() as client:
            assert client._session is not None
        assert client._session.closed

    async def test_external_session_not_closed(self):
        from aiohttp import ClientSession

        session = ClientSession()
        try:
            async with CowayHttpClient(session=session) as client:
                assert client._owns_session is False
            # External session should NOT be closed
            assert not session.closed
        finally:
            await session.close()
