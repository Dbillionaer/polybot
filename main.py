"""
PolyBot 2026 — Production Entry Point
--------------------------------------
Boots all subsystems, discovers live markets from the Gamma API,
then starts strategies determined by config (env vars / markets.json).
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
from loguru import logger

# ── Core ──────────────────────────────────────────────────────────────
from core.auth import initialize_clob_client
from core.client import PolyClient
from core.data import MarketData
from core.database import create_db_and_tables
from core.ws import PolyWebSocket

# ── Engine ────────────────────────────────────────────────────────────
from engine.execution import ExecutionEngine
from engine.risk import RiskManager

load_dotenv()


# ──────────────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────────────

def setup_logger():
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/bot.log",
        rotation="00:00",
        retention="14 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    # Optional Telegram alerts for CRITICAL events
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        import requests

        def _tg_sink(msg):
            if msg.record["level"].no >= 40:  # ERROR and above
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat, "text": f"🤖 PolyBot: {msg}"},
                    timeout=5,
                )

        logger.add(_tg_sink)


# ──────────────────────────────────────────────────────────────────────
# Dynamic market discovery
# ──────────────────────────────────────────────────────────────────────

def discover_markets(md: MarketData) -> list:
    """
    Load markets from markets.json if present, else discover live from Gamma.
    Returns a list of market dicts with at least {token_id, question}.
    """
    markets_file = os.getenv("MARKETS_CONFIG", "markets.json")
    if os.path.exists(markets_file):
        with open(markets_file) as f:
            markets = json.load(f)
        logger.info(f"Loaded {len(markets)} markets from {markets_file}")
        return markets

    min_vol = float(os.getenv("MIN_VOLUME_FILTER", "50000"))
    logger.info(f"Discovering markets from Gamma API (min_vol ${min_vol:,.0f})…")
    raw = md.find_high_liquidity_markets(min_volume=min_vol)

    out = []
    for m in raw:
        tokens = m.get("clobTokenIds") or m.get("tokens", [])
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except Exception:
                tokens = []
        for token_id in tokens:
            out.append({
                "token_id": str(token_id),
                "question": m.get("question", "Unknown"),
                "condition_id": m.get("conditionId", ""),
                "volume": m.get("volume", 0),
            })

    logger.info(f"Discovered {len(out)} live token(s) from {len(raw)} markets")
    return out


# ──────────────────────────────────────────────────────────────────────
# Strategy factory
# ──────────────────────────────────────────────────────────────────────

def build_strategies(engine: ExecutionEngine, ws: PolyWebSocket, markets: list) -> list:
    """
    Create strategy instances from env configuration.
    Each strategy is enabled/disabled via env vars.
    """
    strategies = []
    token_ids = [m["token_id"] for m in markets if m.get("token_id")]

    if not token_ids:
        logger.warning("No valid token_ids — strategies will be empty.")
        return []

    # ── AMM ─────────────────────────────────────────────────────────
    if os.getenv("STRATEGY_AMM", "false").lower() in ("true", "1"):
        from strategies.amm import AMMStrategy
        amm_spread = float(os.getenv("AMM_SPREAD", "0.02"))
        amm_size = int(os.getenv("AMM_SIZE", "100"))
        amm = AMMStrategy(engine, ws, token_ids=token_ids, spread=amm_spread, size=amm_size)
        strategies.append(amm)
        logger.info(f"[AMM] Enabled on {len(token_ids)} market(s)")

    # ── Momentum ────────────────────────────────────────────────────
    if os.getenv("STRATEGY_MOMENTUM", "true").lower() in ("true", "1"):
        from strategies.momentum import MomentumStrategy
        mom_size = int(os.getenv("MOMENTUM_SCALP_SIZE", "50"))
        mom = MomentumStrategy(engine, ws, token_ids=token_ids, scalp_size=mom_size)
        strategies.append(mom)
        logger.info(f"[HFM] Enabled on {len(token_ids)} market(s)")

    # ── Logical Arb ─────────────────────────────────────────────────
    if os.getenv("STRATEGY_LOGICAL_ARB", "true").lower() in ("true", "1"):
        from strategies.logical_arb import LogicalArbStrategy
        arb_threshold = float(os.getenv("ARB_THRESHOLD", "1.05"))
        arb_size = int(os.getenv("ARB_SIZE", "80"))
        arb = LogicalArbStrategy(engine, ws, markets=markets, threshold=arb_threshold, arb_size=arb_size)
        strategies.append(arb)
        logger.info(f"[Arb] Enabled across {len(markets)} market(s)")

    # ── AI Arb ──────────────────────────────────────────────────────
    if os.getenv("STRATEGY_AI_ARB", "false").lower() in ("true", "1"):
        from strategies.ai_arb import AIArbStrategy
        ai_token = os.getenv("AI_ARB_TOKEN_ID")
        ai_market_name = os.getenv("AI_ARB_MARKET_NAME", "Will BTC reach $100k by EOY?")
        if ai_token:
            ai = AIArbStrategy(engine, ws, market_name=ai_market_name, token_id=ai_token)
            strategies.append(ai)
            logger.info(f"[AI-Arb] Enabled for '{ai_market_name}'")
        else:
            logger.warning("[AI-Arb] AI_ARB_TOKEN_ID not set — skipping.")

    # ── Copy Trading ─────────────────────────────────────────────────
    if os.getenv("STRATEGY_COPY_TRADING", "false").lower() in ("true", "1"):
        from strategies.copy_trading import CopyTradingStrategy
        target_wallet = os.getenv("COPY_TRADE_TARGET_WALLET", "")
        copy_mult = float(os.getenv("COPY_TRADE_MULTIPLIER", "0.1"))
        copy = CopyTradingStrategy(engine, ws, target_wallet=target_wallet, size_multiplier=copy_mult)
        strategies.append(copy)
        logger.info(f"[CopyTrade] Enabled targeting {target_wallet[:10]}…")

    return strategies


# ──────────────────────────────────────────────────────────────────────
# Auto-claim scheduled job
# ──────────────────────────────────────────────────────────────────────

def schedule_auto_claim(md: MarketData, poly_client: PolyClient):
    """Schedule a periodic auto-claim of settled positions."""
    from apscheduler.schedulers.background import BackgroundScheduler
    claim_interval_hours = int(os.getenv("AUTO_CLAIM_INTERVAL_HOURS", "6"))

    def _claim_job():
        logger.info("[AutoClaim] Running redemption scan…")
        md.claim_rewards(poly_client.clob)

    scheduler = BackgroundScheduler()
    scheduler.add_job(_claim_job, "interval", hours=claim_interval_hours)
    scheduler.start()
    logger.info(f"[AutoClaim] Scheduler started (every {claim_interval_hours}h)")
    # Run one immediately at boot
    _claim_job()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    setup_logger()
    logger.info("=" * 60)
    logger.info("  PolyBot 2026 — Starting up")
    logger.info("=" * 60)

    # 1. Database
    create_db_and_tables()

    # 2. Polymarket Client
    try:
        clob_client = initialize_clob_client()
        poly_client = PolyClient(clob_client)
        logger.success("CLOB client authenticated")
    except Exception as e:
        logger.critical(f"Failed to initialise CLOB client: {e}")
        sys.exit(1)

    # 3. Risk + Execution Engine
    risk_manager = RiskManager(
        max_pos_size_pct=float(os.getenv("MAX_POSITION_SIZE_PCT", "0.05")),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.05")),
        total_drawdown_limit_pct=float(os.getenv("TOTAL_DRAWDOWN_LIMIT_PCT", "0.25")),
        kelly_fraction=float(os.getenv("KELLY_FRACTION", "0.5")),
    )
    dry_run = os.getenv("DRY_RUN", "true").lower() in ("true", "1")
    execution_engine = ExecutionEngine(poly_client, risk_manager, dry_run=dry_run)
    mode = "DRY-RUN" if dry_run else "🔴 LIVE"
    logger.info(f"Execution mode: {mode}")

    # 4. WebSocket
    ws = PolyWebSocket()
    ws.start()

    # 5. Market Discovery
    md = MarketData()
    markets = discover_markets(md)
    if not markets:
        logger.critical("No markets available. Exiting.")
        sys.exit(1)

    # 6. Build & Run Strategies
    strategies = build_strategies(execution_engine, ws, markets)
    if not strategies:
        logger.warning("No strategies enabled. Set STRATEGY_MOMENTUM=true in .env")

    for strategy in strategies:
        strategy.run()

    logger.success(
        f"All systems operational — {len(strategies)} strategy/ies running "
        f"across {len(markets)} market(s)."
    )

    # 7. Auto-Claim Scheduler
    if os.getenv("ENABLE_AUTO_CLAIM", "false").lower() in ("true", "1"):
        schedule_auto_claim(md, poly_client)

    # 8. Dashboard or keep-alive
    try:
        use_dashboard = os.getenv("ENABLE_DASHBOARD", "true").lower() in ("true", "1")
        if use_dashboard:
            logger.remove(0)  # Remove stderr handler to avoid cluttering UI
            from ui.dashboard import Dashboard
            dash = Dashboard()
            dash.render_loop()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Stopping bot…")
        ws.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
