import pytest
from decimal import Decimal

from unittest.mock import AsyncMock, patch
from app.redis_client import AccountRedisClient, MarketRedisClient

# Connection to redis is mocked, so only set functions are tested below.

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
    async def test_set_balance(self, account_client):
        """Test setting and getting account balance"""
        client, mock_conn = account_client
        
        # Setup mock
        mock_conn.hget.return_value = "10000.50"
        
        # Test set
        await client.set_balance(123, Decimal('10000.50'))
        mock_conn.hset.assert_called_with("balances", "123", "10000.50")
        
    
    @pytest.mark.asyncio
    async def test_set_position(self, account_client):
        """Test setting and getting position"""
        client, mock_conn = account_client
        
        # Setup mock for get_position, existing account to have 1 BTC bought at 50000
        mock_conn.hget.return_value = "1,50000.00"
        
        # Test set
        await client.set_position(123, "BTC-PERP", Decimal('1'), Decimal('40000.00'))
        
        # Verify set calls - should store weighted average: (1*50000 + 1*40000)/2 = 45000
        mock_conn.hset.assert_called_with("positions:123", "BTC-PERP", "2,45000.00")
        
    @pytest.mark.asyncio
    async def test_set_equity(self, account_client):
        """Test setting account equity"""
        client, mock_conn = account_client
        
        # Test set
        await client.set_equity(123, Decimal('15000.75'))
        mock_conn.set.assert_called_with("account:123:equity", "15000.75")
        

class TestMarketRedisClient:
    
    @pytest.mark.asyncio
    async def test_set_mark_price(self, market_client):
        """Test setting and getting mark price"""
        client, mock_conn = market_client
        
        # Setup mock
        mock_conn.hget.return_value = "52000.50"
        
        # Test set
        await client.set_mark_price("BTC-PERP", Decimal('52000.50'))
        mock_conn.hset.assert_called_with("mark_prices", "BTC-PERP", "52000.50")
        
    

