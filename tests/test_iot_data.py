"""Tests for IoT JSON API data methods and extract_iot_parsed_info parser."""

from unittest.mock import AsyncMock

import pytest

from pycoway.constants import Endpoint
from pycoway.devices.data import CowayDataClient
from pycoway.devices.models import DeviceAttributes
from pycoway.devices.parser import extract_iot_parsed_info
from pycoway.exceptions import CowayError


@pytest.fixture
def iot_device_attr() -> DeviceAttributes:
    """DeviceAttributes populated with IoT API discovery fields."""
    return DeviceAttributes(
        device_id="15902EUZ2282500520",
        model="AIRMEGA 300s/400s",
        model_code="AP-2015E(GRAPHITE_US)",
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


class TestBuildDeviceAttr:
    def test_from_legacy_device_dict(self):
        dev = {
            "deviceSerial": "ABC123",
            "productModel": "AIRMEGA-250S",
            "dvcNick": "Living Room",
            "placeId": "place-001",
        }
        attr = CowayDataClient._build_device_attr(dev)
        assert attr.device_id == "ABC123"
        assert attr.model is None
        assert attr.model_code == "AIRMEGA-250S"
        assert attr.name == "Living Room"
        assert attr.place_id == "place-001"
        assert attr.dvc_brand_cd is None
        assert attr.mqtt_device is False

    def test_from_iot_device_dict(self):
        dev = {
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
        }
        attr = CowayDataClient._build_device_attr(dev)
        assert attr.device_id == "15902EUZ2282500520"
        assert attr.model_code == "AP-2015E(GRAPHITE_US)"
        assert attr.dvc_brand_cd == "MG"
        assert attr.dvc_type_cd == "004"
        assert attr.mqtt_device is True

    def test_prefers_device_serial_over_barcode(self):
        dev = {"deviceSerial": "SER1", "barcode": "BAR1"}
        attr = CowayDataClient._build_device_attr(dev)
        assert attr.device_id == "SER1"


class TestIOTDeviceParams:
    def test_builds_expected_params(self, iot_device_attr):
        params = CowayDataClient._iot_device_params(iot_device_attr)
        assert params["devId"] == "15902EUZ2282500520"
        assert params["barcode"] == "15902EUZ2282500520"
        assert params["mqttDevice"] == "true"
        assert params["dvcBrandCd"] == "MG"
        assert params["dvcTypeCd"] == "004"
        assert params["deviceType"] == "004"
        assert params["prodName"] == "AIRMEGA"
        assert params["orderNo"] == "ORD1WBGmBa7P"
        assert params["membershipYn"] == "N"
        assert params["selfYn"] == "N"
        assert params["sellTypeCd"] == "1"
        assert params["admdongCd"] == "GB"
        assert params["stationCd"] == "GB"

    def test_defaults_for_minimal_attr(self):
        attr = DeviceAttributes(
            device_id="DEV1",
            model=None,
            model_code=None,
            code=None,
            name=None,
            product_name=None,
            place_id=None,
        )
        params = CowayDataClient._iot_device_params(attr)
        assert params["devId"] == "DEV1"
        assert params["barcode"] == "DEV1"
        assert params["mqttDevice"] == "false"
        assert params["dvcBrandCd"] == ""
        assert params["orderNo"] == ""
        assert params["admdongCd"] == ""
        assert params["stationCd"] == ""


def _mock_iot_client(response: dict) -> CowayDataClient:
    """Create a CowayDataClient with a mocked _get_iot_endpoint."""
    client = CowayDataClient.__new__(CowayDataClient)
    client._get_iot_endpoint = AsyncMock(return_value=response)
    return client


class TestAsyncGetIOTDeviceControl:
    async def test_returns_data(self, iot_device_attr):
        payload = {
            "controlStatus": {"0001": "1", "0002": "0", "0003": "2"},
            "netStatus": True,
        }
        client = _mock_iot_client({"data": payload})
        result = await client.async_get_iot_device_control(iot_device_attr)
        assert result == payload

    async def test_correct_url(self, iot_device_attr):
        client = _mock_iot_client({"data": {}})
        await client.async_get_iot_device_control(iot_device_attr)
        call_args = client._get_iot_endpoint.call_args
        url = call_args[0][0]
        assert url == (
            f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONTROL}/15902EUZ2282500520/control"
        )

    async def test_raises_on_error(self, iot_device_attr):
        client = _mock_iot_client({"error": "unauthorized"})
        with pytest.raises(CowayError, match="IoT control-status failed"):
            await client.async_get_iot_device_control(iot_device_attr)


class TestAsyncGetIOTAirHome:
    async def test_returns_data(self, iot_device_attr):
        payload = {
            "IAQ": {"dustpm10": "179", "dustpm25": "", "co2": "", "vocs": ""},
            "prodStatus": {"power": "1", "prodMode": "0"},
        }
        client = _mock_iot_client({"data": payload})
        result = await client.async_get_iot_air_home(iot_device_attr)
        assert result == payload

    async def test_correct_url(self, iot_device_attr):
        client = _mock_iot_client({"data": {}})
        await client.async_get_iot_air_home(iot_device_attr)
        url = client._get_iot_endpoint.call_args[0][0]
        assert url == (f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_AIR_HOME}/15902EUZ2282500520/home")

    async def test_raises_on_error(self, iot_device_attr):
        client = _mock_iot_client({"error": "server error"})
        with pytest.raises(CowayError, match="IoT air home failed"):
            await client.async_get_iot_air_home(iot_device_attr)


class TestAsyncGetIOTFilterInfo:
    async def test_returns_data(self, iot_device_attr):
        payload = {"suppliesList": [{"supplyNm": "MAX2 Filter", "filterRemain": 72}]}
        client = _mock_iot_client({"data": payload})
        result = await client.async_get_iot_filter_info(iot_device_attr)
        assert result == payload

    async def test_correct_url(self, iot_device_attr):
        client = _mock_iot_client({"data": {}})
        await client.async_get_iot_filter_info(iot_device_attr)
        url = client._get_iot_endpoint.call_args[0][0]
        assert url == (
            f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_AIR_FILTER_INFO}/15902EUZ2282500520/filter-info"
        )

    async def test_raises_on_error(self, iot_device_attr):
        client = _mock_iot_client({"error": "not found"})
        with pytest.raises(CowayError, match="IoT filter info failed"):
            await client.async_get_iot_filter_info(iot_device_attr)


class TestAsyncGetIOTDeviceConn:
    async def test_returns_data(self, iot_device_attr):
        payload = {"netStatus": "online"}
        client = _mock_iot_client({"data": payload})
        result = await client.async_get_iot_device_conn(iot_device_attr)
        assert result == payload

    async def test_correct_url(self, iot_device_attr):
        client = _mock_iot_client({"data": {}})
        await client.async_get_iot_device_conn(iot_device_attr)
        url = client._get_iot_endpoint.call_args[0][0]
        assert url == f"{Endpoint.IOT_BASE_URI}{Endpoint.IOT_DEVICE_CONN}"

    async def test_raises_on_error(self, iot_device_attr):
        client = _mock_iot_client({"error": "timeout"})
        with pytest.raises(CowayError, match="IoT device connection failed"):
            await client.async_get_iot_device_conn(iot_device_attr)


class TestExtractIOTParsedInfo:
    def test_full_response(self):
        control = {
            "controlStatus": {
                "0001": "1",
                "0002": "1",
                "0003": "2",
                "0007": "2",
                "0008": "120",
                "000A": "2",
                "offTimer": "0",
            },
            "netStatus": True,
        }
        air = {
            "IAQ": {"dustpm25": "12", "dustpm10": "20", "co2": "450", "vocs": "10"},
            "prodStatus": {"dustPollution": "2", "power": "1"},
            "filterList": [
                {
                    "filterName": "극세사망 프리필터",
                    "filterPer": 74,
                    "changeCycle": "3",
                    "cycleInfo": "W",
                },
                {"filterName": "Max2 필터", "filterPer": 42, "changeCycle": "12"},
            ],
        }
        conn = {"netStatus": "online"}

        result = extract_iot_parsed_info(control, air, conn)

        assert result["status_info"]["0001"] == 1
        assert result["status_info"]["0002"] == 1
        assert result["status_info"]["0003"] == 2
        assert result["status_info"]["0007"] == 2
        assert result["status_info"]["000A"] == 2
        assert result["sensor_info"]["PM25_IDX"] == 12
        assert result["sensor_info"]["PM10_IDX"] == 20
        assert result["sensor_info"]["CO2_IDX"] == 450
        assert result["sensor_info"]["VOCs_IDX"] == 10
        assert result["aq_grade"] == {"iaqGrade": 2}
        assert result["network_info"] == {"wifiConnected": True}
        assert result["filter_info"]["pre-filter"] == {"filterRemain": 74, "replaceCycle": 3}
        assert result["filter_info"]["max2"] == {"filterRemain": 42}
        assert result["timer_info"] == 0  # offTimer takes precedence

    def test_timer_from_0008_fallback(self):
        control = {"controlStatus": {"0008": "60"}}
        result = extract_iot_parsed_info(control, {}, {})
        assert result["timer_info"] == 60

    def test_offline_device_from_control(self):
        control = {"controlStatus": {}, "netStatus": False}
        result = extract_iot_parsed_info(control, {}, {})
        assert result["network_info"] == {"wifiConnected": False}

    def test_offline_device_from_conn(self):
        result = extract_iot_parsed_info({}, {}, {"netStatus": "offline"})
        assert result["network_info"] == {"wifiConnected": False}

    def test_net_status_from_air_data(self):
        air = {"netStatus": True}
        result = extract_iot_parsed_info({}, air, {})
        assert result["network_info"] == {"wifiConnected": True}

    def test_empty_responses(self):
        result = extract_iot_parsed_info({}, {}, {})
        assert result["status_info"] == {}
        assert result["mcu_info"] == {}
        assert result["sensor_info"] == {}
        assert result["device_info"] == {}
        assert result["filter_info"] == {}
        assert result["timer_info"] is None

    def test_no_dust_pollution(self):
        air = {"IAQ": {"dustpm10": "5"}, "prodStatus": {}}
        result = extract_iot_parsed_info({}, air, {})
        assert result["aq_grade"] == {}
        assert result["sensor_info"] == {"PM10_IDX": 5}

    def test_empty_iaq_values_skipped(self):
        air = {"IAQ": {"dustpm25": "", "co2": "", "dustpm10": "179"}}
        result = extract_iot_parsed_info({}, air, {})
        assert "PM25_IDX" not in result["sensor_info"]
        assert "CO2_IDX" not in result["sensor_info"]
        assert result["sensor_info"]["PM10_IDX"] == 179

    def test_string_status_converted_to_int(self):
        control = {"controlStatus": {"0001": "1", "0003": "3"}}
        result = extract_iot_parsed_info(control, {}, {})
        assert result["status_info"]["0001"] == 1
        assert result["status_info"]["0003"] == 3

    def test_non_numeric_status_preserved(self):
        control = {"controlStatus": {"serial": "ABC123", "0001": "1"}}
        result = extract_iot_parsed_info(control, {}, {})
        assert result["status_info"]["serial"] == "ABC123"
        assert result["status_info"]["0001"] == 1

    def test_odor_filter_from_filter_list(self):
        air = {
            "filterList": [{"filterName": "탈취 필터", "filterPer": 55}],
        }
        result = extract_iot_parsed_info({}, air, {})
        assert result["filter_info"]["odor-filter"] == {"filterRemain": 55}
