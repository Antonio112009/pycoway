"""Tests for public client behavior and auth fallbacks."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from yarl import URL

from pycoway.account.auth import CowayAuthClient, _token_lifetime
from pycoway.client import CowayClient
from pycoway.exceptions import AuthError


class _MockPostContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return None


class _MockSession:
    def post(self, *args, **kwargs):
        return _MockPostContext()


class TestCowayClient:
    async def test_accepts_positional_credentials(self):
        client = CowayClient("email@example.com", "password")
        try:
            assert client.username == "email@example.com"
            assert client.password == "password"
        finally:
            await client.close()

    async def test_get_purifiers_logs_in_if_places_are_missing(self):
        client = CowayClient("email@example.com", "password")

        async def _fake_login():
            client.places = [
                {
                    "placeId": "place-001",
                    "placeName": "Home",
                    "deviceCnt": 0,
                }
            ]

        try:
            client.login = AsyncMock(side_effect=_fake_login)
            client._create_endpoint_header = AsyncMock(return_value={})

            assert await client.async_get_purifiers() == []
            client.login.assert_awaited_once()
        finally:
            await client.close()

    async def test_context_manager_yields_the_concrete_client(self):
        async with CowayClient("email@example.com", "password") as client:
            assert type(client) is CowayClient


class TestGetAuthCode:
    def _client_with_redirect(self, url: str) -> CowayAuthClient:
        client = CowayAuthClient("email@example.com", "password", session=_MockSession())
        resp = MagicMock()
        resp.url = URL(url)
        client._post_auth = AsyncMock(return_value=(resp, False))
        return client

    async def test_extracts_code_from_query(self):
        client = self._client_with_redirect(
            "https://example.com/redirect?code=auth-code-123&state=xyz"
        )
        assert await client._get_auth_code("https://login", {}) == "auth-code-123"

    async def test_code_not_last_param(self):
        client = self._client_with_redirect(
            "https://example.com/redirect?state=xyz&code=auth-code-123&session_state=abc"
        )
        assert await client._get_auth_code("https://login", {}) == "auth-code-123"

    async def test_missing_code_raises(self):
        client = self._client_with_redirect("https://example.com/login?session_code=not-it")
        with pytest.raises(AuthError):
            await client._get_auth_code("https://login", {})


class TestTokenLifetime:
    def test_uses_expires_in(self):
        assert _token_lifetime({"expiresIn": 7200}) == 7200

    def test_accepts_string_value(self):
        assert _token_lifetime({"expiresIn": "7200"}) == 7200

    def test_snake_case_fallback(self):
        assert _token_lifetime({"expires_in": 1800}) == 1800

    def test_missing_defaults(self):
        assert _token_lifetime({}) == 3600

    def test_invalid_defaults(self):
        assert _token_lifetime({"expiresIn": "soon"}) == 3600

    def test_non_positive_defaults(self):
        assert _token_lifetime({"expiresIn": 0}) == 3600


class TestGetToken:
    def _client(self, data: dict) -> CowayAuthClient:
        client = CowayAuthClient("email@example.com", "password", session=_MockSession())
        client._post_endpoint = AsyncMock(return_value={"data": data})
        return client

    async def test_returns_lifetime_from_response(self):
        client = self._client({"accessToken": "acc", "refreshToken": "ref", "expiresIn": 7200})
        assert await client._get_token("code") == ("acc", "ref", 7200)

    async def test_default_lifetime_when_missing(self):
        client = self._client({"accessToken": "acc", "refreshToken": "ref"})
        assert await client._get_token("code") == ("acc", "ref", 3600)


class TestCowayAuthClient:
    async def test_refresh_token_error_falls_back_to_login(self):
        client = CowayAuthClient(
            "email@example.com",
            "password",
            session=_MockSession(),
        )
        client.refresh_token = "refresh-token"
        client._response = AsyncMock(return_value={"error": "expired"})
        client._do_login = AsyncMock()

        await client._refresh_token()

        client._do_login.assert_awaited_once()
