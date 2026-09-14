#!/usr/bin/env python3
"""Live control-command test against a real Coway purifier.

Sends safe, reversible commands (light, fan speed, timer) to the first
purifier on the account, measures both the API round-trip and how long
the change takes to be reflected in the device status, then restores
the original state.

Credentials: same as scripts/live_test.py (COWAY_EMAIL/COWAY_PASSWORD
env vars or a gitignored .env file in the repo root).
"""

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from live_test import _load_env_file, _mask  # noqa: E402

from pycoway import CowayClient  # noqa: E402
from pycoway.constants import CommandCode  # noqa: E402

POLL_INTERVAL = 1.0
POLL_TIMEOUT = 30.0


async def _wait_for_status(client, attr, code: str, expected: int) -> float | None:
    """Poll the control status until `code` == `expected`; return seconds or None."""
    start = time.perf_counter()
    while time.perf_counter() - start < POLL_TIMEOUT:
        control = await client.async_get_iot_device_control(attr)
        raw = control.get("controlStatus", {}).get(code)
        try:
            current = int(raw)
        except TypeError, ValueError:
            current = raw
        if current == expected:
            return time.perf_counter() - start
        await asyncio.sleep(POLL_INTERVAL)
    return None


async def _step(client, attr, label: str, command, code: str, expected: int) -> bool:
    """Run one control command and report API + propagation timing."""
    t0 = time.perf_counter()
    await command()
    api_time = time.perf_counter() - t0
    seen_in = await _wait_for_status(client, attr, code, expected)
    if seen_in is None:
        print(f"  {label:<28} API {api_time:5.2f}s  NOT CONFIRMED in {POLL_TIMEOUT:.0f}s")
        return False
    print(f"  {label:<28} API {api_time:5.2f}s  visible in status after {seen_in:4.1f}s")
    return True


async def run() -> int:
    email = os.environ.get("COWAY_EMAIL")
    password = os.environ.get("COWAY_PASSWORD")
    if not email or not password:
        print("Set COWAY_EMAIL and COWAY_PASSWORD (env vars or .env file).", file=sys.stderr)
        return 2

    client = CowayClient(email, password, skip_password_change=True)
    ok = True
    try:
        await client.login()
        data = await client.async_get_purifiers_data()
        device_id, purifier = next(iter(data.purifiers.items()))
        attr = purifier.device_attr
        print(f"Testing controls on {attr.name} ({_mask(device_id)})")
        print(
            f"Initial state: on={purifier.is_on} light_on={purifier.light_on} "
            f"light_mode={purifier.light_mode} fan={purifier.fan_speed} "
            f"auto={purifier.auto_mode} eco={purifier.eco_mode} "
            f"night={purifier.night_mode} timer={purifier.timer_remaining}\n"
        )

        if not purifier.is_on:
            print("Purifier is off — turn it on first so mode/fan tests are meaningful.")
            return 1

        control = client.async_get_iot_device_control  # warm reference for polling

        # --- Light: toggle off, then restore -------------------------------
        original_light_on = bool(purifier.light_on)
        ok &= await _step(
            client,
            attr,
            "light off",
            lambda: client.async_set_light(attr, False),
            CommandCode.LIGHT,
            0,
        )
        ok &= await _step(
            client,
            attr,
            f"light restore ({'on' if original_light_on else 'off'})",
            lambda: client.async_set_light(attr, original_light_on),
            CommandCode.LIGHT,
            2 if original_light_on else 0,
        )

        # --- Fan speed: manual 1, then restore prior mode/speed ------------
        ok &= await _step(
            client,
            attr,
            "fan speed -> 1",
            lambda: client.async_set_fan_speed(attr, "1"),
            CommandCode.FAN_SPEED,
            1,
        )
        if purifier.eco_mode:
            restore_label, restore_cmd, restore_expected = (
                "restore eco mode",
                lambda: client.async_set_eco_mode(attr),
                6,
            )
        elif purifier.night_mode:
            restore_label, restore_cmd, restore_expected = (
                "restore night mode",
                lambda: client.async_set_night_mode(attr),
                2,
            )
        elif purifier.rapid_mode:
            restore_label, restore_cmd, restore_expected = (
                "restore rapid mode",
                lambda: client.async_set_rapid_mode(attr),
                5,
            )
        elif purifier.auto_mode:
            restore_label, restore_cmd, restore_expected = (
                "restore auto mode",
                lambda: client.async_set_auto_mode(attr),
                1,
            )
        else:
            speed = str(purifier.fan_speed) if purifier.fan_speed in (1, 2, 3) else "1"
            restore_label, restore_cmd, restore_expected = (
                f"restore fan speed {speed}",
                lambda: client.async_set_fan_speed(attr, speed),
                int(speed),
            )
            ok &= await _step(
                client,
                attr,
                restore_label,
                restore_cmd,
                CommandCode.FAN_SPEED,
                restore_expected,
            )
            restore_cmd = None
        if restore_cmd is not None:
            confirmed = await _step(
                client, attr, restore_label, restore_cmd, CommandCode.MODE, restore_expected
            )
            if not confirmed and purifier.eco_mode:
                # Seen on AP-2015E: the API answers S1000/OK for mode 6 but the
                # device ignores it — eco is only settable from the unit itself.
                print(
                    "  note: eco is not remotely settable on this model; "
                    "falling back to auto — press the mode button on the unit "
                    "to get eco back."
                )
                await _step(
                    client,
                    attr,
                    "fallback: auto mode",
                    lambda: client.async_set_auto_mode(attr),
                    CommandCode.MODE,
                    1,
                )
            else:
                ok &= confirmed

        # --- Timer: 60 minutes, then off -----------------------------------
        ok &= await _step(
            client,
            attr,
            "timer -> 60 min",
            lambda: client.async_set_timer(attr, "60"),
            CommandCode.TIMER,
            60,
        )
        ok &= await _step(
            client,
            attr,
            "timer -> off",
            lambda: client.async_set_timer(attr, "0"),
            CommandCode.TIMER,
            0,
        )

        # Final sanity read
        final = await control(attr)
        status = final.get("controlStatus", {})
        print(
            f"\nFinal raw status: power={status.get(CommandCode.POWER)} "
            f"mode={status.get(CommandCode.MODE)} fan={status.get(CommandCode.FAN_SPEED)} "
            f"light={status.get(CommandCode.LIGHT)} timer={status.get(CommandCode.TIMER)}"
        )
        print("RESULT:", "all commands confirmed" if ok else "SOME COMMANDS NOT CONFIRMED")
    finally:
        await client.close()
    return 0 if ok else 1


def main() -> int:
    repo_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=os.path.join(repo_root, ".env"),
        help="path to env file with COWAY_EMAIL/COWAY_PASSWORD",
    )
    args = parser.parse_args()
    _load_env_file(args.env_file)
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
