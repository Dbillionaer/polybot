import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from engine.telemetry_collector import TelemetryCollector


@dataclass
class FakeAcceptedOrder:
    order_id: str
    token_id: str
    condition_id: str
    outcome: str | None
    side: str
    price: float
    size: float
    strategy_name: str
    filled_size: float = 0.0
    last_status: str | None = None
    accepted_at: datetime = datetime.now(timezone.utc) - timedelta(milliseconds=100)


class TelemetryCollectorTest(unittest.TestCase):
    def test_records_attempts_acceptance_and_fill_metrics(self):
        telemetry = TelemetryCollector()
        telemetry.record_strategy_attempt("StrategyA")
        telemetry.record_strategy_acceptance("StrategyA")
        telemetry.record_fill(
            FakeAcceptedOrder(
                order_id="o1",
                token_id="tok",
                condition_id="cond",
                outcome="YES",
                side="BUY",
                price=0.40,
                size=10,
                strategy_name="StrategyA",
            ),
            fill_price=0.41,
        )
        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["fills"]["count"], 1)
        self.assertEqual(snapshot["strategies"]["StrategyA"]["order_attempts"], 1)
        self.assertEqual(snapshot["strategies"]["StrategyA"]["accepted_orders"], 1)
        self.assertEqual(snapshot["strategies"]["StrategyA"]["fill_events"], 1)
        self.assertAlmostEqual(snapshot["fills"]["avg_adverse_slippage_bps"], 250.0, places=3)

    def test_records_strategy_errors(self):
        telemetry = TelemetryCollector()
        telemetry.record_strategy_error("StrategyB", "ctx", RuntimeError("boom"))
        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["strategies"]["StrategyB"]["error_count"], 1)
        self.assertEqual(len(snapshot["recent_errors"]), 1)


if __name__ == "__main__":
    unittest.main()
