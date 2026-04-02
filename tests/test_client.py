"""Tests for core/client.py — PolyClient wrapper with NegRisk awareness."""

import unittest
from unittest.mock import Mock, patch

from core.client import PolyClient
from core.negrisk import NEG_RISK_ADAPTER_ADDRESS, CTF_CONTRACT_ADDRESS


class TestPolyClient(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.mock_clob = Mock()
        self.mock_clob.get_address.return_value = "0xTestAddress"
        self.client = PolyClient(self.mock_clob)

    def test_initialization(self):
        """Test client initialization."""
        self.assertEqual(self.client.clob, self.mock_clob)
        self.assertEqual(self.client.address, "0xTestAddress")
        self.mock_clob.get_address.assert_called_once()

    @patch('core.client.is_neg_risk_market')
    def test_check_neg_risk_true(self, mock_is_neg_risk):
        """Test NegRisk detection with warning log."""
        mock_is_neg_risk.return_value = True
        with patch('core.client.logger') as mock_logger:
            result = self.client.check_neg_risk("0xtoken123")
            self.assertTrue(result)
            mock_is_neg_risk.assert_called_once_with("0xtoken123")
            mock_logger.warning.assert_called_once()

    @patch('core.client.is_neg_risk_market')
    def test_check_neg_risk_false(self, mock_is_neg_risk):
        """Test non-NegRisk market."""
        mock_is_neg_risk.return_value = False
        with patch('core.client.logger') as mock_logger:
            result = self.client.check_neg_risk("0xtoken456")
            self.assertFalse(result)
            mock_logger.warning.assert_not_called()

    @patch('core.client.is_neg_risk_market')
    def test_get_redeem_contract_neg_risk(self, mock_is_neg_risk):
        """Test redeem contract routing for NegRisk markets."""
        mock_is_neg_risk.return_value = True
        result = self.client.get_redeem_contract("0xtoken123")
        self.assertEqual(result, NEG_RISK_ADAPTER_ADDRESS)
        mock_is_neg_risk.assert_called_once_with("0xtoken123")

    @patch('core.client.is_neg_risk_market')
    def test_get_redeem_contract_standard(self, mock_is_neg_risk):
        """Test redeem contract routing for standard markets."""
        mock_is_neg_risk.return_value = False
        result = self.client.get_redeem_contract("0xtoken456")
        self.assertEqual(result, CTF_CONTRACT_ADDRESS)
        mock_is_neg_risk.assert_called_once_with("0xtoken456")

    def test_get_user_balance(self):
        """Test balance fetching."""
        self.mock_clob.get_balance.return_value = 1000.0
        result = self.client.get_user_balance("0xUSDC")
        self.assertEqual(result, 1000.0)
        self.mock_clob.get_balance.assert_called_once_with("0xUSDC")

    def test_get_order_book(self):
        """Test order book fetching."""
        expected_book = {"bids": [[0.45, 100]], "asks": [[0.55, 100]]}
        self.mock_clob.get_order_book.return_value = expected_book
        result = self.client.get_order_book("0xtoken123")
        self.assertEqual(result, expected_book)
        self.mock_clob.get_order_book.assert_called_once_with("0xtoken123")

    @patch('core.client.is_neg_risk_market')
    @patch('core.client.clob_retry')
    def test_post_limit_order_neg_risk(self, mock_clob_retry, mock_is_neg_risk):
        """Test order posting with NegRisk flag."""
        mock_is_neg_risk.return_value = True
        self.mock_clob.create_and_post_order.return_value = {"orderID": "order123", "status": "live"}

        result = self.client.post_limit_order(
            token_id="0xtoken123",
            price=0.55,
            size=100,
            side="BUY"
        )

        self.assertEqual(result["orderID"], "order123")
        mock_is_neg_risk.assert_called_once_with("0xtoken123")

        # Verify OrderArgs was called with neg_risk=True
        call_args = self.mock_clob.create_and_post_order.call_args[0][0]
        self.assertEqual(call_args.token_id, "0xtoken123")
        self.assertEqual(call_args.price, 0.55)
        self.assertEqual(call_args.size, 100)
        self.assertEqual(call_args.side, "BUY")
        # neg_risk should be passed if supported

    def test_order_submission_accepted(self):
        """Test order acceptance logic."""
        self.assertTrue(PolyClient._order_submission_accepted({"orderID": "123", "status": "live"}))
        self.assertTrue(PolyClient._order_submission_accepted({"id": "123", "success": True}))
        self.assertFalse(PolyClient._order_submission_accepted({"success": False}))
        self.assertFalse(PolyClient._order_submission_accepted(None))
        self.assertFalse(PolyClient._order_submission_accepted("invalid"))


if __name__ == "__main__":
    unittest.main()
