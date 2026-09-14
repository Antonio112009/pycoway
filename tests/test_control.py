"""Tests for purifier control commands."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientConnectionError

from pycoway.client import CowayClient
from pycoway.constants import CommandCode, Endpoint, LightMode
from pycoway.devices.control import CowayControlClient
from pycoway.exceptions import CowayConnectionError, CowayError
from tests.fakes import FakeResponse


def _mock_control_client(response) -> CowayControlClient:
    """Create a CowayControlClient with a mocked async_control_purifier."""
    client = CowayControlClient.__new__(CowayControlClient)
    client.async_control_purifier = AsyncMock(return_value=response)
    return client


class TestSetLightMode:
    async def test_sends_string_wire_value(self, sample_device):
        client = _mock_control_client({"header": {}})
        await client.async_set_light_mode(sample_device, LightMode.OFF)
        client.async_control_purifier.assert_awaited_once_with(
            sample_device, CommandCode.LIGHT, "2"
        )

    async def test_accepts_string_value(self, sample_device):
        client = _mock_control_client({"header": {}})
        await client.async_set_light_mode(sample_device, "1")
        client.async_control_purifier.assert_awaited_once_with(
            sample_device, CommandCode.LIGHT, "1"
        )

    async def test_error_response_raises(self, sample_device):
        client = _mock_control_client({"header": {"error_code": "E1", "error_text": "bad"}})
        with pytest.raises(CowayError, match="light mode"):
            await client.async_set_light_mode(sample_device, LightMode.ON)

    async def test_iot_style_success_code_accepted(self, sample_device):
        client = _mock_control_client({"code": "S1000", "message": "OK", "data": {}})
        await client.async_set_light_mode(sample_device, LightMode.OFF)

    async def test_iot_style_error_code_raises(self, sample_device):
        client = _mock_control_client({"code": "E4000", "message": "invalid attribute"})
        with pytest.raises(CowayError, match="E4000"):
            await client.async_set_light_mode(sample_device, LightMode.OFF)


class TestSetLight:
    async def test_on_off_wire_values(self, sample_device):
        client = _mock_control_client({"header": {}})
        await client.async_set_light(sample_device, True)
        client.async_control_purifier.assert_awaited_with(sample_device, CommandCode.LIGHT, "2")
        await client.async_set_light(sample_device, False)
        client.async_control_purifier.assert_awaited_with(sample_device, CommandCode.LIGHT, "0")


class TestSetFanSpeed:
    async def test_invalid_speed_raises(self, sample_device):
        client = _mock_control_client({"header": {}})
        with pytest.raises(CowayError, match="Invalid fan speed"):
            await client.async_set_fan_speed(sample_device, "5")
        client.async_control_purifier.assert_not_awaited()


class TestControlTransport:
    """Control commands through the real request path with a fake session."""

    def _client(self, fake_session) -> CowayClient:
        client = CowayClient("email@example.com", "password", session=fake_session)
        client.access_token = "acc"
        client.refresh_token = "ref"
        client.token_expiration = datetime.now() + timedelta(hours=1)
        return client

    async def test_power_command_posts_expected_body(self, fake_session, sample_device):
        url = f"{Endpoint.BASE_URI}{Endpoint.PLACES}/place-001/devices/ABC123/control-status"
        fake_session.add("post", url, FakeResponse(json_data={"code": "S1000", "message": "OK"}))
        client = self._client(fake_session)

        await client.async_set_power(sample_device, True)

        (call,) = fake_session.requests("post", url)
        assert json.loads(call["data"]) == {
            "attributes": {"0001": "1"},
            "isMultiControl": False,
            "refreshFlag": False,
        }
        assert call["headers"]["authorization"] == "Bearer acc"
        assert call["headers"]["region"] == "NUS"

    async def test_connection_failure_raises_coway_connection_error(
        self, fake_session, sample_device
    ):
        url = f"{Endpoint.BASE_URI}{Endpoint.PLACES}/place-001/devices/ABC123/control-status"
        fake_session.add("post", url, ClientConnectionError("boom"))
        client = self._client(fake_session)

        with pytest.raises(CowayConnectionError):
            await client.async_set_power(sample_device, False)

    async def test_prefilter_command_posts_cycle(self, fake_session, sample_device):
        url = f"{Endpoint.BASE_URI}{Endpoint.PLACES}/place-001/devices/ABC123/control-param"
        fake_session.add("post", url, FakeResponse(json_data={"header": {}}))
        client = self._client(fake_session)

        await client.async_change_prefilter_setting(sample_device, 3)

        (call,) = fake_session.requests("post", url)
        assert json.loads(call["data"])["attributes"] == {"0001": "168"}
