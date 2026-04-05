# Production Readiness: Phase 4 Implementation Plan


**What remains (go-live checklist):**
1. [x] Dockerfile + docker-compose
2. [ ] JSON structured logging (`LOG_FORMAT` env var)
3. [ ] Backup/export tooling (`scripts/` directory)
4. [ ] Disaster recovery runbook
7. [ ] Health endpoints via /api/status for the end of implementation sequence:
```
 | 3. **JSON logging** — Add `LOG_FORMAT` env var (`text`|`json`) to `core/logger.py`. No structural changes to existing log calls. |
2. **Docker** — Multi-stage build, healthcheck via `/api/status`, `restart: always`, volume mounts for data/ and logs/. |
3. **Backup/export** — `scripts/export_db.py`, `scripts/analyze_markets.py`, `scripts/backup.py`. Minimal effort. |
4. **Disaster recovery** — Runbook + operational script. Wipe + restore procedures. |
5. **Micro-canary** — Deploy guide for supervised micro-canary testing with dry-run mode |

**Recommended Sequence:** Docker → JSON logging → Backup/export → Disaster Recovery → Micro-canary
 (most items are quick and build on parallel, dependencies are minimal)

## Step-by-Step Implementation Details



### Step 1: Docker

**Files: `Dockerfile`, `docker-compose.yml`
- Multi-stage Python 3.12 build
- Healthcheck via `/api/status` endpoint
- `restart: always` policy
- Volume mounts for `data/` and `logs/`

### Step 2: JSON Structured Logging
**File: `core/logger.py`** — Add `LOG_FORMAT` env var (`text`|`json`)
- No structural changes to existing log calls (  just a new formatter/handler)
- All existing log lines unchanged

- Structured data: strategy name, strategy_name, event_type, event_type_name)
- `error` field values
+ error traceback

  + `timestamp` in ISO format

### Step 3: Backup/Export Tooling
**New `scripts/` directory with:**
- `scripts/export_db.py` — Database backup/export (SQLite → JSON)
- `scripts/analyze_markets.py` — Market analysis export (JSON/Markdown)
- `scripts/backup.py` — Backup runner (automated, scheduled)

### Step 4: Disaster Recovery
**New `scripts/recover.py`** — Operational runbook with:
- Safety playbook (pre-flight checklist)
- Emergency shutdown procedure
- Data recovery steps
- Rollback verification

### Step 5: Micro-Canary
**New `scripts/micro_canary.py`** — Deployment guide:
- Phase 4a validation checklist (dry-run checks)
- Supervised micro-canary procedure
- Circuit breaker parameters
- Gradual ramp-up schedule
- Monitoring checklist

**Dependencies:** Existing `requirements.txt` + `docker` + `docker-compose`

**Estimated Effort:** ~1-2 hours each (small, well-tested)
**Risk:** Low (additive, non-breaking)
**Verification:** `ruff check .`, `mypy .`, tests,79 existing)

**Next Steps After Implementation:**
1. Update `README.md` go-live checklist
2. Update `memory-bank/progress.md`
3. Run `ruff check .` + `mypy .`
4. Run test suite (`python -m pytest tests/ -q`)
