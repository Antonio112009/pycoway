"""Recovery from tokens Coway rejects before their stated expiry."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from pycoway.client import CowayClient
from pycoway.constants import Endpoint, ErrorMessages
from pycoway.devices.models import DeviceAttributes
from pycoway.exceptions import AuthError, CowayError, TokenRejected
from tests.fakes import (
    DEFAULT_PLACE,
    LOGIN_ACTION_URL,
    PLACES_URL,
    FakeResponse,
    FakeSession,
    add_login_routes,
)
from tests.test_auth_flow import TestPollRacingControlCommand

EXPIRED = FakeResponse(status=401, json_data={"message": ErrorMessages.EXPIRED_TOKEN})
CONTROL_URL = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONTROL}/S1/control"
CONTROL_OK = FakeResponse(
    json_data={"data": {"controlStatus": {"0001": "1", "0002": "1"}, "netStatus": True}}
)
ATTR = DeviceAttributes(
    device_id="S1",
    model=None,
    model_code=None,
    code=None,
    name="Bedroom",
    product_name=None,
    place_id="p1",
)


def _client(session: FakeSession) -> CowayClient:
    """A client holding a token that looks valid for another hour."""
    client = CowayClient("email@example.com", "password", session=session, timezone="UTC")
    client.access_token = "acc-old"
    client.refresh_token = "ref-old"
    client.token_expiration = datetime.now(UTC) + timedelta(hours=1)
    client.places = [DEFAULT_PLACE]
    return client


def _poll_routes(session: FakeSession) -> None:
    TestPollRacingControlCommand()._add_poll_routes(session)
    add_login_routes(session)


class TestPollRecovery:
    async def test_rejected_token_logs_in_and_retries(self, fake_session, caplog):
        _poll_routes(fake_session)
        fake_session.add("get", CONTROL_URL, EXPIRED, CONTROL_OK)
        client = _client(fake_session)

        with caplog.at_level(logging.WARNING, logger="pycoway"):
            data = await asyncio.wait_for(client.async_get_purifiers_data(), timeout=5)

        assert data.purifiers["S1"].is_on is True
        assert client.access_token == "acc-1"
        assert len(fake_session.requests("post", LOGIN_ACTION_URL)) == 1
        assert "rejected the access token" in caplog.text

    async def test_token_rejected_again_after_login_is_not_auth_error(self, fake_session):
        _poll_routes(fake_session)
        fake_session.add("get", CONTROL_URL, EXPIRED)
        client = _client(fake_session)

        with pytest.raises(CowayError, match="again right after logging in") as info:
            await asyncio.wait_for(client.async_get_purifiers_data(), timeout=5)

        # Credentials work (the login succeeded), so this must not ask the
        # caller to re-authenticate.
        assert not isinstance(info.value, AuthError)

    async def test_bad_credentials_during_recovery_still_raise_auth_error(self):
        client = CowayClient("email@example.com", "password", session=FakeSession())
        client._get_purifiers_data = AsyncMock(side_effect=TokenRejected("expired"))
        client._do_login = AsyncMock(side_effect=AuthError("bad password"))

        with pytest.raises(AuthError, match="bad password"):
            await client.async_get_purifiers_data()

    async def test_token_replaced_concurrently_skips_login(self):
        client = CowayClient("email@example.com", "password", session=FakeSession())
        client.access_token = "acc-old"

        async def rejected_then_ok():
            if client._get_purifiers_data.await_count == 1:
                client.access_token = "acc-new"  # another caller logged in meanwhile
                raise TokenRejected("expired")
            return "data"

        client._get_purifiers_data = AsyncMock(side_effect=rejected_then_ok)
        client._do_login = AsyncMock()

        assert await client.async_get_purifiers_data() == "data"
        client._do_login.assert_not_awaited()


class TestControlRecovery:
    async def test_control_command_retries_after_login(self, fake_session):
        add_login_routes(fake_session)
        control_url = f"{PLACES_URL}/p1/devices/S1/control-status"
        ok = FakeResponse(json_data={"code": "S1000", "message": "OK"})
        fake_session.add("post", control_url, EXPIRED, ok)
        client = _client(fake_session)

        await asyncio.wait_for(client.async_set_power(ATTR, True), timeout=5)

        sent = fake_session.requests("post", control_url)
        assert [c["headers"]["authorization"] for c in sent] == [
            "Bearer acc-old",
            "Bearer acc-1",
        ]

    async def test_prefilter_retries_after_login(self, fake_session):
        add_login_routes(fake_session)
        url = f"{PLACES_URL}/p1/devices/S1/control-param"
        ok = FakeResponse(json_data={"code": "S1000", "message": "OK"})
        fake_session.add("post", url, EXPIRED, ok)
        client = _client(fake_session)

        await asyncio.wait_for(client.async_change_prefilter_setting(ATTR, 3), timeout=5)

        assert len(fake_session.requests("post", url)) == 2

    async def test_invalid_prefilter_value_sends_nothing(self, fake_session):
        client = _client(fake_session)
        with pytest.raises(CowayError, match="Invalid prefilter value"):
            await client.async_change_prefilter_setting(ATTR, 5)  # type: ignore[arg-type]
        assert fake_session.calls == []


class TestClockAndTimezone:
    async def test_token_expiration_is_utc(self, fake_session):
        add_login_routes(fake_session)
        client = CowayClient("email@example.com", "password", session=fake_session)
        await asyncio.wait_for(client.login(), timeout=5)
        assert client.token_expiration is not None
        assert client.token_expiration.tzinfo is UTC

    async def test_configured_timezone_skips_detection(self, fake_session):
        add_login_routes(fake_session)
        html_url = f"{Endpoint.PURIFIER_HTML_BASE}/p1/product/MODEL"
        fake_session.add("get", html_url, FakeResponse(content_type="text/html", text="<html/>"))
        client = CowayClient(
            "email@example.com", "password", session=fake_session, timezone="Europe/London"
        )
        with patch("pycoway.transport.http.get_timezone") as detect:
            await asyncio.wait_for(client.login(), timeout=5)
            await client._get_purifier_html("Bedroom", "S1", "MODEL", "p1")

        detect.assert_not_called()
        (places_call,) = fake_session.requests("get", PLACES_URL)
        assert places_call["params"]["timezoneId"] == "Europe/London"
        (html_call,) = fake_session.requests("get", html_url)
        assert html_call["headers"]["timezoneid"] == "Europe/London"

    async def test_timezone_detected_when_not_configured(self):
        client = CowayClient("email@example.com", "password")
        with patch("pycoway.transport.http.get_timezone", return_value="Asia/Seoul"):
            assert client._timezone_id() == "Asia/Seoul"


class TestLogsWithoutEmail:
    async def test_login_and_poll_logs_never_contain_the_email(self, fake_session, caplog):
        _poll_routes(fake_session)
        fake_session.add("get", CONTROL_URL, EXPIRED, CONTROL_OK)
        client = _client(fake_session)

        with caplog.at_level(logging.DEBUG, logger="pycoway"):
            await asyncio.wait_for(client.async_get_purifiers_data(), timeout=5)

        assert caplog.records
        assert "email@example.com" not in caplog.text
