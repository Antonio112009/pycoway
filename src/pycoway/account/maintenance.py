"""Server maintenance notice handling for Coway IoCare API."""

import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientSession
from bs4 import BeautifulSoup

from pycoway.account.auth import CowayAuthClient
from pycoway.constants import (
    TIMEOUT,
    Endpoint,
    Header,
    Parameter,
)
from pycoway.exceptions import CowayError

LOGGER = logging.getLogger(__name__)

NOTICES_CHECK_INTERVAL = 3600  # seconds — re-check notice list at most once per hour


class CowayMaintenanceClient(CowayAuthClient):
    """Fetches and parses Coway server maintenance notices."""

    def __init__(
        self,
        username: str,
        password: str,
        session: ClientSession | None = None,
        timeout: int = TIMEOUT,
        skip_password_change: bool = False,
    ) -> None:
        super().__init__(
            username=username,
            password=password,
            session=session,
            timeout=timeout,
            skip_password_change=skip_password_change,
        )
        self.server_maintenance: dict[str, Any] | None = None
        self._notices_checked_at: datetime | None = None

    async def async_server_maintenance_notice(self) -> None:
        """Fetch the latest Coway server maintenance notice."""

        if self.check_token:
            await self._check_token()

        now = datetime.now()

        # Skip the full list call if we checked recently and have a cached result.
        if (
            self.server_maintenance is not None
            and self._notices_checked_at is not None
            and (now - self._notices_checked_at).total_seconds() < NOTICES_CHECK_INTERVAL
        ):
            LOGGER.debug("Maintenance notice cache is fresh. Skipping.")
            return

        url = f"{Endpoint.BASE_URI}{Endpoint.NOTICES}"
        headers = {
            "accept": "*/*",
            "langCd": Header.ACCEPT_LANG,
            "ostype": Header.SOURCE_PATH,
            "appVersion": Parameter.APP_VERSION,
            "region": "NUS",
            "user-agent": Header.USER_AGENT,
            "authorization": f"Bearer {self.access_token}",
        }
        params = {
            "content": "",
            "langCd": Header.ACCEPT_LANG,
            "pageIndex": "1",
            "pageSize": "20",
            "title": "",
            "topPinnedYn": "",
        }

        LOGGER.debug(f"Fetching maintenance notices from {url}")
        list_response = await self._get_endpoint(url, headers, params)

        if "error" in list_response:
            raise CowayError(f"Failed to get maintenance notices: {list_response['error']}")

        # Mark the list as checked so we don't hit the server again until TTL expires.
        self._notices_checked_at = now

        notices = list_response.get("data", {}).get("content")
        if not notices:
            return

        notice_seq = notices[0]["noticeSeq"]
        LOGGER.debug(f"Latest notice sequence is {notice_seq}")

        # Skip if we already have this notice cached.
        if self.server_maintenance and notice_seq == self.server_maintenance.get("sequence"):
            LOGGER.debug("Maintenance info already cached. Skipping.")
            return

        await self._fetch_and_parse_notice(notice_seq)

    async def _fetch_and_parse_notice(self, notice_seq: int) -> None:
        """Fetch a single notice by sequence and parse maintenance dates."""

        url = f"{Endpoint.BASE_URI}{Endpoint.NOTICES}/{notice_seq}"
        headers = {
            "region": "NUS",
            "accept": "application/json, text/plain, */*",
            "user-agent": Header.USER_AGENT,
            "authorization": f"Bearer {self.access_token}",
        }
        params = {"langCd": Header.ACCEPT_LANG}

        LOGGER.debug(f"Fetching notice detail. URL: {url}")
        latest_notice = await self._get_endpoint(url, headers, params)
        if "error" in latest_notice:
            raise CowayError(f"Failed to get latest maintenance notice: {latest_notice['error']}")

        soup = BeautifulSoup(latest_notice["data"]["content"], "html.parser")
        notice_lines: list[str] = []
        search_result: tuple[str, ...] | None = None

        for p in soup.find_all("p"):
            if p.text == "\xa0":
                continue
            notice_lines.append(p.text)
            lower_text = p.text.lower()
            if "[edt]" in lower_text:
                pattern = (
                    r"\[edt\].*(\d{4}-\d{2}-\d{2}).*(\d{2}:\d{2})"
                    r".*(\d{4}-\d{2}-\d{2}).*(\d{2}:\d{2})"
                )
                match = re.search(pattern, lower_text)
                if match:
                    search_result = match.groups()

        notice_info = "\n".join(notice_lines)
        LOGGER.debug(f"Notice info: {notice_info}")

        if search_result and len(search_result) == 4:
            fmt = "%Y-%m-%d %H:%M"
            edt_tz = ZoneInfo("America/New_York")
            self.server_maintenance = {
                "sequence": latest_notice["data"]["noticeSeq"],
                "start_date_time": datetime.strptime(
                    f"{search_result[0]} {search_result[1]}", fmt
                ).replace(tzinfo=edt_tz),
                "end_date_time": datetime.strptime(
                    f"{search_result[2]} {search_result[3]}", fmt
                ).replace(tzinfo=edt_tz),
                "description": notice_info,
            }
        else:
            self.server_maintenance = {
                "sequence": latest_notice["data"]["noticeSeq"],
                "start_date_time": None,
                "end_date_time": None,
                "description": notice_info,
            }

        LOGGER.debug(f"server_maintenance set to: {self.server_maintenance}")
