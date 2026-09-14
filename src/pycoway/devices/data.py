"""Data-fetching layer for Coway IoCare purifiers."""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pycoway.account.maintenance import CowayMaintenanceClient
from pycoway.constants import (
    CATEGORY_NAME,
    TIMEOUT,
    Endpoint,
    Header,
    SensorCode,
    TrCode,
)
from pycoway.devices.models import CowayPurifier, DeviceAttributes, PurifierData
from pycoway.devices.parser import (
    build_filter_dict,
    build_purifier,
    extract_html_supplements,
    extract_iot_parsed_info,
    parse_purifier_html,
)
from pycoway.exceptions import (
    AuthError,
    CowayError,
    NoPurifiers,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aiohttp import ClientSession

LOGGER = logging.getLogger(__name__)

IOT_DEVICES_CACHE_INTERVAL = 3600  # seconds — discovery fields rarely change


def _unwrap_results[T](results: Sequence[T | BaseException], labels: Sequence[str]) -> list[T]:
    """Return the successful results of ``gather(..., return_exceptions=True)``.

    The first failure is raised. Every other failure is logged first, so a
    second device (or place) failing for a different reason does not vanish
    silently behind the exception that propagates.
    """

    values: list[T] = []
    failures: list[tuple[str, BaseException]] = []
    for label, result in zip(labels, results, strict=True):
        if isinstance(result, BaseException):
            failures.append((label, result))
        else:
            values.append(result)

    if failures:
        first_label, first_exc = failures[0]
        for label, exc in failures[1:]:
            LOGGER.warning(
                "%s also failed; only the error for %s is raised: %r", label, first_label, exc
            )
        raise first_exc
    return values


class CowayDataClient(CowayMaintenanceClient):
    """Fetches purifier inventories, filter status, and timer data."""

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
        self._iot_devices_by_barcode: dict[str, dict[str, Any]] | None = None
        self._iot_devices_cached_at: datetime | None = None

    async def _fetch_place_devices(
        self, place: dict[str, Any], headers: dict[str, str], params: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Fetch the purifiers registered at a single place."""

        url = f"{Endpoint.BASE_URI}{Endpoint.PLACES}/{place['placeId']}/devices"
        LOGGER.debug(f"Fetching devices for {self.username}. URL: {url}")

        response = await self._get_endpoint(url, headers, params)
        if "error" in response:
            raise CowayError(
                f"Failed to get devices for Place ID: {place.get('placeId')} "
                f"Response: {response['error']}"
            )

        devices = response.get("data", {}).get("content")
        if not devices:
            LOGGER.debug(
                f"No devices at Place ID: {place.get('placeId')}, "
                f"Place Name: {place.get('placeName')}"
            )
            return []
        return [d for d in devices if d.get("categoryName") == CATEGORY_NAME]

    async def async_get_purifiers(self) -> list[dict[str, Any]]:
        """Get all purifiers linked to Coway account."""

        if not self.places:
            LOGGER.debug(f"No places loaded. Doing initial login for {self.username}")
            await self.login()

        params = {"pageIndex": "0", "pageSize": "100"}
        headers = await self._create_endpoint_header()

        places = []
        for place in self.places:
            LOGGER.debug(
                f"Checking place for {self.username}. "
                f"Place ID: {place.get('placeId')}, "
                f"Place Name: {place.get('placeName')}, "
                f"Device Count: {place.get('deviceCnt')}"
            )
            if place.get("deviceCnt"):
                places.append(place)

        results = await asyncio.gather(
            *(self._fetch_place_devices(place, headers, params) for place in places),
            return_exceptions=True,
        )
        if any(isinstance(r, AuthError) for r in results):
            LOGGER.debug("Access and refresh tokens are invalid. Fetching new tokens.")
            await self.login()
            headers = await self._create_endpoint_header()
            results = await asyncio.gather(
                *(self._fetch_place_devices(place, headers, params) for place in places),
                return_exceptions=True,
            )

        labels = [f"place {place.get('placeId')}" for place in places]
        purifiers: list[dict[str, Any]] = []
        for devices in _unwrap_results(results, labels):
            purifiers.extend(devices)
        return purifiers

    async def async_get_purifiers_data(self) -> PurifierData:
        """Return dataclass with all Purifier Devices."""

        LOGGER.debug(f"Getting purifiers data for {self.username}")
        purifiers = await self.async_get_purifiers()
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug(
                "Purifiers found for %s: %s", self.username, json.dumps(purifiers, indent=4)
            )
        if not purifiers:
            raise NoPurifiers(
                f"No purifiers found for any IoCare+ places associated with {self.username}."
            )

        # Fetch IoT device list for fields the legacy discovery doesn't return.
        iot_by_barcode = await self._get_iot_devices_by_barcode()
        for dev in purifiers:
            serial = dev.get("deviceSerial") or dev.get("barcode", "")
            iot_dev = iot_by_barcode.get(serial, {})
            for key in (
                "dvcBrandCd",
                "dvcTypeCd",
                "ordNo",
                "sellTypeCd",
                "admdongCd",
                "stationCd",
                "selfManageYn",
                "comType",
                "prodName",
                "prodNameFull",
                "wifiType",
            ):
                if (key not in dev or dev[key] is None) and key in iot_dev:
                    dev[key] = iot_dev[key]

        await self.async_server_maintenance_notice()

        # All per-device fetches are independent, so build every purifier
        # concurrently. Token checks are serialised by the auth lock, so a
        # refresh that becomes due mid-batch happens exactly once.
        results = await asyncio.gather(
            *(self._build_purifier_from_device(dev) for dev in purifiers),
            return_exceptions=True,
        )
        labels = [
            f"purifier {dev.get('dvcNick') or dev.get('deviceSerial') or dev.get('barcode')}"
            for dev in purifiers
        ]

        device_data: dict[str, CowayPurifier] = {}
        for purifier in _unwrap_results(results, labels):
            device_data[purifier.device_attr.device_id] = purifier

        all_purifiers = PurifierData(purifiers=device_data)
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug(
                "Final PurifierData for %s: %s",
                self.username,
                json.dumps(asdict(all_purifiers), indent=4),
            )
        return all_purifiers

    async def _build_purifier_from_device(self, dev: dict[str, Any]) -> CowayPurifier:
        """Fetch all data sources for one device concurrently and build it."""

        nick = dev.get("dvcNick")
        LOGGER.debug(f"Building CowayPurifier for {nick}")

        # Build a lightweight DeviceAttributes for the IoT API calls.
        attr = self._build_device_attr(dev)
        model_code = dev.get("modelCode") or dev.get("prodType", "")
        place_id = str(dev.get("placeId", ""))
        serial = dev.get("deviceSerial") or dev.get("barcode", "")

        # IoT JSON API (status + air quality), HTML scrape (MCU/lux), and
        # legacy filter data are independent — fetch them in parallel.
        control_data, air_data, supplements, filter_info = await asyncio.gather(
            self.async_get_iot_device_control(attr),
            self.async_get_iot_air_home(attr),
            self._fetch_html_supplements(nick, serial, model_code, place_id),
            self.async_fetch_filter_status(place_id, serial, nick),
        )

        parsed_info = extract_iot_parsed_info(control_data, air_data, {})
        if supplements:
            if supplements["mcu_version"]:
                parsed_info["mcu_info"] = {"currentMcuVer": supplements["mcu_version"]}
            if supplements["lux"] is not None:
                parsed_info["sensor_info"][SensorCode.LUX] = supplements["lux"]

        parsed_info["filter_info"] = build_filter_dict(filter_info)
        LOGGER.debug(f"{nick} filter dict: {parsed_info['filter_info']}")

        purifier = build_purifier(attr, parsed_info, raw_filters=filter_info)
        LOGGER.debug(f"Finished CowayPurifier for {nick}")
        return purifier

    async def _fetch_html_supplements(
        self, nick: str | None, serial: str, model_code: str, place_id: str
    ) -> dict[str, Any] | None:
        """Fetch MCU version + lux from the HTML page; None on failure.

        These two data points are supplemental, so a failed scrape must
        not fail the whole update. Transport failures surface as
        ``CowayConnectionError``, which is a ``CowayError``.
        """

        try:
            LOGGER.debug(f"Fetching HTML page for {nick}")
            html = await self._get_purifier_html(nick, serial, model_code, place_id)
            purifier_info = parse_purifier_html(html, nick)
        except CowayError:
            LOGGER.exception(f"HTML supplement fetch failed for {nick}, skipping MCU/lux")
            return None
        if purifier_info is None:
            return None
        return extract_html_supplements(purifier_info)

    async def async_fetch_filter_status(
        self, place_id: str, serial: str, name: str
    ) -> list[dict[str, Any]]:
        """Fetch Pre-filter and MAX2 filter states."""

        await self._check_token()

        url = f"{Endpoint.SECONDARY_BASE}{Endpoint.PLACES}/{place_id}/devices/{serial}/supplies"
        headers = {
            "region": "NUS",
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {self.access_token}",
            "accept-language": Header.COWAY_LANGUAGE,
            "user-agent": Header.USER_AGENT,
        }
        params = {
            "membershipYn": "N",
            "membershipType": "",
            "langCd": Header.ACCEPT_LANG,
        }

        response = await self._get_endpoint(url, headers, params)
        if "error" in response:
            raise CowayError(
                f"Failed to get filter status for purifier {name}: {response['error']}"
            )
        return response.get("data", {}).get("suppliesList", [])

    async def _get_iot_devices_by_barcode(self) -> dict[str, dict[str, Any]]:
        """Return the IoT device list keyed by barcode, cached for an hour.

        The discovery fields it supplies (brand/type codes, order number)
        are effectively static, so refetching them on every poll is waste.
        An empty result is not cached, so transient failures retry on the
        next poll.
        """

        now = datetime.now()
        if (
            self._iot_devices_by_barcode is not None
            and self._iot_devices_cached_at is not None
            and (now - self._iot_devices_cached_at).total_seconds() < IOT_DEVICES_CACHE_INTERVAL
        ):
            LOGGER.debug("IoT user-devices cache is fresh. Skipping fetch.")
            return self._iot_devices_by_barcode

        iot_devices = await self.async_get_iot_user_devices()
        by_barcode = {d["barcode"]: d for d in iot_devices if "barcode" in d}
        if by_barcode:
            self._iot_devices_by_barcode = by_barcode
            self._iot_devices_cached_at = now
        return by_barcode

    async def async_get_iot_user_devices(self) -> list[dict[str, Any]]:
        """Fetch the IoT device list which contains ordNo, dvcBrandCd, etc."""

        await self._check_token()

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_USER_DEVICES}"
        params = {"pageIndex": "0", "pageSize": "100"}
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.USER_DEVICES)
        if "error" in response:
            LOGGER.debug(f"IoT user-devices failed: {response['error']}")
            return []
        return response.get("data", {}).get("deviceInfos", [])

    # ------------------------------------------------------------------
    # IoT JSON API methods
    # ------------------------------------------------------------------

    @staticmethod
    def _build_device_attr(dev: dict[str, Any]) -> DeviceAttributes:
        """Build a DeviceAttributes from a raw device dict for IoT API calls."""
        return DeviceAttributes(
            device_id=dev.get("deviceSerial") or dev.get("barcode"),
            model=None,
            model_code=dev.get("productModel") or dev.get("dvcModel"),
            code=dev.get("prodType"),
            name=dev.get("dvcNick"),
            product_name=dev.get("prodName"),
            place_id=dev.get("placeId"),
            dvc_brand_cd=dev.get("dvcBrandCd"),
            dvc_type_cd=dev.get("dvcTypeCd"),
            prod_name_full=dev.get("prodNameFull"),
            order_no=dev.get("ordNo"),
            sell_type_cd=dev.get("sellTypeCd"),
            admdong_cd=dev.get("admdongCd"),
            station_cd=dev.get("stationCd"),
            self_manage_yn=dev.get("selfManageYn"),
            mqtt_device=dev.get("comType") == "WIFI" or dev.get("wifiType") is not None,
        )

    @staticmethod
    def _iot_device_params(attr: DeviceAttributes) -> dict[str, str]:
        """Build the query-string params the IoT API endpoints require."""
        return {
            "devId": attr.device_id or "",
            "barcode": attr.device_id or "",
            "mqttDevice": str(attr.mqtt_device).lower(),
            "dvcBrandCd": attr.dvc_brand_cd or "",
            "dvcTypeCd": attr.dvc_type_cd or "",
            "deviceType": attr.dvc_type_cd or "",
            "prodName": attr.product_name or "",
            "orderNo": attr.order_no or "",
            "membershipYn": "N",
            "selfYn": attr.self_manage_yn or "N",
            "sellTypeCd": attr.sell_type_cd or "",
            "admdongCd": attr.admdong_cd or "",
            "stationCd": attr.station_cd or "",
        }

    async def async_get_iot_device_control(self, attr: DeviceAttributes) -> dict[str, Any]:
        """Fetch device control/status data via the IoT JSON API."""

        await self._check_token()

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONTROL}/{attr.device_id}/control"
        params = self._iot_device_params(attr)
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.DEVICE_CONTROL)
        if "error" in response:
            raise CowayError(f"IoT control-status failed for {attr.name}: {response['error']}")
        return response.get("data", {})

    async def async_get_iot_air_home(self, attr: DeviceAttributes) -> dict[str, Any]:
        """Fetch air-quality home data via the IoT JSON API."""

        await self._check_token()

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_AIR_HOME}/{attr.device_id}/home"
        params = self._iot_device_params(attr)
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.AIR_HOME)
        if "error" in response:
            raise CowayError(f"IoT air home failed for {attr.name}: {response['error']}")
        return response.get("data", {})

    async def async_get_iot_device_conn(self, attr: DeviceAttributes) -> dict[str, Any]:
        """Fetch device connection status via the IoT JSON API."""

        await self._check_token()

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONN}"
        params = self._iot_device_params(attr)
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.DEVICE_CONN)
        if "error" in response:
            raise CowayError(f"IoT device connection failed for {attr.name}: {response['error']}")
        return response.get("data", {})
