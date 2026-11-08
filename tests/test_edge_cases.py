"""Error and edge paths of the login flow, control commands and HTML parsing."""

import asyncio

import pytest

from pycoway.account.auth import CowayAuthClient
from pycoway.constants import CommandCode, Endpoint, ErrorMessages
from pycoway.devices.parser import extract_html_supplements
from pycoway.exceptions import CowayError, NoPlaces, RateLimited, ServerMaintenance
from tests.fakes import (
    PLACES_URL,
    TOKEN_URL,
    USER_INFO_URL,
    FakeResponse,
    add_login_routes,
)
from tests.test_control import _mock_control_client


def _client(session) -> CowayAuthClient:
    return CowayAuthClient("email@example.com", "password", session=session, timezone="UTC")


class TestLoginErrors:
    @pytest.mark.parametrize(
        ("status", "error"),
        [(503, ServerMaintenance), (500, CowayError)],
    )
    async def test_login_page_status(self, fake_session, status, error):
        add_login_routes(fake_session)
        fake_session.add(
            "get", Endpoint.OAUTH_URL, FakeResponse(status=status, content_type="text/html")
        )
        with pytest.raises(error):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)

    async def test_invalid_grant_means_rate_limited(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add(
            "post",
            TOKEN_URL,
            FakeResponse(status=400, json_data={"message": ErrorMessages.INVALID_GRANT}),
        )
        with pytest.raises(RateLimited):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)

    async def test_other_token_error(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add("post", TOKEN_URL, FakeResponse(status=400, json_data={"message": "nope"}))
        with pytest.raises(CowayError, match="Failed fetching Coway access token: nope"):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)

    async def test_token_response_without_tokens(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add("post", TOKEN_URL, FakeResponse(json_data={"data": {}}))
        with pytest.raises(CowayError, match="Failed fetching Coway access/refresh token"):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)

    @pytest.mark.parametrize(
        ("user_info", "match"),
        [
            ({"data": {"memberInfo": {}}}, "Failed to get country code"),
            ({"result": "?"}, "Unexpected response getting country code"),
        ],
    )
    async def test_country_code_errors(self, fake_session, user_info, match):
        add_login_routes(fake_session)
        fake_session.add("get", USER_INFO_URL, FakeResponse(json_data=user_info))
        with pytest.raises(CowayError, match=match):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)

    async def test_country_code_maintenance(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add(
            "get", USER_INFO_URL, FakeResponse(json_data={"data": {"maintainInfos": []}})
        )
        with pytest.raises(ServerMaintenance):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)

    async def test_no_places(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add("get", PLACES_URL, FakeResponse(json_data={"data": {}}))
        with pytest.raises(NoPlaces):
            await asyncio.wait_for(_client(fake_session).login(), timeout=5)


class TestModeCommands:
    @pytest.mark.parametrize(
        ("method", "kwargs", "code", "value"),
        [
            ("async_set_power", {"is_on": True}, CommandCode.POWER, "1"),
            ("async_set_power", {"is_on": False}, CommandCode.POWER, "0"),
            ("async_set_auto_mode", {}, CommandCode.MODE, "1"),
            ("async_set_night_mode", {}, CommandCode.MODE, "2"),
            ("async_set_eco_mode", {}, CommandCode.MODE, "6"),
            ("async_set_rapid_mode", {}, CommandCode.MODE, "5"),
            ("async_set_fan_speed", {"speed": "2"}, CommandCode.FAN_SPEED, "2"),
            ("async_set_light", {"light_on": True}, CommandCode.LIGHT, "2"),
            ("async_set_timer", {"time": "120"}, CommandCode.TIMER, "120"),
            (
                "async_set_smart_mode_sensitivity",
                {"sensitivity": "3"},
                CommandCode.SMART_SENSITIVITY,
                "3",
            ),
            ("async_set_button_lock", {"value": "1"}, CommandCode.BUTTON_LOCK, "1"),
        ],
    )
    async def test_wire_values(self, sample_device, method, kwargs, code, value):
        client = _mock_control_client({"code": "S1000"})
        await getattr(client, method)(sample_device, **kwargs)
        client.async_control_purifier.assert_awaited_once_with(sample_device, code, value)

    async def test_text_response_raises(self, sample_device):
        client = _mock_control_client("Bad Gateway")
        with pytest.raises(CowayError, match="Bad Gateway"):
            await client.async_set_power(sample_device, is_on=True)


class TestHtmlSupplements:
    def test_mcu_and_lux(self):
        info = {
            "coreData": [
                {"data": {"currentMcuVer": "1.2.3"}},
                {"data": {"sensorInfo": {"attributes": {"0007": "250"}}}},
            ]
        }
        assert extract_html_supplements(info) == {"mcu_version": "1.2.3", "lux": 250}

    def test_unparseable_lux_is_none(self):
        info = {"coreData": [{"data": {"sensorInfo": {"attributes": {"0007": "dim"}}}}]}
        assert extract_html_supplements(info) == {"mcu_version": None, "lux": None}

    def test_empty(self):
        assert extract_html_supplements({}) == {"mcu_version": None, "lux": None}
