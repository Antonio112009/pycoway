"""Parsing logic for building CowayPurifier objects from raw API data."""

import contextlib
import json
import logging
from typing import Any

from bs4 import BeautifulSoup

from pycoway.constants import IAQ_FIELD_MAP, CommandCode, SensorCode, SensorKey
from pycoway.devices.models import CowayPurifier, DeviceAttributes, FilterInfo
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
    except (IndexError, AttributeError, KeyError, json.JSONDecodeError, ValueError) as exc:
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


def extract_html_supplements(purifier_info: dict[str, Any]) -> dict[str, Any]:
    """Extract MCU version and lux sensor from HTML-parsed purifier data.

    These two data points are only available from the legacy HTML page
    scrape and not from the IoT JSON API.
    """

    mcu_version: str | None = None
    lux: int | None = None

    for data in purifier_info.get("coreData", []):
        inner = data.get("data", {})
        if "currentMcuVer" in inner:
            mcu_version = inner["currentMcuVer"]
        if "sensorInfo" in inner:
            attrs = inner["sensorInfo"].get("attributes", {})
            raw_lux = attrs.get(SensorCode.LUX)
            if raw_lux is not None:
                with contextlib.suppress(ValueError, TypeError):
                    lux = int(raw_lux)

    return {"mcu_version": mcu_version, "lux": lux}


def build_filter_dict(filter_info: list[dict[str, Any]]) -> dict[str, Any]:
    """Organise raw filter list into a dict keyed by filter type."""

    result: dict[str, Any] = {}
    for dev_filter in filter_info:
        filter_name = str(dev_filter.get("supplyNm", "")).casefold()
        if filter_name == "pre-filter":
            result["pre-filter"] = dev_filter
        elif filter_name == "max2 filter" or filter_name == "max2":
            result["max2"] = dev_filter
        elif filter_name in ("deodor filter", "odor filter", "deodorization filter"):
            result["odor-filter"] = dev_filter
    return result


def _parse_supply_description(html_content: str) -> str | None:
    """Extract plain text from the supply HTML content snippet."""
    if not html_content:
        return None
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(strip=True)
    return text or None


def build_filter_info_list(filter_info: list[dict[str, Any]]) -> list[FilterInfo]:
    """Build a list of FilterInfo objects from raw supply data."""

    result: list[FilterInfo] = []
    for supply in filter_info:
        pollutants = [
            p.get("pollutionNm", "") for p in supply.get("pollutions", []) if p.get("pollutionNm")
        ]
        result.append(
            FilterInfo(
                name=supply.get("supplyNm"),
                filter_remain=supply.get("filterRemain"),
                filter_remain_status=supply.get("filterRemainStatus"),
                replace_cycle=supply.get("replaceCycle"),
                replace_cycle_unit=supply.get("replaceCycleUnit"),
                last_date=supply.get("lastDate") or None,
                next_date=supply.get("nextDate") or None,
                pollutants=pollutants,
                description=_parse_supply_description(supply.get("supplyContent", "")),
                pre_filter=supply.get("preFilterYn") == "Y",
                server_reset=supply.get("serverResetFilterYn") == "Y",
            )
        )
    return result


def _sensor_filter_pct(sensor_info: dict[str, Any], key: str) -> int | None:
    """Compute filter % remaining from sensor data, or None if unavailable."""

    if key in sensor_info:
        return 100 - sensor_info[key]
    return None


def build_purifier(
    device_attr: DeviceAttributes,
    parsed_info: dict[str, Any],
    raw_filters: list[dict[str, Any]] | None = None,
) -> CowayPurifier:
    """Construct a CowayPurifier dataclass from parsed API data."""

    device_info = parsed_info["device_info"]
    status = parsed_info["status_info"]
    sensor = parsed_info["sensor_info"]
    filters = parsed_info["filter_info"]

    # Enrich DeviceAttributes with fields from device_info if available.
    if device_info:
        device_attr.model = device_info.get("productName") or device_attr.model
        device_attr.code = device_info.get("modelCode") or device_attr.code
        device_attr.product_name = device_info.get("prodName") or device_attr.product_name

    network_status = parsed_info["network_info"].get("wifiConnected")
    if not network_status and network_status is not None:
        LOGGER.debug(f"{device_attr.name} Purifier is not connected to WiFi.")

    # Filter percentages
    if filters:
        if "pre-filter" in filters:
            pre_filter_pct = filters["pre-filter"].get("filterRemain")
            pre_filter_change_frequency = filters["pre-filter"].get("replaceCycle")
        else:
            pre_filter_pct = _sensor_filter_pct(sensor, SensorCode.PRE_FILTER_USAGE)
            pre_filter_change_frequency = None
        max2_pct = (
            filters["max2"].get("filterRemain")
            if "max2" in filters
            else _sensor_filter_pct(sensor, SensorCode.MAX2_FILTER_USAGE)
        )
    else:
        pre_filter_pct = _sensor_filter_pct(sensor, SensorCode.PRE_FILTER_USAGE)
        max2_pct = _sensor_filter_pct(sensor, SensorCode.MAX2_FILTER_USAGE)
        pre_filter_change_frequency = None

    odor_filter = (
        filters["odor-filter"].get("filterRemain")
        if "odor-filter" in filters
        else _sensor_filter_pct(sensor, SensorCode.ODOR_FILTER_USAGE)
    )

    # Air quality readings
    pm_2_5 = sensor.get(SensorCode.PM25, sensor.get(SensorKey.PM25))
    pm_10 = sensor.get(SensorCode.PM10, sensor.get(SensorKey.PM10))

    mode_value = status.get("0002")

    return CowayPurifier(
        device_attr=device_attr,
        mcu_version=parsed_info["mcu_info"].get("currentMcuVer"),
        network_status=network_status,
        is_on=status.get("0001") == 1,
        auto_mode=mode_value == 1,
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
        carbon_dioxide=sensor.get(SensorKey.CO2),
        volatile_organic_compounds=sensor.get(SensorKey.VOCS),
        air_quality_index=sensor.get(SensorKey.IAQ),
        lux_sensor=sensor.get(SensorCode.LUX),
        pre_filter_change_frequency=pre_filter_change_frequency,
        smart_mode_sensitivity=status.get("000A"),
        filters=build_filter_info_list(raw_filters) if raw_filters else None,
    )


def _safe_int(value: Any) -> int | None:
    """Convert a value to int if possible, otherwise return None."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def extract_iot_parsed_info(
    control_data: dict[str, Any],
    air_data: dict[str, Any],
    conn_data: dict[str, Any],
) -> dict[str, Any]:
    """Build the same parsed-info dict from IoT JSON API responses.

    ``control_data`` comes from the control-status endpoint (``data``
    contains ``controlStatus``, ``netStatus``, etc.),
    ``air_data`` from the air/home endpoint (``data`` contains ``IAQ``,
    ``prodStatus``, ``filterList``, etc.), and ``conn_data`` from the
    devices-conn endpoint.  The returned dict has the same shape as
    :func:`extract_parsed_info` so :func:`build_purifier` can consume
    it unchanged.
    """

    # --- Control status (hex-coded keys, string values → int) ----------
    raw_status = control_data.get("controlStatus", {})
    status_attrs: dict[str, Any] = {}
    for k, v in raw_status.items():
        converted = _safe_int(v)
        status_attrs[k] = converted if converted is not None else v

    # --- IAQ sensor readings → internal sensor keys --------------------
    iaq = air_data.get("IAQ", {})
    sensor_info: dict[str, Any] = {}
    for iaq_field, sensor_key in IAQ_FIELD_MAP.items():
        value = iaq.get(iaq_field)
        converted = _safe_int(value)
        if converted is not None:
            sensor_info[sensor_key] = converted

    # --- AQ grade from prodStatus.dustPollution -----------------------
    prod_status = air_data.get("prodStatus", {})
    dust_pollution = _safe_int(prod_status.get("dustPollution"))
    aq_grade: dict[str, Any] | None = (
        {"iaqGrade": dust_pollution} if dust_pollution is not None else {}
    )

    # --- Network status (available in control, air, and conn) ---------
    net_status = control_data.get("netStatus")
    if net_status is None:
        net_status = air_data.get("netStatus")
    if net_status is None and conn_data:
        net_status = conn_data.get("netStatus") == "online"
    network_info: dict[str, Any] = {}
    if net_status is not None:
        network_info = {"wifiConnected": bool(net_status)}

    # --- Filters from air/home filterList -----------------------------
    filter_info: dict[str, Any] = {}
    for f in air_data.get("filterList", []):
        name = (f.get("filterName") or "").casefold()
        pct = f.get("filterPer")
        cycle = _safe_int(f.get("changeCycle"))
        if "프리필터" in name or "pre" in name:
            entry: dict[str, Any] = {"filterRemain": pct}
            if cycle is not None:
                entry["replaceCycle"] = cycle
            filter_info["pre-filter"] = entry
        elif "max2" in name:
            filter_info["max2"] = {"filterRemain": pct}
        elif any(kw in name for kw in ("탈취", "odor", "deodor")):
            filter_info["odor-filter"] = {"filterRemain": pct}

    # --- Timer --------------------------------------------------------
    timer_value = _safe_int(raw_status.get("offTimer", raw_status.get(CommandCode.TIMER)))

    return {
        "device_info": {},
        "mcu_info": {},
        "network_info": network_info,
        "sensor_info": sensor_info,
        "status_info": status_attrs,
        "aq_grade": aq_grade,
        "filter_info": filter_info,
        "timer_info": timer_value,
    }
