# PolyBot 2026 — Comprehensive Improvement Plan

**Plan Version:** 1.0  
**Created:** 2026-03-30  
**Based On:** assessment1.md  
**Target Completion:** 2026-06-30 (13 weeks)  
**Plan Owner:** Engineering Team  

---

## Top Three Issues Identified in Assessment

Based on the independent assessment, the three most critical gaps requiring immediate attention are:

### 1. Insufficient Test Coverage (~30%)
- **Impact:** Financial software with low test coverage poses significant risk of logic errors leading to monetary loss
- **Evidence:** 8 major modules have zero tests including all 3 untested strategies, core client, and NegRisk handler
- **Urgency:** Critical — must be addressed before any live deployment

### 2. No CI/CD Pipeline
- **Impact:** No automated quality gates; regression risk on every change; no security scanning
- **Evidence:** No `.github/workflows/` directory exists; no automated testing or linting
- **Urgency:** Critical — foundational infrastructure for safe development

### 3. ExecutionEngine God Object (731 lines)
- **Impact:** Difficult to maintain, test, and reason about; mixes order execution, reconciliation, and telemetry
- **Evidence:** Single file handles too many responsibilities
- **Urgency:** High — technical debt that compounds over time

---

## Executive Summary

This plan addresses the deficiencies identified in the independent assessment to bring PolyBot to production-ready status. The plan spans four phases over 13 weeks, prioritizing safety-critical improvements first.

**Goals:**
- Increase test coverage from ~30% to 70%+
- Establish CI/CD pipeline with automated quality gates
- Refactor ExecutionEngine into maintainable components
- Add input validation and security hardening
- Prepare for controlled live deployment with <$500 USDC

**Success Criteria:**
- All CI/CD checks passing
- Test coverage ≥70%
- Zero high-severity security findings
- Successful 7-day dry-run with no errors
- Controlled live deployment with <$500 USDC

---

## Root-Cause and Impact Analysis

### Issue 1: Low Test Coverage (Score: 4/10)

**Root Causes:**
- Testing was deprioritized during feature development
- No test infrastructure established early (no conftest.py, no fixtures)
- Duplicate mock implementations suggest lack of shared testing utilities
- Phase-based test naming indicates tests were written reactively

**Impact:**
- High risk of logic errors in PnL calculations (financial loss)
- NegRisk redemption failures could strand winning positions
- Strategy behavior unverified under edge cases
- Refactoring is risky without test safety net

**Affected Components:**
- `strategies/ai_arb.py`, `strategies/momentum.py`, `strategies/copy_trading.py`
- `core/client.py`, `core/data.py`, `core/negrisk.py`, `core/auth.py`
- `main.py`

### Issue 2: No CI/CD Pipeline (Score: 3/10)

**Root Causes:**
- Single-developer project without team process requirements
- No GitHub repository structure established
- Manual testing approach

**Impact:**
- No automated quality gates on pull requests
- Regression risk on every change
- No security vulnerability scanning
- No enforcement of code style or type checking

**Affected Components:**
- All code changes lack automated verification
- Dependency updates are not scanned for vulnerabilities

### Issue 3: ExecutionEngine God Object (Score: 5/10 maintainability)

**Root Causes:**
- Organic growth during feature development
- Multiple responsibilities added without refactoring
- No code review process to enforce separation of concerns

**Impact:**
- Difficult to understand and modify
- Testing requires complex setup
- Changes have unpredictable side effects
- Lock contention under high-frequency trading

**Affected Components:**
- `engine/execution.py` (731 lines)

### Issue 4: Missing Input Validation (Score: 6/10 robustness)

**Root Causes:**
- Trust in upstream data sources
- Rapid development without defensive programming
- No schema validation layer

**Impact:**
- Malformed API responses could cause crashes or incorrect behavior
- Invalid order parameters could reach CLOB
- Market data parsing errors undetected

**Affected Components:**
- `core/client.py:97-150` (order parameters)
- `main.py:176-203` (market data parsing)

### Issue 5: Inconsistent Error Handling (Score: 6/10 reliability)

**Root Causes:**
- No established error handling patterns
- Mix of exception raising and None returns
- Silent error swallowing in alerting code

**Impact:**
- Failures may go undetected
- Debugging is difficult
- Circuit breaker may not trigger appropriately

**Affected Components:**
- `core/negrisk.py:49-50` (bare except)
- Various modules with inconsistent patterns

---

## Phased Roadmap

### Phase 1: Foundation (Weeks 1-3)
**Theme:** Establish CI/CD and Testing Infrastructure

**Objectives:**
- Create CI/CD pipeline with automated testing and linting
- Set up testing infrastructure with shared fixtures
- Add security scanning for dependencies
- Begin critical module testing

**Deliverables:**
- GitHub Actions workflow file
- `tests/conftest.py` with shared fixtures
- `pyproject.toml` with tool configurations
- Security scanning integration
- Tests for `core/negrisk.py`

**Milestones:**
- M1.1: CI/CD pipeline operational (Week 1)
- M1.2: Test infrastructure established (Week 2)
- M1.3: Security scanning integrated (Week 2)
- M1.4: NegRisk tests complete (Week 3)

### Phase 2: Quality Hardening (Weeks 4-7)
**Theme:** Increase Test Coverage and Add Input Validation

**Objectives:**
- Achieve 70% test coverage
- Add input validation for all external data
- Standardize error handling patterns
- Add property-based tests for numerical calculations

**Deliverables:**
- Tests for all 5 strategies
- Tests for `core/client.py`, `core/data.py`, `core/auth.py`
- Pydantic schemas for market data validation
- Input validation decorators
- Property-based tests for Kelly criterion and PnL

**Milestones:**
- M2.1: Strategy tests complete (Week 5)
- M2.2: Core module tests complete (Week 6)
- M2.3: Input validation implemented (Week 6)
- M2.4: 70% coverage achieved (Week 7)

### Phase 3: Architecture Improvement (Weeks 8-10)
**Theme:** Refactor ExecutionEngine and Improve Maintainability

**Objectives:**
- Split ExecutionEngine into focused components
- Consolidate duplicate mock implementations
- Add pre-commit hooks
- Fix datetime deprecation warnings

**Deliverables:**
- `engine/order_executor.py`
- `engine/fill_reconciler.py`
- `engine/telemetry_collector.py`
- Refactored `engine/execution.py` (orchestrator only)
- Unified mock library in `tests/mocks/`
- Pre-commit configuration

**Milestones:**
- M3.1: ExecutionEngine split complete (Week 9)
- M3.2: Mock consolidation complete (Week 9)
- M3.3: Pre-commit hooks active (Week 10)

### Phase 4: Production Readiness (Weeks 11-13)
**Theme:** Final Validation and Deployment Preparation

**Objectives:**
- Complete integration testing
- Add observability improvements
- Create backup/restore utilities
- Execute 7-day dry-run validation
- Prepare for controlled live deployment

**Deliverables:**
- Integration test suite with mock servers
- JSON logging option
- Backup/restore scripts
- Disaster recovery runbook
- Deployment checklist update

**Milestones:**
- M4.1: Integration tests passing (Week 11)
- M4.2: Observability improvements deployed (Week 12)
- M4.3: 7-day dry-run completed successfully (Week 13)

---

## Detailed Task List

### Phase 1 Tasks

#### Task 1.1: Create GitHub Actions CI/CD Pipeline
| Field | Value |
|-------|-------|
| **Title** | Create GitHub Actions CI/CD Pipeline |
| **Description** | Create `.github/workflows/ci.yml` with test matrix, linting, type checking, and security scanning |
| **Prerequisites** | None |
| **Acceptance Criteria** | - Workflow runs on push to main and pull requests<br>- Tests run on Python 3.10, 3.11, 3.12<br>- Ruff linting passes<br>- Mypy type checking passes<br>- Pip-audit security scan passes |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | DevOps Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-03-31 |
| **Due Date** | 2026-04-02 |

**Justification:** Assessment identified no CI/CD as a critical gap. This is foundational infrastructure for safe development.

#### Task 1.2: Create pyproject.toml Configuration
| Field | Value |
|-------|-------|
| **Title** | Create pyproject.toml Configuration |
| **Description** | Create `pyproject.toml` with ruff, black, mypy, and pytest configurations |
| **Prerequisites** | Task 1.1 |
| **Acceptance Criteria** | - `pyproject.toml` exists with all tool configurations<br>- `ruff check .` passes<br>- `black --check .` passes<br>- `mypy .` passes |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.1 |
| **Proposed Start** | 2026-04-02 |
| **Due Date** | 2026-04-03 |

**Justification:** Assessment noted no linter/formatter configuration. Standardizes code quality tools.

#### Task 1.3: Create Shared Test Fixtures
| Field | Value |
|-------|-------|
| **Title** | Create Shared Test Fixtures (conftest.py) |
| **Description** | Create `tests/conftest.py` with shared fixtures for database, client mocks, and test data |
| **Prerequisites** | Task 1.1 |
| **Acceptance Criteria** | - `tests/conftest.py` exists<br>- Fixtures for: in-memory database, mock PolyClient, mock WebSocket<br>- Existing tests refactored to use shared fixtures<br>- All tests pass with new fixtures |
| **Estimated Effort** | 6 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.1 |
| **Proposed Start** | 2026-04-03 |
| **Due Date** | 2026-04-05 |

**Justification:** Assessment identified duplicate mock implementations across tests. Consolidation improves maintainability.

#### Task 1.4: Add pytest-cov and Coverage Configuration
| Field | Value |
|-------|-------|
| **Title** | Add pytest-cov and Coverage Configuration |
| **Description** | Configure pytest-cov with minimum coverage threshold and coverage reporting |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - `pytest --cov` generates coverage report<br>- Minimum coverage threshold set to 50% (interim)<br>- Coverage report uploaded to CI artifacts |
| **Estimated Effort** | 2 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-05 |
| **Due Date** | 2026-04-06 |

**Justification:** Assessment noted no coverage measurement. Enables tracking progress toward 70% target.

#### Task 1.5: Add Security Scanning with pip-audit
| Field | Value |
|-------|-------|
| **Title** | Add Security Scanning with pip-audit |
| **Description** | Integrate pip-audit into CI pipeline and requirements.txt |
| **Prerequisites** | Task 1.1 |
| **Acceptance Criteria** | - `pip-audit -r requirements.txt` runs in CI<br>- Pipeline fails on known vulnerabilities<br>- Security report generated as artifact |
| **Estimated Effort** | 2 hours |
| **Assigned Owner** | DevOps Engineer |
| **Dependencies** | Task 1.1 |
| **Proposed Start** | 2026-04-06 |
| **Due Date** | 2026-04-07 |

**Justification:** Assessment identified no dependency vulnerability scanning as a medium-severity security concern.

#### Task 1.6: Write Tests for core/negrisk.py
| Field | Value |
|-------|-------|
| **Title** | Write Tests for core/negrisk.py |
| **Description** | Create `tests/test_negrisk.py` with comprehensive tests for NegRisk adapter handling |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Tests for `is_neg_risk_market()`<br>- Tests for `ensure_adapter_approval()`<br>- Tests for `convertToUSDC()` routing<br>- Tests for error handling paths<br>- Coverage for negrisk.py ≥80% |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-07 |
| **Due Date** | 2026-04-11 |

**Justification:** Assessment identified NegRisk module as critical for mainnet and having zero tests.

### Phase 2 Tasks

#### Task 2.1: Write Tests for strategies/momentum.py
| Field | Value |
|-------|-------|
| **Title** | Write Tests for strategies/momentum.py |
| **Description** | Create `tests/test_strategy_momentum.py` with tests for momentum strategy |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Tests for `on_market_update()` callback<br>- Tests for orderbook imbalance calculation<br>- Tests for volume surge detection<br>- Tests for trade execution flow<br>- Coverage for momentum.py ≥80% |
| **Estimated Effort** | 6 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-14 |
| **Due Date** | 2026-04-16 |

**Justification:** Assessment identified momentum strategy as having zero tests.

#### Task 2.2: Write Tests for strategies/ai_arb.py
| Field | Value |
|-------|-------|
| **Title** | Write Tests for strategies/ai_arb.py |
| **Description** | Create `tests/test_strategy_ai_arb.py` with tests for AI arbitrage strategy |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Tests for Grok API integration (mocked)<br>- Tests for probability edge calculation<br>- Tests for 12% threshold logic<br>- Tests for error handling when API unavailable<br>- Coverage for ai_arb.py ≥80% |
| **Estimated Effort** | 6 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-16 |
| **Due Date** | 2026-04-18 |

**Justification:** Assessment identified AI arb strategy as having zero tests.

#### Task 2.3: Write Tests for strategies/copy_trading.py
| Field | Value |
|-------|-------|
| **Title** | Write Tests for strategies/copy_trading.py |
| **Description** | Create `tests/test_strategy_copy_trading.py` with tests for copy trading strategy |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Tests for Falcon API integration (mocked)<br>- Tests for whale tracking logic<br>- Tests for mirror execution<br>- Tests for size multiplier calculation<br>- Coverage for copy_trading.py ≥80% |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-18 |
| **Due Date** | 2026-04-21 |

**Justification:** Assessment identified copy trading strategy as having zero tests.

#### Task 2.4: Write Tests for core/client.py
| Field | Value |
|-------|-------|
| **Title** | Write Tests for core/client.py |
| **Description** | Create `tests/test_client.py` with tests for PolyClient wrapper |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Tests for `post_limit_order()`<br>- Tests for `get_order_book()`<br>- Tests for `get_balance()`<br>- Tests for error handling<br>- Coverage for client.py ≥80% |
| **Estimated Effort** | 6 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-21 |
| **Due Date** | 2026-04-23 |

**Justification:** Assessment identified core client as having zero tests.

#### Task 2.5: Write Tests for core/data.py
| Field | Value |
|-------|-------|
| **Title** | Write Tests for core/data.py |
| **Description** | Create `tests/test_data.py` with tests for Gamma API and auto-claim functionality |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Tests for `get_markets()` from Gamma API<br>- Tests for `claim_rewards()`<br>- Tests for Falcon analytics integration<br>- Tests for error handling<br>- Coverage for data.py ≥80% |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-04-23 |
| **Due Date** | 2026-04-28 |

**Justification:** Assessment identified core data module as having zero tests.

#### Task 2.6: Add Input Validation for Order Parameters
| Field | Value |
|-------|-------|
| **Title** | Add Input Validation for Order Parameters |
| **Description** | Add validation functions for price and size in `core/client.py` and `engine/execution.py` |
| **Prerequisites** | Task 2.4 |
| **Acceptance Criteria** | - `validate_price(price)` raises ValueError if not in (0, 1)<br>- `validate_size(size, bankroll)` raises ValueError if invalid<br>- Validation called before order submission<br>- Tests for validation functions |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 2.4 |
| **Proposed Start** | 2026-04-28 |
| **Due Date** | 2026-04-30 |

**Justification:** Assessment identified no bounds checking on price/size inputs as a high-severity security concern.

#### Task 2.7: Add Pydantic Schemas for Market Data
| Field | Value |
|-------|-------|
| **Title** | Add Pydantic Schemas for Market Data |
| **Description** | Create Pydantic models for Gamma API responses and validate at parse time |
| **Prerequisites** | None |
| **Acceptance Criteria** | - `schemas/market.py` with MarketData, Outcome schemas<br>- Validation applied in `main.py:176-203`<br>- Invalid data raises descriptive error<br>- Tests for schema validation |
| **Estimated Effort** | 6 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-04-30 |
| **Due Date** | 2026-05-02 |

**Justification:** Assessment identified market data parsed without schema validation as a robustness concern.

#### Task 2.8: Add Property-Based Tests for Kelly Criterion
| Field | Value |
|-------|-------|
| **Title** | Add Property-Based Tests for Kelly Criterion |
| **Description** | Use hypothesis library to add property-based tests for Kelly sizing and PnL calculations |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - Property tests for `calculate_kelly_size()`<br>- Property tests for PnL calculations<br>- Tests verify mathematical properties (non-negative, bounded)<br>- Tests run in CI |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-05-02 |
| **Due Date** | 2026-05-05 |

**Justification:** Assessment identified no property-based testing for numerical calculations as a correctness concern.

#### Task 2.9: Standardize Error Handling Patterns
| Field | Value |
|-------|-------|
| **Title** | Standardize Error Handling Patterns |
| **Description** | Replace bare except clauses, establish consistent error propagation pattern |
| **Prerequisites** | None |
| **Acceptance Criteria** | - No bare `except Exception: pass` in codebase<br>- Error handling pattern documented<br>- Telegram failures logged instead of silently ignored<br>- Tests for error paths |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-05-05 |
| **Due Date** | 2026-05-07 |

**Justification:** Assessment identified bare except clauses and inconsistent error propagation as reliability concerns.

### Phase 3 Tasks

#### Task 3.1: Extract OrderExecutor from ExecutionEngine
| Field | Value |
|-------|-------|
| **Title** | Extract OrderExecutor from ExecutionEngine |
| **Description** | Create `engine/order_executor.py` with order submission and cancellation logic |
| **Prerequisites** | Phase 2 complete |
| **Acceptance Criteria** | - `OrderExecutor` class handles order submission<br>- Dry-run logic encapsulated<br>- Spread check logic encapsulated<br>- All existing tests pass<br>- New unit tests for OrderExecutor |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | Senior Backend Engineer |
| **Dependencies** | Phase 2 complete (test safety net) |
| **Proposed Start** | 2026-05-19 |
| **Due Date** | 2026-05-23 |

**Justification:** Assessment identified ExecutionEngine as a 731-line god object requiring refactoring.

#### Task 3.2: Extract FillReconciler from ExecutionEngine
| Field | Value |
|-------|-------|
| **Title** | Extract FillReconciler from ExecutionEngine |
| **Description** | Create `engine/fill_reconciler.py` with fill reconciliation and position update logic |
| **Prerequisites** | Task 3.1 |
| **Acceptance Criteria** | - `FillReconciler` class handles fill polling<br>- Position updates encapsulated<br>- Partial fill logic encapsulated<br>- All existing tests pass<br>- New unit tests for FillReconciler |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | Senior Backend Engineer |
| **Dependencies** | Task 3.1 |
| **Proposed Start** | 2026-05-23 |
| **Due Date** | 2026-05-28 |

**Justification:** Assessment identified ExecutionEngine as mixing too many responsibilities.

#### Task 3.3: Extract TelemetryCollector from ExecutionEngine
| Field | Value |
|-------|-------|
| **Title** | Extract TelemetryCollector from ExecutionEngine |
| **Description** | Create `engine/telemetry_collector.py` with fill latency, slippage, and error tracking |
| **Prerequisites** | Task 3.2 |
| **Acceptance Criteria** | - `TelemetryCollector` class handles metrics collection<br>- Thread-safe telemetry storage<br>- `get_telemetry_snapshot()` moved to collector<br>- All existing tests pass<br>- New unit tests for TelemetryCollector |
| **Estimated Effort** | 6 hours |
| **Assigned Owner** | Senior Backend Engineer |
| **Dependencies** | Task 3.2 |
| **Proposed Start** | 2026-05-28 |
| **Due Date** | 2026-05-30 |

**Justification:** Assessment identified telemetry as a separate concern from execution.

#### Task 3.4: Refactor ExecutionEngine as Orchestrator
| Field | Value |
|-------|-------|
| **Title** | Refactor ExecutionEngine as Orchestrator |
| **Description** | Reduce ExecutionEngine to orchestration layer composing extracted components |
| **Prerequisites** | Tasks 3.1, 3.2, 3.3 |
| **Acceptance Criteria** | - `engine/execution.py` reduced to ~200 lines<br>- Composes OrderExecutor, FillReconciler, TelemetryCollector<br>- Public API unchanged<br>- All existing tests pass |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Senior Backend Engineer |
| **Dependencies** | Tasks 3.1, 3.2, 3.3 |
| **Proposed Start** | 2026-05-30 |
| **Due Date** | 2026-06-02 |

**Justification:** Assessment target of reducing ExecutionEngine from 731 to ~200 lines.

#### Task 3.5: Consolidate Mock Implementations
| Field | Value |
|-------|-------|
| **Title** | Consolidate Mock Implementations |
| **Description** | Create `tests/mocks/` directory with unified mock classes |
| **Prerequisites** | Task 1.3 |
| **Acceptance Criteria** | - `tests/mocks/client.py` with MockPolyClient<br>- `tests/mocks/websocket.py` with MockWebSocket<br>- `tests/mocks/risk.py` with MockRiskManager<br>- All tests refactored to use unified mocks<br>- No duplicate mock implementations |
| **Estimated Effort** | 4 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.3 |
| **Proposed Start** | 2026-06-02 |
| **Due Date** | 2026-06-04 |

**Justification:** Assessment identified duplicate mock implementations across tests as technical debt.

#### Task 3.6: Add Pre-commit Hooks
| Field | Value |
|-------|-------|
| **Title** | Add Pre-commit Hooks |
| **Description** | Create `.pre-commit-config.yaml` with ruff, black, mypy hooks |
| **Prerequisites** | Task 1.2 |
| **Acceptance Criteria** | - `.pre-commit-config.yaml` exists<br>- Hooks for: ruff, black, mypy, trailing whitespace<br>- `pre-commit install` documented in README<br>- All hooks pass on current code |
| **Estimated Effort** | 2 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 1.2 |
| **Proposed Start** | 2026-06-04 |
| **Due Date** | 2026-06-05 |

**Justification:** Assessment noted no pre-commit hooks as a maintainability gap.

#### Task 3.7: Fix datetime.utcnow() Deprecation Warnings
| Field | Value |
|-------|-------|
| **Title** | Fix datetime.utcnow() Deprecation Warnings |
| **Description** | Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` throughout codebase |
| **Prerequisites** | None |
| **Acceptance Criteria** | - No `datetime.utcnow()` calls in codebase<br>- All uses replaced with timezone-aware alternative<br>- Tests pass on Python 3.13<br>- No deprecation warnings |
| **Estimated Effort** | 2 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-06-05 |
| **Due Date** | 2026-06-06 |

**Justification:** Assessment identified datetime.utcnow() deprecation warnings as a known limitation.

### Phase 4 Tasks

#### Task 4.1: Create Mock CLOB Server for Integration Tests
| Field | Value |
|-------|-------|
| **Title** | Create Mock CLOB Server for Integration Tests |
| **Description** | Create HTTP mock server simulating Polymarket CLOB API responses |
| **Prerequisites** | Phase 3 complete |
| **Acceptance Criteria** | - `tests/integration/mock_clob_server.py` exists<br>- Mocks order submission, cancellation, balance endpoints<br>- Configurable responses for error scenarios<br>- Integration tests use mock server |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Phase 3 complete |
| **Proposed Start** | 2026-06-09 |
| **Due Date** | 2026-06-12 |

**Justification:** Assessment recommended integration tests with mock CLOB server.

#### Task 4.2: Create Integration Test Suite
| Field | Value |
|-------|-------|
| **Title** | Create Integration Test Suite |
| **Description** | Create `tests/integration/` with full order lifecycle tests |
| **Prerequisites** | Task 4.1 |
| **Acceptance Criteria** | - `tests/integration/test_order_lifecycle.py`<br>- Tests for: order submission, fill, position update, close<br>- Tests for: circuit breaker triggering<br>- Tests for: error recovery<br>- All integration tests pass |
| **Estimated Effort** | 8 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | Task 4.1 |
| **Proposed Start** | 2026-06-12 |
| **Due Date** | 2026-06-16 |

**Justification:** Assessment identified no integration tests as a critical gap.

#### Task 4.3: Add JSON Logging Option
| Field | Value |
|-------|-------|
| **Title** | Add JSON Logging Option |
| **Description** | Add environment variable to enable structured JSON logging |
| **Prerequisites** | None |
| **Acceptance Criteria** | - `LOG_FORMAT=json` environment variable supported<br>- JSON logs include: timestamp, level, message, context<br>- Backward compatible with current text format<br>- Documented in .env_example |
| **Estimated Effort** | 3 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-06-16 |
| **Due Date** | 2026-06-17 |

**Justification:** Assessment recommended structured logging for observability.

#### Task 4.4: Create Database Backup Script
| Field | Value |
|-------|-------|
| **Title** | Create Database Backup Script |
| **Description** | Create `scripts/backup_db.py` for SQLite backup and rotation |
| **Prerequisites** | None |
| **Acceptance Criteria** | - Script creates timestamped backup of polybot.db<br>- Configurable retention period<br>- Can be run via cron/systemd timer<br>- Documented in README |
| **Estimated Effort** | 3 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-06-17 |
| **Due Date** | 2026-06-18 |

**Justification:** Assessment identified database corruption as a risk without backup utilities.

#### Task 4.5: Create Position Export Utility
| Field | Value |
|-------|-------|
| **Title** | Create Position Export Utility |
| **Description** | Create `scripts/export_positions.py` for CSV/JSON export of trade history |
| **Prerequisites** | None |
| **Acceptance Criteria** | - Exports positions and trades to CSV<br>- Exports to JSON option<br>- Includes all relevant fields<br>- Documented in README |
| **Estimated Effort** | 2 hours |
| **Assigned Owner** | Backend Engineer |
| **Dependencies** | None |
| **Proposed Start** | 2026-06-18 |
| **Due Date** | 2026-06-19 |

**Justification:** Assessment noted no export formats for trade history.

#### Task 4.6: Create Disaster Recovery Runbook
| Field | Value |
|-------|-------|
| **Title** | Create Disaster Recovery Runbook |
| **Description** | Create `docs/disaster_recovery.md` with recovery procedures |
| **Prerequisites** | Tasks 4.4, 4.5 |
| **Acceptance Criteria** | - Documented procedures for: database corruption, position drift, API key rotation<br>- Step-by-step recovery instructions<br>- Contact information for escalations<br>- Linked from README |
| **Estimated Effort** | 3 hours |
| **Assigned Owner** | Engineering Lead |
| **Dependencies** | Tasks 4.4, 4.5 |
| **Proposed Start** | 2026-06-19 |
| **Due Date** | 2026-06-20 |

**Justification:** Assessment recommended disaster recovery runbook.

#### Task 4.7: Execute 7-Day Dry-Run Validation
| Field | Value |
|-------|-------|
| **Title** | Execute 7-Day Dry-Run Validation |
| **Description** | Run bot in dry-run mode for 7 days with monitoring |
| **Prerequisites** | All Phase 1-4 tasks complete |
| **Acceptance Criteria** | - Bot runs continuously for 7 days<br>- Zero ERROR or CRITICAL log lines<br>- Strategy fires visible [DRY-RUN] log lines<br>- Circuit breaker does not trip<br>- Market discovery finds ≥5 markets |
| **Estimated Effort** | 2 hours setup + 7 days monitoring |
| **Assigned Owner** | Engineering Lead |
| **Dependencies** | All Phase 1-4 tasks |
| **Proposed Start** | 2026-06-20 |
| **Due Date** | 2026-06-27 |

**Justification:** Assessment README specifies 7-day dry-run as Phase 1 of go-live checklist.

#### Task 4.8: Update README with New Procedures
| Field | Value |
|-------|-------|
| **Title** | Update README with New Procedures |
| **Description** | Update README with CI/CD badges, new scripts, and updated go-live checklist |
| **Prerequisites** | All tasks complete |
| **Acceptance Criteria** | - CI/CD status badges added<br>- New scripts documented<br>- Go-live checklist updated with new requirements<br>- Version bumped to v1.3 |
| **Estimated Effort** | 2 hours |
| **Assigned Owner** | Engineering Lead |
| **Dependencies** | All tasks |
| **Proposed Start** | 2026-06-27 |
| **Due Date** | 2026-06-30 |

**Justification:** Documentation must reflect all improvements made.

---

## Prioritized, Dependency-Aware Task List

### Critical Path (Must Complete in Order)

```
Week 1: Task 1.1 (CI/CD) → Task 1.2 (pyproject.toml)
Week 2: Task 1.3 (conftest.py) → Task 1.4 (coverage) → Task 1.5 (security)
Week 3: Task 1.6 (negrisk tests)
Week 4-5: Task 2.1-2.3 (strategy tests - parallel)
Week 5-6: Task 2.4-2.5 (core tests - parallel)
Week 6: Task 2.6 (input validation) + Task 2.7 (schemas)
Week 7: Task 2.8 (property tests) + Task 2.9 (error handling)
Week 8-9: Task 3.1-3.4 (ExecutionEngine refactor - sequential)
Week 9: Task 3.5 (mocks) + Task 3.6 (pre-commit) + Task 3.7 (datetime)
Week 10-11: Task 4.1-4.2 (integration tests)
Week 12: Task 4.3-4.6 (observability + utilities)
Week 13: Task 4.7 (dry-run) → Task 4.8 (README)
```

### Parallel Execution Opportunities

| Week | Parallel Tasks |
|------|----------------|
| 4-5 | Tasks 2.1, 2.2, 2.3 (strategy tests) |
| 5-6 | Tasks 2.4, 2.5 (core tests) |
| 6 | Tasks 2.6, 2.7 (validation) |
| 7 | Tasks 2.8, 2.9 (testing + error handling) |
| 9 | Tasks 3.5, 3.6, 3.7 (cleanup tasks) |
| 12 | Tasks 4.3, 4.4, 4.5, 4.6 (utilities) |

---

## Risk and Mitigation Section

### Implementation Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **ExecutionEngine refactoring breaks existing behavior** | Medium | High | Complete Phase 2 test coverage first; refactoring with test safety net |
| **Mock server doesn't match real CLOB behavior** | Medium | Medium | Use recorded CLOB responses for mock; validate against testnet |
| **Test coverage target not met** | Low | Medium | Prioritize critical modules; accept 60% as interim target |
| **CI/CD pipeline too slow** | Low | Low | Parallelize test execution; cache dependencies |
| **Team capacity constraints** | Medium | Medium | Prioritize critical path; defer nice-to-have items |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Live deployment before ready** | Low | Catastrophic | Strict go-live checklist; dry-run validation gate |
| **Database migration issues** | Low | Medium | Test migrations in CI; backup before migration |
| **Dependency vulnerability discovered** | Medium | High | Weekly pip-audit scans; pin dependencies |
| **API breaking changes** | Low | High | Version pin py-clob-client; monitor upstream changelog |

### Contingency Plans

1. **If test coverage target not met by Week 7:**
   - Extend Phase 2 by 1 week
   - Prioritize NegRisk and strategy tests
   - Accept 60% coverage as interim threshold

2. **If ExecutionEngine refactoring causes regressions:**
   - Revert to monolithic implementation
   - Add characterization tests
   - Retry refactoring in smaller increments

3. **If 7-day dry-run fails:**
   - Analyze failure mode
   - Fix root cause
   - Restart 7-day count

---

## Resource and Tooling Plan

### Required Tools

| Tool | Purpose | Installation |
|------|---------|--------------|
| **pytest** | Test framework | `pip install pytest pytest-cov pytest-asyncio` |
| **hypothesis** | Property-based testing | `pip install hypothesis` |
| **ruff** | Linting | `pip install ruff` |
| **black** | Code formatting | `pip install black` |
| **mypy** | Type checking | `pip install mypy` |
| **pip-audit** | Security scanning | `pip install pip-audit` |
| **pre-commit** | Git hooks | `pip install pre-commit` |
| **responses** | HTTP mocking | `pip install responses` |
| **freezegun** | Time mocking | `pip install freezegun` |

### Infrastructure

| Resource | Purpose | Notes |
|----------|---------|-------|
| **GitHub Actions** | CI/CD | Free for public repos; 2000 min/month for private |
| **Python 3.10, 3.11, 3.12** | Test matrix | Test against all supported versions |
| **SQLite in-memory** | Test database | No additional infrastructure needed |

### Team Resources

| Role | Allocation | Responsibilities |
|------|------------|------------------|
| **DevOps Engineer** | 20% (Week 1-2) | CI/CD setup, security scanning |
| **Backend Engineer** | 80% (Week 1-13) | Testing, validation, refactoring |
| **Senior Backend Engineer** | 40% (Week 8-10) | ExecutionEngine refactoring |
| **Engineering Lead** | 10% (Week 12-13) | Dry-run validation, documentation |

---

## Change Management Plan

### Branch Strategy

```
main (protected)
  └── feature/TASK-1.1-cicd-pipeline
  └── feature/TASK-1.3-conftest
  └── feature/TASK-2.1-momentum-tests
  └── refactor/TASK-3.1-order-executor
  └── ...
```

### Pull Request Requirements

1. **All PRs must:**
   - Reference task number in title
   - Pass all CI checks
   - Have at least 1 approval
   - Not decrease test coverage

2. **For refactoring PRs (Phase 3):**
   - Require 2 approvals
   - Must include test updates
   - Performance comparison for hot paths

### Communication

| Event | Channel | Audience |
|-------|---------|----------|
| Phase start | Team meeting | All |
| Milestone complete | Slack update | Stakeholders |
| Blocking issues | Escalation to lead | Engineering Lead |
| Phase complete | Demo + retro | All |

### Documentation Updates

- Update `memory-bank/progress.md` after each phase
- Update `memory-bank/activeContext.md` weekly
- Update README after Phase 4

---

## Testing and QA Strategy

### Testing Scope

| Level | Coverage Target | Focus Areas |
|-------|-----------------|-------------|
| **Unit Tests** | 70%+ | All modules, edge cases, error paths |
| **Integration Tests** | Critical paths | Order lifecycle, fill reconciliation, circuit breaker |
| **Property Tests** | Numerical code | Kelly criterion, PnL calculations |
| **Dry-Run Validation** | 7 days | Full system behavior |

### Test Environments

| Environment | Purpose | Configuration |
|-------------|---------|---------------|
| **CI (GitHub Actions)** | Automated testing | Python 3.10/3.11/3.12, in-memory SQLite |
| **Local Development** | Developer testing | Local Python, local SQLite |
| **Dry-Run** | Pre-production validation | Production config, DRY_RUN=true |

### Test Automation

```yaml
# CI Pipeline Test Stages
stages:
  - lint: ruff, black --check, mypy
  - unit: pytest --cov --cov-fail-under=50
  - security: pip-audit, bandit
  - integration: pytest tests/integration/
```

### Entry Criteria (Per Phase)

| Phase | Entry Criteria |
|-------|----------------|
| Phase 1 | None |
| Phase 2 | Phase 1 complete, CI operational |
| Phase 3 | Phase 2 complete, 70% coverage |
| Phase 4 | Phase 3 complete, all tests passing |

### Exit Criteria (Per Phase)

| Phase | Exit Criteria |
|-------|---------------|
| Phase 1 | CI green, security scanning active, NegRisk tests passing |
| Phase 2 | 70% coverage, input validation complete |
| Phase 3 | ExecutionEngine refactored, pre-commit hooks active |
| Phase 4 | 7-day dry-run successful, documentation updated |

---

## Deployment and Rollout Plan

### Pre-Deployment Checklist

- [ ] All CI checks passing
- [ ] Test coverage ≥70%
- [ ] No high-severity security findings
- [ ] 7-day dry-run completed successfully
- [ ] Backup/restore tested
- [ ] Disaster recovery runbook reviewed

### Rollout Stages

| Stage | Duration | Configuration | Success Criteria |
|-------|----------|---------------|------------------|
| **Dry-Run** | 7 days | DRY_RUN=true | Zero errors, strategies fire |
| **Small Live** | 14 days | BANKROLL=400, DRY_RUN=false | No circuit breaker trips, PnL tracked |
| **Normal Operations** | Ongoing | Target bankroll | Monitoring active |

### Rollback Options

1. **Immediate halt:**
   ```bash
   sudo systemctl stop polybot
   ```

2. **Cancel all orders:**
   ```python
   from core.client import PolyClient
   client.clob.cancel_all()
   ```

3. **Revert to previous version:**
   ```bash
   git checkout v1.2
   sudo systemctl restart polybot
   ```

4. **Database restore:**
   ```bash
   cp backups/polybot.db.2026-03-30 polybot.db
   ```

### Monitoring During Rollout

| Metric | Healthy Threshold | Alert Threshold |
|--------|-------------------|-----------------|
| Circuit breaker trips | 0 | ≥2 in 1 hour |
| Error rate | <1% | >5% |
| Order success rate | >95% | <90% |
| USDC balance drain | <$1/hour | >$10/hour |
| Memory usage | <500MB | >1GB |

---

## Metrics and Success Criteria

### Key Performance Indicators

| KPI | Baseline | Target | Measurement |
|-----|----------|--------|-------------|
| **Test Coverage** | ~30% | 70% | pytest-cov report |
| **CI Build Time** | N/A | <10 min | GitHub Actions duration |
| **Security Findings** | Unknown | 0 high/critical | pip-audit report |
| **Code Quality Score** | Unknown | A rating | ruff analysis |
| **ExecutionEngine Lines** | 731 | ~200 | wc -l |

### Phase Success Criteria

| Phase | Success Criteria |
|-------|------------------|
| **Phase 1** | CI/CD operational, NegRisk tests passing, security scanning active |
| **Phase 2** | Test coverage ≥70%, input validation implemented |
| **Phase 3** | ExecutionEngine refactored, pre-commit hooks active |
| **Phase 4** | 7-day dry-run successful, documentation complete |

### Progress Tracking

| Tracking Method | Frequency | Owner |
|-----------------|-----------|-------|
| CI Dashboard | Real-time | Automated |
| Coverage Report | Per commit | Automated |
| Weekly Status Update | Weekly | Engineering Lead |
| Phase Completion Report | Per phase | Engineering Lead |

### Impact Measurement

| Impact Area | How Measured | Target |
|-------------|--------------|--------|
| **Deployment Confidence** | Successful dry-run days | 7 consecutive |
| **Code Maintainability** | Lines per module, cyclomatic complexity | <300 lines, <10 complexity |
| **Security Posture** | Vulnerability count | 0 high/critical |
| **Development Velocity** | PR merge time | <2 days average |

---

## Appendix: Task Summary Table

| Task ID | Title | Phase | Effort | Start | Due | Owner |
|---------|-------|-------|--------|-------|-----|-------|
| 1.1 | Create GitHub Actions CI/CD Pipeline | 1 | 8h | 2026-03-31 | 2026-04-02 | DevOps |
| 1.2 | Create pyproject.toml Configuration | 1 | 4h | 2026-04-02 | 2026-04-03 | Backend |
| 1.3 | Create Shared Test Fixtures | 1 | 6h | 2026-04-03 | 2026-04-05 | Backend |
| 1.4 | Add pytest-cov and Coverage Configuration | 1 | 2h | 2026-04-05 | 2026-04-06 | Backend |
| 1.5 | Add Security Scanning with pip-audit | 1 | 2h | 2026-04-06 | 2026-04-07 | DevOps |
| 1.6 | Write Tests for core/negrisk.py | 1 | 8h | 2026-04-07 | 2026-04-11 | Backend |
| 2.1 | Write Tests for strategies/momentum.py | 2 | 6h | 2026-04-14 | 2026-04-16 | Backend |
| 2.2 | Write Tests for strategies/ai_arb.py | 2 | 6h | 2026-04-16 | 2026-04-18 | Backend |
| 2.3 | Write Tests for strategies/copy_trading.py | 2 | 4h | 2026-04-18 | 2026-04-21 | Backend |
| 2.4 | Write Tests for core/client.py | 2 | 6h | 2026-04-21 | 2026-04-23 | Backend |
| 2.5 | Write Tests for core/data.py | 2 | 8h | 2026-04-23 | 2026-04-28 | Backend |
| 2.6 | Add Input Validation for Order Parameters | 2 | 4h | 2026-04-28 | 2026-04-30 | Backend |
| 2.7 | Add Pydantic Schemas for Market Data | 2 | 6h | 2026-04-30 | 2026-05-02 | Backend |
| 2.8 | Add Property-Based Tests for Kelly Criterion | 2 | 4h | 2026-05-02 | 2026-05-05 | Backend |
| 2.9 | Standardize Error Handling Patterns | 2 | 4h | 2026-05-05 | 2026-05-07 | Backend |
| 3.1 | Extract OrderExecutor from ExecutionEngine | 3 | 8h | 2026-05-19 | 2026-05-23 | Senior Backend |
| 3.2 | Extract FillReconciler from ExecutionEngine | 3 | 8h | 2026-05-23 | 2026-05-28 | Senior Backend |
| 3.3 | Extract TelemetryCollector from ExecutionEngine | 3 | 6h | 2026-05-28 | 2026-05-30 | Senior Backend |
| 3.4 | Refactor ExecutionEngine as Orchestrator | 3 | 4h | 2026-05-30 | 2026-06-02 | Senior Backend |
| 3.5 | Consolidate Mock Implementations | 3 | 4h | 2026-06-02 | 2026-06-04 | Backend |
| 3.6 | Add Pre-commit Hooks | 3 | 2h | 2026-06-04 | 2026-06-05 | Backend |
| 3.7 | Fix datetime.utcnow() Deprecation Warnings | 3 | 2h | 2026-06-05 | 2026-06-06 | Backend |
| 4.1 | Create Mock CLOB Server for Integration Tests | 4 | 8h | 2026-06-09 | 2026-06-12 | Backend |
| 4.2 | Create Integration Test Suite | 4 | 8h | 2026-06-12 | 2026-06-16 | Backend |
| 4.3 | Add JSON Logging Option | 4 | 3h | 2026-06-16 | 2026-06-17 | Backend |
| 4.4 | Create Database Backup Script | 4 | 3h | 2026-06-17 | 2026-06-18 | Backend |
| 4.5 | Create Position Export Utility | 4 | 2h | 2026-06-18 | 2026-06-19 | Backend |
| 4.6 | Create Disaster Recovery Runbook | 4 | 3h | 2026-06-19 | 2026-06-20 | Lead |
| 4.7 | Execute 7-Day Dry-Run Validation | 4 | 2h+7d | 2026-06-20 | 2026-06-27 | Lead |
| 4.8 | Update README with New Procedures | 4 | 2h | 2026-06-27 | 2026-06-30 | Lead |

---

## Next Steps: Begin Task 1.1

### Task 1.1: Create GitHub Actions CI/CD Pipeline

**Concrete Steps:**

1. **Create workflow directory:**
   ```bash
   mkdir -p .github/workflows
   ```

2. **Create CI workflow file:**
   Create `.github/workflows/ci.yml` with:
   - Test matrix for Python 3.10, 3.11, 3.12
   - Linting with ruff
   - Type checking with mypy
   - Security scanning with pip-audit
   - Test execution with pytest

3. **Create workflow content:**
   ```yaml
   name: CI
   
   on:
     push:
       branches: [main]
     pull_request:
       branches: [main]
   
   jobs:
     test:
       runs-on: ubuntu-latest
       strategy:
         matrix:
           python-version: ['3.10', '3.11', '3.12']
       
       steps:
       - uses: actions/checkout@v4
       
       - name: Set up Python ${{ matrix.python-version }}
         uses: actions/setup-python@v5
         with:
           python-version: ${{ matrix.python-version }}
       
       - name: Install dependencies
         run: |
           python -m pip install --upgrade pip
           pip install -r requirements.txt
           pip install pytest pytest-cov ruff mypy pip-audit
       
       - name: Lint with ruff
         run: ruff check .
       
       - name: Type check with mypy
         run: mypy . --ignore-missing-imports
       
       - name: Security audit
         run: pip-audit -r requirements.txt
       
       - name: Run tests
         run: pytest tests/ -v --cov=. --cov-report=xml
       
       - name: Upload coverage
         uses: codecov/codecov-action@v4
         with:
           file: ./coverage.xml
   ```

4. **Commit and push:**
   ```bash
   git add .github/workflows/ci.yml
   git commit -m "feat: add CI/CD pipeline with testing, linting, and security scanning"
   git push origin main
   ```

**Expected Outputs:**
- `.github/workflows/ci.yml` file created
- CI workflow runs on every push and PR
- Workflow includes test matrix, linting, type checking, security scanning

**Acceptance Criteria:**
- [ ] Workflow file exists at `.github/workflows/ci.yml`
- [ ] Workflow triggers on push to main and pull requests
- [ ] Tests run on Python 3.10, 3.11, 3.12
- [ ] Ruff linting passes
- [ ] Mypy type checking passes (with --ignore-missing-imports initially)
- [ ] Pip-audit security scan runs
- [ ] Coverage report generated

---

*Plan created 2026-03-30. Ready for engineering team execution.*
