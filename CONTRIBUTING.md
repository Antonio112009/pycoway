# Contributing to cowayaio

Thank you for your interest in contributing! This document explains the workflow and guidelines.

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable release branch. Protected — no direct pushes. |
| `development` | Integration branch. All feature work merges here first. |
| `feature/*` | Short-lived branches for individual changes. |

## Workflow

1. **Create a feature branch** from `development`:
   ```bash
   git checkout development && git pull
   git checkout -b feature/my-change
   ```

2. **Make your changes**, commit, and push:
   ```bash
   git push origin feature/my-change
   ```

3. **Open a Pull Request** targeting `development`. CI (lint + tests) must pass before merging.

4. **When ready to release**, open a Pull Request from `development` → `main`. CI runs again.

5. **On merge to `main`**, a release is created automatically:
   - Version in `__version__.py` is bumped (patch by default)
   - A git tag and GitHub release are created
   - Add a `minor` or `major` label to the PR to control the bump type

## Development Setup

```bash
# Clone the repo
git clone https://github.com/Antonio112009/cowayaio.git
cd cowayaio

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

## Linting

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check .
ruff format --check .
```

## Code Style

- Python 3.11+ — use modern syntax (type unions with `|`, `StrEnum`, etc.)
- Line length: 100 characters
- Follow existing patterns in the codebase
- Add tests for new functionality

## Project Structure

```
src/cowayaio/
├── client.py              # Public CowayClient entry point
├── constants.py           # Enums for endpoints, parameters, headers
├── exceptions.py          # Exception hierarchy
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

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
