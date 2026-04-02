# Project Brief

- Last Updated: 2026-04-01 21:17:10 -04:00
- Version: v1.2
- Last Change Summary: Updated the project focus to reflect a clean targeted verification baseline entering Phase 4 production-readiness work.
- Related Changes: `productContext.md`, `activeContext.md`, `systemPatterns.md`, `techContext.md`, `progress.md`, `interactionHistory.md`

## Overview

[RECONSTRUCTED] PolyBot is a Python-based Polymarket trading bot targeting the global CLOB on Polygon/USDC. The project goal is to evolve from a prototype into a production-ready, safety-aware automated trading system with multiple strategies, robust execution controls, telemetry, and deployment hygiene.

## Core Goals

1. Trade Polymarket markets through the official CLOB client.
2. Support multiple strategies behind a shared execution/risk layer.
3. Default to safe operation with `DRY_RUN=true` and strong circuit-breaker/risk controls.
4. Maintain correct accounting for orders, trades, and positions before any live rollout.
5. Provide operational visibility via logs, dashboard, health checks, and task-oriented verification.

## Success Metrics

- **Primary success metric:** deployment readiness
- **Secondary success metric:** profitability

## Target Milestones

- **First target milestone:** small live deployment
- **Secondary target milestone:** profitability

## In-Scope Capabilities

- Market discovery from Gamma or pinned config.
- Strategy execution for momentum, logical arb, AMM, AI arb, and copy trading.
- Order execution through `ExecutionEngine` and `PolyClient`.
- Local ledger using SQLite/SQLModel.
- Optional auto-claim/redemption and health-check endpoints.

## Current Project Focus

[RECONSTRUCTED] Current roadmap focus is **Phase 4: production readiness**. Phase 3 extraction/refactor work is complete, part of Phase 4 operational stability is already in place (websocket deduplication, strategy-safe callback wrappers, execution telemetry), and the targeted regression baseline is now clean again. The next work is the formal production-readiness checklist: integration harnesses, operational tooling, dry-run validation, and deployment documentation.

## Constraints

- Production trading safety is more important than feature speed.
- Live deployment should only happen after dry-run validation and accounting correctness.
- Polymarket identity handling must distinguish market-level `condition_id` from outcome-level `token_id`.

## Confirmed Scope Direction

The following are all confirmed as **in scope and necessary**:

- AI arbitrage
- copy trading
- AMM
- auto-claim
- live deployment
