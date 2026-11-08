"""Server maintenance notices: parsing, caching, and staying best-effort."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pycoway.client import CowayClient
from pycoway.constants import Endpoint
from pycoway.exceptions import CowayError
from tests.fakes import DEFAULT_PLACE, FakeResponse, FakeSession
from tests.test_auth_flow import TestPollRacingControlCommand

NOTICES_URL = f"{Endpoint.BASE_URI}{Endpoint.NOTICES}"
EDT = ZoneInfo("America/New_York")


def _client(session: FakeSession) -> CowayClient:
    client = CowayClient("email@example.com", "password", session=session, timezone="UTC")
    client.access_token = "acc"
    client.refresh_token = "ref"
    client.token_expiration = datetime.now(UTC) + timedelta(hours=1)
    client.places = [DEFAULT_PLACE]
    return client


def _notice(seq: int, html: str) -> FakeResponse:
    return FakeResponse(json_data={"data": {"noticeSeq": seq, "content": html}})


class TestNoticeParsing:
    async def test_edt_window_is_parsed(self, fake_session):
        fake_session.add(
            "get", NOTICES_URL, FakeResponse(json_data={"data": {"content": [{"noticeSeq": 7}]}})
        )
        fake_session.add(
            "get",
            f"{NOTICES_URL}/7",
            _notice(
                7,
                "<p>Server maintenance</p><p>\xa0</p>"
                "<p>[EDT] 2026-11-10 01:00 ~ 2026-11-10 03:30</p>",
            ),
        )
        client = _client(fake_session)

        await client.async_server_maintenance_notice()

        info = client.server_maintenance
        assert info is not None
        assert info["sequence"] == 7
        assert info["start_date_time"] == datetime(2026, 11, 10, 1, 0, tzinfo=EDT)
        assert info["end_date_time"] == datetime(2026, 11, 10, 3, 30, tzinfo=EDT)
        assert info["description"] == (
            "Server maintenance\n[EDT] 2026-11-10 01:00 ~ 2026-11-10 03:30"
        )

    async def test_notice_without_window_keeps_description(self, fake_session):
        fake_session.add(
            "get", NOTICES_URL, FakeResponse(json_data={"data": {"content": [{"noticeSeq": 8}]}})
        )
        fake_session.add("get", f"{NOTICES_URL}/8", _notice(8, "<p>New app version</p>"))
        client = _client(fake_session)

        await client.async_server_maintenance_notice()

        assert client.server_maintenance == {
            "sequence": 8,
            "start_date_time": None,
            "end_date_time": None,
            "description": "New app version",
        }

    async def test_list_is_cached_for_an_hour(self, fake_session):
        fake_session.add("get", NOTICES_URL, FakeResponse(json_data={"data": {"content": []}}))
        client = _client(fake_session)

        await client.async_server_maintenance_notice()
        await client.async_server_maintenance_notice()

        assert len(fake_session.requests("get", NOTICES_URL)) == 1

    async def test_known_notice_is_not_fetched_again(self, fake_session):
        fake_session.add(
            "get", NOTICES_URL, FakeResponse(json_data={"data": {"content": [{"noticeSeq": 8}]}})
        )
        fake_session.add("get", f"{NOTICES_URL}/8", _notice(8, "<p>Hello</p>"))
        client = _client(fake_session)
        await client.async_server_maintenance_notice()

        client._notices_checked_at = None  # list cache expired
        await client.async_server_maintenance_notice()

        assert len(fake_session.requests("get", f"{NOTICES_URL}/8")) == 1

    @pytest.mark.parametrize(
        ("listing", "detail", "match"),
        [
            ({"data": {"content": [{"title": "x"}]}}, None, "without a sequence number"),
            ({"data": {"content": [{"noticeSeq": 9}]}}, {"data": {}}, "has no content"),
            ({"error": {"message": "nope"}}, None, "nope"),
        ],
    )
    async def test_malformed_notices_raise_coway_error(self, fake_session, listing, detail, match):
        fake_session.add("get", NOTICES_URL, FakeResponse(json_data=listing))
        if detail is not None:
            fake_session.add("get", f"{NOTICES_URL}/9", FakeResponse(json_data=detail))
        client = _client(fake_session)

        with pytest.raises(CowayError, match=match):
            await client.async_server_maintenance_notice()


class TestNoticeIsBestEffort:
    async def test_poll_succeeds_when_notices_fail(self, fake_session, caplog):
        TestPollRacingControlCommand()._add_poll_routes(fake_session)
        fake_session.add("get", NOTICES_URL, FakeResponse(json_data={"data": {"content": [{}]}}))
        client = _client(fake_session)

        with caplog.at_level(logging.WARNING, logger="pycoway"):
            data = await asyncio.wait_for(client.async_get_purifiers_data(), timeout=5)

        assert data.purifiers["S1"].is_on is True
        assert "Could not fetch the Coway maintenance notice" in caplog.text
