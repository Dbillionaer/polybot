# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.0.0] - 2026-03-30

### Added

- CI/CD pipeline with GitHub Actions
  - Automated testing, linting, type checking, security scanning
  - Test matrix for Python 3.10, 3.11, 3.12

### Changed

- Updated py-clob-client from 0.34.6 to 0.34.6 (pinned)
- Added pydantic-settings for better configuration management
- Added explicit version pins for all dependencies
- Added development dependencies section for testing tools
- Added pre-commit configuration for code quality enforcement

### Fixed

- Resolved datetime deprecation warnings (datetime.utcnow() → datetime.now(timezone.utc))
  - Will be addressed in Phase 3

### Security

- Added pip-audit for dependency vulnerability scanning
- Added bandit for static security analysis (via CI)

- Added input validation for order parameters (Phase 2)

## [1.1.0] - 2026-03-30

### Added

- Comprehensive test coverage for all 5 strategies
- Input validation for order parameters
- Pydantic schemas for market data
- Property-based tests for numerical calculations
- Standardize error handling patterns

### Changed

- Refactored ExecutionEngine into modular components
  - OrderExecutor: handles order submission
  - FillReconciler: handles fill reconciliation
  - TelemetryCollector: handles metrics collection
- ExecutionEngine reduced to orchestration layer

### Fixed

- datetime.utcnow() deprecation warnings
- Duplicate mock implementations consolidated
- Pre-commit hooks added

### Security

- Input validation for all external data
- No bare except clauses

