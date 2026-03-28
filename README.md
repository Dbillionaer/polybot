# PolyBot 2026 - Advanced Polymarket Trading Bot

PolyBot 2026 is an elite, fully modular, production-ready Python trading bot specifically designed for the Polymarket prediction market. Operating on Polygon (USDC), this bot utilizes the official `py-clob-client`, features gasless L2 transactions, and includes modular strategy blocks targeting momentum, automated market making (AMM), and AI-driven arbitrage over real-time WebSockets.

## 📁 Project Structure

```text
polybot/
├── core/
│   ├── auth.py          # L1/L2 credential derivation & authentication
│   ├── client.py        # Wrapper around the py-clob-client API
│   ├── data.py          # Gamma API & Falcon Analytics API endpoints
│   ├── database.py      # SQLite / SQLModel schema & position tracking
│   ├── logger.py        # Loguru configuration & Discord/Telegram alerts
│   └── ws.py            # Asyncio WebSocket event loop for live orderbooks
├── engine/
│   ├── backtester.py    # Historical backtesting framework
│   ├── execution.py     # Trade execution, slippage safety, fees & dry-run
│   └── risk.py          # Risk management, Kelly sizing, portfolio limits
├── strategies/
│   ├── base.py          # BaseStrategy class interface
│   ├── amm.py           # Automated Market Making logic (Quoting, Inventory)
│   ├── momentum.py      # Orderbook momentum and imbalance trading
│   ├── logical_arb.py   # High probability mathematical arbitrage
│   ├── ai_arb.py        # Grok (xAI) driven probability edge detection
│   └── copy_trading.py  # Falcon API whale tracking and mirror execution
├── ui/
│   └── dashboard.py     # Terminal UI dashboard (Rich)
├── main.py              # Application entry point & service wiring
├── verify_setup.py      # Setup diagnostic and connectivity script
├── .env                 # Secret credentials and configuration
├── .gitignore           # Ignored files (logs, db, venv, .env)
└── README.md            # You are here
```

## ⚙️ Configuration & `.env` Settings

You must create a `.env` file in the project root. Essential keys:

```env
# Polygon & Polymarket Keys
POLYGON_PRIVATE_KEY="YOUR_WALLET_PRIVATE_KEY" # L1 signing 
POLY_API_KEY="" # L2 Key (Auto-derived if left blank)
POLY_API_SECRET=""
POLY_API_PASSPHRASE=""

# Web3 CTF & Polymarket Analytics
POLYGON_RPC_URL="https://polygon-mainnet.g.alchemy.com/v2/..."
CTF_CONTRACT_ADDRESS="0x4D970a446C56654e805562095dB1E0BcB1b623E0"
FALCON_API_KEY="" # For advanced Wallet 360 analytics

# Risk & Bankroll Config
MAX_POSITION_SIZE_PCT=0.05
DAILY_LOSS_LIMIT_PCT=0.05

# External Integrations (Optional)
XAI_API_KEY="xoxb-..." # For Grok AI probability edge
DATABASE_URL="sqlite:///polybot.db"
TELEGRAM_BOT_TOKEN="bot_token"
TELEGRAM_CHAT_ID="chat_id"
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

## 🚀 Setup & Execution

### Prerequisites
- Python 3.10+
- A Polygon wallet with USDC (Polygon) funded.

### Installation
1. Clone the repository and navigate into the `polybot` directory.
2. Ensure you have installed standard requirements: `pip install py-clob-client sqlmodel loguru python-dotenv websockets pandas eth-account rich openai`.
3. Create your `.env` according to the `.env_example` template.

### Dry-Run vs Live Trading
The `ExecutionEngine` operates with **`dry_run=True`** by default across strategies. When `dry_run` is active, the bot fetches live order books, runs its decision logic, but completely bypasses the official `post_limit_order` API calls, simply logging what _would_ have happened.

To move to LIVE trading, change the `dry_run` flag directly in `main.py` when initializing strategies or passing down execution instructions:
```python
self.engine.execute_limit_order(..., dry_run=False) # Danger! Funds at risk.
```

### Running the Bot

**1. Verification (Recommended)**:
Before risking funds or starting the main loop, ensure all your APIs (Gamma, Falcon, Web3, Database) are correctly authenticating by running:
```bash
python verify_setup.py
```

**2. Start Application**:
```bash
python main.py
```

### Monitoring
- **Terminal UI**: The bot features a `rich` dashboard seamlessly integrated into `main.py` (controlled via `ENABLE_DASHBOARD=True` in your `.env`). It dynamically lists real-time open positions and the latest live trades pulled from your local database.
- **Log Files**: Automatic daily rotation logging is seamlessly saved to `logs/bot.log`.
- **Alerts**: Instant discord or telegram webhook posts are available for significant risk limit breaches or trade execution successes using the `core.logger` setup.
