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
def mock_account_0btc():
    """Mock account valueswith USDT 15,000 starting balance"""
    return {
        'account_id': 1,
        'initial_balance': Decimal('15000'),
    }

@pytest.fixture
def mock_account_1btc():
    """Mock account with USDT 15,000 starting balance"""
    return {
        'account_id': 1,
        'initial_balance': Decimal('15000'),
        'btc_quantity': Decimal('1'),
        'btc_avg_price': Decimal('50000')
    }

@pytest.fixture
def trading_service(mock_clients):
    """Create trading service with mocked dependencies"""
    account_client, market_client, postgres_client = mock_clients
    return TradingService(account_client, market_client, postgres_client)

class TestTradingService:
    
    def test_calculate_initial_margin_required(self, trading_service):
        """Test initial margin calculation (20% of notional)"""
        quantity = Decimal('1')
        price = Decimal('50000')
        # Notional = 1 * 50000 = 50000 USDT
        # Initial margin = 50000 * 0.20 = 10000 USDT
        expected = Decimal('10000')
        
        result = trading_service.calculate_initial_margin_required(quantity, price)
        assert result == expected

    @pytest.mark.asyncio
    async def test_calculate_maintenance_margin(self, trading_service, mock_clients):
        """Test maintenance margin calculation (10% of notional)"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mocks
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": Decimal('1'), "avg_price": Decimal('50000')}
        }
        market_client.get_mark_price.return_value = Decimal('50000')
        
        # Maintenance margin = 1 * 50000 * 0.10 = 5000 USDT
        expected = Decimal('5000')
        
        result = await trading_service.calculate_maintenance_margin(1)
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_initial_trade_success(self, trading_service, mock_clients, mock_account_0btc):
        """Test successful initial BTC purchase"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 15000 USDT, no positions
        account_client.get_balance.return_value = mock_account_0btc['initial_balance']
        account_client.get_all_positions.return_value = {}
        
        # Test: Buy 1 BTC at 50000 (needs 10000 margin)
        success, message = await trading_service.pre_trade_check(
            mock_account_0btc['account_id'], "BUY", Decimal('1'), Decimal('50000')
        )
        
        assert success is True
        assert message == "Trade approved"
        # Available equity: 15000 > Required margin: 10000 ✓
    
    @pytest.mark.asyncio
    async def test_equity_calculation_btc_rises(self, trading_service, mock_clients, mock_account_1btc):
        """Test equity calculation when BTC price rises to 55000"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC bought at 50000, balance reduced to 5000
        account_client.get_balance.return_value = Decimal('5000')  # 15000 - 50000 notional + margin
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('55000')  # BTC up 10%
        
        # Test
        equity = await trading_service.calculate_equity(mock_account_1btc['account_id'])
        
        # Expected: balance + position P&L = 5000 + (55000-50000)*1 = 10000 USDT
        assert equity == Decimal('10000')
    
    @pytest.mark.asyncio
    async def test_equity_calculation_btc_falls(self, trading_service, mock_clients, mock_account_1btc):
        """Test equity calculation when BTC price falls to 45000"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC bought at 50000, balance 5000
        account_client.get_balance.return_value = Decimal('5000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('45000')  # BTC down 10%
        
        # Test
        equity = await trading_service.calculate_equity(mock_account_1btc['account_id'])
        
        # Expected: balance + position P&L = 5000 + (45000-50000)*1 = 0 USDT
        assert equity == Decimal('0')
    
    @pytest.mark.asyncio
    async def test_cannot_buy_second_btc_insufficient_free_margin(self, trading_service, mock_clients, mock_account_1btc):
        """Test cannot buy second BTC when free margin insufficient after BTC falls"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC, BTC remains at 50000
        account_client.get_balance.return_value = Decimal('5000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('50000') 
        # Current equity = 5000 + (50000-50000)*1 = 5000 USDT
        # Current free margin = 5000 - 5000 = 0 USDT  (5000 is the initial margin required for the second BTC)
        
        # Test: Try to buy another 1 BTC at current price (needs 5000 free margin)
        success, message = await trading_service.pre_trade_check(
            mock_account_1btc['account_id'], "BUY", Decimal('1'), Decimal('45000')
        )
        
        assert success is False
        assert "Insufficient equity" in message
        # Current free margin: 0 < Required margin: 9000 ✗
    
    @pytest.mark.asyncio
    async def test_can_buy_second_btc_after_price_increase(self, trading_service, mock_clients, mock_account_1btc):
        """Test can buy second BTC when equity sufficient after price increase"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC, BTC price recovered, good equity
        account_client.get_balance.return_value = Decimal('5000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('65000')  # BTC up 30%
        
        # Current equity = 5000 + (65000-50000)*1 = 20000 USDT
        # Current free margin = 20000 - 6500 = 13500 USDT
        
        # Test: Try to buy another 1 BTC at current price (needs 13000 free margin)
        success, message = await trading_service.pre_trade_check(
            mock_account_1btc['account_id'], "BUY", Decimal('1'), Decimal('65000')
        )
        
        assert success is True
        assert message == "Trade approved"
        # Current free margin: 13500 > Required margin: 13000 ✓

    @pytest.mark.asyncio
    async def test_can_buy_second_btc_after_balance_increase(self, trading_service, mock_clients, mock_account_1btc):
        """Test can buy second BTC when equity sufficient after balance increase"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC, increased balance by 7000 USDT
        account_client.get_balance.return_value = Decimal('16000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('50000')  # BTC remains at 50000
        
        # Current equity = 16000 + (50000-50000)*1 = 16000 USDT
        # Current free margin = 16000 - 5000 = 11000 USDT
        
        # Test: Try to buy another 1 BTC at current price (needs 10000 free margin)
        success, message = await trading_service.pre_trade_check(
            mock_account_1btc['account_id'], "BUY", Decimal('1'), Decimal('50000')
        )

        assert success is True
        assert message == "Trade approved"
        # Current free margin: 11000 > Required margin: 10000 ✓
    
    @pytest.mark.asyncio
    async def test_liquidation_scenario_btc_crashes(self, trading_service, mock_clients, mock_account_1btc):
        """Test liquidation scenario when BTC crashes significantly"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC, severe crash
        account_client.get_balance.return_value = mock_account_1btc["initial_balance"]
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('15000')  # BTC down 70%
        
        # Test equity calculation
        equity = await trading_service.calculate_equity(mock_account_1btc['account_id'])
        
        # Expected: balance + position P&L = 15000 + (15000-50000)*1 = -20000 USDT
        assert equity == Decimal('-20000')
        
        # With negative equity, maintenance margin check should fail
        # Maintenance margin needed: 15000 * 0.10 = 1500 USDT
        # Equity: -20000 < Maintenance: 1500 = Liquidation candidate ✓
    
    def test_calculate_pnl_profit(self, mock_account_1btc):
        """Test P&L calculation for profitable position (inline calculation)"""
        avg_price = mock_account_1btc['btc_avg_price']  # 50000
        mark_price = Decimal('55000')
        quantity = mock_account_1btc['btc_quantity']  # 1
        
        # P&L = (mark_price - avg_price) * quantity
        pnl = (mark_price - avg_price) * quantity
        
        # Expected: (55000 - 50000) * 1 = 5000 USDT profit
        assert pnl == Decimal('5000')
    
    def test_calculate_pnl_loss(self, mock_account_1btc):
        """Test P&L calculation for losing position (inline calculation)"""
        avg_price = mock_account_1btc['btc_avg_price']  # 50000
        mark_price = Decimal('45000')
        quantity = mock_account_1btc['btc_quantity']  # 1
        
        # P&L = (mark_price - avg_price) * quantity
        pnl = (mark_price - avg_price) * quantity
        
        # Expected: (45000 - 50000) * 1 = -5000 USDT loss
        assert pnl == Decimal('-5000')
    
    @pytest.mark.asyncio
    async def test_get_trade_history(self, trading_service, mock_clients, mock_account_1btc):
        """Test getting trade history with proper Decimal precision"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup mock trades
        mock_trades = [
            Trade(
                id=1,
                account_id=mock_account_1btc['account_id'],
                symbol="BTC-PERP",
                side="BUY",
                quantity=mock_account_1btc['btc_quantity'],
                price=mock_account_1btc['btc_avg_price'],
                notional=Decimal('50000')
            )
        ]
        postgres_client.fetch_models.return_value = mock_trades
        
        # Test
        trades = await trading_service.get_trade_history(mock_account_1btc['account_id'])
        
        # Verify
        assert len(trades) == 1
        assert trades[0].symbol == "BTC-PERP"
        assert trades[0].side == "BUY"
        assert trades[0].quantity == Decimal('1')
        assert trades[0].price == Decimal('50000')
        postgres_client.fetch_models.assert_called_once()