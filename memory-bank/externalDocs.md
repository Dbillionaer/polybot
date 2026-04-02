# External Docs

- Last Updated: 2026-04-01 21:31:45 -04:00
- Version: v1.1
- Last Change Summary: Expanded external references to cover official Polymarket auth, order/trade state, Gamma market metadata, NegRisk and redemption flows, rate limits, trading constraints, Polygon/USDC operational assumptions, and authoritative SDK references.
- Related Changes: `techContext.md`, `systemPatterns.md`, `activeContext.md`, `interactionHistory.md`

## Documentation Index

### Polymarket Docs Index
- URL: https://docs.polymarket.com/llms.txt
- Verified: 2026-04-01 via direct fetch
- Relevance: master index of official Polymarket docs, OpenAPI specs, AsyncAPI specs, and canonical page URLs
- Key Points:
  - authoritative starting point for discovering current docs without relying on search results
  - includes links for auth, trading, market data, websocket, bridge, CTF, contract addresses, and rate limits
  - includes OpenAPI / AsyncAPI spec links useful for mock-server and integration-test work in Phase 4

## Official Polymarket API / Auth Docs

### API Introduction
- URL: https://docs.polymarket.com/api-reference/introduction
- Verified: 2026-04-01 via direct fetch
- Relevance: high-level map of Gamma, Data, CLOB, and Bridge APIs
- Key Points:
  - Gamma API is the public source for markets, events, tags, sports, and search
  - Data API is public for positions, trades, activity, holder data, and analytics
  - CLOB API mixes public market-data endpoints with authenticated trading endpoints

### Authentication
- URL: https://docs.polymarket.com/api-reference/authentication
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative reference for signing, auth headers, API credential creation, and client setup
- Key Points:
  - L1 auth uses an EIP-712 wallet signature to create or derive API credentials
  - L2 auth uses all 5 `POLY_*` headers with HMAC-SHA256 signing for authenticated CLOB requests
  - `POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_API_KEY`, and `POLY_PASSPHRASE` are required for trading endpoints
  - wallet `signatureType` and `funder` selection are part of safe client initialization for non-EOA / proxy flows

### Clients & SDKs
- URL: https://docs.polymarket.com/api-reference/clients-sdks
- Verified: 2026-04-01 via direct fetch
- Relevance: canonical SDK index for TypeScript, Python, and Rust
- Key Points:
  - official Python package is `py-clob-client`
  - official repo for the Python SDK is `https://github.com/Polymarket/py-clob-client`
  - builder signing and relayer SDKs are separate from the core CLOB client

### L1 Client Methods
- URL: https://docs.polymarket.com/trading/clients/l1
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative reference for initial setup methods that require a signer but no API creds
- Key Points:
  - `createApiKey`, `deriveApiKey`, and `createOrDeriveApiKey` are the canonical credential bootstrap methods
  - `createOrder` and `createMarketOrder` are the canonical pre-post signing methods
  - useful for understanding what must stay local/off-server versus what can be delegated to L2 calls

### L2 Client Methods
- URL: https://docs.polymarket.com/trading/clients/l2
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative reference for authenticated order, trade, balance, and notification methods
- Key Points:
  - `createAndPostOrder`, `postOrder`, `cancelOrder`, `getOrder`, `getOpenOrders`, and `getTrades` map directly to PolyBot execution and reconciliation behavior
  - L2 methods still depend on locally signed orders even though requests are HMAC-authenticated
  - useful for matching SDK behavior to PolyBot wrappers in `core/client.py`

## Order / Fill / State Docs

### Orders Overview
- URL: https://docs.polymarket.com/trading/orders/overview
- Verified: 2026-04-01 via direct fetch
- Relevance: canonical source for order types, tick sizes, insert statuses, trade statuses, heartbeat semantics, and validity checks
- Key Points:
  - all orders are limit orders; market orders are aggressive limit orders
  - insert statuses include `live`, `matched`, `delayed`, and `unmatched`
  - trade lifecycle statuses include `MATCHED`, `MINED`, `CONFIRMED`, `RETRYING`, and `FAILED`
  - heartbeat lapse causes all open orders to be canceled after roughly 10 seconds (+ buffer)
  - neg-risk markets require `negRisk: true` / `neg_risk: True` in order options

### Order Lifecycle
- URL: https://docs.polymarket.com/concepts/order-lifecycle
- Verified: 2026-04-01 via direct fetch
- Relevance: conceptual source for PolyBot's accepted-vs-filled separation
- Key Points:
  - orders are created offchain, matched by the operator, and settled onchain
  - `matched` is not the same as final settlement
  - cancellation can happen via API or onchain fallback
  - settlement is atomic, and final confirmation is a separate step after matching

### Post a New Order
- URL: https://docs.polymarket.com/api-reference/trade/post-a-new-order
- Verified: 2026-04-01 via direct fetch
- Relevance: endpoint-level request/response contract for live order placement
- Key Points:
  - canonical endpoint is `POST /order`
  - production and staging servers are both documented
  - response schema includes `success`, `orderID`, `status`, `makingAmount`, `takingAmount`, `transactionsHashes`, `tradeIDs`, and `errorMsg`
  - docs enumerate specific 400/401/500/503 failure modes relevant for retry and circuit-breaker handling

### Cancel Single Order
- URL: https://docs.polymarket.com/api-reference/trade/cancel-single-order
- Verified: 2026-04-01 via direct fetch
- Relevance: endpoint-level contract for targeted cancellations
- Key Points:
  - canonical endpoint is `DELETE /order`
  - cancels work even in cancel-only mode
  - response distinguishes `canceled` from `not_canceled` order IDs

### Get User Orders
- URL: https://docs.polymarket.com/api-reference/trade/get-user-orders
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative open-order query schema used by reconciliation and operational tooling
- Key Points:
  - canonical endpoint is `GET /orders`
  - supports filters by order id, `market` (condition ID), and `asset_id` (token ID)
  - returns paginated results with `next_cursor`
  - open-order object includes `status`, `original_size`, `size_matched`, `associate_trades`, and `created_at`

### Get Trades
- URL: https://docs.polymarket.com/api-reference/trade/get-trades
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative trade-history schema for reconciliation and ledger assumptions
- Key Points:
  - canonical endpoint is `GET /trades`
  - requires readonly or level-2 API auth
  - supports filters by maker address, market, asset, and time window
  - returns paginated results with `next_cursor`
  - trade schema includes `status`, `transaction_hash`, `maker_orders`, and `trader_side`

### WebSocket Overview
- URL: https://docs.polymarket.com/market-data/websocket/overview
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative source for market/user websocket channels and heartbeat behavior
- Key Points:
  - market channel subscribes by asset IDs; user channel subscribes by condition IDs
  - market/user channels require client `PING` heartbeats every 10 seconds
  - user channel requires API credentials; market channel does not
  - `market_resolved`, `last_trade_price`, `order`, and `trade` events matter for operational resilience and future integration tests

## Gamma Market Metadata Docs

### Fetching Markets
- URL: https://docs.polymarket.com/market-data/fetching-markets
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative source for market discovery and pagination strategy
- Key Points:
  - events and markets endpoints are paginated with `limit` and `offset`
  - recommended broad discovery flow is the events endpoint with `active=true&closed=false`
  - slug-based fetching is best for precise lookups; tags are best for category filtering

### Conditional Token Framework Overview
- URL: https://docs.polymarket.com/trading/ctf/overview
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative explanation of condition IDs, collection IDs, position IDs, and token identity
- Key Points:
  - Yes/No outcome tokens are ERC1155 positions under the Conditional Token Framework
  - Gamma market payloads are the preferred practical source for token IDs and outcome mappings
  - useful when reasoning about `condition_id` versus `token_id` in PolyBot's accounting layer

## NegRisk / Redemption / Settlement Docs

### Negative Risk Markets
- URL: https://docs.polymarket.com/advanced/neg-risk
- Verified: 2026-04-01 via direct fetch
- Relevance: canonical source for special handling of multi-outcome / neg-risk events
- Key Points:
  - neg-risk markets link outcomes through a conversion operation via the Neg Risk Adapter contract
  - Gamma exposes neg-risk flags on events and markets
  - order placement must still use `negRisk: true` / `neg_risk: True`
  - placeholder / augmented neg-risk outcomes should not be treated like fully named markets

### Resolution
- URL: https://docs.polymarket.com/concepts/resolution
- Verified: 2026-04-01 via direct fetch
- Relevance: canonical source for market-resolution assumptions and redemption timing
- Key Points:
  - market titles are not enough; resolution rules are authoritative
  - unresolved or disputed markets can take days to finalize
  - post-resolution behavior determines when redemption and settlement logic are safe to run

### Redeem Tokens
- URL: https://docs.polymarket.com/trading/ctf/redeem
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative source for when positions can be claimed and what redeeming does onchain
- Key Points:
  - redemption is only available after market resolution
  - winning tokens redeem for `1.00` USDC.e each; losing tokens redeem for `0`
  - redemption burns the position tokens and returns collateral

### Merge Tokens
- URL: https://docs.polymarket.com/trading/ctf/merge
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative source for inverse CTF operation relevant to full-set handling
- Key Points:
  - merging converts equal Yes/No token pairs back into USDC.e
  - operation is atomic and reverts if the user lacks either side of the pair

### Gasless Transactions
- URL: https://docs.polymarket.com/trading/gasless
- Verified: 2026-04-01 via direct fetch
- Relevance: operational reference for approvals, split/merge/redeem, and funded wallet assumptions when using the relayer
- Key Points:
  - relayer can sponsor gas for wallet deployment, token approvals, and CTF operations
  - relevant if PolyBot or future operator tooling ever automates redemption or allowance-management flows via relayer services

## Rate Limits / Reliability Docs

### Rate Limits
- URL: https://docs.polymarket.com/api-reference/rate-limits
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative request-budget reference for Phase 4 integration tests and production throttling
- Key Points:
  - CLOB, Gamma, and Data APIs each have distinct rate limits
  - `POST /order` and cancel endpoints have both burst and sustained limits
  - throttling is described as Cloudflare-based delay/queue behavior, not just hard rejection

### Matching Engine Restarts
- URL: https://docs.polymarket.com/trading/matching-engine
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative downtime / retry reference for production reliability behavior
- Key Points:
  - weekly planned restart is Tuesday 7:00 AM ET with roughly 90 seconds downtime
  - order endpoints return HTTP `425` during restart windows
  - recommended handling is exponential backoff and retry, not permanent failure classification

## Rules / Trading Constraints Docs

### Geographic Restrictions
- URL: https://docs.polymarket.com/api-reference/geoblock
- Verified: 2026-04-01 via direct fetch
- Relevance: official compliance reference for whether trading can be attempted at all
- Key Points:
  - blocked countries and region-specific restrictions are explicitly documented
  - geoblock checks happen through `https://polymarket.com/api/geoblock`
  - some jurisdictions are close-only rather than fully tradable

### Contract Addresses
- URL: https://docs.polymarket.com/resources/contract-addresses
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative chain, contract, and token reference for live trading assumptions
- Key Points:
  - all Polymarket contracts are on Polygon mainnet, chain ID `137`
  - collateral token is USDC.e at `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
  - USDC.e is explicitly documented as `6 decimals`
  - exchange, neg-risk exchange, adapter, and CTF contract addresses are all enumerated here

## Polygon / USDC Operational References

### Supported Assets
- URL: https://docs.polymarket.com/trading/bridge/supported-assets
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative source for wallet funding and bridge assumptions
- Key Points:
  - all supported deposits are normalized into USDC.e on Polygon for trading collateral
  - supported chains and minimum deposit amounts are documented and can change over time
  - useful for operational runbooks and wallet-funding procedures before live deployment

### Deposit Flow
- URL: https://docs.polymarket.com/trading/bridge/deposit
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative operational reference for how funds reach Polymarket trading wallets
- Key Points:
  - deposit addresses are generated per wallet
  - Polymarket trading uses USDC.e on Polygon as the collateral destination
  - native USDC deposits may still require activation / conversion into USDC.e before trading
  - useful for documenting operator funding procedures and disaster-recovery wallet steps

## py-clob-client References

### Official Python SDK Repository
- URL: https://github.com/Polymarket/py-clob-client
- Verified: 2026-04-01 via direct fetch
- Relevance: authoritative Python SDK source used by this repo
- Key Points:
  - repo is maintained under the official `Polymarket` GitHub org
  - fetched repo page shows current latest release `v0.34.6` on 2026-02-19
  - README includes quickstart, trading setup, allowances, and examples matching current docs
  - primary authority for Python SDK behavior after official docs themselves

### Secondary Python SDK Guide
- URL: https://agentbets.ai/guides/py-clob-client-reference/
- Verified: 2026-03-30 via direct fetch
- Relevance: practical secondary source for response-shape hints and SDK usage patterns
- Notes: not authoritative; use only to supplement official Polymarket docs, SDK repo examples, and direct code introspection

## Mapping To Memory Bank

- Auth, signer, `POLY_*` header, and client initialization rules inform `techContext.md` and `systemPatterns.md`.
- Order status, trade status, heartbeat, websocket, and restart semantics inform `systemPatterns.md` and `activeContext.md`.
- Gamma market-discovery and CTF identity docs inform `projectbrief.md`, `systemPatterns.md`, and any future operator runbooks.
- Geoblock, resolution, redemption, and funding docs should feed directly into Phase 4 dry-run and disaster-recovery documentation.
