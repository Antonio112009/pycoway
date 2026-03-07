"""Tests for device models dataclasses."""

from pycoway.devices.models import CowayPurifier, DeviceAttributes, FilterInfo, PurifierData


class TestFilterInfo:
    def test_all_fields(self):
        f = FilterInfo(
            name="Pre-Filter",
            filter_remain=80,
            filter_remain_status="AVAILABLE",
            replace_cycle=2,
            replace_cycle_unit="W",
            last_date="2026-01-01",
            next_date="2026-01-15",
            pollutants=["Pollen", "Large dust"],
            description="Removes large dust and pollen",
            pre_filter=True,
            server_reset=True,
        )
        assert f.name == "Pre-Filter"
        assert f.filter_remain == 80
        assert f.filter_remain_status == "AVAILABLE"
        assert f.replace_cycle == 2
        assert f.replace_cycle_unit == "W"
        assert f.last_date == "2026-01-01"
        assert f.next_date == "2026-01-15"
        assert f.pollutants == ["Pollen", "Large dust"]
        assert f.description == "Removes large dust and pollen"
        assert f.pre_filter is True
        assert f.server_reset is True

    def test_minimal_fields(self):
        f = FilterInfo(
            name=None,
            filter_remain=None,
            filter_remain_status=None,
            replace_cycle=None,
            replace_cycle_unit=None,
            last_date=None,
            next_date=None,
            pollutants=[],
            description=None,
            pre_filter=False,
            server_reset=False,
        )
        assert f.name is None
        assert f.filter_remain is None
        assert f.pollutants == []
        assert f.pre_filter is False

    def test_equality(self):
        kwargs = dict(
            name="Max2 Filter",
            filter_remain=43,
            filter_remain_status="AVAILABLE",
            replace_cycle=12,
            replace_cycle_unit="M",
            last_date=None,
            next_date=None,
            pollutants=["VOCs"],
            description=None,
            pre_filter=False,
            server_reset=False,
        )
        assert FilterInfo(**kwargs) == FilterInfo(**kwargs)


class TestDeviceAttributes:
    def test_all_fields(self):
        attr = DeviceAttributes(
            device_id="D1",
            model="AIRMEGA 250S",
            model_code="MC-250S",
            code="C250",
            name="Living Room",
            product_name="Airmega 250S",
            place_id="P1",
        )
        assert attr.device_id == "D1"
        assert attr.model == "AIRMEGA 250S"
        assert attr.model_code == "MC-250S"
        assert attr.code == "C250"
        assert attr.name == "Living Room"
        assert attr.product_name == "Airmega 250S"
        assert attr.place_id == "P1"
        # Extended fields default to None/False
        assert attr.dvc_brand_cd is None
        assert attr.dvc_type_cd is None
        assert attr.prod_name is None
        assert attr.prod_name_full is None
        assert attr.order_no is None
        assert attr.sell_type_cd is None
        assert attr.admdong_cd is None
        assert attr.station_cd is None
        assert attr.self_manage_yn is None
        assert attr.mqtt_device is False

    def test_none_fields(self):
        attr = DeviceAttributes(
            device_id=None,
            model=None,
            model_code=None,
            code=None,
            name=None,
            product_name=None,
            place_id=None,
        )
        assert attr.device_id is None
        assert attr.name is None

    def test_hb_extended_fields(self):
        attr = DeviceAttributes(
            device_id="15902EUZ2282500520",
            model="AP-2015E(GRAPHITE_US)",
            model_code="AP-2015E",
            code="02EUZ",
            name="HH AIR PURIFIER",
            product_name="AIRMEGA",
            place_id=None,
            dvc_brand_cd="MG",
            dvc_type_cd="004",
            prod_name="AIRMEGA",
            prod_name_full="AIRMEGA 300s/400s",
            order_no="ORD1WBGmBa7P",
            sell_type_cd="1",
            admdong_cd="GB",
            station_cd="GB",
            self_manage_yn="N",
            mqtt_device=True,
        )
        assert attr.dvc_brand_cd == "MG"
        assert attr.dvc_type_cd == "004"
        assert attr.prod_name == "AIRMEGA"
        assert attr.prod_name_full == "AIRMEGA 300s/400s"
        assert attr.order_no == "ORD1WBGmBa7P"
        assert attr.sell_type_cd == "1"
        assert attr.admdong_cd == "GB"
        assert attr.station_cd == "GB"
        assert attr.self_manage_yn == "N"
        assert attr.mqtt_device is True

    def test_equality(self):
        a = DeviceAttributes("D1", "M", "MC", "C", "N", "P", "PL")
        b = DeviceAttributes("D1", "M", "MC", "C", "N", "P", "PL")
        assert a == b


class TestCowayPurifier:
    def test_construction(self):
        attr = DeviceAttributes("D1", "M", "MC", "C", "N", "P", "PL")
        purifier = CowayPurifier(
            device_attr=attr,
            mcu_version="2.0.1",
            network_status=True,
            is_on=True,
            auto_mode=True,
            auto_eco_mode=False,
            eco_mode=False,
            night_mode=False,
            rapid_mode=False,
            fan_speed=2,
            light_on=True,
            light_mode=2,
            button_lock=0,
            timer=None,
            timer_remaining=None,
            pre_filter_pct=80,
            max2_pct=65,
            odor_filter_pct=None,
            aq_grade=1,
            particulate_matter_2_5=15,
            particulate_matter_10=25,
            carbon_dioxide=450,
            volatile_organic_compounds=10,
            air_quality_index=50,
            lux_sensor=300,
            pre_filter_change_frequency=112,
            smart_mode_sensitivity=3,
            filters=None,
        )
        assert purifier.is_on is True
        assert purifier.fan_speed == 2
        assert purifier.device_attr.device_id == "D1"
        assert purifier.pre_filter_pct == 80


class TestPurifierData:
    def test_purifiers_dict(self):
        attr = DeviceAttributes("D1", "M", "MC", "C", "N", "P", "PL")
        purifier = CowayPurifier(
            device_attr=attr,
            mcu_version=None,
            network_status=None,
            is_on=None,
            auto_mode=None,
            auto_eco_mode=None,
            eco_mode=None,
            night_mode=None,
            rapid_mode=None,
            fan_speed=None,
            light_on=None,
            light_mode=None,
            button_lock=None,
            timer=None,
            timer_remaining=None,
            pre_filter_pct=None,
            max2_pct=None,
            odor_filter_pct=None,
            aq_grade=None,
            particulate_matter_2_5=None,
            particulate_matter_10=None,
            carbon_dioxide=None,
            volatile_organic_compounds=None,
            air_quality_index=None,
            lux_sensor=None,
            pre_filter_change_frequency=None,
            smart_mode_sensitivity=None,
            filters=None,
        )
        data = PurifierData(purifiers={"D1": purifier})
        assert "D1" in data.purifiers
        assert data.purifiers["D1"].device_attr.device_id == "D1"
