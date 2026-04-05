"""Rich terminal dashboard for monitoring PolyBot runtime state."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import Any

from loguru import logger
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from sqlmodel import select

from core.database import Position, Trade, get_session


class Dashboard:
    """Terminal dashboard showing runtime health, PnL, positions, and trades."""

    def __init__(
        self,
        bot_name: str = "PolyBot 2026",
        *,
        poly_client=None,
        ws=None,
        circuit_breaker=None,
        execution_engine=None,
        strategies: list[Any] | None = None,
        markets: list[dict[str, Any]] | None = None,
        refresh_interval: float = 1.0,
    ):
        self.bot_name = bot_name
        self.poly_client = poly_client
        self.ws = ws
        self.circuit_breaker = circuit_breaker
        self.execution_engine = execution_engine
        self.strategies = list(strategies or [])
        self.markets = list(markets or [])
        self.refresh_interval = refresh_interval
        self.start_time = datetime.now()
        self.last_refresh: datetime | None = None
        self.market_names_by_token: dict[str, str] = {}
        self.market_names_by_condition: dict[str, str] = {}
        self.price_cache: dict[str, float] = {}
        self.price_updated_at: dict[str, float] = {}
        self.dashboard_errors: deque[str] = deque(maxlen=5)

        self._index_markets(self.markets)
        self._register_ws_callbacks()
        self._subscribe_market_feeds(self.market_names_by_token.keys())

    def _index_markets(self, markets: Iterable[dict[str, Any]]) -> None:
        """Build quick token/condition lookup maps for friendly market names."""
        for market in markets:
            name = str(
                market.get("question")
                or market.get("market_name")
                or market.get("title")
                or "Unknown Market"
            )
            token_id = market.get("token_id")
            condition_id = market.get("condition_id")
            if token_id:
                self.market_names_by_token[str(token_id)] = name
            if condition_id:
                self.market_names_by_condition[str(condition_id)] = name

    def _register_ws_callbacks(self) -> None:
        """Subscribe dashboard listeners to websocket updates when available."""
        if not self.ws:
            return
        self.ws.add_callback("book", self._on_book_update)
        self.ws.add_callback("price", self._on_price_update)

    def _subscribe_market_feeds(self, token_ids: Iterable[str]) -> None:
        """Request book/price feeds for known tokens so prices stay warm."""
        if not self.ws:
            return
        for token_id in token_ids:
            if token_id:
                self.ws.subscribe(str(token_id), "book")
                self.ws.subscribe(str(token_id), "price")

    def _record_error(self, context: str, exc: Exception | str) -> None:
        """Persist recent dashboard issues in both logs and the UI footer."""
        message = f"{context}: {exc}"
        stamped = f"{datetime.now().strftime('%H:%M:%S')} {message}"
        if not self.dashboard_errors or self.dashboard_errors[0] != stamped:
            self.dashboard_errors.appendleft(stamped[:220])
        logger.warning(f"[Dashboard] {message}")

    def _extract_token_id(self, data: dict[str, Any]) -> str | None:
        """Pull a token identifier from a websocket payload."""
        for key in ("market", "token_id", "asset_id"):
            value = data.get(key)
            if value:
                return str(value)
        return None

    def _cache_price(self, token_id: str, price: float) -> None:
        """Update cached price state for a token."""
        self.price_cache[token_id] = price
        self.price_updated_at[token_id] = time.time()

    def _extract_level_price(self, level: Any) -> float | None:
        """Read a price from common order-book level shapes."""
        try:
            if isinstance(level, (list, tuple)) and level:
                return float(level[0])
            if isinstance(level, dict):
                if "price" in level:
                    return float(level["price"])
                if "px" in level:
                    return float(level["px"])
            price_attr = getattr(level, "price", None)
            if price_attr is not None:
                return float(price_attr)
        except (TypeError, ValueError):
            return None
        return None

    def _extract_levels(self, order_book: Any, side: str) -> list[Any]:
        """Read bids/asks from either dict-based or object-based order books."""
        if isinstance(order_book, dict):
            levels = order_book.get(side, [])
        else:
            levels = getattr(order_book, side, [])
        return list(levels or [])

    def _extract_mid_price(self, order_book: Any) -> float | None:
        """Compute a mid price from the best bid and ask."""
        bids = self._extract_levels(order_book, "bids")
        asks = self._extract_levels(order_book, "asks")
        if not bids or not asks:
            return None
        best_bid = self._extract_level_price(bids[0])
        best_ask = self._extract_level_price(asks[0])
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / 2

    def _on_book_update(self, data: dict[str, Any]) -> None:
        """Update cached prices from websocket book snapshots."""
        token_id = self._extract_token_id(data)
        if not token_id:
            return
        mid_price = self._extract_mid_price(data)
        if mid_price is not None:
            self._cache_price(token_id, mid_price)

    def _on_price_update(self, data: dict[str, Any]) -> None:
        """Update cached prices from direct websocket price ticks."""
        token_id = self._extract_token_id(data)
        price_value = data.get("price")
        if not token_id or price_value is None:
            return
        try:
            self._cache_price(token_id, float(price_value))
        except (TypeError, ValueError):
            self._record_error("Invalid price update", price_value)

    def _refresh_market_prices(self, token_ids: Iterable[str], ttl_seconds: int = 10) -> None:
        """Refresh stale token prices from the CLOB order book when needed."""
        if not self.poly_client:
            return
        now = time.time()
        for token_id in token_ids:
            if not token_id:
                continue
            last_update = self.price_updated_at.get(token_id, 0)
            if now - last_update < ttl_seconds:
                continue
            try:
                order_book = self.poly_client.get_order_book(token_id)
                mid_price = self._extract_mid_price(order_book)
                if mid_price is not None:
                    self._cache_price(token_id, mid_price)
            except Exception as exc:  # network/API dependent
                self._record_error(f"Price refresh failed for {token_id[:10]}…", exc)

    def _get_market_name(self, token_id: str = "", condition_id: str = "") -> str:
        """Resolve a human-readable market name from known token metadata."""
        if token_id and token_id in self.market_names_by_token:
            return self.market_names_by_token[token_id]
        if condition_id and condition_id in self.market_names_by_condition:
            return self.market_names_by_condition[condition_id]
        if token_id:
            return f"Token {token_id[:12]}…"
        if condition_id:
            return f"Market {condition_id[:12]}…"
        return "Unknown Market"

    def _format_currency(self, value: float | None) -> str:
        """Render currency values consistently for the dashboard."""
        if value is None:
            return "--"
        return f"${value:,.2f}"

    def _format_price(self, value: float | None) -> str:
        """Render token prices consistently."""
        if value is None:
            return "--"
        return f"{value:.3f}"

    def _format_pnl(self, value: float | None) -> str:
        """Render PnL with directional coloring."""
        if value is None:
            return "[dim]--[/dim]"
        color = "green" if value >= 0 else "red"
        sign = "+" if value >= 0 else ""
        return f"[{color}]{sign}${value:,.2f}[/{color}]"

    def _load_open_positions(self) -> list[Position]:
        """Fetch currently open positions from the database."""
        try:
            with get_session() as session:
                query = select(Position).where(Position.status == "OPEN")
                return list(session.exec(query).all())
        except Exception as exc:
            self._record_error("Failed to load open positions", exc)
            return []

    def _load_recent_trades(self, limit: int = 10) -> list[Trade]:
        """Fetch recent recorded trades from the database."""
        try:
            with get_session() as session:
                query = select(Trade)
                trades = list(session.exec(query).all())
                trades.sort(
                    key=lambda trade: (
                        trade.timestamp or datetime.min.replace(tzinfo=timezone.utc),
                        trade.id or 0,
                    )
                )
                trades.reverse()
                return trades[:limit]
        except Exception as exc:
            self._record_error("Failed to load recent trades", exc)
            return []

    def _build_position_rows(self, positions: list[Position]) -> list[dict[str, Any]]:
        """Transform positions into display rows with live price and open PnL."""
        rows: list[dict[str, Any]] = []
        for position in positions:
            current_price = self.price_cache.get(position.token_id)
            open_pnl = None
            if current_price is not None:
                open_pnl = (current_price - float(position.avg_price)) * float(position.size)
            rows.append(
                {
                    "market": self._get_market_name(position.token_id, position.condition_id),
                    "outcome": position.outcome,
                    "size": float(position.size),
                    "avg_price": float(position.avg_price),
                    "current_price": current_price,
                    "open_pnl": open_pnl,
                    "status": position.status,
                    "entry_time": position.entry_time,
                }
            )
        return rows

    def _build_trade_rows(self, trades: list[Trade]) -> list[dict[str, Any]]:
        """Transform trade records into dashboard rows with current market context."""
        rows: list[dict[str, Any]] = []
        for trade in trades:
            trade_time = trade.timestamp.strftime("%H:%M:%S") if trade.timestamp else "--:--:--"
            rows.append(
                {
                    "time": trade_time,
                    "market": self._get_market_name(trade.token_id),
                    "side": trade.side,
                    "size": float(trade.size),
                    "fill_price": float(trade.price),
                    "current_price": self.price_cache.get(trade.token_id),
                    "strategy": trade.strategy,
                    "timestamp": trade.timestamp,
                }
            )
        return rows

    def _build_summary(self, position_rows: list[dict[str, Any]], trades: list[Trade]) -> dict[str, Any]:
        """Compute header metrics from live positions and recorded trades."""
        today = date.today()
        open_pnl_total = sum(row["open_pnl"] or 0.0 for row in position_rows)
        open_pnl_today = sum(
            row["open_pnl"] or 0.0
            for row in position_rows
            if isinstance(row.get("entry_time"), datetime) and row["entry_time"].date() == today
        )
        trades_today = [trade for trade in trades if trade.timestamp.date() == today]
        trade_notional_today = sum(float(trade.price) * float(trade.size) for trade in trades_today)
        return {
            "open_pnl_total": open_pnl_total,
            "open_pnl_today": open_pnl_today,
            "trade_count_today": len(trades_today),
            "trade_notional_today": trade_notional_today,
        }

    def _collect_snapshot(self) -> dict[str, Any]:
        """Gather the current dashboard view-model from runtime state and DB data."""
        positions = self._load_open_positions()
        trades = self._load_recent_trades()
        tracked_tokens = {
            str(token_id)
            for token_id in [*(p.token_id for p in positions), *(t.token_id for t in trades)]
            if token_id
        }
        tracked_tokens.update(self.market_names_by_token.keys())
        self._subscribe_market_feeds(tracked_tokens)
        self._refresh_market_prices(tracked_tokens)

        position_rows = self._build_position_rows(positions)
        trade_rows = self._build_trade_rows(trades)
        self.last_refresh = datetime.now()
        return {
            "positions": position_rows,
            "trades": trade_rows,
            "summary": self._build_summary(position_rows, trades),
            "tracked_tokens": len(tracked_tokens),
        }

    def generate_layout(self) -> Layout:
        """Create the dashboard layout regions."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=5),
        )
        layout["main"].split_row(
            Layout(name="positions", ratio=3),
            Layout(name="recent_trades", ratio=3),
            Layout(name="status", ratio=2),
        )
        return layout

    def update_header(self, layout: Layout, snapshot: dict[str, Any]) -> None:
        """Render the top summary bar."""
        uptime = str(datetime.now() - self.start_time).split(".")[0]
        summary = snapshot.get("summary", {})
        body = (
            f"[bold blue]{self.bot_name}[/bold blue] | "
            f"Uptime: {uptime} | "
            f"Open PnL Today: {self._format_pnl(summary.get('open_pnl_today'))} | "
            f"Open PnL Total: {self._format_pnl(summary.get('open_pnl_total'))} | "
            f"Trades Today: [cyan]{summary.get('trade_count_today', 0)}[/cyan] "
            f"({self._format_currency(summary.get('trade_notional_today'))})"
        )
        layout["header"].update(Panel(body, style="white on black"))

    def update_positions_table(self, layout: Layout, snapshot: dict[str, Any]) -> None:
        """Render open positions with live mark-to-market information."""
        table = Table(title="Open Positions")
        table.add_column("Market", justify="left", overflow="fold")
        table.add_column("Outcome", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Avg Px", justify="right")
        table.add_column("Current Px", justify="right")
        table.add_column("Open PnL", justify="right")

        positions = snapshot["positions"]
        if not positions:
            table.add_row("No open positions", "", "", "", "", "")
        else:
            for row in positions:
                table.add_row(
                    row["market"],
                    row["outcome"],
                    f"{row['size']:.2f}",
                    self._format_price(row["avg_price"]),
                    self._format_price(row["current_price"]),
                    self._format_pnl(row["open_pnl"]),
                )

        layout["positions"].update(Panel(table))

    def update_trades_table(self, layout: Layout, snapshot: dict[str, Any]) -> None:
        """Render recent executed trades with human-readable market names."""
        table = Table(title="Recent Trades")
        table.add_column("Time", justify="left")
        table.add_column("Market", justify="left", overflow="fold")
        table.add_column("Side", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Fill Px", justify="right")
        table.add_column("Last Px", justify="right")
        table.add_column("Strategy", justify="right")

        trades = snapshot["trades"]
        if not trades:
            table.add_row("--", "No recent trades", "", "", "", "", "")
        else:
            for row in trades:
                table.add_row(
                    row["time"],
                    row["market"],
                    row["side"],
                    f"{row['size']:.2f}",
                    self._format_price(row["fill_price"]),
                    self._format_price(row["current_price"]),
                    row["strategy"],
                )

        layout["recent_trades"].update(Panel(table))

    def _render_system_status_panel(self, snapshot: dict[str, Any]) -> Panel:
        """Render runtime mode, circuit, websocket, and strategy status."""
        status_table = Table(title="System Status")
        status_table.add_column("Component", justify="left")
        status_table.add_column("Status", justify="center")
        status_table.add_column("Details", justify="left", overflow="fold")

        mode = "DRY-RUN" if getattr(self.execution_engine, "dry_run", True) else "LIVE"
        status_table.add_row("Mode", mode, "Execution engine")

        if self.ws is None:
            ws_status, ws_details = "N/A", "No websocket attached"
        elif getattr(self.ws, "is_connected", False):
            ws_status = "CONNECTED"
            last_seen = getattr(self.ws, "last_message_at", None)
            ws_details = f"Last msg: {last_seen.strftime('%H:%M:%S') if last_seen else 'waiting'}"
        elif getattr(self.ws, "is_running", False):
            ws_status = "CONNECTING"
            ws_details = getattr(self.ws, "last_error", None) or "Socket started, awaiting connection"
        else:
            ws_status = "STOPPED"
            ws_details = getattr(self.ws, "last_error", None) or "Socket not running"
        status_table.add_row("WebSocket", ws_status, ws_details)

        if self.circuit_breaker is None:
            status_table.add_row("Circuit", "N/A", "No circuit breaker attached")
        else:
            raw_circuit = self.circuit_breaker.status_summary()
            circuit = raw_circuit if isinstance(raw_circuit, dict) else {}
            circuit_status = "OPEN" if bool(circuit.get("tripped")) else "CLOSED"
            circuit_details = str(circuit.get("reason") or "Healthy")
            status_table.add_row("Circuit", circuit_status, circuit_details)

        status_table.add_row(
            "Markets",
            str(snapshot["tracked_tokens"]),
            "Tracked tokens with name/price context",
        )

        strategy_table = Table(title="Strategies")
        strategy_table.add_column("Name", justify="left")
        strategy_table.add_column("Status", justify="center")
        strategy_table.add_column("Markets", justify="right")
        if not self.strategies:
            strategy_table.add_row("None", "IDLE", "0")
        else:
            for strategy in self.strategies:
                strategy_name = getattr(strategy, "name", strategy.__class__.__name__)
                token_count = len(getattr(strategy, "token_ids", []) or [])
                strategy_table.add_row(strategy_name, "RUNNING", str(token_count))

        return Panel(Group(status_table, strategy_table))

    def update_status_panel(self, layout: Layout, snapshot: dict[str, Any]) -> None:
        """Render the right-side runtime status panel."""
        layout["status"].update(self._render_system_status_panel(snapshot))

    def update_footer(self, layout: Layout) -> None:
        """Render last-refresh and recent dashboard warnings."""
        if self.dashboard_errors:
            body = "\n".join(f"• {entry}" for entry in self.dashboard_errors)
            title = "Dashboard Warnings"
        else:
            refreshed = self.last_refresh.strftime("%H:%M:%S") if self.last_refresh else "--"
            body = f"Last refresh: {refreshed} | Cached prices: {len(self.price_cache)} | Status: OK"
            title = "Dashboard Health"
        layout["footer"].update(Panel(body, title=title))

    def render_loop(self) -> None:
        """Continuously render the live dashboard until the process exits."""
        layout = self.generate_layout()
        with Live(layout, refresh_per_second=1, screen=True):
            while True:
                snapshot = self._collect_snapshot()
                self.update_header(layout, snapshot)
                self.update_positions_table(layout, snapshot)
                self.update_trades_table(layout, snapshot)
                self.update_status_panel(layout, snapshot)
                self.update_footer(layout)
                time.sleep(self.refresh_interval)
