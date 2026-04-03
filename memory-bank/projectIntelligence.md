# Project Intelligence

- Last Updated: 2026-04-03 04:17:30 -04:00
- Version: v1.6
- Last Change Summary: Added operator-dashboard UX lessons from the browser polish pass, including layout constraints for strategy cards and the value of a static direct-view preview during UI iteration.
- Related Changes: `activeContext.md`, `progress.md`, `interactionHistory.md`, `techContext.md`

## Stable Conventions

- Treat execution/accounting changes as high-risk and verify with targeted tests.
- Prefer smallest-scope validation first: compile/import → focused test → broader check if needed.
- Keep live-trading semantics conservative: accepted order != filled trade.

## Critical Domain Insights

- `condition_id` / `token_id` confusion is a major historical footgun in this repo.
- Correct accounting depends on grouping by market (`condition_id`) while tracking exposure by token (`token_id`).
- Polymarket NegRisk markets require special order/redemption handling.

## User / Workflow Preferences Observed

- User wants thorough, methodical execution.
- User wants task list tracking on complex work.
- User expects actual verification runs, not just code suggestions.
- User explicitly requires Memory Bank usage and maintenance.
- User prioritizes **deployment readiness first**, with **profitability second**.
- User wants the first concrete milestone to be **small live deployment**.
- User considers AI arb, copy trading, AMM, auto-claim, and live deployment all necessary project scope.

## Effective Work Patterns

- Use SDK introspection plus docs to confirm third-party API semantics before wiring execution logic.
- Treat README as helpful but not authoritative for current runtime truth; verify against code.
- Add focused smoke/regression tests when touching execution lifecycle behavior.
- When repairing persistent state, prefer conservative audit + replay tooling over in-place row guessing.
- Preserve backward compatibility for existing fake test doubles when evolving runtime interfaces.
- The safest seam for strategy-level operational telemetry is the strategy base-class callback wrapper, not the websocket transport itself.
- For websocket stability issues, deduplicate at registration time instead of trying to clean up duplicates later during dispatch.
- SQLModel tests that use persistent sqlite files should explicitly clear metadata with `SQLModel.metadata.drop_all(db_engine)` before recreating tables, or state can leak across tests.
- When project phase focus changes, sync `progress.md`, `activeContext.md`, and `systemPatterns.md` together; otherwise interaction history can advance ahead of the core status files.
- Keep the legacy-ledger regression in the targeted verification bundle because it protects the safety gate that blocks destructive repair when metadata is incomplete.
- `cancel_all_open_orders()` is not a sufficient emergency control by itself; a persistent execution-layer pause gate is required so strategies cannot immediately re-enter after mass cancellation.
- Adding `__init__.py` package markers is a low-friction way to eliminate duplicate-module discovery issues in Python tooling without changing runtime architecture.
- Setting `follow_imports = "skip"` in mypy is a pragmatic fix for repos that depend on large third-party libraries and need a usable local type-check gate.
- The next highest-leverage safety work after green tooling is operator procedure design: exact pause, cancel, observe, and abort steps matter as much as code for a live canary.
- For dense operator grids, forcing too many columns too early can make status badges collide with content; browser dashboards should degrade to fewer columns sooner than a typical marketing layout.
- A static preview artifact like `ui/direct_view.html` is useful for rapid UI iteration when the live runtime is not needed to inspect layout/styling.

## Recovery Note

[RECONSTRUCTED] Memory Bank did not exist in the workspace at initialization time. This baseline was rebuilt from current repository state and conversation context and should be user-validated before being treated as authoritative.
