# System Patterns

- Last Updated: 2026-04-01 20:32:23 -04:00
- Version: v1.3
- Last Change Summary: Synced architecture notes with the current branch reality: Phase 3 engine split is complete, and Phase 4 operational-stability work now includes websocket deduplication and execution telemetry seams.
- Related Changes: `projectbrief.md`, `techContext.md`, `activeContext.md`, `progress.md`

## High-Level Architecture

PolyBot is organized into four main layers:

1. **Core** — external integrations and persistence (`auth`, `client`, `data`, `database`, `ws`, `negrisk`, `retry`)
2. **Engine** — execution, risk, circuit breaker, backtesting
3. **Strategies** — momentum, logical arb, AMM, AI arb, copy trading
4. **UI / Ops** — Rich dashboard, logs, health checks, optional schedulers

## Runtime Flow

`main.py` orchestrates startup:

1. setup logger and DB
2. initialize authenticated `PolyClient`
3. create shared `CircuitBreaker` + `ExecutionEngine`
4. start WebSocket service
5. discover markets
6. register market metadata into execution layer
7. start optional services (health check, auto-claim, fill reconciler)
8. build enabled strategies
9. run dashboard or idle loop until shutdown

## Critical Implementation Patterns

### 1. Safety-first execution
- `DRY_RUN` is the master gate.
- `ExecutionEngine` is now primarily an orchestration facade over focused engine helpers.
- `OrderExecutor` owns order-book checks, spread validation, dry-run behavior, and live order submission/cancellation.
- Strategies should rely on shared engine services rather than direct order posting.

### 2. Correct identity model
- `condition_id` = market family / market identity.
- `token_id` = specific YES/NO or outcome token.
- Market metadata is registered in `ExecutionEngine` for correct fill accounting.

### 3. Accepted vs filled separation
- CLOB acceptance does **not** mean trade execution.
- Accepted orders are stored in `pending_orders` on `ExecutionEngine`.
- `FillReconciler` polls `get_order(order_id)` and records only confirmed fill deltas.

### 4. Fill-driven ledger updates
- `record_trade()` + `update_position()` are only called on confirmed fills.
- SELL fills reduce the same token position and can transition status to `CLOSED`.

### 5. Ledger repair by trade replay
- Position history is treated as reconstructible state; trade rows are the stronger ledger source.
- Legacy repair audits suspicious position rows and rebuilds positions from trade history only when token metadata is sufficient.

### 6. Runtime PnL propagation
- `update_position()` now emits realized PnL on SELL fills.
- `FillReconciler` refreshes MTM from live order-book mids for open positions.
- `RiskManager` maintains realized + MTM snapshot state.
- `CircuitBreaker` observes total-PnL deltas instead of only ad hoc loss events.

### 7. Strategy-owned resting quotes
- AMM strategy owns its resting quote IDs by token and side.
- Quote refresh uses cancel/replace instead of blind reposting.
- Logical arbitrage evaluates mutually exclusive condition families rather than global market sums.

### 8. Operational background services
- APScheduler handles periodic auto-redeem.
- `ExecutionEngine` still owns the background reconciliation thread lifecycle, but reconciliation work is delegated to `FillReconciler`.
- Shutdown path should stop websocket and reconciliation thread cleanly.

### 9. Deduplicated websocket fan-out
- `PolyWebSocket` now deduplicates `(channel, market)` subscriptions before enqueue/send.
- Callback registration is also deduplicated, including stable handling of bound methods.
- Strategy callback wrappers prevent callback crashes from disappearing silently by forwarding them into execution telemetry.

### 10. Execution telemetry surface
- `TelemetryCollector` maintains runtime telemetry snapshots for operators/UI consumers.
- `ExecutionEngine` exposes telemetry via facade methods (`get_telemetry_snapshot`, `record_strategy_error`).
- Current metrics include fill latency, adverse slippage, and per-strategy order attempts / accepted orders / fill events / error counts.
- Telemetry is intentionally in-memory and lightweight; it is not yet persisted historically.

### 11. Phase 3 engine split
- `ExecutionEngine` remains the public interface used by strategies and `main.py`.
- `OrderExecutor` owns submission-time safety checks and client-facing order execution.
- `FillReconciler` owns pending-order reconciliation, fill extraction/parsing, MTM refresh, and total-PnL observation.
- `TelemetryCollector` owns runtime telemetry aggregation and snapshots.
- `ExecutionEngine` still retains market metadata registration, pending-order storage, public lifecycle methods, and the DB-backed `_record_fill()` bridge.

## Known Architectural Gaps

- Backtest/simulation tooling is still pending.
- A mock CLOB server and broader integration-test harness are not yet implemented.
- JSON log output, backup/export utilities, and disaster-recovery runbooks are still missing from the production-readiness layer.
- Legacy-ledger repair still has one test-isolation leak in `tests/test_legacy_ledger_repair.py`, so the accounting regression set is not fully clean yet.
