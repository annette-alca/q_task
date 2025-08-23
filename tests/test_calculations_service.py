import pytest
from decimal import Decimal
from unittest.mock import AsyncMock
from app.services.calculations import CalculationsService

@pytest.fixture
def mock_clients():
    """Create mock clients for testing"""
    account_client = AsyncMock()
    market_client = AsyncMock()
    return account_client, market_client

@pytest.fixture
def account_no_btc():
    """Mock account with no BTC position"""
    return {
        'account_id': 1,
        'balance': Decimal('15000'),  # £15k cash
        'positions': {},
        'expected_equity': Decimal('15000')  # No positions = balance only
    }

@pytest.fixture
def account_low_margin_util():
    """Mock account with 1 BTC position, low margin utilisation (safe)"""
    return {
        'account_id': 2,
        'balance': Decimal('10000'),  # £10k cash remaining
        'positions': {
            "BTC-PERP": {
                "quantity": Decimal('1'),
                "avg_price": Decimal('50000')
            }
        },
        'btc_mark_price': Decimal('52000'),  # £2k profit
        'expected_equity': Decimal('12000'),  # 10000 + 2000 profit
        'expected_maintenance': Decimal('5200')  # 52000 * 0.10
    }

@pytest.fixture
def account_high_margin_util():
    """Mock account with 1 BTC position, high margin utilisation (at risk)"""
    return {
        'account_id': 3,
        'balance': Decimal('2000'),  # £2k cash remaining
        'positions': {
            "BTC-PERP": {
                "quantity": Decimal('1'),
                "avg_price": Decimal('50000')
            }
        },
        'btc_mark_price': Decimal('45000'),  # £5k loss
        'expected_equity': Decimal('-3000'),  # 2000 + (-5000) loss
        'expected_maintenance': Decimal('4500')  # 45000 * 0.10
    }

@pytest.fixture
def calculations_service(mock_clients):
    """Create calculations service with mocked dependencies"""
    account_client, market_client = mock_clients
    return CalculationsService(account_client, market_client)

class TestCalculationsService:
    
    def test_calculate_initial_margin_required(self, calculations_service):
        """Test initial margin calculation (20% of notional)"""
        quantity = Decimal('1')
        price = Decimal('50000')
        # Notional = 1 * 50000 = 50000 USDT
        # Initial margin = 50000 * 0.20 = 10000 USDT
        expected = Decimal('10000')
        
        result = calculations_service.calculate_initial_margin_required(quantity, price)
        assert result == expected

    def test_calculate_margin_utilisation(self, calculations_service):
        """Test margin utilisation calculation"""
        equity = Decimal('12000')
        maintenance_required = Decimal('6000')
        # Utilisation = 6000 / 12000 * 100 = 50%
        expected = Decimal('50')
        
        result = calculations_service.calculate_margin_utilisation(equity, maintenance_required)
        assert result == expected

    def test_calculate_margin_utilisation_zero_equity(self, calculations_service):
        """Test margin utilisation calculation with zero equity"""
        equity = Decimal('0')
        maintenance_required = Decimal('5000')
        # Should return 100% when equity is 0
        expected = Decimal('Infinity')
        
        result = calculations_service.calculate_margin_utilisation(equity, maintenance_required)
        assert result == expected

    def test_calculate_new_position_no_current_position(self, calculations_service):
        """Test new position calculation when no current position exists"""
        current_position = None
        trade_quantity = Decimal('1')
        trade_price = Decimal('50000')
        
        new_quantity, new_avg_price = calculations_service.calculate_new_position(
            current_position, trade_quantity, trade_price
        )
        
        assert new_quantity == Decimal('1')
        assert new_avg_price == Decimal('50000')

    def test_calculate_new_position_same_direction(self, calculations_service):
        """Test new position calculation for same direction trades (weighted average)"""
        current_position = {
            "quantity": Decimal('1'),
            "avg_price": Decimal('50000')
        }
        trade_quantity = Decimal('1')
        trade_price = Decimal('52000')
        
        new_quantity, new_avg_price = calculations_service.calculate_new_position(
            current_position, trade_quantity, trade_price
        )
        
        # Total cost = 1*50000 + 1*52000 = 102000
        # New avg price = 102000 / 2 = 51000
        assert new_quantity == Decimal('2')
        assert new_avg_price == Decimal('51000')

    def test_calculate_new_position_position_flip(self, calculations_service):
        """Test new position calculation when position flips direction"""
        current_position = {
            "quantity": Decimal('1'),
            "avg_price": Decimal('50000')
        }
        trade_quantity = Decimal('-2')  # Sell 2 BTC
        trade_price = Decimal('52000')
        
        new_quantity, new_avg_price = calculations_service.calculate_new_position(
            current_position, trade_quantity, trade_price
        )
        
        # Position flip: 1 + (-2) = -1
        # Should use new price for flip
        assert new_quantity == Decimal('-1')
        assert new_avg_price == Decimal('52000')

    def test_calculate_new_position_position_close(self, calculations_service):
        """Test new position calculation when position is closed"""
        current_position = {
            "quantity": Decimal('1'),
            "avg_price": Decimal('50000')
        }
        trade_quantity = Decimal('-1')  # Sell 1 BTC (exactly close)
        trade_price = Decimal('52000')
        
        new_quantity, new_avg_price = calculations_service.calculate_new_position(
            current_position, trade_quantity, trade_price
        )
        
        # Position closed: 1 + (-1) = 0
        assert new_quantity == Decimal('0')
        assert new_avg_price == Decimal('0')

    @pytest.mark.asyncio
    async def test_calculate_equity_no_positions(self, calculations_service, mock_clients, account_no_btc):
        """Test equity calculation for account with no positions"""
        account_client, market_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = account_no_btc['balance']
        account_client.get_all_positions.return_value = account_no_btc['positions']
        
        result = await calculations_service.calculate_equity(account_no_btc['account_id'])
        assert result == account_no_btc['expected_equity']

    @pytest.mark.asyncio
    async def test_calculate_equity_with_profit(self, calculations_service, mock_clients, account_low_margin_util):
        """Test equity calculation for account with profitable position"""
        account_client, market_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = account_low_margin_util['balance']
        account_client.get_all_positions.return_value = account_low_margin_util['positions']
        market_client.get_mark_price.return_value = account_low_margin_util['btc_mark_price']
        
        result = await calculations_service.calculate_equity(account_low_margin_util['account_id'])
        assert result == account_low_margin_util['expected_equity']

    @pytest.mark.asyncio
    async def test_calculate_equity_with_loss(self, calculations_service, mock_clients, account_high_margin_util):
        """Test equity calculation for account with losing position"""
        account_client, market_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = account_high_margin_util['balance']
        account_client.get_all_positions.return_value = account_high_margin_util['positions']
        market_client.get_mark_price.return_value = account_high_margin_util['btc_mark_price']
        
        result = await calculations_service.calculate_equity(account_high_margin_util['account_id'])
        assert result == account_high_margin_util['expected_equity']

    @pytest.mark.asyncio
    async def test_calculate_maintenance_margin_no_positions(self, calculations_service, mock_clients, account_no_btc):
        """Test maintenance margin calculation for account with no positions"""
        account_client, market_client = mock_clients
        
        # Setup mocks
        account_client.get_all_positions.return_value = account_no_btc['positions']
        
        result = await calculations_service.calculate_maintenance_margin(account_no_btc['account_id'])
        assert result == Decimal('0')

    @pytest.mark.asyncio
    async def test_calculate_maintenance_margin_with_position(self, calculations_service, mock_clients, account_low_margin_util):
        """Test maintenance margin calculation for account with position"""
        account_client, market_client = mock_clients
        
        # Setup mocks
        account_client.get_all_positions.return_value = account_low_margin_util['positions']
        market_client.get_mark_price.return_value = account_low_margin_util['btc_mark_price']
        
        result = await calculations_service.calculate_maintenance_margin(account_low_margin_util['account_id'])
        assert result == account_low_margin_util['expected_maintenance']

    @pytest.mark.asyncio
    async def test_get_account_positions(self, calculations_service, mock_clients, account_low_margin_util):
        """Test get account positions with P&L calculation"""
        account_client, market_client = mock_clients
        
        # Setup mocks
        account_client.get_balance.return_value = account_low_margin_util['balance']
        account_client.get_all_positions.return_value = account_low_margin_util['positions']
        market_client.get_mark_price.return_value = account_low_margin_util['btc_mark_price']
        
        result = await calculations_service.get_account_positions(account_low_margin_util['account_id'])
        
        assert result['account_id'] == account_low_margin_util['account_id']
        assert result['balance'] == account_low_margin_util['balance']
        assert result['equity'] == account_low_margin_util['expected_equity']
        assert len(result['positions']) == 1
        
        position = result['positions'][0]
        assert position['symbol'] == 'BTC-PERP'
        assert position['quantity'] == Decimal('1')
        assert position['avg_price'] == Decimal('50000')
        assert position['mark_price'] == Decimal('52000')
        assert position['unrealised_pnl'] == Decimal('2000')  # (52000 - 50000) * 1
