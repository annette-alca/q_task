from decimal import Decimal
from typing import Dict, Optional, Tuple, Any, List
from app.redis_client import AccountRedisClient, MarketRedisClient

class CalculationsService:
    """Shared calculation service for Trading and Margin Services. 
    Calculates equity, margin, and position calculations"""
    
    def __init__(self, account_client: AccountRedisClient, market_client: MarketRedisClient):
        self.account_client = account_client
        self.market_client = market_client
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

    def calculate_margin_utilisation(self, equity: Decimal, maintenance_required: Decimal) -> Decimal:
        """Calculate margin utilisation percentage (pure function)"""
        if maintenance_required == 0:
            return Decimal('0')
        if equity == 0:
            return Decimal('Infinity')
        return (maintenance_required / equity * 100) #can be over 100%

    def calculate_new_position(self, current_position: Optional[Dict[str, Decimal]], 
                             trade_quantity: Decimal, trade_price: Decimal) -> Tuple[Decimal, Decimal]:
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

    async def get_account_positions(self, account_id: int) -> Dict[str, Any]:
        """Get account balance, equity, and all positions with P&L"""
        balance = await self.account_client.get_balance(account_id)
        equity = await self.calculate_equity(account_id)
        positions_data = await self.account_client.get_all_positions(account_id)
        
        positions = []
        for symbol, pos_data in positions_data.items():
            mark_price = await self.market_client.get_mark_price(symbol)
            if mark_price:
                unrealised_pnl = (mark_price - pos_data["avg_price"]) * pos_data["quantity"]
            else:
                unrealised_pnl = Decimal('0')
            
            positions.append({
                "symbol": symbol,
                "quantity": pos_data["quantity"],
                "avg_price": pos_data["avg_price"],
                "mark_price": mark_price or Decimal('0'),
                "unrealised_pnl": unrealised_pnl
            })
        
        return {
            "account_id": account_id,
            "balance": balance,
            "equity": equity,
            "positions": positions
        }
