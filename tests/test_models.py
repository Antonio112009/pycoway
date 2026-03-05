"""Tests for purifier_model dataclasses."""

from cowayaio.purifier_model import CowayPurifier, DeviceAttributes, PurifierData


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
        )
        data = PurifierData(purifiers={"D1": purifier})
        assert "D1" in data.purifiers
        assert data.purifiers["D1"].device_attr.device_id == "D1"
