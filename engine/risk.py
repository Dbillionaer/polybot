from loguru import logger

from core.database import get_open_positions


class RiskManager:
    """Provides position sizing and risk management rules."""

    def __init__(

        self, 
        max_pos_size_pct: float = 0.05, 
        daily_loss_limit_pct: float = 0.05,
        total_drawdown_limit_pct: float = 0.25,
        kelly_fraction: float = 0.5
    ):
        self.max_pos_size_pct = max_pos_size_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.total_drawdown_limit_pct = total_drawdown_limit_pct
        self.kelly_fraction = kelly_fraction

    def calculate_kelly_size(self, price: float, win_prob: float, bankroll: float) -> float:
        """
        Calculates position size using Fractional Kelly Criterion.
        f* = (p * (b + 1) - 1) / b
        where b = net odds (odds - 1)
        """
        if price <= 0 or price >= 1:
            return 0
            
        b = (1.0 - price) / price  # net odds
        p = win_prob
        
        if b == 0:
            return 0
            
        f_star = (p * (b + 1) - 1) / b
        
        if f_star <= 0:
            return 0 # No edge
            
        # Apply fractional Kelly and hard cap
        suggested_pct = min(f_star * self.kelly_fraction, self.max_pos_size_pct)
        return bankroll * suggested_pct

    def check_trade_allowed(
        self,
        current_bankroll: float,
        initial_bankroll: float,
        daily_pnl: float
    ) -> bool:

        """
        Checks if trading is globally allowed based on drawdown and daily loss limits.
        """
        total_drawdown = (initial_bankroll - current_bankroll) / initial_bankroll
        if total_drawdown >= self.total_drawdown_limit_pct:
            logger.critical(f"Total drawdown limit reached ({total_drawdown:.2%}). AUTO-SHUTDOWN.")
            return False
            
        if daily_pnl <= - (initial_bankroll * self.daily_loss_limit_pct):
            logger.warning("Daily loss limit reached. Trading paused.")

            return False
            
        return True

    def validate_position_overlap(self, condition_id: str, new_side: str):
        """
        Ensures we don't hold both YES and NO for the same market.
        Returns False if a conflict exists.
        """
        # We can implement a more robust check here by querying the database
        positions = get_open_positions()
        for pos in positions:
            if pos.condition_id == condition_id and pos.outcome != new_side:
                logger.error(
                    f"Cannot take {new_side} position. Already holding "
                    f"{pos.outcome} for market {condition_id}."
                )
                return False

        return True
