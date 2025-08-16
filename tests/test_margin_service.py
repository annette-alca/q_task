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
def safe_account():
    """Mock account with 1 BTC position, safe from liquidation"""
    return {
        'account_id': 1,
        'balance': Decimal('10000'),  # £10k cash remaining
        'btc_quantity': Decimal('1'),
        'btc_entry_price': Decimal('50000'),
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
        'btc_entry_price': Decimal('50000'),
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
    async def test_calculate_account_equity_safe_account(self, margin_service, mock_clients, safe_account):
        """Test equity calculation for safe account with profit"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = safe_account['balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": safe_account['btc_quantity'], 
                "entry_price": safe_account['btc_entry_price']
            }
        }
        market_client.get_mark_price.return_value = safe_account['btc_mark_price']
        
        # Test
        equity = await margin_service.calculate_account_equity(safe_account['account_id'])
        
        # Expected: balance + position P&L = 10000 + (52000-50000)*1 = 12000
        assert equity == Decimal('12000')
    
    @pytest.mark.asyncio
    async def test_calculate_account_equity_liquidation_account(self, margin_service, mock_clients, liquidation_account):
        """Test equity calculation for account needing liquidation"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = liquidation_account['balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": liquidation_account['btc_quantity'], 
                "entry_price": liquidation_account['btc_entry_price']
            }
        }
        market_client.get_mark_price.return_value = liquidation_account['btc_mark_price']
        
        # Test
        equity = await margin_service.calculate_account_equity(liquidation_account['account_id'])
        
        # Expected: balance + position P&L = 2000 + (45000-50000)*1 = -3000
        assert equity == Decimal('-3000')
    
    @pytest.mark.asyncio
    async def test_calculate_maintenance_margin_required(self, margin_service, mock_clients, safe_account):
        """Test calculation of maintenance margin required (10% of notional)"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": safe_account['btc_quantity'], 
                "entry_price": safe_account['btc_entry_price']
            }
        }
        market_client.get_mark_price.return_value = safe_account['btc_mark_price']
        
        # Test
        maintenance_required = await margin_service.calculate_maintenance_margin_required(safe_account['account_id'])
        
        # Expected: quantity * mark_price * 0.10 = 1 * 52000 * 0.10 = 5200
        assert maintenance_required == Decimal('5200')
    
    @pytest.mark.asyncio
    async def test_no_liquidation_needed_safe_account(self, margin_service, mock_clients, safe_account):
        """Test that safe account does not need liquidation"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks for safe account
        account_client.get_balance.return_value = safe_account['balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": safe_account['btc_quantity'], 
                "entry_price": safe_account['btc_entry_price']
            }
        }
        market_client.get_mark_price.return_value = safe_account['btc_mark_price']
        
        # Test
        equity = await margin_service.calculate_account_equity(safe_account['account_id'])
        maintenance_required = await margin_service.calculate_maintenance_margin_required(safe_account['account_id'])
        needs_liquidation = margin_service.is_liquidation_candidate(equity, maintenance_required)
        
        # Verify account is safe
        assert equity == Decimal('12000')
        assert maintenance_required == Decimal('5200')
        assert needs_liquidation is False
        print(f"Account {safe_account['account_id']}: Safe - Equity £{equity} > Maintenance £{maintenance_required}")
    
    @pytest.mark.asyncio
    async def test_liquidation_needed_underwater_account(self, margin_service, mock_clients, liquidation_account):
        """Test that underwater account needs liquidation"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks for liquidation account
        account_client.get_balance.return_value = liquidation_account['balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": liquidation_account['btc_quantity'], 
                "entry_price": liquidation_account['btc_entry_price']
            }
        }
        market_client.get_mark_price.return_value = liquidation_account['btc_mark_price']
        
        # Test
        equity = await margin_service.calculate_account_equity(liquidation_account['account_id'])
        maintenance_required = await margin_service.calculate_maintenance_margin_required(liquidation_account['account_id'])
        needs_liquidation = margin_service.is_liquidation_candidate(equity, maintenance_required)
        
        # Verify account needs liquidation
        assert equity == Decimal('-3000')
        assert maintenance_required == Decimal('4500')
        assert needs_liquidation is True
        print(f"Account {liquidation_account['account_id']}: Liquidation needed - Equity £{equity} < Maintenance £{maintenance_required}")
    
    @pytest.mark.asyncio
    async def test_record_liquidation(self, margin_service, mock_clients, liquidation_account):
        """Test recording liquidation event"""
        account_client, market_client, postgres_client = mock_clients
        
        # Test data
        equity = Decimal('-3000')
        maintenance_margin = Decimal('4500')
        reason = "Equity below maintenance margin after BTC price drop"
        
        # Test
        await margin_service.record_liquidation(
            liquidation_account['account_id'], 
            equity, 
            maintenance_margin, 
            reason
        )
        
        # Verify liquidation was recorded in Postgres
        postgres_client.insert_model.assert_called_once()
        
        # Verify the liquidation model data
        call_args = postgres_client.insert_model.call_args[0]
        liquidation_model = call_args[0]
        
        assert isinstance(liquidation_model, Liquidation)
        assert liquidation_model.account_id == liquidation_account['account_id']
        assert liquidation_model.equity == equity
        assert liquidation_model.maintenance_margin == maintenance_margin
        assert liquidation_model.reason == reason
    
    @pytest.mark.asyncio
    async def test_get_liquidation_history(self, margin_service, mock_clients):
        """Test getting liquidation history with proper Decimal precision"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mock liquidations
        mock_liquidations = [
            Liquidation(
                id=1,
                account_id=2,
                equity=Decimal('-3000'),
                maintenance_margin=Decimal('4500'),
                reason="Equity below maintenance margin after BTC price drop"
            )
        ]
        postgres_client.fetch_models.return_value = mock_liquidations
        
        # Test
        liquidations = await margin_service.get_liquidation_history()
        
        # Verify
        assert len(liquidations) == 1
        assert liquidations[0].account_id == 2
        assert liquidations[0].equity == Decimal('-3000')
        assert liquidations[0].maintenance_margin == Decimal('4500')
        postgres_client.fetch_models.assert_called_once()