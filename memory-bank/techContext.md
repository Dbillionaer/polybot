# Tech Context

- Last Updated: 2026-03-30 00:00:00 UTC
- Version: v1.0
- Last Change Summary: Captured stack, setup, and tooling conventions.
- Related Changes: `systemPatterns.md`, `interactionHistory.md`, `externalDocs.md`

## Core Stack

- Python 3.10+
- `py-clob-client==0.34.6`
- `sqlmodel==0.0.14`
- `apscheduler==3.10.4`
- `web3==6.11.3`
- `requests`, `python-dotenv`, `rich`, `loguru`

## Data / Runtime Infrastructure

- Exchange/API: Polymarket CLOB + Gamma
- Settlement chain: Polygon
- Persistence: SQLite via SQLModel
- UI: terminal dashboard in `ui/dashboard.py`

## Important Commands

- Run bot: `python main.py`
- Verify setup: `python verify_setup.py`
- Compile touched files: `python -m py_compile <files>`
- Reconciliation test: `python tests/test_execution_reconciliation.py`

## Environment Patterns

- Config is env-driven.
- Safety-critical flags include:
  - `DRY_RUN`
  - `CIRCUIT_BREAKER_ENABLED`
  - `MAX_SPREAD`
  - `ENABLE_ORDER_RECONCILIATION`
  - `ORDER_RECONCILIATION_INTERVAL_SECONDS`

## Tooling / Workflow Notes

- Prefer targeted tests and import/compile checks after edits.
- Use task lists for multi-step work.
- Use conservative patches around execution and accounting code.

## Interaction History Policy

- Rolling interaction history limit `N = 50` summarized entries.
- New entries should be appended for every user request and major action block.

## Current Technical Caveats

- Some code paths still use `datetime.utcnow()`, which emits deprecation warnings on Python 3.13.
- Existing SQLite files may contain stale data from pre-fix accounting logic.