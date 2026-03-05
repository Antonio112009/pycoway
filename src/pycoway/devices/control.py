"""Purifier control commands for Coway IoCare API."""

import json
import logging
from typing import Any

from pycoway.constants import (
    PREFILTER_CYCLE,
    Endpoint,
    LightMode,
)
from pycoway.devices.data import CowayDataClient
from pycoway.devices.models import DeviceAttributes
from pycoway.exceptions import CowayError

LOGGER = logging.getLogger(__name__)


class CowayControlClient(CowayDataClient):
    """Sends control commands to Coway purifiers."""

    def _validate_control_response(self, response: dict[str, Any] | str, command_name: str) -> None:
        """Validate a control-command response."""

        if isinstance(response, dict):
            header = response.get("header", {})
            if "error_code" in header:
                raise CowayError(
                    f"Failed to execute {command_name} command. "
                    f"Error code: {header['error_code']}, "
                    f"Error message: {header['error_text']}"
                )
        else:
            raise CowayError(f"Failed to execute {command_name} command. Response: {response}")

    async def _send_control(
        self,
        device_attr: DeviceAttributes,
        command: str,
        value: Any,
        command_name: str,
    ) -> None:
        """Send a control command and validate the response."""

        response = await self.async_control_purifier(device_attr, command, value)
        LOGGER.debug(f"{device_attr.name} - {command_name} command sent. Response: {response}")
        self._validate_control_response(response, command_name)

    async def async_set_power(self, device_attr: DeviceAttributes, is_on: bool) -> None:
        """Provide is_on as True for On and False for Off."""
        await self._send_control(device_attr, "0001", "1" if is_on else "0", "power")

    async def async_set_auto_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Auto Mode."""
        await self._send_control(device_attr, "0002", "1", "auto mode")

    async def async_set_night_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Night Mode."""
        await self._send_control(device_attr, "0002", "2", "night mode")

    async def async_set_eco_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Eco Mode.
        Only applies to AIRMEGA AP-1512HHS models.
        """
        await self._send_control(device_attr, "0002", "6", "eco mode")

    async def async_set_rapid_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Rapid Mode.
        Only applies to AIRMEGA 250s.
        """
        await self._send_control(device_attr, "0002", "5", "rapid mode")

    async def async_set_fan_speed(self, device_attr: DeviceAttributes, speed: str) -> None:
        """Speed can be 1, 2, or 3 represented as a string."""
        await self._send_control(device_attr, "0003", speed, "fan speed")

    async def async_set_light(self, device_attr: DeviceAttributes, light_on: bool) -> None:
        """Provide light_on as True for On and False for Off.
        NOT used for 250s purifiers.
        """
        await self._send_control(device_attr, "0007", "2" if light_on else "0", "light")

    async def async_set_light_mode(
        self, device_attr: DeviceAttributes, light_mode: LightMode
    ) -> None:
        """Sets light mode for purifiers that support more than On/Off.
        See LightMode constant for available options.
        """
        await self._send_control(device_attr, "0007", light_mode, "light mode")

    async def async_set_timer(self, device_attr: DeviceAttributes, time: str) -> None:
        """Time in minutes: 0, 60, 120, 240, or 480 as a string. 0 = off."""
        await self._send_control(device_attr, "0008", time, "set timer")

    async def async_set_smart_mode_sensitivity(
        self, device_attr: DeviceAttributes, sensitivity: str
    ) -> None:
        """Sensitivity: 1 = Sensitive, 2 = Moderate, 3 = Insensitive."""
        await self._send_control(device_attr, "000A", sensitivity, "smart mode sensitivity")

    async def async_set_button_lock(self, device_attr: DeviceAttributes, value: str) -> None:
        """Set button lock to ON (1) or OFF (0)."""
        await self._send_control(device_attr, "0024", value, "button lock")

    async def async_control_purifier(
        self, device_attr: DeviceAttributes, command: str, value: Any
    ) -> dict[str, Any] | str:
        """Execute an individual purifier control command."""

        await self._check_token()
        url = (
            f"{Endpoint.BASE_URI}{Endpoint.PLACES}/"
            f"{device_attr.place_id}/devices/"
            f"{device_attr.device_id}/control-status"
        )
        headers = self._construct_control_header()
        data = {
            "attributes": {command: value},
            "isMultiControl": False,
            "refreshFlag": False,
        }

        async with self._session.post(
            url, headers=headers, data=json.dumps(data), timeout=self.timeout
        ) as resp:
            return await self._control_command_response(resp)

    async def async_change_prefilter_setting(
        self, device_attr: DeviceAttributes, value: int
    ) -> None:
        """Change pre-filter wash frequency. Value can be 2, 3, or 4."""

        await self._check_token()
        url = (
            f"{Endpoint.BASE_URI}{Endpoint.PLACES}/"
            f"{device_attr.place_id}/devices/"
            f"{device_attr.device_id}/control-param"
        )
        headers = self._construct_control_header()
        cycle = PREFILTER_CYCLE[value]
        data = {
            "attributes": {"0001": cycle},
            "deviceSerial": device_attr.device_id,
            "placeId": str(device_attr.place_id),
            "refreshFlag": False,
        }

        async with self._session.post(
            url, headers=headers, data=json.dumps(data), timeout=self.timeout
        ) as resp:
            response = await self._control_command_response(resp)

        LOGGER.debug(f"{device_attr.name} - Prefilter command sent. Response: {response}")
        self._validate_control_response(response, "prefilter")
