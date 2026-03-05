"""Parsing logic for building CowayPurifier objects from raw API/HTML data."""

import json
import logging
from typing import Any

from bs4 import BeautifulSoup

from pycoway.devices.models import CowayPurifier, DeviceAttributes
from pycoway.exceptions import CowayError

LOGGER = logging.getLogger(__name__)


def parse_purifier_html(html: str, nick_name: str) -> dict[str, Any] | None:
    """Extract the purifier JSON data embedded in the HTML page.

    Returns the first dict child from the top-level 'children' key,
    or None if not found.
    """

    soup = BeautifulSoup(html, "html.parser")
    try:
        script_search = soup.select('script:-soup-contains("sensorInfo")')
        script_text = script_search[0].text
        start_index = script_text.find("{")
        end_index = script_text.rfind("}")
        extracted_string = script_text[start_index : end_index + 1].replace("\\", "")
        purifier_json = json.loads(extracted_string)
        LOGGER.debug(f"Parsed purifier JSON info: {json.dumps(purifier_json, indent=4)}")
    except Exception as exc:
        raise CowayError(f"Failed to parse purifier HTML page for info: {exc}") from exc

    if "children" not in purifier_json:
        LOGGER.debug(
            f"No children key found for purifier {nick_name}. Setting purifier info to None."
        )
        return None

    for data in purifier_json["children"]:
        if isinstance(data, dict):
            return data
    return None


def extract_parsed_info(purifier_info: dict[str, Any]) -> dict[str, Any]:
    """Pull structured sections out of the raw purifier info dict."""

    parsed: dict[str, Any] = {
        "device_info": {},
        "mcu_info": {},
        "network_info": {},
        "sensor_info": {},
        "status_info": {},
        "aq_grade": {},
        "filter_info": {},
        "timer_info": None,
    }

    for data in purifier_info.get("coreData", []):
        inner = data.get("data", {})
        if "currentMcuVer" in inner:
            parsed["mcu_info"] = inner
        if "sensorInfo" in inner:
            parsed["sensor_info"] = inner["sensorInfo"].get("attributes", {})

    if "deviceStatusData" in purifier_info:
        parsed["status_info"] = (
            purifier_info["deviceStatusData"]
            .get("data", {})
            .get("statusInfo", {})
            .get("attributes", {})
        )

    if "baseInfoForModelCodeData" in purifier_info:
        parsed["device_info"] = purifier_info["baseInfoForModelCodeData"].get("deviceInfo", {})

    if "deviceModule" in purifier_info:
        module_detail = (
            purifier_info["deviceModule"]
            .get("data", {})
            .get("content", {})
            .get("deviceModuleDetailInfo", {})
        )
        parsed["network_info"] = module_detail
        parsed["aq_grade"] = module_detail.get("airStatusInfo")

    return parsed


def build_filter_dict(filter_info: list[dict[str, Any]]) -> dict[str, Any]:
    """Organise raw filter list into a dict keyed by filter type."""

    result: dict[str, Any] = {}
    for dev_filter in filter_info:
        filter_name = str(dev_filter.get("supplyNm", "")).casefold()
        if filter_name == "pre-filter":
            result["pre-filter"] = dev_filter
        elif "max2" in filter_name:
            result["max2"] = dev_filter
        elif "deodor" in filter_name or "odor" in filter_name:
            result["odor-filter"] = dev_filter
    return result


def _sensor_filter_pct(sensor_info: dict[str, Any], key: str) -> int | None:
    """Compute filter % remaining from sensor data, or None if unavailable."""

    if key in sensor_info:
        return 100 - sensor_info[key]
    return None


def build_purifier(
    dev: dict[str, Any],
    parsed_info: dict[str, Any],
) -> CowayPurifier:
    """Construct a CowayPurifier dataclass from parsed API data."""

    device_info = parsed_info["device_info"]
    status = parsed_info["status_info"]
    sensor = parsed_info["sensor_info"]
    filters = parsed_info["filter_info"]

    device_attr = DeviceAttributes(
        device_id=dev.get("deviceSerial"),
        model=device_info.get("productName"),
        model_code=dev.get("productModel"),
        code=device_info.get("modelCode"),
        name=dev.get("dvcNick"),
        product_name=device_info.get("prodName"),
        place_id=dev.get("placeId"),
    )

    network_status = parsed_info["network_info"].get("wifiConnected")
    if not network_status and network_status is not None:
        LOGGER.debug(f"{device_attr.name} Purifier is not connected to WiFi.")

    # Filter percentages
    if filters:
        if "pre-filter" in filters:
            pre_filter_pct = filters["pre-filter"].get("filterRemain")
            pre_filter_change_frequency = filters["pre-filter"].get("replaceCycle")
        else:
            pre_filter_pct = _sensor_filter_pct(sensor, "0011")
            pre_filter_change_frequency = None
        max2_pct = (
            filters["max2"].get("filterRemain")
            if "max2" in filters
            else _sensor_filter_pct(sensor, "0012")
        )
    else:
        pre_filter_pct = _sensor_filter_pct(sensor, "0011")
        max2_pct = _sensor_filter_pct(sensor, "0012")
        pre_filter_change_frequency = None

    odor_filter = (
        filters["odor-filter"].get("filterRemain")
        if "odor-filter" in filters
        else _sensor_filter_pct(sensor, "0013")
    )

    # Air quality readings
    pm_2_5 = sensor.get("0001", sensor.get("PM25_IDX"))
    pm_10 = sensor.get("0002", sensor.get("PM10_IDX"))

    mode_value = status.get("0002")

    return CowayPurifier(
        device_attr=device_attr,
        mcu_version=parsed_info["mcu_info"].get("currentMcuVer"),
        network_status=network_status,
        is_on=status.get("0001") == 1,
        auto_mode=mode_value == 1,
        auto_eco_mode=mode_value == 6,
        eco_mode=mode_value == 6,
        night_mode=mode_value == 2,
        rapid_mode=mode_value == 5,
        fan_speed=status.get("0003"),
        light_on=status.get("0007") == 2,
        light_mode=status.get("0007"),
        button_lock=status.get("0024"),
        timer=parsed_info["timer_info"],
        timer_remaining=status.get("0008"),
        pre_filter_pct=pre_filter_pct,
        max2_pct=max2_pct,
        odor_filter_pct=odor_filter,
        aq_grade=parsed_info["aq_grade"].get("iaqGrade") if parsed_info["aq_grade"] else None,
        particulate_matter_2_5=pm_2_5,
        particulate_matter_10=pm_10,
        carbon_dioxide=sensor.get("CO2_IDX"),
        volatile_organic_compounds=sensor.get("VOCs_IDX"),
        air_quality_index=sensor.get("IAQ"),
        lux_sensor=sensor.get("0007"),
        pre_filter_change_frequency=pre_filter_change_frequency,
        smart_mode_sensitivity=status.get("000A"),
    )
