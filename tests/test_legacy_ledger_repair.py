import os
from datetime import datetime
from pathlib import Path
import sys
import unittest

from sqlmodel import select


TEST_DB_PATH = Path("phase1_legacy_repair_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import (  # noqa: E402
    Position,
    Trade,
    audit_legacy_ledger,
    create_db_and_tables,
    engine as db_engine,
    get_session,
    repair_legacy_positions_from_trades,
)


class LegacyLedgerRepairTest(unittest.TestCase):
    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        create_db_and_tables()

    def tearDown(self):
        db_engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_rebuilds_positions_from_trades_and_repairs_legacy_rows(self):
        with get_session() as session:
            session.add_all([
                Trade(order_id="BUY-1", token_id="tok-yes", side="BUY", price=0.40, size=10.0, strategy="legacy", timestamp=datetime(2026, 1, 1, 0, 0, 1)),
                Trade(order_id="SELL-1", token_id="tok-yes", side="SELL", price=0.55, size=4.0, strategy="legacy", timestamp=datetime(2026, 1, 1, 0, 1, 1)),
                Position(condition_id="tok-yes", token_id="tok-yes", outcome="YES", avg_price=0.40, size=10.0, side="LONG", status="OPEN"),
                Position(condition_id="tok-yes", token_id="tok-yes", outcome="NO", avg_price=0.55, size=4.0, side="LONG", status="OPEN"),
            ])
            session.commit()

        market_metadata = [{"token_id": "tok-yes", "condition_id": "cond-1", "outcome": "YES"}]
        audit = audit_legacy_ledger(market_metadata)
        issue_types = {issue["issue_type"] for issue in audit["issues"]}
        self.assertIn("condition_id_equals_token_id", issue_types)
        self.assertIn("condition_mismatch", issue_types)
        self.assertIn("outcome_mismatch", issue_types)
        self.assertIn("duplicate_open_positions", issue_types)

        repair_report = repair_legacy_positions_from_trades(market_metadata, apply=True)
        self.assertTrue(repair_report["can_apply"])
        self.assertTrue(repair_report["applied"])
        self.assertEqual(repair_report["rebuilt_position_count"], 1)

        with get_session() as session:
            positions = session.exec(select(Position)).all()
            self.assertEqual(len(positions), 1)
            position = positions[0]
            self.assertEqual(position.condition_id, "cond-1")
            self.assertEqual(position.token_id, "tok-yes")
            self.assertEqual(position.outcome, "YES")
            self.assertEqual(position.size, 6.0)
            self.assertEqual(position.status, "OPEN")

    def test_refuses_apply_when_trade_metadata_is_missing(self):
        with get_session() as session:
            session.add_all([
                Trade(order_id="BUY-1", token_id="tok-missing", side="BUY", price=0.33, size=3.0, strategy="legacy", timestamp=datetime(2026, 1, 1, 0, 0, 1)),
                Position(condition_id="tok-missing", token_id="tok-missing", outcome="YES", avg_price=0.33, size=3.0, side="LONG", status="OPEN"),
            ])
            session.commit()

        repair_report = repair_legacy_positions_from_trades([], apply=True)
        self.assertFalse(repair_report["can_apply"])
        self.assertFalse(repair_report["applied"])
        self.assertIn("tok-missing", repair_report["unknown_trade_tokens"])

        with get_session() as session:
            positions = session.exec(select(Position)).all()
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0].condition_id, "tok-missing")


if __name__ == "__main__":
    unittest.main()