# pycoway

[![CI](https://github.com/Antonio112009/cowayaio/actions/workflows/ci.yml/badge.svg)](https://github.com/Antonio112009/cowayaio/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pycoway?color=blue&label=pypi)](https://pypi.org/project/pycoway/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/github/v/release/Antonio112009/cowayaio?display_name=tag&sort=semver&color=orange&label=version)](https://github.com/Antonio112009/cowayaio/releases/latest)

`pycoway` is an asynchronous Python client for the [Coway IoCare](https://iocare.com/) API. It is designed for AIRMEGA air purifiers and exposes both state retrieval and device control through a typed, `asyncio`-friendly interface.

Based on [RobertD502/cowayaio](https://github.com/RobertD502/cowayaio) with active maintenance, typed models, tests, CI, and automated releases.

## Features

- Async API built on [aiohttp](https://docs.aiohttp.org/)
- Typed dataclass models for purifier state
- Device control for power, fan speed, light, timers, and operating modes
- Air-quality and filter-health readings
- Automatic token and session management
- Test coverage and GitHub Actions CI
- Automated semantic version bumping and GitHub releases

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

from cowayaio import CowayClient


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

## Common Control Operations

Every control method accepts the `device_attr` from a `CowayPurifier` instance:

```python
import asyncio

from cowayaio import CowayClient, LightMode


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

Additional commands are also available:

- `async_set_night_mode()`
- `async_set_eco_mode()` for AIRMEGA AP-1512HHS models
- `async_set_rapid_mode()` for AIRMEGA 250s models
- `async_set_smart_mode_sensitivity()`
- `async_set_button_lock()`
- `async_change_prefilter_setting()`

## Data Model

`async_get_purifiers_data()` returns a `PurifierData` dataclass containing a `purifiers` dictionary keyed by device ID.

Each `CowayPurifier` includes identity, control state, air-quality readings, timer info, and filter metrics. Common fields include:

| Field | Type | Description |
|---|---|---|
| `device_attr` | `DeviceAttributes` | IDs, model metadata, display name, place ID |
| `is_on` | `bool \| None` | Power state |
| `fan_speed` | `int \| None` | Fan speed level |
| `auto_mode` | `bool \| None` | Auto mode flag |
| `eco_mode` | `bool \| None` | Eco mode flag |
| `night_mode` | `bool \| None` | Night mode flag |
| `rapid_mode` | `bool \| None` | Rapid mode flag |
| `light_on` | `bool \| None` | Basic light state |
| `light_mode` | `int \| None` | Device-specific light mode |
| `timer` | `str \| None` | Configured off timer |
| `timer_remaining` | `int \| None` | Remaining timer duration |
| `particulate_matter_2_5` | `int \| None` | PM2.5 reading |
| `particulate_matter_10` | `int \| None` | PM10 reading |
| `carbon_dioxide` | `int \| None` | CO2 reading |
| `volatile_organic_compounds` | `int \| None` | VOC reading |
| `air_quality_index` | `int \| None` | AQI value |
| `pre_filter_pct` | `int \| None` | Pre-filter health percentage |
| `max2_pct` | `int \| None` | MAX2 filter health percentage |
| `odor_filter_pct` | `int \| None` | Odor filter health percentage |

For the complete schema, see [`src/cowayaio/devices/models.py`](src/cowayaio/devices/models.py).

## Exceptions

All public exceptions inherit from `CowayError` and can be imported directly from the package:

```python
from cowayaio import AuthError, CowayError, PasswordExpired
```

| Exception | Description |
|---|---|
| `CowayError` | Base exception for all library errors |
| `AuthError` | Authentication failed |
| `PasswordExpired` | Coway requires a password change |
| `ServerMaintenance` | Coway API is under maintenance |
| `RateLimited` | Coway temporarily blocked the account |
| `NoPlaces` | No places are configured in the IoCare account |
| `NoPurifiers` | No air purifiers were found |

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
- The workflow bumps `src/cowayaio/__version__.py`
- PR labels control the version bump: `patch` (default), `minor`, or `major`
- A git tag and GitHub release are created automatically
- The package is published to PyPI automatically

## Project Structure

```text
src/cowayaio/
├── __init__.py            # Public API exports
├── __version__.py         # Version string
├── client.py              # Public CowayClient entry point
├── constants.py           # API constants
├── enums.py               # Enumerations
├── exceptions.py          # Public exception hierarchy
├── py.typed               # PEP 561 marker
├── account/               # Authentication and maintenance handling
├── devices/               # Purifier control, models, parsing, data fetches
└── transport/             # Shared HTTP client/session layer
```

## License

[MIT](LICENSE), originally authored by [RobertD502](https://github.com/RobertD502)
