"""End-to-end authentication tests driven through a fake session (no network)."""

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from pycoway.account.auth import TOKEN_REFRESH_MARGIN, CowayAuthClient
from pycoway.client import CowayClient
from pycoway.constants import CATEGORY_NAME, Endpoint, ErrorMessages
from pycoway.exceptions import AuthError, CowayError, PasswordExpired
from tests.fakes import (
    DEFAULT_PLACE,
    LOGIN_ACTION_URL,
    PASSWORD_CHANGE_URL,
    PLACES_URL,
    REFRESH_URL,
    TOKEN_URL,
    FakeResponse,
    FakeSession,
    add_login_routes,
    html_page,
    redirect_bridge,
    token_response,
)

WRONG_PASSWORD_PAGE = html_page(
    '<p class="member_error_msg">Your ID or password is incorrect.</p>', title="Coway"
)


def _authed_client(session: FakeSession, *, expires_in: float) -> CowayAuthClient:
    """A client that already holds tokens expiring ``expires_in`` seconds from now."""
    client = CowayAuthClient("email@example.com", "password", session=session)
    client.access_token = "acc-old"
    client.refresh_token = "ref-old"
    client.token_expiration = datetime.now() + timedelta(seconds=expires_in)
    return client


class TestLoginFlow:
    async def test_full_login_populates_tokens_and_account(self, fake_session):
        add_login_routes(fake_session)
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        # login() holds the token lock while it runs the account calls; a
        # re-entrant token check inside them would deadlock, hence the timeout.
        await asyncio.wait_for(client.login(), timeout=5)

        assert client.access_token == "acc-1"
        assert client.refresh_token == "ref-1"
        assert client.country_code == "US"
        assert client.places == [DEFAULT_PLACE]
        assert client.token_expiration is not None
        remaining = client.token_expiration - datetime.now()
        assert timedelta(seconds=3500) < remaining <= timedelta(seconds=3600)

        (login_post,) = fake_session.requests("post", LOGIN_ACTION_URL)
        assert login_post["data"]["username"] == "email@example.com"
        assert login_post["data"]["password"] == "password"

        (token_post,) = fake_session.requests("post", TOKEN_URL)
        assert json.loads(token_post["data"]) == {
            "authCode": "auth-code-1",
            "redirectUrl": Endpoint.REDIRECT_URL,
        }

        # Account calls run with the freshly issued token.
        (places_get,) = fake_session.requests("get", PLACES_URL)
        assert places_get["headers"]["authorization"] == "Bearer acc-1"
        assert places_get["params"]["countryCode"] == "US"

    async def test_login_clears_only_coway_cookies(self, fake_session):
        add_login_routes(fake_session)
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        await client.login()

        cleared = {call.args[0] for call in fake_session.cookie_jar.clear_domain.call_args_list}
        assert cleared == {"id.coway.com", "iocare.iotsvc.coway.com", "iocareapi.iot.coway.com"}

    async def test_wrong_password_raises_auth_error(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add("post", LOGIN_ACTION_URL, WRONG_PASSWORD_PAGE)
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        with pytest.raises(AuthError, match="Invalid username/password"):
            await client.login()
        assert client.access_token is None
        assert fake_session.requests("post", TOKEN_URL) == []

    async def test_password_change_page_raises_when_not_skipped(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add(
            "post",
            LOGIN_ACTION_URL,
            html_page(
                f'<form id="kc-password-change-form" action="{PASSWORD_CHANGE_URL}"></form>',
                title="Coway - Password change message",
            ),
        )
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        with pytest.raises(PasswordExpired):
            await client.login()

    async def test_password_change_is_skipped_when_requested(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add(
            "post",
            LOGIN_ACTION_URL,
            html_page(
                f'<form id="kc-password-change-form" action="{PASSWORD_CHANGE_URL}"></form>',
                title="Coway - Password change message",
            ),
        )
        fake_session.add("post", PASSWORD_CHANGE_URL, redirect_bridge())
        client = CowayAuthClient(
            "email@example.com", "password", session=fake_session, skip_password_change=True
        )

        await client.login()

        (skip_post,) = fake_session.requests("post", PASSWORD_CHANGE_URL)
        assert skip_post["data"]["cmd"] == "change_next_time"
        assert client.access_token == "acc-1"

    async def test_missing_login_form_raises(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add("get", Endpoint.OAUTH_URL, html_page("<p>maintenance</p>"))
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        with pytest.raises(CowayError, match="valid Login URL"):
            await client.login()

    async def test_get_purifiers_logs_in_then_lists_devices(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add(
            "get",
            f"{PLACES_URL}/p1/devices",
            FakeResponse(
                json_data={
                    "data": {
                        "content": [
                            {"categoryName": CATEGORY_NAME, "deviceSerial": "S1", "placeId": "p1"},
                            {"categoryName": "water", "deviceSerial": "S2", "placeId": "p1"},
                        ]
                    }
                }
            ),
        )
        client = CowayClient("email@example.com", "password", session=fake_session)

        purifiers = await asyncio.wait_for(client.async_get_purifiers(), timeout=5)

        assert [p["deviceSerial"] for p in purifiers] == ["S1"]
        (devices_get,) = fake_session.requests("get", f"{PLACES_URL}/p1/devices")
        assert devices_get["headers"]["authorization"] == "Bearer acc-1"
        # The initial login is the only credential round-trip.
        assert len(fake_session.requests("post", LOGIN_ACTION_URL)) == 1


class TestTokenLock:
    async def test_concurrent_checks_share_one_refresh(self, fake_session):
        client = _authed_client(fake_session, expires_in=TOKEN_REFRESH_MARGIN - 1)

        async def slow_refresh(**_):
            await asyncio.sleep(0.01)  # let the other callers queue on the lock
            return token_response("acc-2", "ref-2")

        fake_session.add("post", REFRESH_URL, slow_refresh)

        await asyncio.gather(*(client._check_token() for _ in range(3)))

        assert len(fake_session.requests("post", REFRESH_URL)) == 1
        assert client.access_token == "acc-2"
        assert client.refresh_token == "ref-2"

    async def test_concurrent_checks_share_one_login(self, fake_session):
        add_login_routes(fake_session, oauth_page_delay=0.01)
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        await asyncio.gather(*(client._check_token() for _ in range(3)))

        assert len(fake_session.requests("post", LOGIN_ACTION_URL)) == 1
        assert client.access_token == "acc-1"

    async def test_login_and_check_do_not_deadlock_back_to_back(self, fake_session):
        add_login_routes(fake_session)
        client = CowayAuthClient("email@example.com", "password", session=fake_session)

        await asyncio.wait_for(client.login(), timeout=5)
        await asyncio.wait_for(client._check_token(), timeout=5)

        assert len(fake_session.requests("post", LOGIN_ACTION_URL)) == 1

    async def test_valid_token_makes_no_requests(self, fake_session):
        client = _authed_client(fake_session, expires_in=3600)

        await client._check_token()

        assert fake_session.calls == []
        assert client.access_token == "acc-old"

    async def test_check_token_disabled_skips_login(self, fake_session):
        client = CowayAuthClient("email@example.com", "password", session=fake_session)
        client.check_token = False

        await client._check_token()

        assert fake_session.calls == []
        assert client.access_token is None


class TestRefreshFallback:
    async def test_refresh_success_updates_tokens_without_login(self, fake_session):
        client = _authed_client(fake_session, expires_in=10)
        fake_session.add("post", REFRESH_URL, token_response("acc-2", "ref-2", expires_in=7200))

        await client._check_token()

        assert client.access_token == "acc-2"
        assert client.refresh_token == "ref-2"
        assert client.token_expiration is not None
        assert client.token_expiration - datetime.now() > timedelta(seconds=7000)
        (refresh_post,) = fake_session.requests("post", REFRESH_URL)
        assert json.loads(refresh_post["data"]) == {"refreshToken": "ref-old"}
        assert fake_session.requests("post", LOGIN_ACTION_URL) == []

    async def test_rejected_refresh_token_falls_back_to_login(self, fake_session):
        add_login_routes(fake_session)
        client = _authed_client(fake_session, expires_in=10)
        fake_session.add(
            "post",
            REFRESH_URL,
            FakeResponse(
                json_data={"error": {"message": str(ErrorMessages.INVALID_REFRESH_TOKEN)}}
            ),
        )

        await asyncio.wait_for(client._check_token(), timeout=5)

        assert client.access_token == "acc-1"  # issued by the credential login
        assert len(fake_session.requests("post", LOGIN_ACTION_URL)) == 1

    async def test_refresh_error_response_falls_back_to_login(self, fake_session):
        add_login_routes(fake_session)
        client = _authed_client(fake_session, expires_in=10)
        fake_session.add(
            "post", REFRESH_URL, FakeResponse(status=500, json_data={"error": "expired"})
        )

        await asyncio.wait_for(client._check_token(), timeout=5)

        assert client.access_token == "acc-1"
        assert len(fake_session.requests("post", LOGIN_ACTION_URL)) == 1

    async def test_fallback_login_with_bad_credentials_still_raises(self, fake_session):
        add_login_routes(fake_session)
        fake_session.add("post", LOGIN_ACTION_URL, WRONG_PASSWORD_PAGE)
        client = _authed_client(fake_session, expires_in=10)
        fake_session.add(
            "post",
            REFRESH_URL,
            FakeResponse(
                json_data={"error": {"message": str(ErrorMessages.INVALID_REFRESH_TOKEN)}}
            ),
        )

        with pytest.raises(AuthError, match="Invalid username/password"):
            await client._check_token()
