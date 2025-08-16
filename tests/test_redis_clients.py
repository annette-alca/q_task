import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from app.redis_client import AccountRedisClient, MarketRedisClient

@pytest.fixture
def account_client():
    """Create account redis client with mocked connection"""
    with patch('app.redis_client.aioredis.Redis') as mock_redis:
        mock_conn = AsyncMock()
        mock_redis.return_value = mock_conn
        
        client = AccountRedisClient()
        client._conn = mock_conn
        return client, mock_conn

@pytest.fixture
def market_client():
    """Create market redis client with mocked connection"""
    with patch('app.redis_client.aioredis.Redis') as mock_redis:
        mock_conn = AsyncMock()
        mock_redis.return_value = mock_conn
        
        client = MarketRedisClient()
        client._conn = mock_conn
        return client, mock_conn

class TestAccountRedisClient:
    
    @pytest.mark.asyncio
    async def test_set_get_balance(self, account_client):
        """Test setting and getting account balance"""
        client, mock_conn = account_client
        
        # Setup mock
        mock_conn.hget.return_value = "10000.50"
        
        # Test set
        await client.set_balance(123, Decimal('10000.50'))
        mock_conn.hset.assert_called_with("balances", "123", "10000.50")
        
        # Test get
        balance = await client.get_balance(123)
        mock_conn.hget.assert_called_with("balances", "123")
        assert balance == Decimal('10000.50')
    
    @pytest.mark.asyncio
    async def test_get_balance_nonexistent(self, account_client):
        """Test getting balance for non-existent account"""
        client, mock_conn = account_client
        
        # Setup mock to return None
        mock_conn.hget.return_value = None
        
        # Test
        balance = await client.get_balance(999)
        assert balance == Decimal('0')
    
    @pytest.mark.asyncio
    async def test_set_get_position(self, account_client):
        """Test setting and getting position"""
        client, mock_conn = account_client
        
        # Setup mock for get
        mock_conn.hgetall.return_value = {
            "quantity": "1.5",
            "entry_price": "50000.00"
        }
        
        # Test set
        await client.set_position(123, "BTC-PERP", Decimal('1.5'), Decimal('50000.00'))
        
        # Verify set calls
        assert mock_conn.hset.call_count == 2
        mock_conn.hset.assert_any_call("position:123:BTC-PERP", "quantity", "1.5")
        mock_conn.hset.assert_any_call("position:123:BTC-PERP", "entry_price", "50000.00")
        
        # Test get
        position = await client.get_position(123, "BTC-PERP")
        mock_conn.hgetall.assert_called_with("position:123:BTC-PERP")
        
        assert position["quantity"] == Decimal('1.5')
        assert position["entry_price"] == Decimal('50000.00')

class TestMarketRedisClient:
    
    @pytest.mark.asyncio
    async def test_set_get_mark_price(self, market_client):
        """Test setting and getting mark price"""
        client, mock_conn = market_client
        
        # Setup mock
        mock_conn.hget.return_value = "52000.50"
        
        # Test set
        await client.set_mark_price("BTC-PERP", Decimal('52000.50'))
        mock_conn.hset.assert_called_with("mark_prices", "BTC-PERP", "52000.50")
        
        # Test get
        price = await client.get_mark_price("BTC-PERP")
        mock_conn.hget.assert_called_with("mark_prices", "BTC-PERP")
        assert price == Decimal('52000.50')
    
    @pytest.mark.asyncio
    async def test_get_mark_price_nonexistent(self, market_client):
        """Test getting mark price for non-existent symbol"""
        client, mock_conn = market_client
        
        # Setup mock to return None
        mock_conn.hget.return_value = None
        
        # Test
        price = await client.get_mark_price("NONEXISTENT")
        assert price is None
