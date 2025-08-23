import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from app.services.margin import MarginService
from app.models import Liquidation

@pytest.fixture
def mock_clients():
    """Create mock clients for testing"""
    account_client = AsyncMock()
    market_client = AsyncMock()
    postgres_client = AsyncMock()
    return account_client, market_client, postgres_client

@pytest.fixture
def safe_account():
    """Mock account with 1 BTC position, safe from liquidation"""
    return {
        'account_id': 1,
        'balance': Decimal('10000'),  # £10k cash remaining
        'btc_quantity': Decimal('1'),
        'btc_avg_price': Decimal('50000'),
        'btc_mark_price': Decimal('52000')  # £2k profit
        # Total equity: 10000 + 2000 = 12000
        # Maintenance required: 52000 * 0.10 = 5200
        # Safe: 12000 > 5200 ✓
    }

@pytest.fixture
def liquidation_account():
    """Mock account with 1 BTC position, needs liquidation"""
    return {
        'account_id': 2,
        'balance': Decimal('2000'),  # £2k cash remaining
        'btc_quantity': Decimal('1'),
        'btc_avg_price': Decimal('50000'),
        'btc_mark_price': Decimal('45000')  # £5k loss
        # Total equity: 2000 + (-5000) = -3000
        # Maintenance required: 45000 * 0.10 = 4500
        # Liquidation: -3000 < 4500 ✗
    }

@pytest.fixture
def margin_service(mock_clients):
    """Create margin service with mocked dependencies"""
    account_client, market_client, postgres_client = mock_clients
    return MarginService(account_client, market_client, postgres_client)

class TestMarginService:
    
    def test_is_liquidation_candidate_false_safe_account(self, margin_service):
        """Test liquidation detection - account is safe"""
        equity = Decimal('12000')
        maintenance_required = Decimal('5200')
        
        result = margin_service.is_liquidation_candidate(equity, maintenance_required)
        assert result is False
    
    def test_is_liquidation_candidate_true_insufficient_equity(self, margin_service):
        """Test liquidation detection - equity below maintenance margin"""
        equity = Decimal('4000')
        maintenance_required = Decimal('5000')
        
        result = margin_service.is_liquidation_candidate(equity, maintenance_required)
        assert result is True
    
    def test_is_liquidation_candidate_true_negative_equity(self, margin_service):
        """Test liquidation detection - negative equity"""
        equity = Decimal('-3000')
        maintenance_required = Decimal('4500')
        
        result = margin_service.is_liquidation_candidate(equity, maintenance_required)
        assert result is True
    
    def test_is_liquidation_candidate_edge_case_equal_amounts(self, margin_service):
        """Test liquidation detection - equity exactly equals maintenance margin"""
        equity = Decimal('5000')
        maintenance_required = Decimal('5000')
        
        # At exactly maintenance level, should not liquidate
        result = margin_service.is_liquidation_candidate(equity, maintenance_required)
        assert result is False

    @pytest.mark.asyncio
    async def test_record_liquidation(self, margin_service, mock_clients):
        """Test recording liquidation event in PostgreSQL"""
        account_client, market_client, postgres_client = mock_clients
        
        account_id = 123
        reason = "Equity below maintenance margin"
        
        # Mock the insert_model method
        postgres_client.insert_model.return_value = 1
        
        await margin_service.record_liquidation(account_id, reason)
        
        # Verify the liquidation was recorded
        postgres_client.insert_model.assert_called_once()
        call_args = postgres_client.insert_model.call_args
        liquidation = call_args[0][0]  # First argument is the liquidation object
        
        assert liquidation.account_id == account_id
        assert liquidation.reason == reason

    @pytest.mark.asyncio
    async def test_get_liquidation_history_all_accounts(self, margin_service, mock_clients):
        """Test getting liquidation history for all accounts"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mock liquidations
        mock_liquidations = [
            Liquidation(
                id=1,
                account_id=2,
                reason="Equity below maintenance margin after BTC price drop",
                timestamp=None
            )
        ]
        
        postgres_client.fetch_models.return_value = mock_liquidations
        
        liquidations = await margin_service.get_liquidation_history()
        
        # Verify the query was called correctly
        postgres_client.fetch_models.assert_called_once()
        call_args = postgres_client.fetch_models.call_args
        assert call_args[0][0] == Liquidation  # First argument is the model class
        
        # Verify results
        assert len(liquidations) == 1
        assert liquidations[0].account_id == 2
        assert liquidations[0].reason == "Equity below maintenance margin after BTC price drop"

    @pytest.mark.asyncio
    async def test_get_liquidation_history_filtered_by_account(self, margin_service, mock_clients):
        """Test getting liquidation history filtered by account"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mock liquidations
        mock_liquidations = [
            Liquidation(
                id=1,
                account_id=123,
                reason="Insufficient margin",
                timestamp=None
            )
        ]
        
        postgres_client.fetch_models.return_value = mock_liquidations
        
        liquidations = await margin_service.get_liquidation_history(account_id=123, limit=50)
        
        # Verify the query was called correctly
        postgres_client.fetch_models.assert_called_once()
        call_args = postgres_client.fetch_models.call_args
        assert call_args[0][0] == Liquidation  # First argument is the model class
        
        # Verify results
        assert len(liquidations) == 1
        assert liquidations[0].account_id == 123
        assert liquidations[0].reason == "Insufficient margin"

    @pytest.mark.asyncio
    async def test_get_margin_utilisation(self, margin_service, mock_clients):
        """Test getting margin utilisation report"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_all_accounts.return_value = [1, 2]
        
        # Mock calculations service calls
        margin_service.calculations.calculate_equity = AsyncMock()
        margin_service.calculations.calculate_equity.side_effect = [
            Decimal('12000'),  # Account 1: safe
            Decimal('-3000')   # Account 2: liquidation needed
        ]
        
        margin_service.calculations.calculate_maintenance_margin = AsyncMock()
        margin_service.calculations.calculate_maintenance_margin.side_effect = [
            Decimal('5200'),   # Account 1
            Decimal('4500')    # Account 2
        ]
        
        margin_service.calculations.calculate_margin_utilisation = Mock()
        margin_service.calculations.calculate_margin_utilisation.side_effect = [
            Decimal('43.33'),  # Account 1: 5200/12000 * 100
            Decimal('100')     # Account 2: 100% (negative equity)
        ]
        
        # Mock liquidation recording
        margin_service.record_liquidation = AsyncMock()
        
        result = await margin_service.get_margin_utilisation()
        
        # Verify the structure of the result
        assert result['total_accounts'] == 2
        assert result['liquidation_candidates'] == [2]  # Only account 2 needs liquidation
        assert len(result['accounts_detail']) == 2
        
        # Verify account details
        account1_detail = result['accounts_detail'][0]
        assert account1_detail['account_id'] == 1
        assert account1_detail['equity'] == Decimal('12000')
        assert account1_detail['maintenance_margin_required'] == Decimal('5200')
        assert account1_detail['margin_utilisation_pct'] == Decimal('43.33')
        assert account1_detail['liquidation_risk'] is False
        
        account2_detail = result['accounts_detail'][1]
        assert account2_detail['account_id'] == 2
        assert account2_detail['equity'] == Decimal('-3000')
        assert account2_detail['maintenance_margin_required'] == Decimal('4500')
        assert account2_detail['margin_utilisation_pct'] == Decimal('100')
        assert account2_detail['liquidation_risk'] is True
        
        # Verify liquidation was recorded for account 2
        margin_service.record_liquidation.assert_called_once_with(
            2, 
            "Equity (-3000) below maintenance margin (4500)"
        )
