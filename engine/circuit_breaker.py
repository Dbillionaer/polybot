"""
Circuit Breaker for PolyBot.

Pauses all trading automatically when:
  - N consecutive errors occur within a rolling window, OR
  - Portfolio drawdown exceeds X% in a short time window.

After the cool-down period, trading automatically resumes.
Sends Telegram alerts on trip and reset.

Usage:
    from engine.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()

    # Before every order:
    if not cb.is_open():
        execute_order(...)

    # After any error:
    cb.record_error("CLOB timeout on token 0xABC")

    # After PnL update:
    cb.record_pnl_delta(-15.0)
"""

from __future__ import annotations

import os
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger


def _send_telegram(message: str) -> None:
    """Fire-and-forget Telegram alert."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": f"🚨 PolyBot Circuit Breaker: {message}"},
            timeout=5,
        )
    except Exception:
        pass  # Never let alerting crash the bot


class CircuitBreaker:
    """
    Thread-safe circuit breaker with auto-reset.

    States:
        CLOSED  → trading allowed
        OPEN    → trading blocked; resets after cool_down_minutes
    """

    def __init__(
        self,
        max_consecutive_errors: int | None = None,
        drawdown_pct_trigger: float | None = None,
        drawdown_window_minutes: int | None = None,
        cool_down_minutes: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        enabled_env = os.getenv("CIRCUIT_BREAKER_ENABLED", "true").lower() in ("true", "1")
        self.enabled = enabled if enabled is not None else enabled_env

        self.max_errors = max_consecutive_errors or int(
            os.getenv("CB_MAX_CONSECUTIVE_ERRORS", "4")
        )
        self.drawdown_trigger = drawdown_pct_trigger or float(
            os.getenv("CB_DRAWDOWN_PCT_TRIGGER", "0.03")
        )
        self.drawdown_window_min = drawdown_window_minutes or int(
            os.getenv("CB_DRAWDOWN_WINDOW_MINUTES", "5")
        )
        self.cool_down_min = cool_down_minutes or int(
            os.getenv("CB_COOL_DOWN_MINUTES", "10")
        )

        self._lock = threading.Lock()
        self._tripped: bool = False
        self._trip_reason: str = ""
        self._trip_time: datetime | None = None
        self._consecutive_errors: int = 0
        # Rolling PnL events: list of (timestamp, pnl_delta)
        self._pnl_window: deque[tuple[datetime, float]] = deque()
        self._last_total_pnl: float | None = None
        self._initial_bankroll: float = float(os.getenv("BANKROLL_USDC", "1000"))

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def allows_trading(self) -> bool:
        """
        Returns True if trading is allowed (breaker healthy / CLOSED).
        Returns False if trading is paused (breaker tripped / OPEN).
        """
        if not self.enabled:
            return True

        with self._lock:
            if not self._tripped:
                return True
            # Check if cool-down has elapsed
            if self._trip_time and datetime.now(timezone.utc) >= self._trip_time + timedelta(
                minutes=self.cool_down_min
            ):
                self._reset()
                return True
            trip_time = self._trip_time
            if trip_time is None:
                logger.warning(
                    f"[CircuitBreaker] 🔴 OPEN — trading blocked. Reason: {self._trip_reason}"
                )
                return False
            remaining = (
                trip_time + timedelta(minutes=self.cool_down_min) - datetime.now(timezone.utc)
            ).seconds // 60
            logger.warning(
                f"[CircuitBreaker] 🔴 OPEN — trading blocked for ~{remaining} more min. "
                f"Reason: {self._trip_reason}"
            )
            return False

    def is_open(self) -> bool:
        """Backward-compatible alias for trading-allowed status checks."""
        return self.allows_trading()

    def record_error(self, context: str = "") -> None:
        """Call this after any CLOB/Gamma/WS error."""
        if not self.enabled:
            return
        with self._lock:
            self._consecutive_errors += 1
            logger.debug(
                f"[CircuitBreaker] Error #{self._consecutive_errors}/{self.max_errors}: {context}"
            )
            if self._consecutive_errors >= self.max_errors:
                self._trip(
                    f"{self._consecutive_errors} consecutive errors — last: {context}"
                )

    def record_success(self) -> None:
        """Call after a successful order or API call to reset consecutive-error counter."""
        if not self.enabled:
            return
        with self._lock:
            if self._consecutive_errors > 0:
                logger.debug("[CircuitBreaker] Consecutive error counter reset after success.")
            self._consecutive_errors = 0

    def record_pnl_delta(self, delta: float) -> None:
        """
        Record a PnL change.  Triggers the breaker if the rolling window loss
        exceeds drawdown_trigger % of the initial bankroll.
        """
        if not self.enabled:
            return
        with self._lock:
            self._record_pnl_delta_locked(delta)

    def observe_total_pnl(self, total_pnl: float) -> None:
        """Observe absolute total PnL and convert it into rolling deltas for breaker logic."""
        if not self.enabled:
            return
        with self._lock:
            if self._last_total_pnl is None:
                self._last_total_pnl = total_pnl
                return

            delta = total_pnl - self._last_total_pnl
            self._last_total_pnl = total_pnl
            if delta:
                self._record_pnl_delta_locked(delta)

    def status_summary(self) -> dict[str, Any]:
        """Returns a dict suitable for dashboard display."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "tripped": self._tripped,
                "trading_allowed": (not self._tripped) if self.enabled else True,
                "reason": self._trip_reason,
                "trip_time": self._trip_time.isoformat() if self._trip_time else None,
                "consecutive_errors": self._consecutive_errors,
                "last_total_pnl": self._last_total_pnl,
            }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _record_pnl_delta_locked(self, delta: float) -> None:
        """Internal rolling-drawdown update (must be called under lock)."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=self.drawdown_window_min)

        while self._pnl_window and self._pnl_window[0][0] < cutoff:
            self._pnl_window.popleft()

        self._pnl_window.append((now, delta))

        window_loss = sum(d for _, d in self._pnl_window if d < 0)
        trigger_usdc = self._initial_bankroll * self.drawdown_trigger

        if abs(window_loss) >= trigger_usdc:
            self._trip(
                f"{self.drawdown_window_min}-min drawdown ${abs(window_loss):.2f} "
                f"≥ {self.drawdown_trigger:.1%} of bankroll"
            )

    def _trip(self, reason: str) -> None:
        """Internal: trip the breaker (must be called under self._lock)."""
        if self._tripped:
            return  # Already tripped

        self._tripped = True
        self._trip_reason = reason
        self._trip_time = datetime.now(timezone.utc)

        msg = (
            f"⚡ CIRCUIT BREAKER TRIPPED — all trading paused for "
            f"{self.cool_down_min} minutes.\nReason: {reason}"
        )
        logger.critical(f"[CircuitBreaker] {msg}")
        _send_telegram(msg)

    def _reset(self) -> None:
        """Internal: reset the breaker after cool-down (must be called under self._lock)."""
        self._tripped = False
        self._consecutive_errors = 0
        self._pnl_window.clear()
        self._last_total_pnl = None
        msg = f"✅ Circuit breaker RESET after {self.cool_down_min}-min cool-down. Trading resumed."
        logger.success(f"[CircuitBreaker] {msg}")
        _send_telegram(msg)
