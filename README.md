# PolyBot 2026 — Production Polymarket Trading Bot

PolyBot 2026 is an elite, fully modular, production-ready Python trading bot built for the **Polymarket** prediction market. It runs on **Polygon (USDC)**, uses the official `py-clob-client`, features gasless L2 order placement, and includes five live-wired strategies — all controlled entirely through environment variables.

---

## 📁 Project Structure

```text
polybot/
├── core/
│   ├── auth.py            # L1/L2 credential derivation & authentication
│   ├── client.py          # py-clob-client wrapper (orders, book, balance)
│   ├── data.py            # Gamma API + Falcon analytics + auto-claim (web3)
│   ├── database.py        # SQLite / SQLModel schema, positions, trades
│   └── ws.py              # Asyncio WebSocket event loop (book, trades, price)
├── engine/
│   ├── backtester.py      # Historical backtesting framework
│   ├── execution.py       # Order execution, dry-run gate, fee/spread checks
│   └── risk.py            # Kelly sizing, drawdown guard, daily loss limit
├── strategies/
│   ├── base.py            # BaseStrategy — WS callbacks auto-registered here
│   ├── amm.py             # AMM quoting with inventory dampening + scheduler
│   ├── momentum.py        # Orderbook imbalance + volume surge scalper
│   ├── logical_arb.py     # Multi-leg sum-violation arbitrage
│   ├── ai_arb.py          # Grok (xAI) probability edge detection
│   └── copy_trading.py    # Falcon API whale tracking + mirror execution
├── ui/
│   └── dashboard.py       # Rich terminal dashboard (live positions + trades)
├── main.py                # Application entry point — fully config-driven
├── markets.json.example   # Template for pinned markets (delete for auto-discovery)
├── verify_setup.py        # Connectivity / credential diagnostic script
├── .env_example           # All environment variables documented
├── .gitignore
└── README.md
```

---

## ⚙️ Configuration (`/env`)

Copy `.env_example` → `.env` and fill in your values:

```env
# ─── Credentials ──────────────────────────────────────────────────────
POLYGON_PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
POLY_CHAIN_ID=137                  # 137 = Polygon mainnet

# ─── Execution mode ───────────────────────────────────────────────────
DRY_RUN=true                       # NEVER touch real funds until you set false

# ─── Market discovery ─────────────────────────────────────────────────
MARKETS_CONFIG=                    # Path to markets.json; blank = auto-discover
MIN_VOLUME_FILTER=50000            # Minimum 24h volume for auto-discovery
BANKROLL_USDC=1000                 # Your current USDC bankroll

# ─── Strategy toggles ─────────────────────────────────────────────────
STRATEGY_MOMENTUM=true
STRATEGY_LOGICAL_ARB=true
STRATEGY_AMM=false
STRATEGY_AI_ARB=false              # Requires XAI_API_KEY
STRATEGY_COPY_TRADING=false        # Requires FALCON_API_KEY

# ─── Risk ─────────────────────────────────────────────────────────────
MAX_POSITION_SIZE_PCT=0.05
DAILY_LOSS_LIMIT_PCT=0.05
TOTAL_DRAWDOWN_LIMIT_PCT=0.25
KELLY_FRACTION=0.5
MAX_SPREAD=0.05
TAKER_FEE_RATE=0.002

# ─── Auto-claim ───────────────────────────────────────────────────────
ENABLE_AUTO_CLAIM=false
AUTO_CLAIM_INTERVAL_HOURS=6
```

See `.env_example` for the full list of all options including strategy-specific tuning.

---

## 🚀 Setup & Execution

### Prerequisites
- Python 3.10+
- A funded Polygon wallet (USDC)

### Installation

```bash
pip install -r requirements.txt
```

> **Recommended:** use `uv` for 10× faster installs: `uv pip install -r requirements.txt`

### Quick Start (dry-run — no funds at risk)

```bash
# 1. Copy and configure
cp .env_example .env
# edit .env and add POLYGON_PRIVATE_KEY

# 2. Verify connectivity
python verify_setup.py

# 3. Run in safe dry-run mode (default)
python main.py
```

### Going Live

> ⚠️ **Set `DRY_RUN=false` only when you are 100% confident in your config.**

```bash
DRY_RUN=false python main.py
```

---

## 🧠 Strategy Overview

| Strategy | Env var | Default | What it does |
|---|---|---|---|
| **Momentum** | `STRATEGY_MOMENTUM` | `true` | Orderbook imbalance + volume surge scalping |
| **Logical Arb** | `STRATEGY_LOGICAL_ARB` | `true` | Shorts overpriced leg when outcome sum > 105% |
| **AMM** | `STRATEGY_AMM` | `false` | Two-sided quoting with inventory dampening + 15s requote scheduler |
| **AI Arb** | `STRATEGY_AI_ARB` | `false` | Grok probability vs market price edge (≥12% required) |
| **Copy Trading** | `STRATEGY_COPY_TRADING` | `false` | Mirror known profitable wallets via Falcon API |

All strategies share the same **`BaseStrategy`** parent which auto-registers WebSocket callbacks on construction — they react to live `book` and `trades` events immediately.

---

## 🌐 Market Discovery

PolyBot supports two modes:

| Mode | How |
|---|---|
| **Pinned markets** | Create a `markets.json` from `markets.json.example` and set `MARKETS_CONFIG=markets.json` |
| **Auto-discovery** | Leave `MARKETS_CONFIG` blank. The bot queries the Gamma API for markets with ≥ `MIN_VOLUME_FILTER` 24h volume |

---

## 📊 Monitoring

- **Terminal UI**: Rich live dashboard (enabled via `ENABLE_DASHBOARD=true`) shows open positions and last 10 trades
- **Log file**: `logs/bot.log` with daily rotation, 14-day retention
- **Telegram alerts**: Set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` to get ERROR/CRITICAL notifications
- **Discord**: Set `DISCORD_WEBHOOK_URL` for webhook alerts

---

## 🔒 Risk Controls

| Control | What happens |
|---|---|
| **DRY_RUN** | All orders are logged only — zero API calls to CLOB |
| **MAX_SPREAD** | Skips execution if book spread is too wide |
| **DAILY_LOSS_LIMIT_PCT** | Pauses all trading when daily draw exceeds limit |
| **TOTAL_DRAWDOWN_LIMIT_PCT** | Full auto-shutdown if portfolio drawdown breaches limit |
| **MAX_POSITION_SIZE_PCT** | Caps each trade notional as % of bankroll |
| **Position collision** | Prevents holding YES + NO in the same market simultaneously |

---

## 🪙 Auto-Claim (Winning Shares)

When `ENABLE_AUTO_CLAIM=true`, the bot scans for settled CTF positions every `AUTO_CLAIM_INTERVAL_HOURS` hours and redeems winning shares into USDC via `web3.py`.

Requires:
- `POLYGON_RPC_URL`
- `POLYGON_PRIVATE_KEY`
- `CTF_CONTRACT_ADDRESS` (default: `0x4D970a446C56654e805562095dB1E0BcB1b623E0`)

---

## 📝 Commit Log Highlights

```
feat: production wiring — dynamic markets, strategy factory, live order execution
- BaseStrategy auto-registers WS callbacks on construction
- All 5 strategies fire real orders through ExecutionEngine (dry_run gated)
- main.py: strategy factory driven entirely by .env vars
- Dynamic market discovery from Gamma API (fallback: markets.json)
- RiskManager: check_trade_allowed() with drawdown/daily-loss/size guards
- ExecutionEngine: master dry_run flag + position update after fill
- AMM: 15s APScheduler requote loop + inventory sync at boot
- AI Arb: live mid-price from WS instead of hardcoded 0.50
- Auto-claim scheduler (web3 CTF redemption every N hours)
- Expanded .env_example with all tuning knobs documented
```
