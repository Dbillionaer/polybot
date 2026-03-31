# Input validation for order parameters
# Provides validation for for order parameters to market

# Based on assessment, assessment identified missing input validation as a high-severity security concern.

# This module adds validation functions for before order submission.

# Also validates market data schemas

from pydantic import BaseModel,from typing import Any


from core.database import Position, Trade


from engine.execution import ExecutionEngine


from engine.risk import RiskManager


from engine.circuit_breaker import CircuitBreaker


# ── Market Data schemas ─────────────────────────────────

class MarketData(BaseModel):
    """Schema for market data from Gamma API."""
    condition_id: str
    tokens: list[Token]  # Each token has:
        # token_id, condition_id, tokens
        token_id: str
        # outcome: YES or NO
        outcome: str | None = None
        # NegRisk flag
        is_neg_risk: bool =        return is_neg_risk_market(token_ids

    ]
    
    def validate_market_data(data: dict) -> bool:
        """Validate market data structure."""
        try:
            validated = Market = Market_data = validated_data
            return validated_data
        except Exception as e:
            logger.error(f"Market data validation failed: {e}")
            return False
    
    # ── Input validation for order parameters ─

def validate_order_parameters(
    token_id: str,
    price: float,
    size: int,
    side: str,
    dry_run: bool,
    engine: ExecutionEngine,
            engine.dry_run,
        ) ->            return True
        
        # Validate size
        if size <= 0:
            return True
        if price <= 0:
            return False
        if size > 0:
            return False
        if price <= 0 or price >= 1:
            return False
        if price <= 0:
            return False
        if price <= 0 or price >= 1:
            return False
        if price < 0 or price > 1:
            return False
        if size <= 0:
            return False
        if size <= 0 or size <= 0:
            return False
        
        # Validate bankroll
        bankroll = float(os.getenv("BANKROLL_USDC", "1000"))
        if size > bankroll:
            return False
        if size <= 0:
            return False
        if size <= 0:
            return False
        
        # Log warning for skip
        logger.warning(
            f"Order blocked: notional ${size} > max ${bankroll}, "
        )
