# pycoway

[![CI](https://github.com/Antonio112009/cowayaio/actions/workflows/ci.yml/badge.svg)](https://github.com/Antonio112009/cowayaio/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pycoway?color=blue&label=pypi)](https://pypi.org/project/pycoway/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/github/v/release/Antonio112009/cowayaio?display_name=tag&sort=semver&color=orange&label=version)](https://github.com/Antonio112009/cowayaio/releases/latest)

`pycoway` is an asynchronous Python client for the [Coway IoCare](https://iocare.com/) API. It is designed for AIRMEGA air purifiers and exposes both state retrieval and device control through a typed, `asyncio`-friendly interface.

> Based on [RobertD502/cowayaio](https://github.com/RobertD502/cowayaio) with active maintenance, typed models, tests, CI, and automated releases.

## Features

- Async API built on [aiohttp](https://docs.aiohttp.org/)
- Typed dataclass models for purifier state
- Device control: power, fan speed, light, timers, modes, button lock, and more
- Air-quality readings: PM2.5, PM10, CO2, VOC, AQI
- Filter health monitoring: pre-filter, MAX2, and odor filter
- Automatic token and session management
- Full test coverage with GitHub Actions CI
- Automated semantic version bumping, GitHub releases, and PyPI publishing

## Requirements

- Python 3.11 or newer
- A Coway IoCare account with at least one registered purifier

## Installation

```bash
pip install pycoway
```

For local development:

```bash
git clone https://github.com/Antonio112009/cowayaio.git
cd cowayaio
pip install -e ".[dev]"
```

## Quick Start

```python
import asyncio

from pycoway import CowayClient


async def main() -> None:
    async with CowayClient("email@example.com", "password") as client:
        await client.login()
        data = await client.async_get_purifiers_data()

        for device_id, purifier in data.purifiers.items():
            print(f"{purifier.device_attr.name} ({device_id})")
            print(f"  Power: {'On' if purifier.is_on else 'Off'}")
            print(f"  Fan Speed: {purifier.fan_speed}")
            print(f"  PM2.5: {purifier.particulate_matter_2_5}")
            print(f"  AQI: {purifier.air_quality_index}")


asyncio.run(main())
```

## Device Control

Every control method accepts the `device_attr` from a `CowayPurifier` instance:

```python
import asyncio

from pycoway import CowayClient, LightMode


async def control_first_purifier() -> None:
    async with CowayClient("email@example.com", "password") as client:
        await client.login()
        data = await client.async_get_purifiers_data()

        purifier = next(iter(data.purifiers.values()))
        attr = purifier.device_attr

        await client.async_set_power(attr, is_on=True)
        await client.async_set_auto_mode(attr)
        await client.async_set_fan_speed(attr, speed="2")
        await client.async_set_light(attr, light_on=True)
        await client.async_set_light_mode(attr, LightMode.AQI_OFF)
        await client.async_set_timer(attr, time="120")


asyncio.run(control_first_purifier())
```

### Available Control Methods

| Method | Parameters | Description |
|---|---|---|
| `async_set_power()` | `is_on: bool` | Turn purifier on or off |
| `async_set_auto_mode()` | — | Switch to auto mode |
| `async_set_night_mode()` | — | Switch to night mode |
| `async_set_eco_mode()` | — | Switch to eco mode (AP-1512HHS only) |
| `async_set_rapid_mode()` | — | Switch to rapid mode (250s only) |
| `async_set_fan_speed()` | `speed: str` | Set fan speed: `"1"`, `"2"`, or `"3"` |
| `async_set_light()` | `light_on: bool` | Toggle light on/off (not for 250s) |
| `async_set_light_mode()` | `light_mode: LightMode` | Set light mode for advanced models |
| `async_set_timer()` | `time: str` | Off timer in minutes: `"0"`, `"60"`, `"120"`, `"240"`, `"480"` |
| `async_set_smart_mode_sensitivity()` | `sensitivity: str` | `"1"` sensitive, `"2"` moderate, `"3"` insensitive |
| `async_set_button_lock()` | `value: str` | `"1"` lock, `"0"` unlock |
| `async_change_prefilter_setting()` | `value: int` | Wash frequency: `2`, `3`, or `4` weeks |

## Data Model

`async_get_purifiers_data()` returns a `PurifierData` dataclass containing a `purifiers` dictionary keyed by device ID.

Each `CowayPurifier` includes:

### Device Identity

| Field | Type | Description |
|---|---|---|
| `device_attr` | `DeviceAttributes` | Device ID, model, name, place ID |
| `mcu_version` | `str \| None` | Firmware version |
| `network_status` | `bool \| None` | Network connectivity |

### Control State

| Field | Type | Description |
|---|---|---|
| `is_on` | `bool \| None` | Power state |
| `auto_mode` | `bool \| None` | Auto mode |
| `auto_eco_mode` | `bool \| None` | Auto eco mode |
| `eco_mode` | `bool \| None` | Eco mode |
| `night_mode` | `bool \| None` | Night mode |
| `rapid_mode` | `bool \| None` | Rapid mode |
| `fan_speed` | `int \| None` | Fan speed level |
| `light_on` | `bool \| None` | Light state |
| `light_mode` | `int \| None` | Device-specific light mode |
| `button_lock` | `int \| None` | Button lock state |
| `smart_mode_sensitivity` | `int \| None` | Smart mode sensitivity level |
| `timer` | `str \| None` | Configured off timer |
| `timer_remaining` | `int \| None` | Remaining timer (minutes) |

### Air Quality

| Field | Type | Description |
|---|---|---|
| `particulate_matter_2_5` | `int \| None` | PM2.5 (μg/m³) |
| `particulate_matter_10` | `int \| None` | PM10 (μg/m³) |
| `carbon_dioxide` | `int \| None` | CO₂ (ppm) |
| `volatile_organic_compounds` | `int \| None` | VOC level |
| `air_quality_index` | `int \| None` | AQI value |
| `aq_grade` | `int \| None` | Air quality grade |
| `lux_sensor` | `int \| None` | Ambient light sensor |

### Filter Health

| Field | Type | Description |
|---|---|---|
| `pre_filter_pct` | `int \| None` | Pre-filter remaining (%) |
| `pre_filter_change_frequency` | `int \| None` | Wash frequency (weeks) |
| `max2_pct` | `int \| None` | MAX2 filter remaining (%) |
| `odor_filter_pct` | `int \| None` | Odor filter remaining (%) |

For the complete schema, see [`src/pycoway/devices/models.py`](src/pycoway/devices/models.py).

## Exceptions

All exceptions inherit from `CowayError`:

```python
from pycoway import AuthError, CowayError, PasswordExpired
```

| Exception | Description |
|---|---|
| `CowayError` | Base exception for all library errors |
| `AuthError` | Authentication failed |
| `PasswordExpired` | Coway requires a password change |
| `ServerMaintenance` | Coway API is under maintenance |
| `RateLimited` | Coway temporarily blocked the account |
| `NoPlaces` | No places configured in the IoCare account |
| `NoPurifiers` | No air purifiers found |

## Migrating from cowayaio

If you're switching from the original `cowayaio` package:

```bash
pip uninstall cowayaio
pip install pycoway
```

Update your imports:

```python
# Before
from cowayaio import CowayClient

# After
from pycoway import CowayClient
```

## Development

```bash
git clone https://github.com/Antonio112009/cowayaio.git
cd cowayaio
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

Feature work should branch from `development`, and pull requests merge into `development` first. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## Release Flow

- PRs from `development` to `main` trigger the release workflow when merged
- The workflow bumps `src/pycoway/__version__.py`
- PRs to `main` must have exactly one version label: `patch`, `minor`, or `major`
- A git tag and GitHub release are created automatically
- The package is published to PyPI automatically

## Project Structure

```text
src/pycoway/
├── __init__.py            # Public API exports
├── __version__.py         # Version string
├── client.py              # Public CowayClient entry point
├── constants.py           # API constants
├── enums.py               # Enumerations
├── exceptions.py          # Public exception hierarchy
├── py.typed               # PEP 561 marker
├── account/
│   ├── auth.py            # Authentication (login, token refresh)
│   └── maintenance.py     # Server maintenance checks
├── devices/
│   ├── control.py         # Purifier control commands
│   ├── data.py            # Data fetching (purifiers, filters, air quality)
│   ├── models.py          # Dataclasses (CowayPurifier, PurifierData)
│   └── parser.py          # HTML/JSON response parsing
└── transport/
    └── http.py            # HTTP base client with session management
```

## License

[MIT](LICENSE), originally authored by [RobertD502](https://github.com/RobertD502)
