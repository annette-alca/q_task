import pytest
from decimal import Decimal

from unittest.mock import AsyncMock
from app.services.trading import TradingService, TradingError, TradeNotApproved
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
    """Mock account valueswith USDT 15,000 current balance"""
    return {
        'account_id': 1,
        'current_balance': Decimal('15000'),
    }

@pytest.fixture
def mock_account_1btc():
    """Mock account with USDT 5,000 current balance after buying 1 BTC at 50000"""
    return {
        'account_id': 1,
        'current_balance': Decimal('5000'), # 15000 - 10000 (initial margin)
        'btc_quantity': Decimal('1'),
        'btc_avg_price': Decimal('50000')
    }

@pytest.fixture
def trading_service(mock_clients):
    """Create trading service with mocked dependencies"""
    account_client, market_client, postgres_client = mock_clients
    return TradingService(account_client, market_client, postgres_client)


        
class TestPreTradeCheck:
    """Test pre-trade validation functionality. Different scenarios are tested here."""
    
    @pytest.mark.asyncio
    async def test_initial_pretrade_check_buy_success(self, trading_service, mock_clients, mock_account_0btc):
        """Test successful initial BTC purchase"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 15000 USDT, no positions
        account_client.get_balance.return_value = mock_account_0btc['current_balance']
        account_client.get_all_positions.return_value = {}
        
        # Test: Buy 1 BTC at 50000 (needs 10000 margin)
        success, message, required_margin = await trading_service.pre_trade_check(
            mock_account_0btc['account_id'], "BUY", Decimal('1'), Decimal('50000')
        )
        
        assert success is True
        assert message == "Trade approved"
        # Available equity: 15000 > Required margin: 10000 ✓

    @pytest.mark.asyncio
    async def test_initial_pretrade_check_sell_success(self, trading_service, mock_clients, mock_account_1btc):
        """Test successful initial BTC sell (short)"""
        account_client, market_client, postgres_client = mock_clients

        # Setup: Account has 5000 USDT, holds 1 BTC at 50000
        account_client.get_balance.return_value = mock_account_1btc['current_balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": mock_account_1btc['btc_quantity'],
                "avg_price": mock_account_1btc['btc_avg_price']
            }
        }
        market_client.get_mark_price.return_value = Decimal('50000')

        # Test: Sell 1 BTC at 50000 (releases margin)
        success, message, required_margin = await trading_service.pre_trade_check(
            mock_account_1btc['account_id'], "SELL", Decimal('1'), Decimal('50000')
        )

        assert success is True
        assert message == "Trade approved"
        assert required_margin == Decimal('10000')

    @pytest.mark.asyncio
    async def test_cannot_buy_second_btc_insufficient_free_margin(self, trading_service, mock_clients, mock_account_1btc):
        """Test cannot buy second BTC when free margin insufficient after BTC falls"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC, BTC remains at 50000
        account_client.get_balance.return_value = mock_account_1btc['current_balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('50000') 
        # Current equity = 5000 + (50000-50000)*1 = 5000 USDT
        # Current free margin = 5000 - 5000 = 0 USDT  (5000 is the initial margin required for the second BTC)
        
        # Test: Try to buy another 1 BTC at current price (needs 5000 free margin)
        success, message, required_margin = await trading_service.pre_trade_check(
            mock_account_1btc['account_id'], "BUY", Decimal('1'), Decimal('45000')
        )
        
        assert success is False
        assert "Insufficient equity" in message
        assert required_margin == Decimal('9000')
        # Current free margin: 0 < Required margin: 9000 ✗
    
    @pytest.mark.asyncio
    async def test_can_buy_second_btc_after_price_increase(self, trading_service, mock_clients, mock_account_1btc):
        """Test can buy second BTC when equity sufficient after price increase"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account holds 1 BTC, current balance is 5000, BTC price increased to 65000
        account_client.get_balance.return_value = mock_account_1btc['current_balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {"quantity": mock_account_1btc['btc_quantity'], "avg_price": mock_account_1btc['btc_avg_price']}
        }
        market_client.get_mark_price.return_value = Decimal('65000')  # BTC up 30%
        
        # Current equity = 5000 + (65000-50000)*1 = 20000 USDT
        # Current free margin = 20000 - 6500 = 13500 USDT
        
        # Test: Try to buy another 1 BTC at current price (needs 13000 free margin)
        success, message, required_margin = await trading_service.pre_trade_check(
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
        success, message, required_margin = await trading_service.pre_trade_check(
            mock_account_1btc['account_id'], "BUY", Decimal('1'), Decimal('50000')
        )

        assert success is True
        assert message == "Trade approved"
        # Current free margin: 11000 > Required margin: 10000 ✓



class TestCalculatePnL:
    """Test P&L calculation functionality"""
    
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

class TestGetTradeHistory:
    """Test trade history functionality"""
    
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
                price=mock_account_1btc['btc_avg_price']
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

    
class TestExecuteTrade:
    """Test trade execution functionality. Different scenarios are tested here."""
    
    @pytest.mark.asyncio
    async def test_execute_trade_buy_success(self, trading_service, mock_clients, mock_account_0btc):
        """Test successful buy trade execution"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 15000 USDT, no positions
        account_client.get_balance.return_value = mock_account_0btc['current_balance']
        account_client.get_all_positions.return_value = {}
        account_client.get_position.return_value = None  # No existing position
        postgres_client.insert_model.return_value = 123  # Mock trade ID
        
        # Test: Buy 1 BTC at 50000
        success, message, trade_id = await trading_service.execute_trade(
            mock_account_0btc['account_id'], "BTC-PERP", "BUY", Decimal('1'), Decimal('50000')
        )
        
        assert success is True
        assert message == "Trade executed successfully"
        assert trade_id == 123
        
        # Verify position was updated
        account_client.set_position.assert_called_once_with(
            mock_account_0btc['account_id'], "BTC-PERP", Decimal('1'), Decimal('50000')
        )
        
        # Verify balance was updated (should be reduced by margin amount)
        account_client.set_balance.assert_called_once_with(
            mock_account_0btc['account_id'], Decimal('5000')  # 15000 - 10000 (margin required)
        )
        
        # Verify trade was recorded
        postgres_client.insert_model.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_trade_sell_success(self, trading_service, mock_clients, mock_account_1btc):
        """Test successful sell trade execution"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 5000 USDT, holds 1 BTC at 50000
        account_client.get_balance.return_value = mock_account_1btc['current_balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": mock_account_1btc['btc_quantity'],
                "avg_price": mock_account_1btc['btc_avg_price']
            }
        }
        account_client.get_position.return_value = {
            "quantity": mock_account_1btc['btc_quantity'],
            "avg_price": mock_account_1btc['btc_avg_price']
        }
        postgres_client.insert_model.return_value = 124  # Mock trade ID
        
        # Test: Sell 1 BTC at 50000
        success, message, trade_id = await trading_service.execute_trade(
            mock_account_1btc['account_id'], "BTC-PERP", "SELL", Decimal('1'), Decimal('50000')
        )
        
        assert success is True
        assert message == "Trade executed successfully"
        assert trade_id == 124
        
        # Verify position was updated (should be 0 after selling all)
        account_client.set_position.assert_called_once_with(
            mock_account_1btc['account_id'], "BTC-PERP", Decimal('0'), Decimal('0')
        )
        
        # Verify balance was updated (should increase as margin is released)
        account_client.set_balance.assert_called_once_with(
            mock_account_1btc['account_id'], Decimal('15000')  # 5000 + 10000 (released margin)
        )
        
        # Verify trade was recorded
        postgres_client.insert_model.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_trade_fractional_btc_error(self, trading_service, mock_clients, mock_account_0btc):
        """Test that fractional BTC trades are rejected"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 15000 USDT, no positions
        account_client.get_balance.return_value = mock_account_0btc['current_balance']
        account_client.get_all_positions.return_value = {}
        
        # Test: Try to buy 0.5 BTC (should fail)
        with pytest.raises(TradingError, match="BTC trades must be in whole numbers"):
            await trading_service.execute_trade(
                mock_account_0btc['account_id'], "BTC-PERP", "BUY", Decimal('0.5'), Decimal('50000')
            )
    
    @pytest.mark.asyncio
    async def test_execute_trade_insufficient_margin_error(self, trading_service, mock_clients, mock_account_0btc):
        """Test that trades with insufficient margin are rejected"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has only 5000 USDT (not enough for 1 BTC at 50000)
        account_client.get_balance.return_value = Decimal('5000')
        account_client.get_all_positions.return_value = {}
        
        # Test: Try to buy 1 BTC at 50000 (needs 10000 margin, but only have 5000)
        with pytest.raises(TradeNotApproved, match="Insufficient equity"):
            await trading_service.execute_trade(
                mock_account_0btc['account_id'], "BTC-PERP", "BUY", Decimal('1'), Decimal('50000')
            )
    
    @pytest.mark.asyncio
    async def test_execute_trade_insufficient_quantity_error(self, trading_service, mock_clients, mock_account_1btc):
        """Test that selling more than owned quantity is rejected"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 1 BTC, tries to sell 2 BTC
        account_client.get_balance.return_value = mock_account_1btc['current_balance']
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": mock_account_1btc['btc_quantity'],  # 1 BTC
                "avg_price": mock_account_1btc['btc_avg_price']
            }
        }
        
        # Test: Try to sell 2 BTC when only have 1 BTC
        with pytest.raises(TradeNotApproved, match="Insufficient quantity"):
            await trading_service.execute_trade(
                mock_account_1btc['account_id'], "BTC-PERP", "SELL", Decimal('2'), Decimal('50000')
            )
    
    @pytest.mark.asyncio
    async def test_execute_trade_position_averaging(self, trading_service, mock_clients, mock_account_1btc):
        """Test that buying more BTC averages the position correctly"""
        account_client, market_client, postgres_client = mock_clients
        
        # Setup: Account has 1 BTC at 50000, buying 1 more BTC at 60000, current balance is 20000
        account_client.get_balance.return_value = Decimal('20000')
        account_client.get_all_positions.return_value = {
            "BTC-PERP": {
                "quantity": mock_account_1btc['btc_quantity'],
                "avg_price": mock_account_1btc['btc_avg_price']
            }
        }
        account_client.get_position.return_value = {
            "quantity": mock_account_1btc['btc_quantity'],
            "avg_price": mock_account_1btc['btc_avg_price']
        }
        market_client.get_mark_price.return_value = Decimal('60000')  # Add mark price for equity calculation
        postgres_client.insert_model.return_value = 125
        
        # Test: Buy 1 more BTC at 60000
        success, message, trade_id = await trading_service.execute_trade(
            mock_account_1btc['account_id'], "BTC-PERP", "BUY", Decimal('1'), Decimal('60000')
        )
        
        assert success is True
        
        # Verify position was updated with weighted average price
        # Expected: (1 * 50000 + 1 * 60000) / 2 = 55000
        account_client.set_position.assert_called_once_with(
            mock_account_1btc['account_id'], "BTC-PERP", Decimal('2'), Decimal('55000')
        ) 