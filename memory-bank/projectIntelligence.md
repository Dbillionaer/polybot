# Project Intelligence

- Last Updated: 2026-03-30 00:00:00 UTC
- Version: v1.3
- Last Change Summary: Added Phase 4 lessons on deduplication and telemetry seams.
- Related Changes: `activeContext.md`, `progress.md`, `interactionHistory.md`

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

## Recovery Note

[RECONSTRUCTED] Memory Bank did not exist in the workspace at initialization time. This baseline was rebuilt from current repository state and conversation context and should be user-validated before being treated as authoritative.