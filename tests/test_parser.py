"""Tests for parser module."""

from pycoway.devices.parser import (
    build_filter_dict,
    build_filter_info_list,
    build_purifier,
)


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


class TestBuildFilterInfoList:
    def test_builds_from_raw_supplies(self):
        raw = [
            {
                "supplyNm": "Pre-Filter",
                "filterRemain": 0,
                "filterRemainStatus": "INITIAL",
                "replaceCycle": 2,
                "replaceCycleUnit": "W",
                "lastDate": "",
                "nextDate": "",
                "preFilterYn": "Y",
                "serverResetFilterYn": "Y",
                "supplyContent": "<div>Removes dust</div>",
                "pollutions": [
                    {"pollutionNm": "Pollen"},
                    {"pollutionNm": "Large dust"},
                ],
            },
            {
                "supplyNm": "Max2 Filter",
                "filterRemain": 43,
                "filterRemainStatus": "AVAILABLE",
                "replaceCycle": 12,
                "replaceCycleUnit": "M",
                "lastDate": "",
                "nextDate": "",
                "preFilterYn": "N",
                "serverResetFilterYn": "N",
                "supplyContent": "",
                "pollutions": [{"pollutionNm": "VOCs"}],
            },
        ]
        result = build_filter_info_list(raw)
        assert len(result) == 2

        pre = result[0]
        assert pre.name == "Pre-Filter"
        assert pre.filter_remain == 0
        assert pre.filter_remain_status == "INITIAL"
        assert pre.replace_cycle == 2
        assert pre.replace_cycle_unit == "W"
        assert pre.last_date is None  # empty string → None
        assert pre.pre_filter is True
        assert pre.server_reset is True
        assert pre.description == "Removes dust"
        assert pre.pollutants == ["Pollen", "Large dust"]

        m2 = result[1]
        assert m2.name == "Max2 Filter"
        assert m2.filter_remain == 43
        assert m2.replace_cycle == 12
        assert m2.replace_cycle_unit == "M"
        assert m2.pre_filter is False
        assert m2.server_reset is False
        assert m2.pollutants == ["VOCs"]

    def test_empty_list(self):
        assert build_filter_info_list([]) == []


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

    def test_iot_discovery_fields_populated(self):
        """When device dict comes from IoT API user-devices, extended attrs are populated."""
        iot_device = {
            "barcode": "15902EUZ2282500520",
            "dvcModel": "AP-2015E(GRAPHITE_US)",
            "dvcNick": "HH AIR PURIFIER",
            "prodType": "02EUZ",
            "prodName": "AIRMEGA",
            "prodNameFull": "AIRMEGA 300s/400s",
            "dvcBrandCd": "MG",
            "dvcTypeCd": "004",
            "ordNo": "ORD1WBGmBa7P",
            "sellTypeCd": "1",
            "admdongCd": "GB",
            "stationCd": "GB",
            "selfManageYn": "N",
            "comType": "WIFI",
            "wifiType": "M",
        }
        empty_parsed = {
            "mcu_info": {},
            "sensor_info": {},
            "status_info": {},
            "device_info": {},
            "network_info": {},
            "aq_grade": {},
            "filter_info": {},
            "timer_info": {},
        }
        purifier = build_purifier(iot_device, empty_parsed)
        attr = purifier.device_attr

        assert attr.device_id == "15902EUZ2282500520"
        assert attr.model_code == "AP-2015E(GRAPHITE_US)"
        assert attr.code == "02EUZ"
        assert attr.prod_name == "AIRMEGA"
        assert attr.dvc_brand_cd == "MG"
        assert attr.dvc_type_cd == "004"
        assert attr.prod_name_full == "AIRMEGA 300s/400s"
        assert attr.order_no == "ORD1WBGmBa7P"
        assert attr.sell_type_cd == "1"
        assert attr.admdong_cd == "GB"
        assert attr.station_cd == "GB"
        assert attr.self_manage_yn == "N"
        assert attr.mqtt_device is True

    def test_legacy_device_has_none_iot_fields(self, sample_device, sample_parsed_info):
        """Legacy device dict leaves IoT API-only fields as None/False."""
        purifier = build_purifier(sample_device, sample_parsed_info)
        attr = purifier.device_attr

        assert attr.dvc_brand_cd is None
        assert attr.dvc_type_cd is None
        assert attr.order_no is None
        assert attr.mqtt_device is False
