# Operator Web UI

## Goal
Add a safe, localhost-first web admin UI/API for monitoring PolyBot and performing a small set of operator actions without restarting the bot.

## Tasks
- [ ] Add an operator controller that exposes runtime snapshot data and safe control actions -> Verify: controller returns bot status, positions, trades, telemetry, and action results in tests
- [ ] Add an HTTP admin server with a minimal HTML UI and JSON API -> Verify: local server serves `/` and `/api/status` successfully
- [ ] Protect mutating actions with an operator token and safe defaults -> Verify: POST actions fail without the token and succeed with it in tests
- [ ] Wire the operator server into `main.py` behind env flags -> Verify: bot can start with server disabled by default and enabled via env
- [ ] Add focused tests for status and control endpoints -> Verify: pytest passes for the new operator UI/API tests

## Done When
- [ ] PolyBot exposes a local operator web page plus JSON endpoints for status, cancel-all, and reconciliation control
