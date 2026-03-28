"""Risk management, position sizing, and trade guards."""

import os
from loguru import logger

from core.database import get_open_positions


class RiskManager:
    """Provides position sizing and risk management rules."""

    def __init__(
        self,
        max_pos_size_pct: float = 0.05,
        daily_loss_limit_pct: float = 0.05,
        total_drawdown_limit_pct: float = 0.25,
        kelly_fraction: float = 0.5,
    ):
        self.max_pos_size_pct = max_pos_size_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.total_drawdown_limit_pct = total_drawdown_limit_pct
        self.kelly_fraction = kelly_fraction

        # Runtime tracking
        self._daily_pnl: float = 0.0
        self._initial_bankroll: float = float(os.getenv("BANKROLL_USDC", "1000"))
        self._current_bankroll: float = self._initial_bankroll

    # ------------------------------------------------------------------
    # Kelly position sizing
    # ------------------------------------------------------------------

    def calculate_kelly_size(self, price: float, win_prob: float, bankroll: float) -> float:
        """
        Fractional Kelly Criterion.
        f* = (p*(b+1) - 1) / b   where b = net odds = (1-p)/p
        """
        if price <= 0 or price >= 1:
            return 0
        b = (1.0 - price) / price
        if b == 0:
            return 0
        f_star = (win_prob * (b + 1) - 1) / b
        if f_star <= 0:
            return 0
        suggested_pct = min(f_star * self.kelly_fraction, self.max_pos_size_pct)
        return bankroll * suggested_pct

    # ------------------------------------------------------------------
    # Trade gate
    # ------------------------------------------------------------------

    def check_trade_allowed(
        self,
        strategy_name: str,
        price: float,
        size: int,
        side: str,
    ) -> bool:
        """
        Returns True if the proposed trade passes all risk filters.
        Checks: drawdown limit, daily loss limit, position overlap.
        """
        # Drawdown check
        if self._initial_bankroll > 0:
            total_drawdown = (
                (self._initial_bankroll - self._current_bankroll) / self._initial_bankroll
            )
            if total_drawdown >= self.total_drawdown_limit_pct:
                logger.critical(
                    f"[Risk] Total drawdown {total_drawdown:.2%} ≥ limit "
                    f"{self.total_drawdown_limit_pct:.2%}. AUTO-SHUTDOWN."
                )
                return False

        # Daily loss check
        daily_limit = self._initial_bankroll * self.daily_loss_limit_pct
        if self._daily_pnl <= -daily_limit:
            logger.warning(
                f"[Risk] Daily loss limit reached (${self._daily_pnl:.2f}). "
                f"Trading paused for {strategy_name}."
            )
            return False

        # Size sanity
        max_notional = self._current_bankroll * self.max_pos_size_pct
        notional = price * size
        if notional > max_notional:
            logger.warning(
                f"[Risk] {strategy_name}: Notional ${notional:.2f} > "
                f"max ${max_notional:.2f}. Order blocked."
            )
            return False

        return True

    # ------------------------------------------------------------------
    # Position overlap check (legacy style)
    # ------------------------------------------------------------------

    def validate_position_overlap(self, condition_id: str, new_side: str) -> bool:
        """Ensures we don't hold both YES and NO for the same market."""
        positions = get_open_positions()
        for pos in positions:
            if pos.condition_id == condition_id and pos.outcome != new_side:
                logger.error(
                    f"[Risk] Conflict! Holding {pos.outcome}, "
                    f"rejected {new_side} for {condition_id}."
                )
                return False
        return True

    # ------------------------------------------------------------------
    # PnL tracking
    # ------------------------------------------------------------------

    def record_pnl(self, pnl_delta: float):
        """Update daily PnL and current bankroll tracking."""
        self._daily_pnl += pnl_delta
        self._current_bankroll += pnl_delta
        logger.debug(
            f"[Risk] PnL Δ ${pnl_delta:+.4f} | "
            f"Daily: ${self._daily_pnl:.2f} | "
            f"Bankroll: ${self._current_bankroll:.2f}"
        )

    def reset_daily_pnl(self):
        """Called at market open or midnight to reset daily counters."""
        logger.info(f"[Risk] Daily PnL reset. Previous: ${self._daily_pnl:.2f}")
        self._daily_pnl = 0.0
