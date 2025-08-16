from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, List
from ..redis_client import AccountRedisClient, MarketRedisClient
from ..postgres import AsyncPostgresClient
from ..models import Trade

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
                pnl = (mark_price - position_data["entry_price"]) * position_data["quantity"]
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

    async def pre_trade_check(self, account_id: int, side: str, quantity: Decimal, price: Decimal) -> Tuple[bool, str]:
        """Perform pre-trade margin checks"""
        equity = await self.calculate_equity(account_id)
        
    #     trade_quantity = quantity if side.upper() == "BUY" else -quantity
    #     required_margin = self.calculate_initial_margin_required(trade_quantity, price)
    #     current_maintenance = await self.calculate_maintenance_margin(account_id)
        
    #     total_required = required_margin + current_maintenance
    #     if equity < total_required:
    #         return False, f"Insufficient equity. Required: {total_required}, Available: {equity}"
        
        trade_quantity = quantity if side.upper() == "BUY" else -quantity
        required_initial_margin = self.calculate_initial_margin_required(trade_quantity, price)
        
        # For initial margin check, we only need to ensure equity covers the new trade's margin
        if equity < required_initial_margin:
            return False, f"Insufficient equity. Required: {required_initial_margin}, Available: {equity}"
        
        return True, "Trade approved"

    def calculate_new_position(self, current_position: Optional[Dict[str, Decimal]], trade_quantity: Decimal, trade_price: Decimal) -> Tuple[Decimal, Decimal]:
        """Calculate new position after trade (pure function)"""
        if current_position is None:
            return trade_quantity, trade_price
        
        current_qty = current_position["quantity"]
        current_entry = current_position["entry_price"]
        new_quantity = current_qty + trade_quantity
        
        if new_quantity == 0:
            return Decimal('0'), Decimal('0')
        
        # Weighted average for same direction trades
        if (current_qty > 0 and trade_quantity > 0) or (current_qty < 0 and trade_quantity < 0):
            total_cost = (current_qty * current_entry) + (trade_quantity * trade_price)
            new_entry_price = total_cost / new_quantity
        else:
            # Position flip or closing - use new price
            new_entry_price = trade_price
            
        return new_quantity, new_entry_price

    async def _record_trade_in_postgres(self, account_id: int, symbol: str, side: str, quantity: Decimal, price: Decimal, notional: Decimal) -> int:
        """Record trade in PostgreSQL and return trade ID"""
        trade = Trade(
            account_id=account_id,
            symbol=symbol,
            side=side.upper(),
            quantity=float(quantity),
            price=float(price),
            notional=float(notional)
        )
        
        return await self.postgres_client.insert_model(trade, "trades")

    async def execute_trade(self, account_id: int, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Tuple[bool, str, Optional[int]]:
        """Execute a trade after pre-trade checks"""
        # Validate quantity for BTC trades (must be whole numbers)
        if symbol == "BTC-PERP" and quantity % 1 != 0:
            return False, "BTC trades must be in whole numbers (no fractional BTC)", None
        
        # Pre-trade check
        check_passed, message = await self.pre_trade_check(account_id, side, quantity, price)
        if not check_passed:
            return False, message, None

        # Calculate trade details
        notional = quantity * price
        trade_quantity = quantity if side.upper() == "BUY" else -quantity
        
        # Get current position and calculate new position
        current_position = await self.account_client.get_position(account_id, symbol)
        new_quantity, new_entry_price = self.calculate_new_position(current_position, trade_quantity, price)

        # Update position in Redis
        await self.account_client.set_position(account_id, symbol, new_quantity, new_entry_price)

        # Update balance
        current_balance = await self.account_client.get_balance(account_id)
        balance_change = -notional if side.upper() == "BUY" else notional
        new_balance = current_balance + balance_change
        await self.account_client.set_balance(account_id, new_balance)

        # Record trade in PostgreSQL
        trade_id = await self._record_trade_in_postgres(account_id, symbol, side, quantity, price, notional)

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
                unrealised_pnl = (mark_price - pos_data["entry_price"]) * pos_data["quantity"]
                notional = abs(pos_data["quantity"]) * mark_price
                total_pnl += unrealised_pnl
                
                positions.append({
                    "symbol": symbol,
                    "quantity": pos_data["quantity"],
                    "entry_price": pos_data["entry_price"],
                    "mark_price": mark_price,
                    "unrealised_pnl": unrealised_pnl,
                    "notional": notional
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
            SELECT id, account_id, symbol, side, quantity, price, notional, timestamp
            FROM trades 
            WHERE account_id = $1 
            ORDER BY timestamp DESC 
            LIMIT $2
        """
        return await self.postgres_client.fetch_models(Trade, query, account_id, limit)
