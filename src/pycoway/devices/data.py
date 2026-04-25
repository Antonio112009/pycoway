"""Data-fetching layer for Coway IoCare purifiers."""

import json
import logging
from typing import Any

from aiohttp import ClientError

from pycoway.account.maintenance import CowayMaintenanceClient
from pycoway.constants import (
    CATEGORY_NAME,
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

LOGGER = logging.getLogger(__name__)


class CowayDataClient(CowayMaintenanceClient):
    """Fetches purifier inventories, filter status, and timer data."""

    async def async_get_purifiers(self) -> list[dict[str, Any]]:
        """Get all purifiers linked to Coway account."""

        if not self.places:
            LOGGER.debug(f"No places loaded. Doing initial login for {self.username}")
            await self.login()

        params = {"pageIndex": "0", "pageSize": "100"}
        headers = await self._create_endpoint_header()
        purifiers: list[dict[str, Any]] = []

        for place in self.places:
            LOGGER.debug(
                f"Checking place for {self.username}. "
                f"Place ID: {place.get('placeId')}, "
                f"Place Name: {place.get('placeName')}, "
                f"Device Count: {place.get('deviceCnt')}"
            )
            if place["deviceCnt"] == 0:
                continue

            url = f"{Endpoint.BASE_URI}{Endpoint.PLACES}/{place['placeId']}/devices"
            LOGGER.debug(f"Fetching devices for {self.username}. URL: {url}")

            try:
                response = await self._get_endpoint(url, headers, params)
            except AuthError:
                LOGGER.debug("Access and refresh tokens are invalid. Fetching new tokens.")
                await self.login()
                headers = await self._create_endpoint_header()
                response = await self._get_endpoint(url, headers, params)

            if "error" in response:
                raise CowayError(
                    f"Failed to get devices for Place ID: {place.get('placeId')} "
                    f"Response: {response['error']}"
                )

            devices = response.get("data", {}).get("content")
            if devices:
                purifiers.extend(d for d in devices if d["categoryName"] == CATEGORY_NAME)
            else:
                LOGGER.debug(
                    f"No devices at Place ID: {place.get('placeId')}, "
                    f"Place Name: {place.get('placeName')}"
                )

        return purifiers

    async def async_get_purifiers_data(self) -> PurifierData:
        """Return dataclass with all Purifier Devices."""

        LOGGER.debug(f"Getting purifiers data for {self.username}")
        if not self.places:
            LOGGER.debug(f"No places loaded. Doing initial login for {self.username}")
            await self.login()

        purifiers = await self.async_get_purifiers()
        LOGGER.debug(f"Purifiers found for {self.username}: {json.dumps(purifiers, indent=4)}")
        if not purifiers:
            raise NoPurifiers(
                f"No purifiers found for any IoCare+ places associated with {self.username}."
            )

        # Fetch IoT device list for fields the legacy discovery doesn't return.
        iot_devices = await self.async_get_iot_user_devices()
        iot_by_barcode: dict[str, dict[str, Any]] = {
            d["barcode"]: d for d in iot_devices if "barcode" in d
        }
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

        # Only check the token once for the entire batch.
        self.check_token = False
        LOGGER.debug("self.check_token set to False for batch processing.")

        try:
            await self.async_server_maintenance_notice()

            device_data: dict[str, CowayPurifier] = {}
            for dev in purifiers:
                nick = dev.get("dvcNick")
                LOGGER.debug(f"Building CowayPurifier for {nick}")

                # Build a lightweight DeviceAttributes for the IoT API calls.
                attr = self._build_device_attr(dev)

                # IoT JSON API: device status + timer, air quality + sensors.
                LOGGER.debug(f"Fetching IoT control data for {nick}")
                control_data = await self.async_get_iot_device_control(attr)

                LOGGER.debug(f"Fetching IoT air home data for {nick}")
                air_data = await self.async_get_iot_air_home(attr)

                parsed_info = extract_iot_parsed_info(control_data, air_data, {})

                # HTML scrape for MCU version + lux sensor (not in IoT API).
                model_code = dev.get("modelCode") or dev.get("prodType", "")
                place_id = str(dev.get("placeId", ""))
                serial = dev.get("deviceSerial") or dev.get("barcode", "")
                try:
                    LOGGER.debug(f"Fetching HTML page for {nick}")
                    html = await self._get_purifier_html(nick, serial, model_code, place_id)
                    purifier_info = parse_purifier_html(html, nick)
                    if purifier_info:
                        supplements = extract_html_supplements(purifier_info)
                        if supplements["mcu_version"]:
                            parsed_info["mcu_info"] = {"currentMcuVer": supplements["mcu_version"]}
                        if supplements["lux"] is not None:
                            parsed_info["sensor_info"][SensorCode.LUX] = supplements["lux"]
                except (ClientError, TimeoutError, CowayError):
                    LOGGER.exception(f"HTML supplement fetch failed for {nick}, skipping MCU/lux")

                # Rich filter data (dates, pollutants, descriptions) from legacy API.
                LOGGER.debug(f"Fetching filter info for {nick}")
                filter_info = await self.async_fetch_filter_status(
                    dev["placeId"], dev["deviceSerial"], nick
                )
                parsed_info["filter_info"] = build_filter_dict(filter_info)
                LOGGER.debug(f"{nick} filter dict: {parsed_info['filter_info']}")

                purifier = build_purifier(attr, parsed_info, raw_filters=filter_info)
                device_data[purifier.device_attr.device_id] = purifier
                LOGGER.debug(f"Finished CowayPurifier for {nick}")
        finally:
            self.check_token = True
            LOGGER.debug("self.check_token set back to True")

        all_purifiers = PurifierData(purifiers=device_data)
        LOGGER.debug(
            f"Final PurifierData for {self.username}: "
            f"{json.dumps(all_purifiers, default=vars, indent=4)}"
        )
        return all_purifiers

    async def async_fetch_filter_status(
        self, place_id: str, serial: str, name: str
    ) -> list[dict[str, Any]]:
        """Fetch Pre-filter and MAX2 filter states."""

        if self.check_token:
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

    async def async_get_iot_user_devices(self) -> list[dict[str, Any]]:
        """Fetch the IoT device list which contains ordNo, dvcBrandCd, etc."""

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

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONTROL}/{attr.device_id}/control"
        params = self._iot_device_params(attr)
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.DEVICE_CONTROL)
        if "error" in response:
            raise CowayError(f"IoT control-status failed for {attr.name}: {response['error']}")
        return response.get("data", {})

    async def async_get_iot_air_home(self, attr: DeviceAttributes) -> dict[str, Any]:
        """Fetch air-quality home data via the IoT JSON API."""

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_AIR_HOME}/{attr.device_id}/home"
        params = self._iot_device_params(attr)
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.AIR_HOME)
        if "error" in response:
            raise CowayError(f"IoT air home failed for {attr.name}: {response['error']}")
        return response.get("data", {})

    async def async_get_iot_device_conn(self, attr: DeviceAttributes) -> dict[str, Any]:
        """Fetch device connection status via the IoT JSON API."""

        url = f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONN}"
        params = self._iot_device_params(attr)
        response = await self._get_iot_endpoint(url, params, trcode=TrCode.DEVICE_CONN)
        if "error" in response:
            raise CowayError(f"IoT device connection failed for {attr.name}: {response['error']}")
        return response.get("data", {})
