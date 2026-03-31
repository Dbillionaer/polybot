# Tests for core/negrisk.py
# Critical tests for NegRisk adapter handling - required for mainnet deployment

import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from web3 import Web3
from eth_account import Account

# Module under test
from core.negrisk import (
    is_neg_risk_market,
    ensure_adapter_approval,
    convert_to_usdc,
    redeem_neg_risk_position,
    NEG_RISK_ADAPTER_ADDRESS,
    CTF_CONTRACT_ADDRESS,
    GAMMA_API_URL,
)


class TestIsNegRiskMarket(unittest.TestCase):
    """Tests for NegRisk market detection."""

    @patch('core.negrisk.requests.get')
    def test_is_neg_risk_market_true(self, mock_get):
        """Test detection of NegRisk market."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "neg_risk": True,
            "condition_id": "0x1234"
        }
        mock_get.return_value = mock_response
        
        result = is_neg_risk_market("0x1234")
        
        self.assertTrue(result)
        mock_get.assert_called_once_with(f"{GAMMA_API_URL}/markets")

    @patch('core.negrisk.requests.get')
    def test_is_neg_risk_market_false(self, mock_get):
        """Test detection of standard (non-NegRisk) market."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "neg_risk": False,
            "condition_id": "0x5678"
        }
        mock_get.return_value = mock_response
        
        result = is_neg_risk_market("0x5678")
        
        self.assertFalse(result)

    @patch('core.negrisk.requests.get')
    def test_is_neg_risk_market_missing_field(self, mock_get):
        """Test handling of market without neg_risk field."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "condition_id": "0x9999"
            # No neg_risk field
        }
        mock_get.return_value = mock_response
        
        result = is_neg_risk_market("0x9999")
        
        self.assertFalse(result)

    @patch('core.negrisk.requests.get')
    def test_is_neg_risk_market_api_error(self, mock_get):
        """Test handling of API error."""
        mock_get.side_effect = Exception("API error")
        
        result = is_neg_risk_market("0x1234")
        
        self.assertFalse(result)

    @patch('core.negrisk.requests.get')
    def test_is_neg_risk_market_cached(self, mock_get):
        """Test that results are cached."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "neg_risk": True,
            "condition_id": "0xabcd"
        }
        mock_get.return_value = mock_response
        
        # First call
        result1 = is_neg_risk_market("0xabcd")
        self.assertTrue(result1)
        
        # Second call should use cache
        result2 = is_neg_risk_market("0xabcd")
        self.assertTrue(result2)
        
        # API should only be called once due to caching
        self.assertEqual(mock_get.call_count, 1)


class TestEnsureAdapterApproval(unittest.TestCase):
    """Tests for ERC-1155 approval handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_web3 = Mock(spec=Web3)
        self.mock_account = Mock(spec=Account)
        self.mock_contract = Mock()
        
        self.condition_id = "0x1234567890abcdef"
        self.wallet_address = "0xWalletAddress"

    @patch('core.negrisk.Web3')
    @patch('core.negrisk.os.getenv')
    def test_ensure_adapter_approval_already_approved(self, mock_getenv, mock_web3_class):
        """Test when adapter is already approved."""
        mock_getenv.side_effect = lambda k: {
            "POLYGON_RPC_URL": "https://polygon-mainnet.example.com",
            "POLYGON_PRIVATE_KEY": "0x1234567890abcdef"
        }.get(k)
        
        mock_web3_instance = Mock()
        mock_web3_class.return_value = mock_web3_instance
        
        # Mock contract call to return already approved
        mock_contract = Mock()
        mock_contract.functions.isApprovedForAll.return_value.call.return_value = True
        mock_web3_instance.eth.contract.return_value = mock_contract
        
        result = ensure_adapter_approval(self.condition_id, self.wallet_address)
        
        self.assertTrue(result)

    @patch('core.negrisk.Web3')
    @patch('core.negrisk.os.getenv')
    def test_ensure_adapter_approval_needs_approval(self, mock_getenv, mock_web3_class):
        """Test when adapter needs approval."""
        mock_getenv.side_effect = lambda k: {
            "POLYGON_RPC_URL": "https://polygon-mainnet.example.com",
            "POLYGON_PRIVATE_KEY": "0x1234567890abcdef"
        }.get(k)
        
        mock_web3_instance = Mock()
        mock_web3_class.return_value = mock_web3_instance
        
        # Mock contract to return not approved, then approve
        mock_contract = Mock()
        mock_contract.functions.isApprovedForAll.return_value.call.return_value = False
        mock_contract.functions.setApprovalForAll.return_value.transact.return_value = Mock(
            gas=200000,
            gasPrice=Web3.to_wei(30, 'gwei')
        )
        mock_web3_instance.eth.contract.return_value = mock_contract
        
        result = ensure_adapter_approval(self.condition_id, self.wallet_address)
        
        self.assertTrue(result)

    @patch('core.negrisk.Web3')
    @patch('core.negrisk.os.getenv')
    def test_ensure_adapter_approval_no_rpc_url(self, mock_getenv, mock_web3_class):
        """Test handling when RPC URL is not configured."""
        mock_getenv.side_effect = lambda k: None
        
        result = ensure_adapter_approval(self.condition_id, self.wallet_address)
        
        self.assertFalse(result)


class TestConvertToUSDC(unittest.TestCase):
    """Tests for NegRisk redemption via convertToUSDC."""

    def setUp(self):
        """Set up test fixtures."""
        self.condition_id = "0x1234567890abcdef"
        self.token_id = "0xtoken123"
        self.outcome = "YES"
        self.size = 100
        self.wallet_address = "0xWalletAddress"

    @patch('core.negrisk.Web3')
    @patch('core.negrisk.os.getenv')
    def test_convert_to_usdc_success(self, mock_getenv, mock_web3_class):
        """Test successful conversion to USDC."""
        mock_getenv.side_effect = lambda k: {
            "POLYGON_RPC_URL": "https://polygon-mainnet.example.com",
            "POLYGON_PRIVATE_KEY": "0x1234567890abcdef",
            "CTF_CONTRACT_ADDRESS": CTF_CONTRACT_ADDRESS,
            "NEG_RISK_ADAPTER_ADDRESS": NEG_RISK_ADAPTER_ADDRESS,
        }.get(k)
        
        mock_web3_instance = Mock()
        mock_web3_class.return_value = mock_web3_instance
        
        # Mock contract
        mock_contract = Mock()
        mock_contract.functions.convertToUSDC.return_value.transact.return_value = Mock(
            gas=200000,
            gasPrice=Web3.to_wei(30, 'gwei')
        )
        mock_web3_instance.eth.contract.return_value = mock_contract
        
        result = convert_to_usdc(
            self.condition_id,
            self.token_id,
            self.outcome,
            self.size,
            self.wallet_address
        )
        
        self.assertTrue(result)

    @patch('core.negrisk.Web3')
    @patch('core.negrisk.os.getenv')
    def test_convert_to_usdc_transaction_failure(self, mock_getenv, mock_web3_class):
        """Test handling of transaction failure."""
        mock_getenv.side_effect = lambda k: {
            "POLYGON_RPC_URL": "https://polygon-mainnet.example.com",
            "POLYGON_PRIVATE_KEY": "0x1234567890abcdef",
        }.get(k)
        
        mock_web3_instance = Mock()
        mock_web3_class.return_value = mock_web3_instance
        
        # Mock contract to raise exception
        mock_contract = Mock()
        mock_contract.functions.convertToUSDC.side_effect = Exception("Transaction failed")
        mock_web3_instance.eth.contract.return_value = mock_contract
        
        result = convert_to_usdc(
            self.condition_id,
            self.token_id,
            self.outcome,
            self.size,
            self.wallet_address
        )
        
        self.assertFalse(result)


class TestRedeemNegRiskPosition(unittest.TestCase):
    """Tests for the main redemption orchestration function."""

    def setUp(self):
        """Set up test fixtures."""
        self.condition_id = "0x1234567890abcdef"
        self.token_id = "0xtoken123"
        self.outcome = "YES"
        self.size = 100
        self.wallet_address = "0xWalletAddress"

    @patch('core.negrisk.convert_to_usdc')
    @patch('core.negrisk.ensure_adapter_approval')
    @patch('core.negrisk.is_neg_risk_market')
    def test_redeem_neg_risk_position_success(self, mock_is_neg, mock_ensure, mock_convert):
        """Test successful redemption of NegRisk position."""
        mock_is_neg.return_value = True
        mock_ensure.return_value = True
        mock_convert.return_value = True
        
        result = redeem_neg_risk_position(
            self.condition_id,
            self.token_id,
            self.outcome,
            self.size,
            self.wallet_address
        )
        
        self.assertTrue(result)
        mock_is_neg.assert_called_once_with(self.condition_id)
        mock_ensure.assert_called_once()
        mock_convert.assert_called_once()

    @patch('core.negrisk.convert_to_usdc')
    @patch('core.negrisk.ensure_adapter_approval')
    @patch('core.negrisk.is_neg_risk_market')
    def test_redeem_neg_risk_position_not_neg_risk(self, mock_is_neg, mock_ensure, mock_convert):
        """Test handling of non-NegRisk market."""
        mock_is_neg.return_value = False
        
        result = redeem_neg_risk_position(
            self.condition_id,
            self.token_id,
            self.outcome,
            self.size,
            self.wallet_address
        )
        
        self.assertFalse(result)
        mock_convert.assert_not_called()

    @patch('core.negrisk.convert_to_usdc')
    @patch('core.negrisk.ensure_adapter_approval')
    @patch('core.negrisk.is_neg_risk_market')
    def test_redeem_neg_risk_position_approval_fails(self, mock_is_neg, mock_ensure, mock_convert):
        """Test handling when adapter approval fails."""
        mock_is_neg.return_value = True
        mock_ensure.return_value = False
        
        result = redeem_neg_risk_position(
            self.condition_id,
            self.token_id,
            self.outcome,
            self.size,
            self.wallet_address
        )
        
        self.assertFalse(result)
        mock_convert.assert_not_called()

    @patch('core.negrisk.convert_to_usdc')
    @patch('core.negrisk.ensure_adapter_approval')
    @patch('core.negrisk.is_neg_risk_market')
    def test_redeem_neg_risk_position_conversion_fails(self, mock_is_neg, mock_ensure, mock_convert):
        """Test handling when conversion fails."""
        mock_is_neg.return_value = True
        mock_ensure.return_value = True
        mock_convert.return_value = False
        
        result = redeem_neg_risk_position(
            self.condition_id,
            self.token_id,
            self.outcome,
            self.size,
            self.wallet_address
        )
        
        self.assertFalse(result)


class TestContractAddresses(unittest.TestCase):
    """Tests for contract address constants."""

    def test_adapter_address_format(self):
        """Test that adapter address is valid hex."""
        self.assertTrue(NEG_RISK_ADAPTER_ADDRESS.startswith("0x"))
        self.assertEqual(len(NEG_RISK_ADAPTER_ADDRESS), 42)

    def test_ctf_address_format(self):
        """Test that CTF address is valid hex."""
        self.assertTrue(CTF_CONTRACT_ADDRESS.startswith("0x"))
        self.assertEqual(len(CTF_CONTRACT_ADDRESS), 42)

    def test_addresses_are_different(self):
        """Test that adapter and CTF addresses are different."""
        self.assertNotEqual(NEG_RISK_ADAPTER_ADDRESS, CTF_CONTRACT_ADDRESS)


if __name__ == "__main__":
    unittest.main()
