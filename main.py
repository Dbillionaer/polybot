"""
PolyBot 2026 — Production Entry Point
--------------------------------------
Boots all subsystems, discovers live markets from the Gamma API,
then starts strategies determined by config (env vars / markets.json).

Safety layers enabled at startup:
  - Circuit breaker (CIRCUIT_BREAKER_ENABLED)
  - NegRisk adapter approval (one-time, idempotent)
  - Graceful SIGTERM handler for VPS deployments
  - Optional health-check HTTP endpoint (HEALTH_CHECK_PORT)
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
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
from engine.circuit_breaker import CircuitBreaker
from engine.execution import ExecutionEngine
from engine.risk import RiskManager

load_dotenv()

# Shared shutdown flag (set by SIGTERM handler)
_shutdown_event = threading.Event()


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
    # Optional Telegram alerts for ERROR/CRITICAL events
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        import requests as _req

        def _tg_sink(msg):
            if msg.record["level"].no >= 40:  # ERROR and above
                try:
                    _req.post(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        json={"chat_id": tg_chat, "text": f"🤖 PolyBot: {msg}"},
                        timeout=5,
                    )
                except Exception:
                    pass

        logger.add(_tg_sink)
        logger.info("[Logger] Telegram alert sink registered for ERROR+ events.")


# ──────────────────────────────────────────────────────────────────────
# Graceful shutdown (SIGTERM / SIGINT)
# ──────────────────────────────────────────────────────────────────────

def _make_shutdown_handler(ws: PolyWebSocket | None = None):
    def _handler(signum, frame):
        logger.info(
            f"[Main] Signal {signum} received — initiating graceful shutdown…"
        )
        _shutdown_event.set()
        if ws:
            try:
                ws.stop()
            except Exception:
                pass
        logger.info("[Main] Shutdown complete.")
        sys.exit(0)

    return _handler


# ──────────────────────────────────────────────────────────────────────
# Health-check HTTP endpoint (optional, for VPS monitoring)
# ──────────────────────────────────────────────────────────────────────

def start_health_check_server(circuit_breaker: CircuitBreaker, port: int = 8080):
    """
    Starts a minimal HTTP server on /health that returns 200 (OK) or 503 (tripped).
    Used by process monitors (supervisord, systemd, Caddy health probes).
    """
    import http.server
    import json as _json

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                status = circuit_breaker.status_summary()
                healthy = not status["tripped"]
                body = _json.dumps({
                    "status": "ok" if healthy else "circuit_breaker_open",
                    **status,
                }).encode()
                code = 200 if healthy else 503
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass  # Suppress default access log noise

    server = http.server.HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"[Health] HTTP health-check listening on :{port}/health")


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
        # Strip comment entries from the example template
        markets = [m for m in markets if not m.get("_comment")]
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
                "neg_risk": m.get("neg_risk", False) or m.get("negRisk", False),
            })

    logger.info(f"Discovered {len(out)} live token(s) from {len(raw)} markets")
    return out


# ──────────────────────────────────────────────────────────────────────
# Strategy factory
# ──────────────────────────────────────────────────────────────────────

def build_strategies(engine: ExecutionEngine, ws: PolyWebSocket, markets: list) -> list:
    """Create strategy instances from env configuration."""
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
        logger.info(f"[Momentum] Enabled on {len(token_ids)} market(s)")

    # ── Logical Arb ─────────────────────────────────────────────────
    if os.getenv("STRATEGY_LOGICAL_ARB", "true").lower() in ("true", "1"):
        from strategies.logical_arb import LogicalArbStrategy
        arb_threshold = float(os.getenv("ARB_THRESHOLD", "1.05"))
        arb_size = int(os.getenv("ARB_SIZE", "80"))
        arb = LogicalArbStrategy(
            engine, ws, markets=markets, threshold=arb_threshold, arb_size=arb_size
        )
        strategies.append(arb)
        logger.info(f"[LogicalArb] Enabled across {len(markets)} market(s)")

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
        copy = CopyTradingStrategy(
            engine, ws, target_wallet=target_wallet, size_multiplier=copy_mult
        )
        strategies.append(copy)
        logger.info(f"[CopyTrade] Enabled targeting {target_wallet[:10]}…")

    return strategies


# ──────────────────────────────────────────────────────────────────────
# Auto-Redeem scheduler (every 60 minutes)
# ──────────────────────────────────────────────────────────────────────

def schedule_auto_redeem(md: MarketData, poly_client: PolyClient):
    """
    Schedule periodic auto-redemption of settled positions.
    Runs every REDEEM_INTERVAL_MINUTES (default 60) minutes.
    NegRisk routing is handled inside md.claim_rewards().
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    interval_min = int(os.getenv("AUTO_CLAIM_INTERVAL_HOURS", "1")) * 60
    # Allow override in minutes for testing
    interval_min = int(os.getenv("REDEEM_INTERVAL_MINUTES", str(interval_min)))
    dry_run = os.getenv("DRY_RUN", "true").lower() in ("true", "1")

    def _redeem_job():
        logger.info("[AutoRedeem] ⏰ Starting scheduled redemption scan…")
        md.claim_rewards(poly_client.clob, dry_run=dry_run)

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_redeem_job, "interval", minutes=interval_min, id="auto_redeem")
    scheduler.start()
    logger.info(f"[AutoRedeem] Scheduler started — runs every {interval_min} minutes.")
    # Run one immediately at boot so we don't wait an hour for first check
    _redeem_job()
    return scheduler


# ──────────────────────────────────────────────────────────────────────
# NegRisk adapter approval at startup
# ──────────────────────────────────────────────────────────────────────

def run_startup_neg_risk_approval():
    """
    One-time idempotent ERC-1155 approval so the NegRisk adapter can move
    CTF tokens on behalf of the wallet.  Safe to call every time — skips if
    already approved.
    """
    rpc_url = os.getenv("POLYGON_RPC_URL")
    private_key = os.getenv("POLYGON_PRIVATE_KEY")
    if not rpc_url or not private_key:
        logger.debug(
            "[Startup] POLYGON_RPC_URL / POLYGON_PRIVATE_KEY not set — "
            "skipping NegRisk approval check."
        )
        return

    try:
        from web3 import Web3
        from core.negrisk import ensure_adapter_approval

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if w3.is_connected():
            wallet = w3.eth.account.from_key(private_key).address
            ensure_adapter_approval(w3, wallet, private_key)
        else:
            logger.warning("[Startup] Polygon RPC not reachable — skipping NegRisk approval.")
    except Exception as e:
        logger.warning(f"[Startup] NegRisk approval check skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    setup_logger()
    logger.info("=" * 60)
    logger.info("  PolyBot 2026 — Starting up")
    logger.info("=" * 60)

    vps_mode = os.getenv("VPS_LATENCY_MODE", "false").lower() in ("true", "1")
    if vps_mode:
        logger.info("[VPS] VPS_LATENCY_MODE=true — optimised for low-latency execution.")

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

    # 3. Circuit breaker (shared across engine + strategies)
    circuit_breaker = CircuitBreaker()

    # 4. Risk + Execution Engine
    risk_manager = RiskManager(
        max_pos_size_pct=float(os.getenv("MAX_POSITION_SIZE_PCT", "0.05")),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.05")),
        total_drawdown_limit_pct=float(os.getenv("TOTAL_DRAWDOWN_LIMIT_PCT", "0.25")),
        kelly_fraction=float(os.getenv("KELLY_FRACTION", "0.5")),
    )
    dry_run = os.getenv("DRY_RUN", "true").lower() in ("true", "1")
    execution_engine = ExecutionEngine(
        poly_client, risk_manager, dry_run=dry_run, circuit_breaker=circuit_breaker
    )
    mode = "DRY-RUN 🟡" if dry_run else "🔴 LIVE — REAL MONEY"
    logger.info(f"Execution mode: {mode}")
    if not dry_run:
        logger.warning(
            "⚠️  LIVE MODE active — real USDC at stake. "
            "Ensure 7-day dry-run completed before proceeding."
        )

    # 5. WebSocket
    ws = PolyWebSocket()
    ws.start()

    # 6. Register SIGTERM / SIGINT for graceful shutdown
    handler = _make_shutdown_handler(ws)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    # 7. Market Discovery
    md = MarketData()
    markets = discover_markets(md)
    if not markets:
        logger.critical("No markets available. Exiting.")
        sys.exit(1)

    # 8. NegRisk adapter approval (one-time, idempotent)
    run_startup_neg_risk_approval()

    # 9. Health-check endpoint (optional)
    hc_port = int(os.getenv("HEALTH_CHECK_PORT", "0"))
    if hc_port:
        start_health_check_server(circuit_breaker, port=hc_port)

    # 10. Build & Run Strategies
    strategies = build_strategies(execution_engine, ws, markets)
    if not strategies:
        logger.warning("No strategies enabled. Set STRATEGY_MOMENTUM=true in .env")

    for strategy in strategies:
        strategy.run()

    logger.success(
        f"All systems operational — {len(strategies)} strategy/ies running "
        f"across {len(markets)} market(s)."
    )

    # 11. Auto-Redeem Scheduler (every 60 min, NegRisk-aware)
    if os.getenv("ENABLE_AUTO_CLAIM", "false").lower() in ("true", "1"):
        schedule_auto_redeem(md, poly_client)

    # 12. Dashboard or keep-alive loop
    try:
        use_dashboard = os.getenv("ENABLE_DASHBOARD", "true").lower() in ("true", "1")
        if use_dashboard:
            logger.remove(0)  # Remove stderr handler to avoid cluttering Rich UI
            from ui.dashboard import Dashboard
            dash = Dashboard()
            dash.render_loop()
        else:
            while not _shutdown_event.is_set():
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[Main] KeyboardInterrupt — stopping bot…")
    finally:
        ws.stop()
        logger.info("[Main] PolyBot stopped cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    main()
