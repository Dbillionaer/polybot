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

---

## ⚡ NegRisk Adapter Support

Many Polymarket markets (politics, sports multi-outcome) use the **NegRisk CTF Adapter** instead of the standard CTF contract. Standard `redeemPositions()` **silently fails** on these markets.

| Concern | How PolyBot handles it |
|---|---|
| **Order placement** | `is_neg_risk_market()` auto-detected via Gamma API; `neg_risk=True` passed to CLOB |
| **Redemption routing** | `claim_rewards()` routes to `convertToUSDC()` on adapter, not standard CTF |
| **ERC-1155 approval** | `ensure_adapter_approval()` called once at startup (idempotent — no extra gas if already set) |
| **Silent failures** | All NegRisk detections log a prominent `⚠️` warning |

Adapter contract: `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` (Polygon mainnet)

---

## 🔌 Circuit Breaker

All trading auto-pauses when either condition is met:

| Trigger | Default | Env var |
|---|---|---|
| Consecutive API/order errors | 4 errors | `CB_MAX_CONSECUTIVE_ERRORS` |
| Rapid drawdown | 3% loss in 5 min | `CB_DRAWDOWN_PCT_TRIGGER` + `CB_DRAWDOWN_WINDOW_MINUTES` |
| Cool-down period | 10 minutes | `CB_COOL_DOWN_MINUTES` |

Telegram alert sent on trip **and** reset. Auto-resumes after cool-down with no manual intervention needed.

Disable entirely: `CIRCUIT_BREAKER_ENABLED=false`

---

## 🚀 FINAL GO-LIVE CHECKLIST (March 2026)

> Follow this checklist in order. Do NOT flip `DRY_RUN=false` until every step is complete.

### Phase 1 — 7-Day Dry Run

```bash
# 1. Clone and configure
git clone https://github.com/Dbillionaer/polybot && cd polybot
pip install -r requirements.txt
cp .env_example .env
# Fill in POLYGON_PRIVATE_KEY, POLYGON_RPC_URL, FALCON_API_KEY

# 2. Verify all connections
python verify_setup.py

# 3. Start in dry-run (default)
# DRY_RUN=true is the default — confirm this in .env
python main.py
```

**What to watch during dry run (7 days minimum):**
- Strategy fires visible `[DRY-RUN] Would post:` log lines for Momentum and LogicalArb
- `[NegRisk]` detection messages on political/sports markets (expected — means detection is working)
- Circuit breaker does NOT trip during normal operation
- `logs/bot.log` grows steadily with INFO-level entries
- Zero `ERROR` or `CRITICAL` log lines
- Market discovery finds ≥5 markets at startup

### Phase 2 — Small Live Bankroll ($300–500 USDC)

```bash
# 1. Fund wallet with $300–500 USDC on Polygon
# 2. Update .env:
BANKROLL_USDC=400
MAX_POSITION_SIZE_PCT=0.03   # $12 max per trade at $400
DAILY_LOSS_LIMIT_PCT=0.025   # Pause after $10 loss/day
TOTAL_DRAWDOWN_LIMIT_PCT=0.15 # Shutdown after $60 total loss
ENABLE_AUTO_CLAIM=true
CIRCUIT_BREAKER_ENABLED=true
TELEGRAM_BOT_TOKEN=your_token  # Get alerts on your phone
TELEGRAM_CHAT_ID=your_chat_id

# 3. Flip to LIVE — point of no return
DRY_RUN=false

# 4. Start bot
python main.py
```

### Phase 3 — VPS Deployment

```bash
# Recommended: Ubuntu 22.04 VPS, 2GB RAM, low-latency Polygon RPC

# systemd service (create /etc/systemd/system/polybot.service):
[Unit]
Description=PolyBot 2026
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/polybot
ExecStart=/opt/polybot/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/polybot/.env

[Install]
WantedBy=multi-user.target

# Enable and start:
sudo systemctl enable polybot
sudo systemctl start polybot
```

**Monitoring commands:**
```bash
# Live logs
tail -f /opt/polybot/logs/bot.log

# Health check
curl http://localhost:8080/health

# Circuit breaker status
grep -i 'circuit' /opt/polybot/logs/bot.log | tail -20

# Check for errors in last 24h
grep 'ERROR\|CRITICAL' /opt/polybot/logs/bot.log | tail -50

# Watch for successful trades
grep 'Order.*accepted' /opt/polybot/logs/bot.log | tail -20

# Watch auto-redeem
grep 'AutoRedeem' /opt/polybot/logs/bot.log | tail -10
```

### What to Watch in First 24h

| Metric | Healthy | Danger sign |
|---|---|---|
| Circuit breaker trips | 0 | ≥ 2 in first hour |
| Successful orders | ≥ 1 per hour (active markets) | 0 after 4 hours |
| Error rate | < 1% of log lines | > 5% |
| NegRisk detection | Occasional `⚠️` on political markets | Errors on detection |
| Auto-redeem (if enabled) | Runs every 60 min, `0 redeemed` normal | `Fatal error` in claim_rewards |
| USDC balance | Slowly consumed by fees | Rapid drain > $10/hour |
| Health endpoint | `{"status": "ok"}` | 503 |

### Emergency Stop

```bash
# Immediate halt (cancels NO orders — positions stay open)
sudo systemctl stop polybot

# OR send SIGTERM for graceful shutdown (cancels open orders first)
kill -TERM $(pgrep -f 'python main.py')

# Cancel all open CLOB orders via Python
python -c "
from dotenv import load_dotenv; load_dotenv()
from core.auth import initialize_clob_client
from core.client import PolyClient
client = PolyClient(initialize_clob_client())
client.clob.cancel_all()
print('All orders cancelled.')
"
```

> ⚠️ **Final reminder**: Prediction markets are zero-sum. Start small. Respect the daily loss limit.  
> The circuit breaker and risk manager are your last line of defence — don't disable them.
