import pytest
from decimal import Decimal
from unittest.mock import AsyncMock
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
def margin_service(mock_clients):
    """Create margin service with mocked dependencies"""
    account_client, market_client, postgres_client = mock_clients
    return MarginService(account_client, market_client, postgres_client)

class TestMarginService:
    
    def test_calculate_margin_utilisation(self, margin_service):
        """Test pure function - margin utilisation calculation"""
        equity = Decimal('10000')
        maintenance_required = Decimal('2000')
        expected = Decimal('20')  # 20%
        
        result = margin_service.calculate_margin_utilisation(equity, maintenance_required)
        assert result == expected
    
    def test_calculate_margin_utilisation_zero_equity(self, margin_service):
        """Test margin utilisation with zero equity"""
        equity = Decimal('0')
        maintenance_required = Decimal('1000')
        
        result = margin_service.calculate_margin_utilisation(equity, maintenance_required)
        assert result == Decimal('100')
    
    def test_is_liquidation_candidate_true(self, margin_service):
        """Test liquidation detection - should liquidate"""
        equity = Decimal('900')
        maintenance_required = Decimal('1000')
        
        result = margin_service.is_liquidation_candidate(equity, maintenance_required)
        assert result is True
    
    def test_is_liquidation_candidate_false(self, margin_service):
        """Test liquidation detection - should not liquidate"""
        equity = Decimal('1100')
        maintenance_required = Decimal('1000')
        
        result = margin_service.is_liquidation_candidate(equity, maintenance_required)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_calculate_account_equity(self, margin_service, mock_clients):
        """Test account equity calculation"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = Decimal('10000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": Decimal('1'), "entry_price": Decimal('50000')}
        }
        market_client.get_mark_price.return_value = Decimal('48000')  # Loss position
        
        # Test
        equity = await margin_service.calculate_account_equity(1)
        
        # Verify: balance + position P&L = 10000 + (48000-50000)*1 = 8000
        assert equity == Decimal('8000')

    @pytest.mark.asyncio
    async def test_get_liquidation_history(self, margin_service, mock_clients):
        """Test getting liquidation history using Liquidation models"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mock liquidations
        mock_liquidations = [
            Liquidation(
                id=1,
                account_id=1,
                equity=800.0,
                maintenance_margin=1000.0,
                reason="Equity below maintenance margin"
            ),
            Liquidation(
                id=2,
                account_id=2,
                equity=500.0,
                maintenance_margin=800.0,
                reason="Equity below maintenance margin"
            )
        ]
        postgres_client.fetch_models.return_value = mock_liquidations
        
        # Test
        liquidations = await margin_service.get_liquidation_history(limit=10)
        
        # Verify
        assert len(liquidations) == 2
        assert liquidations[0].account_id == 1
        assert liquidations[0].equity == 800.0
        assert liquidations[1].account_id == 2
        postgres_client.fetch_models.assert_called_once()
