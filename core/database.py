"""Database initialization and models for PolyBot."""

import os
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
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
    entry_time: datetime = Field(default_factory=datetime.utcnow)
    status: str = "OPEN"  # "OPEN", "CLOSED"


class Trade(SQLModel, table=True):
    """Records executed trades."""


    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(index=True)
    token_id: str
    side: str  # "BUY", "SELL"
    price: float
    size: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strategy: str


class BotState(SQLModel, table=True):
    """Stores key-value state for the bot."""


    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

sqlite_url = os.getenv("DATABASE_URL", "sqlite:///polybot.db")
engine = create_engine(sqlite_url)


def create_db_and_tables():
    """Initializes the database schema."""

    SQLModel.metadata.create_all(engine)


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


def update_position(
    condition_id: str,
    _token_id: str,
    outcome: str,
    _size_delta: float,
    _price: float
):
    """
    Updates or creates a position. 
    Prevents holding both YES and NO by checking condition_id.
    """
    with get_session() as session:

        # Check if we already have a position in this market (any side)
        statement = select(Position).where(
            Position.condition_id == condition_id, Position.status == "OPEN"
        )
        existing_pos = session.exec(statement).first()

        if existing_pos:
            if existing_pos.outcome != outcome:
                from loguru import logger
                logger.warning(
                    f"Prevented opposing position! Holding {existing_pos.outcome}, "
                    f"rejected {outcome} for {condition_id}"
                )
                return False
            else:
                total_size = existing_pos.size + _size_delta
                if total_size > 0:
                    existing_pos.avg_price = (
                        (existing_pos.avg_price * existing_pos.size) + 
                        (_price * _size_delta)
                    ) / total_size
                existing_pos.size = total_size
        else:
            pos = Position(
                condition_id=condition_id, 
                token_id=_token_id, 
                outcome=outcome, 
                avg_price=_price, 
                size=_size_delta, 
                side="LONG"
            )
            session.add(pos)
        session.commit()
        return True
