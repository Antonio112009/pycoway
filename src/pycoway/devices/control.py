"""Purifier control commands for Coway IoCare API."""

import json
import logging
from typing import TYPE_CHECKING, Any, Literal

from pycoway.constants import (
    PREFILTER_CYCLE,
    CommandCode,
    Endpoint,
    LightMode,
    ParamCode,
)
from pycoway.devices.data import CowayDataClient
from pycoway.exceptions import CowayError

if TYPE_CHECKING:
    from pycoway.devices.models import DeviceAttributes

LOGGER = logging.getLogger(__name__)


class CowayControlClient(CowayDataClient):
    """Sends control commands to Coway purifiers."""

    def _validate_control_response(self, response: dict[str, Any] | str, command_name: str) -> None:
        """Validate a control-command response.

        Handles both response shapes seen in the wild: the legacy
        ``{"header": {"error_code": ...}}`` and the current
        ``{"code": "S1000", "message": "OK"}`` (S1000 = success).
        """

        if isinstance(response, dict):
            header = response.get("header", {})
            if "error_code" in header:
                raise CowayError(
                    f"Failed to execute {command_name} command. "
                    f"Error code: {header['error_code']}, "
                    f"Error message: {header.get('error_text', 'unknown')}"
                )
            code = response.get("code")
            if code is not None and code != "S1000":
                raise CowayError(
                    f"Failed to execute {command_name} command. "
                    f"Code: {code}, Message: {response.get('message', 'unknown')}"
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
        await self._send_control(device_attr, CommandCode.POWER, "1" if is_on else "0", "power")

    async def async_set_auto_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Auto Mode."""
        await self._send_control(device_attr, CommandCode.MODE, "1", "auto mode")

    async def async_set_night_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Night Mode."""
        await self._send_control(device_attr, CommandCode.MODE, "2", "night mode")

    async def async_set_eco_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Eco Mode.
        Only applies to AIRMEGA AP-1512HHS models.
        """
        await self._send_control(device_attr, CommandCode.MODE, "6", "eco mode")

    async def async_set_rapid_mode(self, device_attr: DeviceAttributes) -> None:
        """Set Purifier to Rapid Mode.
        Only applies to AIRMEGA 250s.
        """
        await self._send_control(device_attr, CommandCode.MODE, "5", "rapid mode")

    async def async_set_fan_speed(
        self, device_attr: DeviceAttributes, speed: Literal["1", "2", "3"]
    ) -> None:
        """Speed can be 1, 2, or 3 represented as a string."""
        if speed not in ("1", "2", "3"):
            raise CowayError(f"Invalid fan speed '{speed}'. Must be '1', '2', or '3'.")
        await self._send_control(device_attr, CommandCode.FAN_SPEED, speed, "fan speed")

    async def async_set_light(self, device_attr: DeviceAttributes, light_on: bool) -> None:
        """Provide light_on as True for On and False for Off.
        NOT used for 250s purifiers: basic on/off models use wire value
        2 for on and 0 for off; multi-mode models invert this — use
        async_set_light_mode with LightMode for those.
        """
        await self._send_control(device_attr, CommandCode.LIGHT, "2" if light_on else "0", "light")

    async def async_set_light_mode(
        self, device_attr: DeviceAttributes, light_mode: LightMode
    ) -> None:
        """Sets light mode for purifiers that support more than On/Off.
        See LightMode constant for available options.
        """
        # The API expects the value as a string (e.g. "2"), while LightMode
        # is an IntEnum so it compares equal to CowayPurifier.light_mode.
        await self._send_control(device_attr, CommandCode.LIGHT, str(int(light_mode)), "light mode")

    async def async_set_timer(
        self, device_attr: DeviceAttributes, time: Literal["0", "60", "120", "240", "480"]
    ) -> None:
        """Time in minutes: 0, 60, 120, 240, or 480 as a string. 0 = off."""
        await self._send_control(device_attr, CommandCode.TIMER, time, "set timer")

    async def async_set_smart_mode_sensitivity(
        self, device_attr: DeviceAttributes, sensitivity: Literal["1", "2", "3"]
    ) -> None:
        """Sensitivity: 1 = Sensitive, 2 = Moderate, 3 = Insensitive."""
        await self._send_control(
            device_attr, CommandCode.SMART_SENSITIVITY, sensitivity, "smart mode sensitivity"
        )

    async def async_set_button_lock(
        self, device_attr: DeviceAttributes, value: Literal["0", "1"]
    ) -> None:
        """Set button lock to ON (1) or OFF (0)."""
        await self._send_control(device_attr, CommandCode.BUTTON_LOCK, value, "button lock")

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

        async with self._request("post", url, headers=headers, data=json.dumps(data)) as resp:
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
        if value not in PREFILTER_CYCLE:
            raise CowayError(
                f"Invalid prefilter value '{value}'. Must be one of {list(PREFILTER_CYCLE)}."
            )
        cycle = PREFILTER_CYCLE[value]
        data = {
            "attributes": {ParamCode.PREFILTER: cycle},
            "deviceSerial": device_attr.device_id,
            "placeId": str(device_attr.place_id),
            "refreshFlag": False,
        }

        async with self._request("post", url, headers=headers, data=json.dumps(data)) as resp:
            response = await self._control_command_response(resp)

        LOGGER.debug(f"{device_attr.name} - Prefilter command sent. Response: {response}")
        self._validate_control_response(response, "prefilter")
