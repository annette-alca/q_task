import redis.asyncio as aioredis
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from abc import ABC

class BaseRedisClient(ABC):
    """Base Redis client with core connection functionality"""
    
    def __init__(self, host: str = "localhost", port: int = 6379, password: Optional[str] = None, db: int = 0):
        self._host = host
        self._port = port
        self._password = password
        self._db = db
        self._conn: Optional[aioredis.Redis] = None

    async def connect(self):
        if not self._conn:
            self._conn = aioredis.Redis(
                host=self._host,
                port=self._port,
                password=self._password,
                db=self._db,
                decode_responses=True
            )

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def set(self, key: str, value: str):
        if not self._conn:
            await self.connect()
        await self._conn.set(key, value)

    async def get(self, key: str):
        if not self._conn:
            await self.connect()
        return await self._conn.get(key)

    async def hset(self, name: str, key: str, value: str):
        if not self._conn:
            await self.connect()
        await self._conn.hset(name, key, value)

    async def hgetall(self, name: str):
        if not self._conn:
            await self.connect()
        return await self._conn.hgetall(name)
    
    async def hget(self, name: str, key: str):
        if not self._conn:
            await self.connect()
        return await self._conn.hget(name, key)
    
    async def keys(self, pattern: str):
        if not self._conn:
            await self.connect()
        return await self._conn.keys(pattern)


class AccountRedisClient(BaseRedisClient):
    """Redis client for account-related operations (balances, positions)"""
    
    async def set_balance(self, account_id: int, balance: Decimal):
        """Set account balance"""
        await self.hset("balances", str(account_id), str(balance))

    async def get_balance(self, account_id: int) -> Decimal:
        """Get account balance"""
        balance_str = await self.hget("balances", str(account_id))
        return Decimal(balance_str) if balance_str else Decimal('0')

    async def set_position(self, account_id: int, symbol: str, quantity: Decimal, avg_price: Decimal):
        """Set position for account and symbol"""
        key = f"positions:{account_id}"

        await self.hset(key, symbol, f"{quantity},{avg_price}")

    async def get_position(self, account_id: int, symbol: str) -> Optional[Dict[str, Decimal]]:
        """Get position for account and symbol"""
        key = f"positions:{account_id}"
        
        # Get position data from hash
        value = await self.hget(key, symbol)
        
        if not value:
            return {
                "quantity": Decimal('0'),
                "avg_price": Decimal('0')
            }

        quantity_str, avg_price_str = value.split(',')
        quantity = Decimal(quantity_str)
        avg_price = Decimal(avg_price_str)
        return {
            "quantity": quantity,
            "avg_price": avg_price
        }

    async def get_all_positions(self, account_id: int) -> Dict[str, Dict[str, Decimal]]:
        """Get all positions for an account"""
        key = f"positions:{account_id}"
        all_fields = await self.hgetall(key)
        
        if not all_fields:
            return {}
        
        # Parse hash fields to extract positions
        positions = {}
        
        for symbol, value in all_fields.items():
            quantity_str, avg_price_str = value.split(',')
            quantity = Decimal(quantity_str)
            avg_price = Decimal(avg_price_str)
            positions[symbol] = {
                "quantity": quantity,
                "avg_price": avg_price
            }
        
        return positions

    async def get_all_accounts(self) -> list[int]:
        """Get all account IDs that have balances"""
        balance_data = await self.hgetall("balances")
        return [int(account_id) for account_id in balance_data.keys()]

    async def set_equity(self, account_id: int, equity: Decimal):
        '''Update equity, done after a trade is executed'''
        await self.set(f"account:{account_id}:equity", str(equity))


    async def get_equity(self, account_id: int) -> Decimal:
        equity_str = await self.get(f"account:{account_id}:equity")
        return Decimal(equity_str) if equity_str else Decimal('0')


    async def set_used_margin(self, account_id: int, used_margin: Decimal):
        '''Update used margin, done after a trade is executed'''
        await self.set(f"account:{account_id}:used_margin", str(used_margin))


    async def get_used_margin(self, account_id: int) -> Decimal:
        margin_str = await self.get(f"account:{account_id}:used_margin")
        return Decimal(margin_str) if margin_str else Decimal('0')


class MarketRedisClient(BaseRedisClient):
    """Redis client for market-related operations (mark prices)"""
    
    async def set_mark_price(self, symbol: str, price: Decimal):
        """Set mark price for symbol"""
        await self.hset("mark_prices", symbol, str(price))

    async def get_mark_price(self, symbol: str) -> Optional[Decimal]:
        """Get mark price for symbol"""
        price_str = await self.hget("mark_prices", symbol)
        return Decimal(price_str) if price_str else None

    async def get_all_mark_prices(self) -> Dict[str, Decimal]:
        """Get all mark prices"""
        prices_data = await self.hgetall("mark_prices")
        return {symbol: Decimal(price) for symbol, price in prices_data.items()}
