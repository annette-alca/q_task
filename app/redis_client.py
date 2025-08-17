import json
import redis.asyncio as aioredis
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
    
    async def set_balance(self, account_id: int, balance: float):
        """Set account balance"""
        await self.hset("balances", str(account_id), str(balance))

    async def get_balance(self, account_id: int) -> float:
        """Get account balance"""
        balance_str = await self.hget("balances", str(account_id))
        return float(balance_str) if balance_str else 0.0

    async def set_position(self, account_id: int, symbol: str, quantity: float, entry_price: float):
        """Set position for account and symbol"""
        key = f"positions:{account_id}"
        
        # Get existing position for this symbol (if any)
        existing_position = await self.get_position(account_id, symbol)
        existing_qty = existing_position["quantity"]
        existing_avg_price = existing_position["avg_price"]
        
        # Calculate new position with weighted average
        new_quantity = existing_qty + quantity
        if new_quantity != 0:
            new_avg_price = (existing_qty * existing_avg_price + quantity * entry_price) / new_quantity
        else:
            new_avg_price = 0.0
        
        # Store position as tuple string "quantity,avg_price"
        await self.hset(key, symbol, f"{new_quantity},{new_avg_price}")

    async def get_position(self, account_id: int, symbol: str) -> Optional[Dict[str, float]]:
        """Get position for account and symbol"""
        key = f"positions:{account_id}"
        
        # Get position data from hash
        value = await self.hget(key, symbol)
        
        if not value:
            return {
                "quantity": 0.0,
                "avg_price": 0.0
            }
            
        quantity_str, avg_price_str = value.split(',')
        quantity = float(quantity_str)
        avg_price = float(avg_price_str)
        return {
            "quantity": quantity,
            "avg_price": avg_price
        }

    async def get_all_positions(self, account_id: int) -> Dict[str, Dict[str, float]]:
        """Get all positions for an account"""
        key = f"positions:{account_id}"
        all_fields = await self.hgetall(key)
        
        if not all_fields:
            return {}
        
        # Parse hash fields to extract positions
        positions = {}
        
        for symbol, value in all_fields.items():
            quantity_str, avg_price_str = value.split(',')
            quantity = float(quantity_str)
            avg_price = float(avg_price_str)
            positions[symbol] = {
                "quantity": quantity,
                "avg_price": avg_price
            }
        
        return positions

    async def get_all_accounts(self) -> list[int]:
        """Get all account IDs that have balances"""
        balance_data = await self.hgetall("balances")
        return [int(account_id) for account_id in balance_data.keys()]

     # In trading service after each trade
    async def _update_equity_in_redis(self, account_id: int):
        equity = await self.calculate_equity(account_id)
        await self.account_client.set(f"account:{account_id}:equity", str(equity))

    # Get equity from Redis (as required)
    async def get_equity_from_redis(self, account_id: int) -> float:
        equity_str = await self.account_client.get(f"account:{account_id}:equity")
        return float(equity_str) if equity_str else 0.0

    #Update used_margin in Redis:
    # Calculate and store used margin
    async def _update_used_margin_in_redis(self, account_id: int):
        used_margin = await self.calculate_maintenance_margin(account_id)
        await self.account_client.set(f"account:{account_id}:used_margin", str(used_margin))

    # Get used margin from Redis
    async def get_used_margin_from_redis(self, account_id: int) -> float:
        margin_str = await self.account_client.get(f"account:{account_id}:used_margin")
        return float(margin_str) if margin_str else 0.0


class MarketRedisClient(BaseRedisClient):
    """Redis client for market-related operations (mark prices)"""
    
    async def set_mark_price(self, symbol: str, price: float):
        """Set mark price for symbol"""
        await self.hset("mark_prices", symbol, str(price))

    async def get_mark_price(self, symbol: str) -> Optional[float]:
        """Get mark price for symbol"""
        price_str = await self.hget("mark_prices", symbol)
        return float(price_str) if price_str else None

    async def get_all_mark_prices(self) -> Dict[str, float]:
        """Get all mark prices"""
        prices_data = await self.hgetall("mark_prices")
        return {symbol: float(price) for symbol, price in prices_data.items()}
