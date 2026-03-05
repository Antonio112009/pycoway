"""Tests for parser module."""

import json

import pytest

from cowayaio.exceptions import CowayError
from cowayaio.devices.parser import (
    build_filter_dict,
    build_purifier,
    extract_parsed_info,
    parse_purifier_html,
)


class TestParseHtml:
    def _wrap_html(self, json_data: dict) -> str:
        """Wrap JSON in a minimal HTML page with the expected script tag."""
        raw = json.dumps(json_data)
        return (
            "<html><body>"
            f"<script>var sensorInfo = {raw};</script>"
            "</body></html>"
        )

    def test_returns_first_dict_child(self, sample_purifier_json_children):
        html = self._wrap_html(sample_purifier_json_children)
        result = parse_purifier_html(html, "Test")
        assert result is not None
        assert "coreData" in result

    def test_returns_none_when_no_children(self):
        html = self._wrap_html({"other_key": "value"})
        result = parse_purifier_html(html, "Test")
        assert result is None

    def test_raises_on_invalid_html(self):
        with pytest.raises(CowayError, match="Failed to parse"):
            parse_purifier_html("<html><body></body></html>", "Test")

    def test_returns_none_for_non_dict_children(self):
        html = self._wrap_html({"children": ["string_child", 123]})
        result = parse_purifier_html(html, "Test")
        assert result is None


class TestExtractParsedInfo:
    def test_extracts_mcu_info(self, sample_purifier_json_children):
        child = sample_purifier_json_children["children"][0]
        parsed = extract_parsed_info(child)
        assert parsed["mcu_info"]["currentMcuVer"] == "2.0.1"

    def test_extracts_sensor_info(self, sample_purifier_json_children):
        child = sample_purifier_json_children["children"][0]
        parsed = extract_parsed_info(child)
        assert parsed["sensor_info"]["0001"] == 15

    def test_extracts_status_info(self, sample_purifier_json_children):
        child = sample_purifier_json_children["children"][0]
        parsed = extract_parsed_info(child)
        assert parsed["status_info"]["0001"] == 1

    def test_extracts_device_info(self, sample_purifier_json_children):
        child = sample_purifier_json_children["children"][0]
        parsed = extract_parsed_info(child)
        assert parsed["device_info"]["productName"] == "AIRMEGA 250S"

    def test_extracts_network_and_aq_grade(self, sample_purifier_json_children):
        child = sample_purifier_json_children["children"][0]
        parsed = extract_parsed_info(child)
        assert parsed["network_info"]["wifiConnected"] is True
        assert parsed["aq_grade"]["iaqGrade"] == 1

    def test_defaults_for_empty_input(self):
        parsed = extract_parsed_info({})
        assert parsed["device_info"] == {}
        assert parsed["mcu_info"] == {}
        assert parsed["sensor_info"] == {}
        assert parsed["status_info"] == {}
        assert parsed["timer_info"] is None


class TestBuildFilterDict:
    def test_pre_filter_keyed(self):
        filters = [{"supplyNm": "Pre-Filter", "filterRemain": 80}]
        result = build_filter_dict(filters)
        assert "pre-filter" in result
        assert result["pre-filter"]["filterRemain"] == 80

    def test_max2_filter_keyed(self):
        filters = [{"supplyNm": "MAX2 Filter", "filterRemain": 50}]
        result = build_filter_dict(filters)
        assert "max2" in result

    def test_both_filters(self):
        filters = [
            {"supplyNm": "Pre-Filter", "filterRemain": 80},
            {"supplyNm": "MAX2 Filter", "filterRemain": 50},
        ]
        result = build_filter_dict(filters)
        assert "pre-filter" in result
        assert "max2" in result

    def test_empty_list(self):
        assert build_filter_dict([]) == {}

    def test_odor_filter_is_keyed_without_overwriting_max2(self):
        filters = [
            {"supplyNm": "MAX2 Filter", "filterRemain": 50},
            {"supplyNm": "Deodorization Filter", "filterRemain": 40},
        ]
        result = build_filter_dict(filters)
        assert result["max2"]["filterRemain"] == 50
        assert result["odor-filter"]["filterRemain"] == 40


class TestBuildPurifier:
    def test_basic_build(self, sample_device, sample_parsed_info):
        purifier = build_purifier(sample_device, sample_parsed_info)

        assert purifier.device_attr.device_id == "ABC123"
        assert purifier.device_attr.model == "AIRMEGA 250S"
        assert purifier.device_attr.model_code == "AIRMEGA-250S"
        assert purifier.device_attr.name == "Living Room"
        assert purifier.device_attr.place_id == "place-001"

        assert purifier.is_on is True
        assert purifier.auto_mode is True
        assert purifier.fan_speed == 2
        assert purifier.light_on is True
        assert purifier.light_mode == 2
        assert purifier.mcu_version == "2.0.1"
        assert purifier.network_status is True

    def test_filter_values(self, sample_device, sample_parsed_info):
        purifier = build_purifier(sample_device, sample_parsed_info)
        assert purifier.pre_filter_pct == 80
        assert purifier.max2_pct == 65
        assert purifier.odor_filter_pct == 60  # 100 - 40
        assert purifier.pre_filter_change_frequency == 112

    def test_air_quality_values(self, sample_device, sample_parsed_info):
        purifier = build_purifier(sample_device, sample_parsed_info)
        assert purifier.particulate_matter_2_5 == 15
        assert purifier.particulate_matter_10 == 25
        assert purifier.carbon_dioxide == 450
        assert purifier.volatile_organic_compounds == 10
        assert purifier.air_quality_index == 50
        assert purifier.aq_grade == 1

    def test_no_filters(self, sample_device, sample_parsed_info):
        sample_parsed_info["filter_info"] = {}
        purifier = build_purifier(sample_device, sample_parsed_info)
        # Falls back to sensor_info keys
        assert purifier.pre_filter_pct == 80  # 100 - 20
        assert purifier.max2_pct == 70  # 100 - 30

    def test_mode_flags(self, sample_device, sample_parsed_info):
        # mode_value == 1 => auto_mode
        assert build_purifier(sample_device, sample_parsed_info).auto_mode is True

        sample_parsed_info["status_info"]["0002"] = 2
        assert build_purifier(sample_device, sample_parsed_info).night_mode is True

        sample_parsed_info["status_info"]["0002"] = 5
        assert build_purifier(sample_device, sample_parsed_info).rapid_mode is True

        sample_parsed_info["status_info"]["0002"] = 6
        p = build_purifier(sample_device, sample_parsed_info)
        assert p.eco_mode is True
        assert p.auto_eco_mode is True

    def test_no_aq_grade(self, sample_device, sample_parsed_info):
        sample_parsed_info["aq_grade"] = None
        purifier = build_purifier(sample_device, sample_parsed_info)
        assert purifier.aq_grade is None

    def test_odor_filter_prefers_supply_data(self, sample_device, sample_parsed_info):
        sample_parsed_info["filter_info"]["odor-filter"] = {"filterRemain": 35}
        purifier = build_purifier(sample_device, sample_parsed_info)
        assert purifier.odor_filter_pct == 35
