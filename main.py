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

import http.server
import json
import os
import signal
import sys
import threading
import time
from typing import Any

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from loguru import logger
from requests import RequestException
from web3 import Web3

# ── Core ──────────────────────────────────────────────────────────────
from core.auth import initialize_clob_client
from core.client import PolyClient
from core.data import MarketData
from core.database import create_db_and_tables
from core.negrisk import ensure_adapter_approval
from core.ws import PolyWebSocket

# ── Engine ────────────────────────────────────────────────────────────
from engine.circuit_breaker import CircuitBreaker
from engine.execution import ExecutionEngine
from engine.risk import RiskManager
from strategies.ai_arb import AIArbStrategy
from strategies.amm import AMMStrategy
from strategies.base import BaseStrategy
from strategies.copy_trading import CopyTradingStrategy
from strategies.logical_arb import LogicalArbStrategy
from strategies.momentum import MomentumStrategy
from ui.dashboard import Dashboard
from ui.operator_controller import OperatorController
from ui.operator_server import OperatorControlSurface

load_dotenv()

# Shared shutdown flag (set by SIGTERM handler)
_shutdown_event = threading.Event()


# ──────────────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────────────

def setup_logger():
    """Configure file logging and optional Telegram alerts for error events."""
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
        def _tg_sink(msg):
            if msg.record["level"].no >= 40:  # ERROR and above
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        json={"chat_id": tg_chat, "text": f"🤖 PolyBot: {msg}"},
                        timeout=5,
                    )
                except requests.RequestException as exc:
                    logger.debug(f"[Logger] Telegram alert delivery failed: {exc}")

        logger.add(_tg_sink)
        logger.info("[Logger] Telegram alert sink registered for ERROR+ events.")


# ──────────────────────────────────────────────────────────────────────
# Graceful shutdown (SIGTERM / SIGINT)
# ──────────────────────────────────────────────────────────────────────

def _make_shutdown_handler(ws: PolyWebSocket | None = None):
    def _handler(signum: int, frame: object) -> None:
        _ = frame
        logger.info(
            f"[Main] Signal {signum} received — initiating graceful shutdown…"
        )
        _shutdown_event.set()
        if ws:
            try:
                ws.stop()
            except RuntimeError as exc:
                logger.warning(f"[Main] Error while stopping WebSocket: {exc}")
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
    class _Handler(http.server.BaseHTTPRequestHandler):
        def _handle_get(self) -> None:
            """Respond to health-check requests with bot circuit-breaker status."""
            if self.path == "/health":
                raw_status = circuit_breaker.status_summary()
                status = raw_status if isinstance(raw_status, dict) else {}
                healthy = not bool(status.get("tripped"))
                body = json.dumps({
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

        do_GET = _handle_get

        def log_message(self, format: str, *args: object) -> None:  # pylint: disable=redefined-builtin
            del format, args

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
        with open(markets_file, encoding="utf-8") as f:
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
            except json.JSONDecodeError:
                tokens = []
        for token in tokens:
            if isinstance(token, dict):
                token_id = (
                    token.get("token_id")
                    or token.get("tokenId")
                    or token.get("clobTokenId")
                    or token.get("id")
                )
                outcome = token.get("outcome") or token.get("name") or token.get("label")
            else:
                token_id = token
                outcome = None
            if not token_id:
                continue
            out.append({
                "token_id": str(token_id),
                "question": m.get("question", "Unknown"),
                "condition_id": m.get("conditionId", ""),
                "outcome": outcome,
                "volume": m.get("volume", 0),
                "neg_risk": m.get("neg_risk", False) or m.get("negRisk", False),
            })

    logger.info(f"Discovered {len(out)} live token(s) from {len(raw)} markets")
    return out


# ──────────────────────────────────────────────────────────────────────
# Strategy factory
# ──────────────────────────────────────────────────────────────────────

MarketConfig = dict[str, Any]
DashboardContext = dict[str, Any]


def _env_enabled(name: str, default: str = "false") -> bool:
    """Return True when the named environment flag is enabled."""
    return os.getenv(name, default).lower() in ("true", "1")


def _build_amm_strategy(
    engine: ExecutionEngine,
    ws: PolyWebSocket,
    token_ids: list[str],
) -> BaseStrategy | None:
    """Build the AMM strategy when enabled by configuration."""
    if not _env_enabled("STRATEGY_AMM"):
        return None

    amm_spread = float(os.getenv("AMM_SPREAD", "0.02"))
    amm_size = int(os.getenv("AMM_SIZE", "100"))
    amm = AMMStrategy(engine, ws, token_ids=token_ids, spread=amm_spread, size=amm_size)
    logger.info(f"[AMM] Enabled on {len(token_ids)} market(s)")
    return amm


def _build_momentum_strategy(
    engine: ExecutionEngine,
    ws: PolyWebSocket,
    token_ids: list[str],
) -> BaseStrategy | None:
    """Build the momentum strategy when enabled by configuration."""
    if not _env_enabled("STRATEGY_MOMENTUM", "true"):
        return None

    mom_size = int(os.getenv("MOMENTUM_SCALP_SIZE", "50"))
    momentum = MomentumStrategy(engine, ws, token_ids=token_ids, scalp_size=mom_size)
    logger.info(f"[Momentum] Enabled on {len(token_ids)} market(s)")
    return momentum


def _build_logical_arb_strategy(
    engine: ExecutionEngine,
    ws: PolyWebSocket,
    markets: list[MarketConfig],
) -> BaseStrategy | None:
    """Build the logical arbitrage strategy when enabled by configuration."""
    if not _env_enabled("STRATEGY_LOGICAL_ARB", "true"):
        return None

    arb_threshold = float(os.getenv("ARB_THRESHOLD", "1.05"))
    arb_size = int(os.getenv("ARB_SIZE", "80"))
    arb = LogicalArbStrategy(
        engine,
        ws,
        markets=markets,
        threshold=arb_threshold,
        arb_size=arb_size,
    )
    logger.info(f"[LogicalArb] Enabled across {len(markets)} market(s)")
    return arb


def _build_ai_arb_strategy(
    engine: ExecutionEngine,
    ws: PolyWebSocket,
) -> BaseStrategy | None:
    """Build the AI arbitrage strategy when enabled and configured."""
    if not _env_enabled("STRATEGY_AI_ARB"):
        return None

    ai_token = os.getenv("AI_ARB_TOKEN_ID")
    ai_market_name = os.getenv("AI_ARB_MARKET_NAME", "Will BTC reach $100k by EOY?")
    if not ai_token:
        logger.warning("[AI-Arb] AI_ARB_TOKEN_ID not set — skipping.")
        return None

    ai_arb = AIArbStrategy(engine, ws, market_name=ai_market_name, token_id=ai_token)
    logger.info(f"[AI-Arb] Enabled for '{ai_market_name}'")
    return ai_arb


def _build_copy_trading_strategy(
    engine: ExecutionEngine,
    ws: PolyWebSocket,
) -> BaseStrategy | None:
    """Build the copy-trading strategy when enabled by configuration."""
    if not _env_enabled("STRATEGY_COPY_TRADING"):
        return None

    target_wallet = os.getenv("COPY_TRADE_TARGET_WALLET", "")
    copy_mult = float(os.getenv("COPY_TRADE_MULTIPLIER", "0.1"))
    copy_trading = CopyTradingStrategy(
        engine,
        ws,
        target_wallet=target_wallet,
        size_multiplier=copy_mult,
    )
    logger.info(f"[CopyTrade] Enabled targeting {target_wallet[:10]}…")
    return copy_trading


def build_strategies(
    engine: ExecutionEngine,
    ws: PolyWebSocket,
    markets: list[MarketConfig],
) -> list[BaseStrategy]:
    """Create strategy instances from env configuration."""
    token_ids = [m["token_id"] for m in markets if m.get("token_id")]

    if not token_ids:
        logger.warning("No valid token_ids — strategies will be empty.")
        return []

    strategy_candidates = (
        _build_amm_strategy(engine, ws, token_ids),
        _build_momentum_strategy(engine, ws, token_ids),
        _build_logical_arb_strategy(engine, ws, markets),
        _build_ai_arb_strategy(engine, ws),
        _build_copy_trading_strategy(engine, ws),
    )
    return [strategy for strategy in strategy_candidates if strategy is not None]


# ──────────────────────────────────────────────────────────────────────
# Auto-Redeem scheduler (every 60 minutes)
# ──────────────────────────────────────────────────────────────────────

def schedule_auto_redeem(md: MarketData, poly_client: PolyClient):
    """
    Schedule periodic auto-redemption of settled positions.
    Runs every REDEEM_INTERVAL_MINUTES (default 60) minutes.
    NegRisk routing is handled inside md.claim_rewards().
    """
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
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if w3.is_connected():
            wallet = w3.eth.account.from_key(private_key).address
            ensure_adapter_approval(w3, wallet, private_key)
        else:
            logger.warning("[Startup] Polygon RPC not reachable — skipping NegRisk approval.")
    except ValueError as e:
        logger.warning(f"[Startup] NegRisk approval check skipped: {e}")


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def _log_startup_banner() -> None:
    """Log the standard PolyBot startup banner and latency-mode status."""
    logger.info("=" * 60)
    logger.info("  PolyBot 2026 — Starting up")
    logger.info("=" * 60)

    if _env_enabled("VPS_LATENCY_MODE"):
        logger.info("[VPS] VPS_LATENCY_MODE=true — optimised for low-latency execution.")


def _initialize_poly_client() -> PolyClient:
    """Create and authenticate the Polymarket CLOB client."""
    try:
        clob_client = initialize_clob_client()
        poly_client = PolyClient(clob_client)
        logger.success("CLOB client authenticated")
        return poly_client
    except (ImportError, RequestException, RuntimeError, ValueError) as exc:
        logger.critical(f"Failed to initialise CLOB client: {exc}")
        sys.exit(1)


def _create_execution_engine(
    poly_client: PolyClient,
    circuit_breaker: CircuitBreaker,
) -> ExecutionEngine:
    """Construct the risk manager and execution engine for the current run mode."""
    risk_manager = RiskManager(
        max_pos_size_pct=float(os.getenv("MAX_POSITION_SIZE_PCT", "0.05")),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.05")),
        total_drawdown_limit_pct=float(os.getenv("TOTAL_DRAWDOWN_LIMIT_PCT", "0.25")),
        kelly_fraction=float(os.getenv("KELLY_FRACTION", "0.5")),
    )
    dry_run = _env_enabled("DRY_RUN", "true")
    execution_engine = ExecutionEngine(
        poly_client,
        risk_manager,
        dry_run=dry_run,
        circuit_breaker=circuit_breaker,
    )
    mode = "DRY-RUN 🟡" if dry_run else "🔴 LIVE — REAL MONEY"
    logger.info(f"Execution mode: {mode}")
    if not dry_run:
        logger.warning(
            "⚠️  LIVE MODE active — real USDC at stake. "
            "Ensure 7-day dry-run completed before proceeding."
        )
    return execution_engine


def _start_websocket() -> PolyWebSocket:
    """Start the shared websocket client and register signal handlers."""
    ws = PolyWebSocket()
    ws.start()

    handler = _make_shutdown_handler(ws)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    return ws


def _load_markets_or_exit() -> tuple[MarketData, list[MarketConfig]]:
    """Load market data configuration and exit if no markets are available."""
    market_data = MarketData()
    markets = discover_markets(market_data)
    if not markets:
        logger.critical("No markets available. Exiting.")
        sys.exit(1)
    return market_data, markets


def _start_optional_services(
    market_data: MarketData,
    poly_client: PolyClient,
    circuit_breaker: CircuitBreaker,
    execution_engine: ExecutionEngine,
) -> None:
    """Start optional background services after core startup succeeds."""
    run_startup_neg_risk_approval()

    if _env_enabled("ENABLE_ORDER_RECONCILIATION", "true"):
        poll_interval_seconds = float(os.getenv("ORDER_RECONCILIATION_INTERVAL_SECONDS", "2.0"))
        execution_engine.start_fill_reconciliation(poll_interval_seconds=poll_interval_seconds)

    health_check_port = int(os.getenv("HEALTH_CHECK_PORT", "0"))
    if health_check_port:
        start_health_check_server(circuit_breaker, port=health_check_port)

    if _env_enabled("ENABLE_AUTO_CLAIM"):
        schedule_auto_redeem(market_data, poly_client)


def _start_operator_surface(
    poly_client: PolyClient,
    execution_engine: ExecutionEngine,
    ws: PolyWebSocket,
    circuit_breaker: CircuitBreaker,
    strategies: list[BaseStrategy],
    markets: list[MarketConfig],
) -> OperatorControlSurface | None:
    """Start the local operator web surface when enabled."""
    if not _env_enabled("ENABLE_OPERATOR_UI"):
        return None

    host = os.getenv("OPERATOR_UI_HOST", "127.0.0.1")
    port = int(os.getenv("OPERATOR_UI_PORT", "8081"))
    operator_token = os.getenv("OPERATOR_UI_TOKEN", "")
    controller = OperatorController(
        poly_client=poly_client,
        execution_engine=execution_engine,
        ws=ws,
        circuit_breaker=circuit_breaker,
        strategies=strategies,
        markets=markets,
    )
    surface = OperatorControlSurface(
        controller,
        host=host,
        port=port,
        operator_token=operator_token,
    )
    surface.start()
    return surface


def _run_strategies(strategies: list[BaseStrategy], markets: list[MarketConfig]) -> None:
    """Start all configured strategies and log the resulting runtime state."""
    if not strategies:
        logger.warning("No strategies enabled. Set STRATEGY_MOMENTUM=true in .env")

    for strategy in strategies:
        strategy.run()

    logger.success(
        f"All systems operational — {len(strategies)} strategy/ies running "
        f"across {len(markets)} market(s)."
    )


def _run_dashboard_or_idle_loop(dashboard_context: DashboardContext) -> None:
    """Run the dashboard UI or keep the main thread alive until shutdown."""
    execution_engine = dashboard_context["execution_engine"]
    ws = dashboard_context["ws"]
    operator_surface = dashboard_context.get("operator_surface")
    try:
        if _env_enabled("ENABLE_DASHBOARD", "true"):
            logger.remove(0)  # Remove stderr handler to avoid cluttering Rich UI
            dash = Dashboard(**dashboard_context)
            dash.render_loop()
        else:
            while not _shutdown_event.is_set():
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[Main] KeyboardInterrupt — stopping bot…")
    finally:
        execution_engine.stop_fill_reconciliation()
        if operator_surface is not None:
            operator_surface.stop()
        ws.stop()
        logger.info("[Main] PolyBot stopped cleanly.")
        sys.exit(0)


def main():
    """Initialize PolyBot services, start enabled strategies, and run until shutdown."""
    setup_logger()
    _log_startup_banner()
    create_db_and_tables()

    poly_client = _initialize_poly_client()
    circuit_breaker = CircuitBreaker()
    execution_engine = _create_execution_engine(poly_client, circuit_breaker)
    ws = _start_websocket()
    market_data, markets = _load_markets_or_exit()
    execution_engine.register_markets(markets)
    _start_optional_services(market_data, poly_client, circuit_breaker, execution_engine)

    strategies = build_strategies(execution_engine, ws, markets)
    _run_strategies(strategies, markets)
    operator_surface = _start_operator_surface(
        poly_client,
        execution_engine,
        ws,
        circuit_breaker,
        strategies,
        markets,
    )
    dashboard_context: DashboardContext = {
        "poly_client": poly_client,
        "ws": ws,
        "circuit_breaker": circuit_breaker,
        "execution_engine": execution_engine,
        "strategies": strategies,
        "markets": markets,
        "operator_surface": operator_surface,
    }
    _run_dashboard_or_idle_loop(dashboard_context)


if __name__ == "__main__":
    main()
