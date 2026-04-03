from datetime import datetime, timezone

from sqlmodel import SQLModel

from core.database import Position, Trade, create_db_and_tables, engine, get_session
from ui.operator_controller import OperatorController


class StubExecutionEngine:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self._running = False
        self.cancel_all_calls = 0
        self._operator_paused = False

    def get_pending_orders(self):
        return []

    def get_telemetry_snapshot(self):
        return {"accepted_orders": 2}

    def is_fill_reconciliation_running(self):
        return self._running

    def start_fill_reconciliation(self, poll_interval_seconds: float = 2.0):
        del poll_interval_seconds
        if self._running or self.dry_run:
            return False
        self._running = True
        return True

    def stop_fill_reconciliation(self):
        self._running = False

    def cancel_all_open_orders(self):
        self.cancel_all_calls += 1
        return True

    def pause_operator_trading(self, reason: str = ""):
        del reason
        self._operator_paused = True
        return True

    def resume_operator_trading(self):
        self._operator_paused = False
        return True

    def get_operator_trading_status(self):
        return {"paused": self._operator_paused, "reason": "" if not self._operator_paused else "manual"}


class StubWebSocket:
    def status_summary(self):
        return {"is_connected": True, "subscription_count": 3}


class StubCircuitBreaker:
    def status_summary(self):
        return {"tripped": False, "reason": "", "trading_allowed": True}


class StubStrategy:
    def __init__(self, name: str, token_ids: list[str]):
        self.name = name
        self.token_ids = token_ids


class TestOperatorController:
    def setup_method(self):
        SQLModel.metadata.drop_all(engine)
        create_db_and_tables()

        with get_session() as session:
            session.add(
                Position(
                    condition_id="cond-1",
                    token_id="token-1",
                    outcome="YES",
                    size=5,
                    avg_price=0.42,
                    side="LONG",
                    status="OPEN",
                    entry_time=datetime.now(timezone.utc),
                )
            )
            session.add(
                Trade(
                    order_id="order-1",
                    token_id="token-1",
                    side="BUY",
                    price=0.42,
                    size=5,
                    strategy="HFM",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            session.commit()

    def test_status_snapshot_includes_runtime_and_db_state(self):
        controller = OperatorController(
            execution_engine=StubExecutionEngine(dry_run=False),
            ws=StubWebSocket(),
            circuit_breaker=StubCircuitBreaker(),
            strategies=[StubStrategy("HFM", ["token-1"])],
            markets=[{"token_id": "token-1", "question": "Will BTC rally?"}],
        )

        snapshot = controller.get_status_snapshot()

        assert snapshot["mode"] == "LIVE"
        assert snapshot["market_count"] == 1
        assert snapshot["strategies"][0]["name"] == "HFM"
        assert snapshot["websocket"]["is_connected"] is True
        assert snapshot["circuit_breaker"]["tripped"] is False
        assert snapshot["positions"][0]["market_name"] == "Will BTC rally?"
        assert snapshot["recent_trades"][0]["trade_id"] == "order-1"
        assert snapshot["execution"]["telemetry"]["accepted_orders"] == 2
        assert snapshot["execution"]["operator_pause"]["paused"] is False

    def test_control_actions_delegate_to_execution_engine(self):
        engine = StubExecutionEngine(dry_run=False)
        controller = OperatorController(execution_engine=engine)

        start_result = controller.start_fill_reconciliation(3.0)
        cancel_result = controller.cancel_all_open_orders()
        stop_result = controller.stop_fill_reconciliation()

        assert start_result["success"] is True
        assert cancel_result["success"] is True
        assert engine.cancel_all_calls == 1
        assert stop_result["success"] is True

    def test_pause_and_resume_delegate_to_execution_engine(self):
        engine = StubExecutionEngine(dry_run=False)
        controller = OperatorController(execution_engine=engine)

        pause_result = controller.pause_trading("manual test")
        paused_snapshot = controller.get_status_snapshot()
        resume_result = controller.resume_trading()
        resumed_snapshot = controller.get_status_snapshot()

        assert pause_result["success"] is True
        assert paused_snapshot["execution"]["operator_pause"]["paused"] is True
        assert resume_result["success"] is True
        assert resumed_snapshot["execution"]["operator_pause"]["paused"] is False
