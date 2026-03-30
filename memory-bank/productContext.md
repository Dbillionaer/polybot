# Product Context

- Last Updated: 2026-03-30 00:00:00 UTC
- Version: v1.1
- Last Change Summary: Added validated success priority and confirmed that all major strategy/integration tracks remain in scope.
- Related Changes: `projectbrief.md`, `activeContext.md`, `progress.md`

## Why This Project Exists

[RECONSTRUCTED] PolyBot exists to automate Polymarket trading workflows that are too fast, repetitive, or operationally fragile to manage manually. It combines market discovery, execution, strategy logic, and operational controls in one runtime.

## Product Priority

- Primary product priority: achieve **deployment readiness**.
- Secondary product priority: achieve **profitability** after readiness is credible.
- First operational target: **small live deployment**.

## Problems It Solves

- Manual Polymarket trading is slow and inconsistent for multi-market monitoring.
- Strategy experiments need a shared execution and risk layer instead of ad hoc scripts.
- Production trading requires monitoring, failure containment, and reconciliation beyond simple API order posting.
- Polymarket-specific market structures such as NegRisk require specialized handling.

## Intended User Experience

- Start the bot from a config-driven entry point (`main.py`).
- Run safely in dry-run by default.
- Turn strategies on/off via environment variables rather than code edits.
- Observe runtime state through dashboard, logs, and health endpoints.
- Trust that accepted orders are reconciled into real fills before positions/PnL are treated as real.
- Progress from dry-run confidence into a controlled small live deployment.

## Operational UX Goals

- Safe-by-default startup.
- Clear logging for order lifecycle and failures.
- Reproducible targeted verification after code changes.
- Predictable recovery path after restarts or interruptions.

## Current Product Risks

- Legacy database rows may still reflect old identity/accounting semantics.
- Realized/mark-to-market PnL plumbing is not yet fully wired into risk and breaker logic.
- Some README claims are ahead of fully production-ready execution behavior.

## Confirmed In-Scope Capabilities

- AI arb
- copy trading
- AMM
- auto-claim
- live deployment