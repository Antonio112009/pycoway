"""Tests for HB (homebridge-style) API endpoint constants and transport."""

from unittest.mock import AsyncMock, MagicMock

from pycoway.constants import Endpoint
from pycoway.transport.http import CowayHttpClient


class TestHBEndpointConstants:
    def test_hb_base_uri(self):
        assert Endpoint.HB_BASE_URI == "https://iocareapi.iot.coway.com/api/v1"

    def test_hb_user_devices(self):
        assert Endpoint.HB_USER_DEVICES == "/com/user-devices"

    def test_hb_device_control(self):
        assert Endpoint.HB_DEVICE_CONTROL == "/com/devices"

    def test_hb_device_conn(self):
        assert Endpoint.HB_DEVICE_CONN == "/com/devices-conn"

    def test_hb_air_home(self):
        assert Endpoint.HB_AIR_HOME == "/air/devices"

    def test_hb_air_filter_info(self):
        assert Endpoint.HB_AIR_FILTER_INFO == "/air/devices"


class TestHBHeader:
    def test_construct_hb_header(self):
        client = CowayHttpClient.__new__(CowayHttpClient)
        client.access_token = "test-token-123"
        header = client._construct_hb_header()
        assert header["authorization"] == "Bearer test-token-123"
        assert header["Content-Type"] == "application/json"
        assert header["Accept"] == "*/*"
        # HB header should NOT include 'region'
        assert "region" not in header

    def test_control_header_has_region(self):
        client = CowayHttpClient.__new__(CowayHttpClient)
        client.access_token = "test-token-123"
        header = client._construct_control_header()
        assert header["region"] == "NUS"


class TestGetHBEndpoint:
    async def test_calls_session_get_with_params(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"data": {"result": "ok"}})

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_ctx)

        client = CowayHttpClient(session=mock_session)
        client.access_token = "test-token"

        result = await client._get_hb_endpoint(
            "https://iocareapi.iot.coway.com/api/v1/com/user-devices",
            params={"pageIndex": "0", "pageSize": "100"},
        )

        mock_session.get.assert_called_once()
        call_kwargs = mock_session.get.call_args
        assert "pageIndex" in call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))
        assert result == {"data": {"result": "ok"}}

    async def test_passes_hb_header(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"data": {}})

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_ctx)

        client = CowayHttpClient(session=mock_session)
        client.access_token = "my-token"

        await client._get_hb_endpoint("https://example.com/test")

        call_kwargs = mock_session.get.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert headers["authorization"] == "Bearer my-token"
        assert "region" not in headers
