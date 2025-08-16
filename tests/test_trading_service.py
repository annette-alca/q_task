import pytest
from decimal import Decimal
from unittest.mock import AsyncMock
from app.services.trading import TradingService
from app.models import Trade

@pytest.fixture
def mock_clients():
    """Create mock clients for testing"""
    account_client = AsyncMock()
    market_client = AsyncMock()
    postgres_client = AsyncMock()
    return account_client, market_client, postgres_client

@pytest.fixture
def trading_service(mock_clients):
    """Create trading service with mocked dependencies"""
    account_client, market_client, postgres_client = mock_clients
    return TradingService(account_client, market_client, postgres_client)

class TestTradingService:
    
    def test_calculate_initial_margin_required(self, trading_service):
        """Test pure function - initial margin calculation"""
        quantity = Decimal('1')
        price = Decimal('50000')
        expected = Decimal('10000')  # 20% of 50000
        
        result = trading_service.calculate_initial_margin_required(quantity, price)
        assert result == expected
    
    def test_calculate_new_position_new(self, trading_service):
        """Test pure function - new position calculation"""
        current_position = None
        trade_quantity = Decimal('1')
        trade_price = Decimal('50000')
        
        new_qty, new_price = trading_service.calculate_new_position(current_position, trade_quantity, trade_price)
        
        assert new_qty == Decimal('1')
        assert new_price == Decimal('50000')
    
    def test_calculate_new_position_same_direction(self, trading_service):
        """Test pure function - position update same direction"""
        current_position = {"quantity": Decimal('1'), "entry_price": Decimal('50000')}
        trade_quantity = Decimal('1')
        trade_price = Decimal('60000')
        
        new_qty, new_price = trading_service.calculate_new_position(current_position, trade_quantity, trade_price)
        
        assert new_qty == Decimal('2')
        assert new_price == Decimal('55000')  # Weighted average
    
    @pytest.mark.asyncio
    async def test_calculate_equity(self, trading_service, mock_clients):
        """Test equity calculation with mocked dependencies"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = Decimal('10000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": Decimal('1'), "entry_price": Decimal('50000')}
        }
        market_client.get_mark_price.return_value = Decimal('52000')
        
        # Test
        equity = await trading_service.calculate_equity(1)
        
        # Verify: balance + position P&L = 10000 + (52000-50000)*1 = 12000
        assert equity == Decimal('12000')
    
    @pytest.mark.asyncio
    async def test_pre_trade_check_sufficient_equity(self, trading_service, mock_clients):
        """Test pre-trade check with sufficient equity"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks - account has plenty of equity
        account_client.get_balance.return_value = Decimal('100000')
        account_client.get_all_positions.return_value = {}
        
        # Test
        success, message = await trading_service.pre_trade_check(1, "BUY", Decimal('1'), Decimal('50000'))
        
        assert success is True
        assert message == "Trade approved"
    
    @pytest.mark.asyncio
    async def test_pre_trade_check_insufficient_equity(self, trading_service, mock_clients):
        """Test pre-trade check with insufficient equity"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks - account has insufficient equity
        account_client.get_balance.return_value = Decimal('5000')  # Only 5000 USDT
        account_client.get_all_positions.return_value = {}
        
        # Test - trying to buy 1 BTC at 50000 (needs 10000 margin)
        success, message = await trading_service.pre_trade_check(1, "BUY", Decimal('1'), Decimal('50000'))
        
        assert success is False
        assert "Insufficient equity" in message

    @pytest.mark.asyncio
    async def test_get_trade_history(self, trading_service, mock_clients):
        """Test getting trade history using Trade models"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mock trades
        mock_trades = [
            Trade(
                id=1,
                account_id=1,
                symbol="BTC-PERP",
                side="BUY",
                quantity=1.0,
                price=50000.0,
                notional=50000.0
            ),
            Trade(
                id=2,
                account_id=1,
                symbol="BTC-PERP",
                side="SELL",
                quantity=0.5,
                price=52000.0,
                notional=26000.0
            )
        ]
        postgres_client.fetch_models.return_value = mock_trades
        
        # Test
        trades = await trading_service.get_trade_history(1, limit=10)
        
        # Verify
        assert len(trades) == 2
        assert trades[0].symbol == "BTC-PERP"
        assert trades[0].side == "BUY"
        assert trades[1].side == "SELL"
        postgres_client.fetch_models.assert_called_once()
