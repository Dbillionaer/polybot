# System Patterns

- Last Updated: 2026-03-30 00:00:00 UTC
- Version: v1.2
- Last Change Summary: Added websocket deduplication and execution telemetry patterns from Phase 4.
- Related Changes: `projectbrief.md`, `techContext.md`, `activeContext.md`

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
- `ExecutionEngine` checks circuit breaker, risk manager, spread, then order submission.
- Strategies should rely on shared engine services rather than direct order posting.

### 2. Correct identity model
- `condition_id` = market family / market identity.
- `token_id` = specific YES/NO or outcome token.
- Market metadata is registered in `ExecutionEngine` for correct fill accounting.

### 3. Accepted vs filled separation
- CLOB acceptance does **not** mean trade execution.
- Accepted orders are stored in `pending_orders`.
- Reconciliation polls `get_order(order_id)` and records only confirmed fill deltas.

### 4. Fill-driven ledger updates
- `record_trade()` + `update_position()` are only called on confirmed fills.
- SELL fills reduce the same token position and can transition status to `CLOSED`.

### 5. Ledger repair by trade replay
- Position history is treated as reconstructible state; trade rows are the stronger ledger source.
- Legacy repair audits suspicious position rows and rebuilds positions from trade history only when token metadata is sufficient.

### 6. Runtime PnL propagation
- `update_position()` now emits realized PnL on SELL fills.
- `ExecutionEngine` refreshes MTM from live order-book mids for open positions.
- `RiskManager` maintains realized + MTM snapshot state.
- `CircuitBreaker` observes total-PnL deltas instead of only ad hoc loss events.

### 7. Strategy-owned resting quotes
- AMM strategy owns its resting quote IDs by token and side.
- Quote refresh uses cancel/replace instead of blind reposting.
- Logical arbitrage evaluates mutually exclusive condition families rather than global market sums.

### 8. Operational background services
- APScheduler handles periodic auto-redeem.
- Background reconciliation thread polls pending orders in live mode.
- Shutdown path should stop websocket and reconciliation thread cleanly.

### 9. Deduplicated websocket fan-out
- `PolyWebSocket` now deduplicates `(channel, market)` subscriptions before enqueue/send.
- Callback registration is also deduplicated, including stable handling of bound methods.
- Strategy callback wrappers prevent callback crashes from disappearing silently by forwarding them into execution telemetry.

### 10. Execution telemetry surface
- `ExecutionEngine` now maintains runtime telemetry snapshots for operators/UI consumers.
- Current metrics include fill latency, adverse slippage, and per-strategy order attempts / accepted orders / fill events / error counts.
- Telemetry is intentionally in-memory and lightweight; it is not yet persisted historically.

## Known Architectural Gaps

- Backtest/simulation tooling is still pending.