
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, List
from ..redis_client import AccountRedisClient, MarketRedisClient
from ..postgres import AsyncPostgresClient
from ..models import Trade
from .calculations import CalculationsService


class TradingError(Exception):
    """Custom exception for trading-related business logic errors"""
    pass

class TradeNotApproved(Exception):
    """Custom exception for when trying to execute a trade that is not approved"""
    pass

class TradingService:
    def __init__(self, account_client: AccountRedisClient, market_client: MarketRedisClient, postgres_client: AsyncPostgresClient):
        self.account_client = account_client
        self.market_client = market_client
        self.postgres_client = postgres_client
        
        # Inject the shared calculations service
        self.calculations = CalculationsService(account_client, market_client)



    async def pre_trade_check(self, account_id: int, side: str, trade_quantity: Decimal, price: Decimal) -> Tuple[bool, str, Decimal]:
        """Perform pre-trade margin checks"""
        equity = await self.calculations.calculate_equity(account_id)
        
        required_margin = self.calculations.calculate_initial_margin_required(trade_quantity, price) #positive value whether buy or sell
        
        # Get current positions to calculate maintenance margin impact
        current_positions = await self.account_client.get_all_positions(account_id)
        current_maintenance = await self.calculations.calculate_maintenance_margin(account_id)
        
        if side.upper() == "SELL": #assume only BTC-PERP is traded
            current_quantity = current_positions.get("BTC-PERP", {}).get("quantity", Decimal('0')) #assume only BTC-PERP is traded
            if current_quantity - trade_quantity < 0:
                return False, f"Insufficient quantity. Required: {trade_quantity}, Available: {current_quantity}", required_margin
 
        elif side.upper() == "BUY":
            total_required = required_margin + current_maintenance
        
            if equity < total_required:
                return False, f"Insufficient equity. Required: {total_required}, Available: {equity}", required_margin
        else:
            raise TradingError("Invalid side. Side must be BUY or SELL")
        
        return True, "Trade approved", required_margin



    async def _record_trade_in_postgres(self, account_id: int, symbol: str, side: str, quantity: Decimal, price: Decimal) -> int:
        """Record trade in PostgreSQL and return trade ID"""
        trade = Trade(
            account_id=account_id,
            symbol=symbol,
            side=side.upper(),
            quantity=quantity,
            price=price
        )
        
        return await self.postgres_client.insert_model(trade, "trades")

    async def execute_trade(self, account_id: int, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Tuple[bool, str, Optional[int]]:
        """Execute a trade after pre-trade checks"""
        # Validate quantity for BTC trades (must be whole numbers)
       
        if symbol == "BTC-PERP" and quantity % 1 != 0:
            raise TradingError("BTC trades must be in whole numbers (no fractional BTC)")
        
        # Pre-trade check
        check_passed, message, required_margin = await self.pre_trade_check(account_id, side, quantity, price)
        if not check_passed:
            raise TradeNotApproved(message)
        # Calculate trade details
        trade_quantity = quantity if side.upper() == "BUY" else -quantity
        
        # Get current position and calculate new position, update in redis
        current_position = await self.account_client.get_position(account_id, symbol)
        new_quantity, new_avg_price = self.calculations.calculate_new_position(current_position, trade_quantity, price)
        await self.account_client.set_position(account_id, symbol, new_quantity, new_avg_price)

        # Calculate new balance and update in redis
        current_balance = await self.account_client.get_balance(account_id)
        balance_change = -required_margin if side.upper() == "BUY" else required_margin
        new_balance = current_balance + balance_change
        await self.account_client.set_balance(account_id, new_balance)

        # Calculate new equity and update in redis
        equity = await self.calculations.calculate_equity(account_id)
        await self.account_client.set_equity(account_id, equity)

        # Calculate new used margin and update in redis
        used_margin = await self.calculations.calculate_maintenance_margin(account_id)
        await self.account_client.set_used_margin(account_id, used_margin)

        # Record trade in PostgreSQL
        trade_id = await self._record_trade_in_postgres(account_id, symbol, side, quantity, price)        
        return True, "Trade executed successfully", trade_id

    async def get_account_positions(self, account_id: int) -> Dict[str, Any]:
        """Get account balance, equity, and all positions with P&L"""
        return await self.calculations.get_account_positions(account_id)

    async def get_trade_history(self, account_id: int, limit: int = 100) -> List[Trade]:
        """Get trade history for an account"""
        query = """
            SELECT id, account_id, symbol, side, quantity, price, timestamp
            FROM trades 
            WHERE account_id = $1 
            ORDER BY timestamp DESC 
            LIMIT $2
        """
        return await self.postgres_client.fetch_models(Trade, query, account_id, limit)
