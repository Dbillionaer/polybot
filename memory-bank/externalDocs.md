# External Docs

- Last Updated: 2026-03-30 00:00:00 UTC
- Version: v1.0
- Last Change Summary: Added external references used during execution/reconciliation work.
- Related Changes: `techContext.md`, `systemPatterns.md`, `activeContext.md`

## References

### Polymarket Orders Overview
- URL: https://docs.polymarket.com/trading/orders/overview
- Verified: 2026-03-30 via web fetch/search
- Relevance: insert statuses and order lifecycle semantics
- Key Points:
  - order insert statuses include `matched`, `live`, `delayed`, `unmatched`
  - API order responses expose status used for reconciliation decisions
  - CLOB order lifecycle is not equivalent to immediate fill confirmation

### Polymarket Order Lifecycle / Cancel Docs
- URL: https://docs.polymarket.com/concepts/order-lifecycle
- URL: https://docs.polymarket.com/trading/orders/cancel
- Verified: 2026-03-30 via search results
- Relevance: confirms open/cancel/fill lifecycle expectations and `getOrder` usage patterns

### AgentBets py_clob_client Reference
- URL: https://agentbets.ai/guides/py-clob-client-reference/
- Verified: 2026-03-30 via web fetch
- Relevance: practical response-shape hints for `get_order()` and order-management methods
- Notes: non-authoritative secondary source; useful for SDK usage patterns but subordinate to official Polymarket docs and code introspection

## Mapping To Memory Bank

- Order-status semantics inform `systemPatterns.md` and `activeContext.md`.
- SDK method expectations inform `techContext.md` and Phase 1 progress notes.