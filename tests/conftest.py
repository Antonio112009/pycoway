"""Shared test fixtures for pycoway tests."""

import sys
from pathlib import Path

import pytest

# Keep direct test runs working with the src/ layout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def sample_device() -> dict:
    """A minimal device dict as returned by the Coway API."""
    return {
        "deviceSerial": "ABC123",
        "productModel": "AIRMEGA-250S",
        "dvcNick": "Living Room",
        "placeId": "place-001",
    }


@pytest.fixture
def sample_parsed_info() -> dict:
    """Parsed purifier info matching extract_parsed_info output structure."""
    return {
        "device_info": {
            "productName": "AIRMEGA 250S",
            "modelCode": "MC-250S",
            "prodName": "Airmega 250S",
        },
        "mcu_info": {"currentMcuVer": "2.0.1"},
        "network_info": {"wifiConnected": True},
        "sensor_info": {
            "0001": 15,
            "0002": 25,
            "0007": 300,
            "0011": 20,
            "0012": 30,
            "0013": 40,
            "CO2_IDX": 450,
            "VOCs_IDX": 10,
            "IAQ": 50,
        },
        "status_info": {
            "0001": 1,
            "0002": 1,
            "0003": 2,
            "0007": 2,
            "0008": 120,
            "0024": 0,
            "000A": 3,
        },
        "aq_grade": {"iaqGrade": 1},
        "filter_info": {
            "pre-filter": {"filterRemain": 80, "replaceCycle": 112},
            "max2": {"filterRemain": 65},
        },
        "timer_info": None,
    }


@pytest.fixture
def sample_purifier_json_children() -> dict:
    """Minimal purifier JSON matching what parse_purifier_html extracts."""
    return {
        "children": [
            {
                "coreData": [
                    {"data": {"currentMcuVer": "2.0.1"}},
                    {"data": {"sensorInfo": {"attributes": {"0001": 15}}}},
                ],
                "deviceStatusData": {
                    "data": {"statusInfo": {"attributes": {"0001": 1, "0002": 1, "0003": 2}}}
                },
                "baseInfoForModelCodeData": {
                    "deviceInfo": {
                        "productName": "AIRMEGA 250S",
                        "modelCode": "MC-250S",
                    }
                },
                "deviceModule": {
                    "data": {
                        "content": {
                            "deviceModuleDetailInfo": {
                                "wifiConnected": True,
                                "airStatusInfo": {"iaqGrade": 1},
                            }
                        }
                    }
                },
            }
        ]
    }
