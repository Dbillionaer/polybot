# Tech Context

- Last Updated: 2026-04-01 21:17:10 -04:00
- Version: v1.1
- Last Change Summary: Updated the verification commands and caveats after clearing the legacy-ledger isolation failure and restoring a clean targeted regression baseline.
- Related Changes: `systemPatterns.md`, `interactionHistory.md`, `externalDocs.md`, `activeContext.md`, `progress.md`

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
- Phase 4 stability test: `python -m pytest tests/test_phase4_operational_stability.py -q`
- Legacy repair regression: `python -m pytest tests/test_legacy_ledger_repair.py -q`
- Combined Phase 3/remediation regressions: `python -m pytest tests/test_order_executor.py tests/test_fill_reconciler.py tests/test_telemetry_collector.py tests/test_execution_reconciliation.py tests/test_risk_pnl_plumbing.py tests/test_client.py tests/test_strategy_momentum.py tests/test_strategy_ai_arb.py tests/test_negrisk.py -q`

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

- Existing SQLite files may still contain stale data from pre-fix accounting logic, so repair/audit flows remain important before live deployment.
- Lint, typecheck, and exact coverage status were not re-verified during this memory-bank sync.
- The targeted verification baseline is green, but Phase 4 production-readiness tooling is still missing: integration harness, JSON logging option, backup/export utilities, disaster-recovery runbook, and dry-run documentation.
