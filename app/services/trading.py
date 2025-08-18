
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, List
from ..redis_client import AccountRedisClient, MarketRedisClient
from ..postgres import AsyncPostgresClient
from ..models import Trade


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
        
        # Configuration
        self.INITIAL_MARGIN_RATE = Decimal('0.20')  # 20%
        self.MAINTENANCE_MARGIN_RATE = Decimal('0.10')  # 10%

    async def calculate_equity(self, account_id: int) -> Decimal:
        """Calculate account equity = balance + sum(position PnL)"""
        balance = await self.account_client.get_balance(account_id)
        positions = await self.account_client.get_all_positions(account_id)
        
        total_pnl = Decimal('0')
        for symbol, position_data in positions.items():
            if position_data["quantity"] == 0:
                continue
                
            mark_price = await self.market_client.get_mark_price(symbol)
            if mark_price:
                pnl = (mark_price - position_data["avg_price"]) * position_data["quantity"]
                total_pnl += pnl
        
        return balance + total_pnl

    async def calculate_maintenance_margin(self, account_id: int) -> Decimal:
        """Calculate total maintenance margin required"""
        positions = await self.account_client.get_all_positions(account_id)
        total_maintenance = Decimal('0')
        
        for symbol, position_data in positions.items():
            if position_data["quantity"] == 0:
                continue
                
            mark_price = await self.market_client.get_mark_price(symbol)
            if mark_price:
                notional = abs(position_data["quantity"]) * mark_price
                maintenance = notional * self.MAINTENANCE_MARGIN_RATE
                total_maintenance += maintenance
        
        return total_maintenance

    def calculate_initial_margin_required(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Calculate initial margin required for a new trade (pure function)"""
        notional = abs(quantity) * price
        return notional * self.INITIAL_MARGIN_RATE

    async def pre_trade_check(self, account_id: int, side: str, trade_quantity: Decimal, price: Decimal) -> Tuple[bool, str, Decimal]:
        """Perform pre-trade margin checks"""
        equity = await self.calculate_equity(account_id)
        
        required_margin = self.calculate_initial_margin_required(trade_quantity, price) #positive value whether buy or sell
        
        # Get current positions to calculate maintenance margin impact
        current_positions = await self.account_client.get_all_positions(account_id)
        current_maintenance = await self.calculate_maintenance_margin(account_id)
        
        if side.upper() == "SELL":
            current_quantity = current_positions["BTC-PERP"]["quantity"] #assume only BTC-PERP is traded
            if current_quantity - trade_quantity < 0:
                return False, f"Insufficient quantity. Required: {trade_quantity}, Available: {current_quantity}", required_margin
 
        elif side.upper() == "BUY":
            total_required = required_margin + current_maintenance
        
            if equity < total_required:
                return False, f"Insufficient equity. Required: {total_required}, Available: {equity}", required_margin
        else:
            raise TradingError("Invalid side. Side must be BUY or SELL")
        
        return True, "Trade approved", required_margin

    def calculate_new_position(self, current_position: Optional[Dict[str, Decimal]], trade_quantity: Decimal, trade_price: Decimal) -> Tuple[Decimal, Decimal]:
        """Calculate new position after trade with weighted average price (pure function)"""
        if current_position is None:
            return trade_quantity, trade_price
        
        current_qty = current_position["quantity"]
        current_avg_price = current_position["avg_price"]
        new_quantity = current_qty + trade_quantity
        
        if new_quantity == 0:
            return Decimal('0'), Decimal('0')
        
        # Weighted average for same direction trades
        if (current_qty > 0 and trade_quantity > 0) or (current_qty < 0 and trade_quantity < 0):
            total_cost = (current_qty * current_avg_price) + (trade_quantity * trade_price)
            new_avg_price = total_cost / new_quantity
        else:
            # Position flip or closing - use new price
            new_avg_price = trade_price
            
        return new_quantity, new_avg_price

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
        
        # Get current position and calculate new position
        current_position = await self.account_client.get_position(account_id, symbol)
        new_quantity, new_avg_price = self.calculate_new_position(current_position, trade_quantity, price)

        # Update position in Redis
        await self.account_client.set_position(account_id, symbol, new_quantity, new_avg_price)

        # Update balance
        current_balance = await self.account_client.get_balance(account_id)
        balance_change = -required_margin if side.upper() == "BUY" else required_margin
        new_balance = current_balance + balance_change
        await self.account_client.set_balance(account_id, new_balance)

        # Update equity in Redis
        equity = await self.calculate_equity(account_id)
        await self.account_client.set_equity(account_id, equity)

        # Update used margin in Redis
        used_margin = await self.calculate_maintenance_margin(account_id)
        await self.account_client.set_used_margin(account_id, used_margin)

        # Record trade in PostgreSQL
        trade_id = await self._record_trade_in_postgres(account_id, symbol, side, quantity, price)

        return True, "Trade executed successfully", trade_id

    async def get_account_positions(self, account_id: int) -> Dict[str, Any]:
        """Get account balance, equity, and all positions with P&L"""
        balance = await self.account_client.get_balance(account_id)
        positions_data = await self.account_client.get_all_positions(account_id)
        
        positions = []
        total_pnl = Decimal('0')
        
        for symbol, pos_data in positions_data.items():
            if pos_data["quantity"] == 0:
                continue
                
            mark_price = await self.market_client.get_mark_price(symbol)
            if mark_price:
                unrealised_pnl = (mark_price - pos_data["avg_price"]) * pos_data["quantity"]
                total_pnl += unrealised_pnl
                
                positions.append({
                    "symbol": symbol,
                    "quantity": pos_data["quantity"],
                    "avg_price": pos_data["avg_price"],
                    "mark_price": mark_price,
                    "unrealised_pnl": unrealised_pnl
                })
        
        equity = balance + total_pnl
        
        return {
            "account_id": account_id,
            "balance": balance,
            "equity": equity,
            "positions": positions
        }

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
