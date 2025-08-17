from decimal import Decimal
from typing import List, Dict, Any, Optional
from ..redis_client import AccountRedisClient, MarketRedisClient
from ..postgres import AsyncPostgresClient
from ..models import Liquidation

class MarginService:
    def __init__(self, account_client: AccountRedisClient, market_client: MarketRedisClient, postgres_client: AsyncPostgresClient):
        self.account_client = account_client
        self.market_client = market_client
        self.postgres_client = postgres_client
        self.MAINTENANCE_MARGIN_RATE = Decimal('0.10')  # 10%

    async def calculate_account_equity(self, account_id: int) -> Decimal:
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

    async def calculate_maintenance_margin_required(self, account_id: int) -> Decimal:
        """Calculate total maintenance margin required for account"""
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

    def calculate_margin_utilisation(self, equity: Decimal, maintenance_required: Decimal) -> Decimal:
        """Calculate margin utilisation percentage (pure function)"""
        return (maintenance_required / equity * 100) if equity > 0 else Decimal('100')

    def is_liquidation_candidate(self, equity: Decimal, maintenance_required: Decimal) -> bool:
        """Check if account should be liquidated (pure function)"""
        return equity < maintenance_required

    async def record_liquidation(self, account_id: int, equity: Decimal, maintenance_margin: Decimal, reason: str):
        """Record liquidation event in PostgreSQL"""
        liquidation = Liquidation(
            account_id=account_id,
            equity=float(equity),
            maintenance_margin=float(maintenance_margin),
            reason=reason
        )
        
        await self.postgres_client.insert_model(liquidation, "liquidations")

    async def get_liquidation_history(self, account_id: Optional[int] = None, limit: int = 100) -> List[Liquidation]:
        """Get liquidation history, optionally filtered by account"""
        if account_id:
            query = """
                SELECT id, account_id, equity, maintenance_margin, reason, timestamp
                FROM liquidations 
                WHERE account_id = $1 
                ORDER BY timestamp DESC 
                LIMIT $2
            """
            return await self.postgres_client.fetch_models(Liquidation, query, account_id, limit)
        else:
            query = """
                SELECT id, account_id, equity, maintenance_margin, reason, timestamp
                FROM liquidations 
                ORDER BY timestamp DESC 
                LIMIT $1
            """
            return await self.postgres_client.fetch_models(Liquidation, query, limit)

    async def get_margin_utilisation(self) -> Dict[str, Any]:
        """Get margin utilisation for all accounts"""
        all_accounts = await self.account_client.get_all_accounts()
        liquidation_candidates = []
        accounts_detail = []
        
        for account_id in all_accounts:
            equity = await self.calculate_account_equity(account_id)
            maintenance_required = await self.calculate_maintenance_margin_required(account_id)
            utilisation = self.calculate_margin_utilisation(equity, maintenance_required)
            is_liquidation = self.is_liquidation_candidate(equity, maintenance_required)
            
            account_detail = {
                "account_id": account_id,
                "equity": float(equity),
                "maintenance_margin_required": float(maintenance_required),
                "margin_utilisation_pct": float(utilisation),
                "liquidation_risk": is_liquidation
            }
            
            accounts_detail.append(account_detail)
            
            # Handle liquidation
            if is_liquidation:
                liquidation_candidates.append(account_id)
                reason = f"Equity ({equity}) below maintenance margin ({maintenance_required})"
                await self.record_liquidation(account_id, equity, maintenance_required, reason)

        return {
            "total_accounts": len(all_accounts),
            "liquidation_candidates": liquidation_candidates,
            "accounts_detail": accounts_detail
        }
