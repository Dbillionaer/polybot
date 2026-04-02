"""Database initialization and models for PolyBot."""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional

from dotenv import load_dotenv
from loguru import logger
from sqlmodel import Field, Session, SQLModel, create_engine, select

load_dotenv()


class Position(SQLModel, table=True):
    """Represents an open or closed position."""


    id: Optional[int] = Field(default=None, primary_key=True)
    condition_id: str = Field(index=True)
    token_id: str = Field(index=True)
    outcome: str  # "YES" or "NO"
    avg_price: float
    size: float
    side: str  # "LONG"
    entry_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "OPEN"  # "OPEN", "CLOSED"


class Trade(SQLModel, table=True):
    """Records executed trades."""


    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True)
    token_id: str
    side: str  # "BUY", "SELL"
    price: float
    size: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy: str


class BotState(SQLModel, table=True):
    """Stores key-value state for the bot."""


    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

sqlite_url = os.getenv("DATABASE_URL", "sqlite:///polybot.db")
engine = create_engine(sqlite_url)


@dataclass(slots=True)
class MarketIdentity:
    """Minimal token→market identity used for ledger repair."""

    token_id: str
    condition_id: str
    outcome: str | None = None


@dataclass(slots=True)
class PositionUpdateResult:
    """Outcome of a confirmed fill being applied to the position ledger."""

    applied: bool
    realized_pnl: float = 0.0
    position_size: float = 0.0
    avg_price: float | None = None
    status: str | None = None

    def __bool__(self) -> bool:
        return self.applied


def create_db_and_tables():
    """Initializes the database schema."""

    SQLModel.metadata.create_all(engine)


init_db = create_db_and_tables


def get_session():
    """Yields a database session."""

    return Session(engine)


def record_trade(
    order_id: str,
    token_id: str,
    side: str,
    price: float,
    size: float,
    strategy: str
):
    """Records a trade in the database."""


    with get_session() as session:
        trade = Trade(
            order_id=order_id,
            token_id=token_id,
            side=side,
            price=price,
            size=size,
            strategy=strategy
        )
        session.add(trade)
        session.commit()


def get_open_positions() -> List[Position]:
    """Retrieves all open positions."""


    with get_session() as session:
        statement = select(Position).where(Position.status == "OPEN")
        return session.exec(statement).all()


def get_all_positions() -> List[Position]:
    """Retrieve all position rows, open and closed."""
    with get_session() as session:
        statement = select(Position).order_by(Position.id)
        return list(session.exec(statement).all())


def get_all_trades() -> List[Trade]:
    """Retrieve all trade rows in deterministic chronological order."""
    with get_session() as session:
        statement = select(Trade).order_by(Trade.timestamp, Trade.id)
        return list(session.exec(statement).all())


def _normalize_market_metadata(
    market_metadata: Iterable[dict[str, Any]] | Mapping[str, dict[str, Any]] | None,
) -> dict[str, MarketIdentity]:
    """Normalize supported market metadata inputs into a token-indexed map."""
    if not market_metadata:
        return {}

    if isinstance(market_metadata, Mapping):
        values = []
        for token_id, meta in market_metadata.items():
            if isinstance(meta, MarketIdentity):
                merged = asdict(meta)
                merged.setdefault("token_id", token_id)
                values.append(merged)
            elif isinstance(meta, Mapping):
                merged = dict(meta)
                merged.setdefault("token_id", token_id)
                values.append(merged)
            else:
                values.append({"token_id": token_id, "condition_id": str(meta)})
    else:
        values = list(market_metadata)

    normalized: dict[str, MarketIdentity] = {}
    for meta in values:
        token_id = str(meta.get("token_id") or meta.get("tokenId") or "")
        if not token_id:
            continue
        condition_id = str(meta.get("condition_id") or meta.get("conditionId") or token_id)
        outcome = meta.get("outcome") or meta.get("name") or meta.get("label")
        normalized[token_id] = MarketIdentity(
            token_id=token_id,
            condition_id=condition_id,
            outcome=str(outcome) if outcome else None,
        )
    return normalized


def _serialize_position(position: Position) -> dict[str, Any]:
    """Convert a position model to a JSON-friendly dict."""
    return {
        "id": position.id,
        "condition_id": position.condition_id,
        "token_id": position.token_id,
        "outcome": position.outcome,
        "avg_price": float(position.avg_price),
        "size": float(position.size),
        "side": position.side,
        "entry_time": position.entry_time.isoformat() if position.entry_time else None,
        "status": position.status,
    }


def audit_legacy_ledger(
    market_metadata: Iterable[dict[str, Any]] | Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inspect positions/trades for signatures of pre-fix ledger corruption."""
    market_index = _normalize_market_metadata(market_metadata)
    positions = get_all_positions()
    trades = get_all_trades()
    issue_counts: dict[str, int] = defaultdict(int)
    issues: list[dict[str, Any]] = []
    open_positions_by_token: dict[str, list[int | None]] = defaultdict(list)

    for position in positions:
        expected = market_index.get(position.token_id)
        if position.status == "OPEN":
            open_positions_by_token[position.token_id].append(position.id)

        if position.condition_id == position.token_id:
            issue_counts["condition_id_equals_token_id"] += 1
            issues.append({
                "issue_type": "condition_id_equals_token_id",
                "position_id": position.id,
                "token_id": position.token_id,
                "condition_id": position.condition_id,
                "expected_condition_id": expected.condition_id if expected else None,
            })

        if expected and position.condition_id != expected.condition_id:
            issue_counts["condition_mismatch"] += 1
            issues.append({
                "issue_type": "condition_mismatch",
                "position_id": position.id,
                "token_id": position.token_id,
                "condition_id": position.condition_id,
                "expected_condition_id": expected.condition_id,
            })

        if expected and expected.outcome and position.outcome != expected.outcome:
            issue_counts["outcome_mismatch"] += 1
            issues.append({
                "issue_type": "outcome_mismatch",
                "position_id": position.id,
                "token_id": position.token_id,
                "outcome": position.outcome,
                "expected_outcome": expected.outcome,
            })

        if position.size == 0 and position.status != "CLOSED":
            issue_counts["zero_size_open_position"] += 1
            issues.append({
                "issue_type": "zero_size_open_position",
                "position_id": position.id,
                "token_id": position.token_id,
                "status": position.status,
            })

        if position.size > 0 and position.status == "CLOSED":
            issue_counts["closed_position_with_size"] += 1
            issues.append({
                "issue_type": "closed_position_with_size",
                "position_id": position.id,
                "token_id": position.token_id,
                "size": float(position.size),
            })

    for token_id, position_ids in open_positions_by_token.items():
        if len(position_ids) > 1:
            issue_counts["duplicate_open_positions"] += 1
            issues.append({
                "issue_type": "duplicate_open_positions",
                "token_id": token_id,
                "position_ids": position_ids,
            })

    trade_token_ids = sorted({trade.token_id for trade in trades})
    unknown_trade_tokens = sorted(token_id for token_id in trade_token_ids if token_id not in market_index)

    return {
        "position_count": len(positions),
        "trade_count": len(trades),
        "issue_counts": dict(issue_counts),
        "issues": issues,
        "unknown_trade_tokens": unknown_trade_tokens,
        "can_rebuild_from_trades": not unknown_trade_tokens,
    }


def repair_legacy_positions_from_trades(
    market_metadata: Iterable[dict[str, Any]] | Mapping[str, dict[str, Any]] | None,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Rebuild the position table from trades using corrected BUY/SELL semantics."""
    market_index = _normalize_market_metadata(market_metadata)
    audit_report = audit_legacy_ledger(market_index)
    trades = get_all_trades()

    rebuilt_states: dict[str, dict[str, Any]] = {}
    oversold_trades: list[dict[str, Any]] = []
    invalid_trade_sides: list[dict[str, Any]] = []

    for trade in trades:
        market = market_index.get(trade.token_id)
        if market is None:
            continue

        normalized_side = trade.side.upper()
        state = rebuilt_states.get(trade.token_id)

        if normalized_side == "BUY":
            if state is None or state["status"] == "CLOSED":
                rebuilt_states[trade.token_id] = {
                    "condition_id": market.condition_id,
                    "token_id": trade.token_id,
                    "outcome": market.outcome or "UNKNOWN",
                    "avg_price": float(trade.price),
                    "size": float(trade.size),
                    "side": "LONG",
                    "entry_time": trade.timestamp,
                    "status": "OPEN",
                }
            else:
                total_size = float(state["size"]) + float(trade.size)
                state["avg_price"] = (
                    (float(state["avg_price"]) * float(state["size"])) + (float(trade.price) * float(trade.size))
                ) / total_size
                state["size"] = total_size
                state["condition_id"] = market.condition_id
                state["outcome"] = market.outcome or state["outcome"]
                state["status"] = "OPEN"
        elif normalized_side == "SELL":
            if state is None or state["status"] != "OPEN" or float(trade.size) > float(state["size"]) + 1e-9:
                oversold_trades.append({
                    "trade_id": trade.id,
                    "order_id": trade.order_id,
                    "token_id": trade.token_id,
                    "sell_size": float(trade.size),
                    "open_size": float(state["size"]) if state else 0.0,
                })
                continue

            remaining_size = float(state["size"]) - float(trade.size)
            state["size"] = 0.0 if abs(remaining_size) <= 1e-9 else remaining_size
            state["condition_id"] = market.condition_id
            state["outcome"] = market.outcome or state["outcome"]
            if float(state["size"]) == 0.0:
                state["status"] = "CLOSED"
        else:
            invalid_trade_sides.append({
                "trade_id": trade.id,
                "order_id": trade.order_id,
                "token_id": trade.token_id,
                "side": trade.side,
            })

    rebuilt_positions = [
        {
            **state,
            "entry_time": state["entry_time"].isoformat() if state.get("entry_time") else None,
        }
        for _, state in sorted(rebuilt_states.items())
    ]

    can_apply = (
        not audit_report["unknown_trade_tokens"]
        and not oversold_trades
        and not invalid_trade_sides
    )
    applied = False
    backup_positions = [_serialize_position(position) for position in get_all_positions()]

    if apply and can_apply:
        with get_session() as session:
            for position in session.exec(select(Position)).all():
                session.delete(position)
            for state in rebuilt_states.values():
                session.add(Position(**state))
            session.commit()
        applied = True

    return {
        **audit_report,
        "rebuilt_position_count": len(rebuilt_positions),
        "rebuilt_positions": rebuilt_positions,
        "oversold_trades": oversold_trades,
        "invalid_trade_sides": invalid_trade_sides,
        "can_apply": can_apply,
        "applied": applied,
        "blocked_reason": None if can_apply else (
            "missing market metadata or inconsistent trade history prevents safe automatic rewrite"
        ),
        "backup_positions": backup_positions,
    }


def update_position(
    condition_id: str,
    token_id: str,
    outcome: str | None,
    side: str,
    size_delta: float,
    price: float,
) -> PositionUpdateResult:
    """
    Update position state from a confirmed fill.

    BUY fills increase or open a position for the specific token.
    SELL fills reduce that same token position and mark it CLOSED once fully exited.
    """
    if size_delta <= 0:
        logger.warning("[Positions] Ignoring non-positive fill size update.")
        return PositionUpdateResult(applied=False)

    normalized_side = side.upper()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError(f"Unsupported fill side: {side}")

    resolved_condition_id = condition_id or token_id
    resolved_outcome = outcome or "UNKNOWN"

    with get_session() as session:
        statement = select(Position).where(
            Position.token_id == token_id, Position.status == "OPEN"
        )
        existing_pos = session.exec(statement).first()

        if normalized_side == "BUY":
            if existing_pos:
                total_size = existing_pos.size + size_delta
                existing_pos.avg_price = (
                    (existing_pos.avg_price * existing_pos.size) + (price * size_delta)
                ) / total_size
                existing_pos.size = total_size
                existing_pos.condition_id = resolved_condition_id
                existing_pos.outcome = resolved_outcome
                existing_pos.status = "OPEN"
            else:
                pos = Position(
                    condition_id=resolved_condition_id,
                    token_id=token_id,
                    outcome=resolved_outcome,
                    avg_price=price,
                    size=size_delta,
                    side="LONG",
                )
                session.add(pos)
        else:
            if not existing_pos:
                logger.warning(
                    f"[Positions] Cannot apply SELL fill for {token_id[:12]}… "
                    "because no OPEN position exists."
                )
                return PositionUpdateResult(applied=False)

            if size_delta > existing_pos.size:
                logger.warning(
                    f"[Positions] SELL fill {size_delta:.2f} exceeds OPEN size "
                    f"{existing_pos.size:.2f} for {token_id[:12]}…."
                )
                return PositionUpdateResult(applied=False)

            realized_pnl = (price - existing_pos.avg_price) * size_delta
            remaining_size = existing_pos.size - size_delta
            existing_pos.condition_id = resolved_condition_id
            existing_pos.outcome = resolved_outcome
            existing_pos.size = 0.0 if abs(remaining_size) <= 1e-9 else remaining_size
            if existing_pos.size == 0.0:
                existing_pos.status = "CLOSED"
            else:
                existing_pos.status = "OPEN"

        session.commit()
        persisted = existing_pos if existing_pos else pos
        return PositionUpdateResult(
            applied=True,
            realized_pnl=realized_pnl if normalized_side == "SELL" else 0.0,
            position_size=float(persisted.size),
            avg_price=float(persisted.avg_price),
            status=persisted.status,
        )
