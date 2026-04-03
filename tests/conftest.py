# PolyBot Test Configuration
# Shared fixtures for mocks and and test utilities

import os
import tempfile

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Core imports for mocking
from core.client import PolyClient
from core.database import Position, Trade, init_db
from engine.circuit_breaker import CircuitBreaker
from engine.risk import RiskManager

# ──────────────────────────────────────────────────────────────────────────
# Database Fixtures
# ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    # Create temporary file for database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    # Create engine
    engine = create_engine(f"sqlite:///{db_path}")

    # Initialize tables
    SQLModel.metadata.create_all(engine)

    # Create session
    session = Session(engine)

    yield session

    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def test_db_path():
    """Return a temporary database path."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    yield db_path
    os.unlink(db_path)


# ──────────────────────────────────────────────────────────────────────────
# Mock Client Fixtures
# ──────────────────────────────────────────────────────────────────────────

class MockPolyClient:
    """Mock PolyClient for testing."""

    def __init__(self):
        self.orders = {}
        self.order_counter = 0
        self.balance = 1000.0

    def post_limit_order(self, token_id: str, side: str, price: float, size: int, **kwargs) -> dict:
        order_id = f"order_{self.order_counter}"
        self.order_counter += 1

        order = {
            "order_id": order_id,
            "token_id": token_id,
            "side": side,
            "price": price,
            "size": size,
            "status": "LIVE",
        }
        self.orders[order_id] = order
        return order

    def get_order(self, order_id: str) -> dict | None:
        return self.orders.get(order_id)

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            del self.orders[order_id]
            return True
        return False

    def get_order_book(self, token_id: str) -> dict:
        return {
            "bids": [[0.45, 100]],
            "asks": [[0.55, 100]],
        }

    def get_balance(self) -> float:
        return self.balance

    def set_balance(self, balance: float):
        self.balance = balance


@pytest.fixture
def mock_client():
    """Provide a MockPolyClient instance."""
    return MockPolyClient()


# ──────────────────────────────────────────────────────────────────────────
# Mock Risk Manager Fixtures
# ──────────────────────────────────────────────────────────────────────────

class MockRiskManager:
    """Mock RiskManager for testing."""

    def __init__(self):
        self.daily_pnl = 0.0
        self.realized_pnl = 0.0
        self.trades_allowed = True

    def check_trade_allowed(self, strategy_name: str, price: float, size: int, side: str) -> bool:
        return self.trades_allowed

    def record_realized_pnl(self, pnl_delta: float):
        self.realized_pnl += pnl_delta
        self.daily_pnl += pnl_delta

    def snapshot(self) -> dict:
        return {
            "daily_pnl": self.daily_pnl,
            "realized_pnl": self.realized_pnl,
        }


@pytest.fixture
def mock_risk_manager():
    """Provide a MockRiskManager instance."""
    return MockRiskManager()


# ──────────────────────────────────────────────────────────────────────────
# Mock Circuit Breaker Fixtures
# ──────────────────────────────────────────────────────────────────────────

class MockCircuitBreaker:
    """Mock CircuitBreaker for testing."""

    def __init__(self):
        self.tripped = False
        self.enabled = True

    def allows_trading(self) -> bool:
        return self.enabled and not self.tripped

    def is_open(self) -> bool:
        return self.tripped

    def record_error(self, context: str = "") -> None:
        pass

    def record_success(self) -> None:
        pass

    def record_pnl_delta(self, delta: float) -> None:
        pass

    def status_summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "tripped": self.tripped,
            "trading_allowed": self.allows_trading(),
        }


@pytest.fixture
def mock_circuit_breaker():
    """Provide a MockCircuitBreaker instance."""
    return MockCircuitBreaker()


# ──────────────────────────────────────────────────────────────────────────
# Mock WebSocket Fixtures
# ──────────────────────────────────────────────────────────────────────────

class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.subscriptions = {}
        self.connected = False

    def subscribe(self, channel: str, callback) -> None:
        self.subscriptions[channel] = callback

    def unsubscribe(self, channel: str) -> None:
        if channel in self.subscriptions:
            del self.subscriptions[channel]

    def simulate_message(self, channel: str, data: dict) -> None:
        if channel in self.subscriptions:
                self.subscriptions[channel](data)


@pytest.fixture
def mock_websocket():
    """Provide a MockWebSocket instance."""
    return MockWebSocket()


# ──────────────────────────────────────────────────────────────────────────
# Test Data Fixtures
# ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        "condition_id": "0x1234567890abcdef",
        "question_id": "0xabcdef1234567890",
        "tokens": [
            {
                "token_id": "0xtoken1",
                "outcome": "YES",
                "price": 0.55,
            },
            {
                "token_id": "0xtoken2",
                "outcome": "NO",
                "price": 0.45,
            },
        ],
    }


@pytest.fixture
def sample_order_book():
    """Sample order book for testing."""
    return {
        "bids": [
            {"price": "0.50", "size": "100"},
            {"price": "0.49", "size": "200"},
        ],
        "asks": [
            {"price": "0.51", "size": "100"},
            {"price": "0.52", "size": "200"},
        ],
    }


@pytest.fixture
def sample_position():
    """Sample position for testing."""
    return Position(
        condition_id="0x1234567890abcdef",
        token_id="0xtoken1",
        outcome="YES",
        size=100.0,
        avg_price=0.50,
        side="LONG",
        status="OPEN",
    )


@pytest.fixture
def sample_trade():
    """Sample trade for testing."""
    return Trade(
        order_id="order_test_001",
        token_id="0xtoken1",
        side="BUY",
        size=100.0,
        price=0.50,
        strategy="momentum",
    )


# ──────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────

def create_test_position(session, condition_id="0xtest", token_id="0xtoken", outcome="YES", size=100.0, avg_price=0.5):
    """Create a test position in the database."""
    position = Position(
        condition_id=condition_id,
        token_id=token_id,
        outcome=outcome,
        size=size,
        avg_price=avg_price,
        status="OPEN",
    )
    session.add(position)
    session.commit()
    return position


def create_test_trade(session, order_id="order_test", token_id="0xtoken", side="BUY", size=100.0, price=0.5, strategy="test"):
    """Create a test trade in the database."""
    trade = Trade(
        order_id=order_id,
        token_id=token_id,
        side=side,
        size=size,
        price=price,
        strategy=strategy,
    )
    session.add(trade)
    session.commit()
    return trade
