import unittest
from unittest.mock import Mock, patch

from core.negrisk import (
    CTF_CONTRACT_ADDRESS,
    NEG_RISK_ADAPTER_ADDRESS,
    _fetch_market_meta,
    ensure_adapter_approval,
    get_redeem_contract,
    is_neg_risk_market,
    redeem_neg_risk_position,
)


class TestIsNegRiskMarket(unittest.TestCase):
    def tearDown(self):
        _fetch_market_meta.cache_clear()

    @patch("core.negrisk._fetch_market_meta")
    def test_is_neg_risk_market_true(self, mock_fetch):
        mock_fetch.return_value = {"neg_risk": True, "condition_id": "0x1234"}
        self.assertTrue(is_neg_risk_market("0x1234"))
        mock_fetch.assert_called_once_with("0x1234")

    @patch("core.negrisk._fetch_market_meta")
    def test_is_neg_risk_market_false(self, mock_fetch):
        mock_fetch.return_value = {"neg_risk": False, "condition_id": "0x5678"}
        self.assertFalse(is_neg_risk_market("0x5678"))

    @patch("core.negrisk._fetch_market_meta")
    def test_is_neg_risk_market_missing_field(self, mock_fetch):
        mock_fetch.return_value = {"condition_id": "0x9999"}
        self.assertFalse(is_neg_risk_market("0x9999"))

    @patch("core.negrisk.requests.get")
    def test_is_neg_risk_market_api_error(self, mock_get):
        _fetch_market_meta.cache_clear()
        mock_get.side_effect = Exception("API error")
        self.assertFalse(is_neg_risk_market("0x1234"))

    @patch("core.negrisk.requests.get")
    def test_is_neg_risk_market_cached(self, mock_get):
        _fetch_market_meta.cache_clear()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"neg_risk": True, "condition_id": "0xabcd"}]
        mock_get.return_value = response

        self.assertTrue(is_neg_risk_market("0xabcd"))
        self.assertTrue(is_neg_risk_market("0xabcd"))
        self.assertEqual(mock_get.call_count, 1)


class TestGetRedeemContract(unittest.TestCase):
    @patch("core.negrisk._fetch_market_meta")
    def test_get_redeem_contract_neg_risk(self, mock_fetch):
        mock_fetch.return_value = {"neg_risk": True}
        self.assertEqual(get_redeem_contract("0x1234"), NEG_RISK_ADAPTER_ADDRESS)

    @patch("core.negrisk._fetch_market_meta")
    def test_get_redeem_contract_standard(self, mock_fetch):
        mock_fetch.return_value = {"neg_risk": False}
        self.assertEqual(get_redeem_contract("0x5678"), CTF_CONTRACT_ADDRESS)


class TestEnsureAdapterApproval(unittest.TestCase):
    def setUp(self):
        self.mock_w3 = Mock()
        self.mock_w3.eth = Mock()
        self.mock_w3.eth.account = Mock()
        self.mock_w3.to_checksum_address.side_effect = lambda x: x
        self.mock_w3.to_wei.side_effect = lambda value, _unit: int(float(value) * 1_000_000_000)
        self.wallet_address = "0xWalletAddress"
        self.private_key = "0xPrivateKey"

    def test_ensure_adapter_approval_already_approved(self):
        mock_contract = Mock()
        mock_contract.functions.isApprovedForAll.return_value.call.return_value = True
        self.mock_w3.eth.contract.return_value = mock_contract

        result = ensure_adapter_approval(self.mock_w3, self.wallet_address, self.private_key)
        self.assertTrue(result)

    def test_ensure_adapter_approval_needs_approval(self):
        mock_contract = Mock()
        mock_contract.functions.isApprovedForAll.return_value.call.return_value = False
        mock_contract.functions.setApprovalForAll.return_value.build_transaction.return_value = {"tx": 1}
        self.mock_w3.eth.contract.return_value = mock_contract
        self.mock_w3.eth.get_transaction_count.return_value = 1
        signed = Mock()
        signed.rawTransaction = b"signed"
        self.mock_w3.eth.account.sign_transaction.return_value = signed
        tx_hash = Mock()
        tx_hash.hex.return_value = "0xabc"
        self.mock_w3.eth.send_raw_transaction.return_value = tx_hash
        self.mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}

        result = ensure_adapter_approval(self.mock_w3, self.wallet_address, self.private_key)
        self.assertTrue(result)

    def test_ensure_adapter_approval_exception_returns_false(self):
        self.mock_w3.eth.contract.side_effect = RuntimeError("boom")
        result = ensure_adapter_approval(self.mock_w3, self.wallet_address, self.private_key)
        self.assertFalse(result)


class TestRedeemNegRiskPosition(unittest.TestCase):
    def setUp(self):
        self.condition_id = "0x" + "12" * 32
        self.amount_wei = 100
        self.mock_w3 = Mock()
        self.mock_w3.eth = Mock()
        self.mock_w3.eth.account = Mock()
        self.mock_w3.to_checksum_address.side_effect = lambda x: x
        self.mock_w3.to_wei.side_effect = lambda value, _unit: int(float(value) * 1_000_000_000)
        self.wallet_address = "0xWalletAddress"
        self.private_key = "0xPrivateKey"

    def test_redeem_neg_risk_position_dry_run(self):
        result = redeem_neg_risk_position(
            self.mock_w3,
            self.wallet_address,
            self.private_key,
            self.condition_id,
            self.amount_wei,
            dry_run=True,
        )
        self.assertTrue(result)

    def test_redeem_neg_risk_position_success(self):
        adapter = Mock()
        adapter.functions.convertToUSDC.return_value.build_transaction.return_value = {"tx": 1}
        self.mock_w3.eth.contract.return_value = adapter
        self.mock_w3.eth.get_transaction_count.return_value = 1
        signed = Mock()
        signed.rawTransaction = b"signed"
        self.mock_w3.eth.account.sign_transaction.return_value = signed
        tx_hash = Mock()
        tx_hash.hex.return_value = "0xabc"
        self.mock_w3.eth.send_raw_transaction.return_value = tx_hash
        self.mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 1, "logs": [{"data": "0x0"}]}

        result = redeem_neg_risk_position(
            self.mock_w3,
            self.wallet_address,
            self.private_key,
            self.condition_id,
            self.amount_wei,
            dry_run=False,
        )
        self.assertTrue(result)

    def test_redeem_neg_risk_position_reverted(self):
        adapter = Mock()
        adapter.functions.convertToUSDC.return_value.build_transaction.return_value = {"tx": 1}
        self.mock_w3.eth.contract.return_value = adapter
        self.mock_w3.eth.get_transaction_count.return_value = 1
        signed = Mock()
        signed.rawTransaction = b"signed"
        self.mock_w3.eth.account.sign_transaction.return_value = signed
        tx_hash = Mock()
        tx_hash.hex.return_value = "0xabc"
        self.mock_w3.eth.send_raw_transaction.return_value = tx_hash
        self.mock_w3.eth.wait_for_transaction_receipt.return_value = {"status": 0, "logs": [{"data": "0x0"}]}

        result = redeem_neg_risk_position(
            self.mock_w3,
            self.wallet_address,
            self.private_key,
            self.condition_id,
            self.amount_wei,
            dry_run=False,
        )
        self.assertFalse(result)

    def test_redeem_neg_risk_position_exception_returns_false(self):
        self.mock_w3.eth.contract.side_effect = RuntimeError("boom")
        result = redeem_neg_risk_position(
            self.mock_w3,
            self.wallet_address,
            self.private_key,
            self.condition_id,
            self.amount_wei,
            dry_run=False,
        )
        self.assertFalse(result)


class TestContractAddresses(unittest.TestCase):
    def test_adapter_address_format(self):
        self.assertTrue(NEG_RISK_ADAPTER_ADDRESS.startswith("0x"))
        self.assertEqual(len(NEG_RISK_ADAPTER_ADDRESS), 42)

    def test_ctf_address_format(self):
        self.assertTrue(CTF_CONTRACT_ADDRESS.startswith("0x"))
        self.assertEqual(len(CTF_CONTRACT_ADDRESS), 42)

    def test_addresses_are_different(self):
        self.assertNotEqual(NEG_RISK_ADAPTER_ADDRESS, CTF_CONTRACT_ADDRESS)


if __name__ == "__main__":
    unittest.main()
