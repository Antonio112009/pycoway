"""Tests for public client behavior and auth fallbacks."""

from unittest.mock import AsyncMock

from pycoway.account.auth import CowayAuthClient
from pycoway.client import CowayClient


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


class TestCowayAuthClient:
    async def test_refresh_token_error_falls_back_to_login(self):
        client = CowayAuthClient(
            "email@example.com",
            "password",
            session=_MockSession(),
        )
        client.refresh_token = "refresh-token"
        client._response = AsyncMock(return_value={"error": "expired"})
        client.login = AsyncMock()

        await client._refresh_token()

        client.login.assert_awaited_once()
