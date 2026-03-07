"""Data classes for Coway IoCare Purifiers."""

from dataclasses import dataclass, field


@dataclass
class DeviceAttributes:
    """Device identification attributes for a Coway purifier."""

    device_id: str | None
    model: str | None
    model_code: str | None
    code: str | None
    name: str | None
    product_name: str | None
    place_id: str | None

    # Extended fields from the HB (homebridge-style) API discovery response.
    # All default to None for backward compatibility with the legacy API path.
    dvc_brand_cd: str | None = None
    dvc_type_cd: str | None = None
    prod_name: str | None = None
    prod_name_full: str | None = None
    order_no: str | None = None
    sell_type_cd: str | None = None
    admdong_cd: str | None = None
    station_cd: str | None = None
    self_manage_yn: str | None = None
    mqtt_device: bool = field(default=False)


@dataclass
class FilterInfo:
    """Detailed information about a single purifier filter/supply."""

    name: str | None
    filter_remain: int | None
    filter_remain_status: str | None
    replace_cycle: int | None
    replace_cycle_unit: str | None
    last_date: str | None
    next_date: str | None
    pollutants: list[str]
    description: str | None
    pre_filter: bool
    server_reset: bool


@dataclass
class PurifierData:
    """Dataclass for Purifier Data"""

    purifiers: dict[str, "CowayPurifier"]


@dataclass
class CowayPurifier:
    """Dataclass for Coway IoCare Purifier"""

    device_attr: DeviceAttributes
    mcu_version: str | None
    network_status: bool | None
    is_on: bool | None
    auto_mode: bool | None
    auto_eco_mode: bool | None
    eco_mode: bool | None
    night_mode: bool | None
    rapid_mode: bool | None
    fan_speed: int | None
    light_on: bool | None
    light_mode: int | None
    button_lock: int | None
    timer: str | None
    timer_remaining: int | None
    pre_filter_pct: int | None
    max2_pct: int | None
    odor_filter_pct: int | None
    aq_grade: int | None
    particulate_matter_2_5: int | None
    particulate_matter_10: int | None
    carbon_dioxide: int | None
    volatile_organic_compounds: int | None
    air_quality_index: int | None
    lux_sensor: int | None
    pre_filter_change_frequency: int | None
    smart_mode_sensitivity: int | None
    filters: list[FilterInfo] | None
