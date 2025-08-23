
from decimal import Decimal
from typing import List, Dict, Any, Optional
from ..redis_client import AccountRedisClient, MarketRedisClient
from ..postgres import AsyncPostgresClient
from ..models import Liquidation
from .calculations import CalculationsService

class MarginService:
    def __init__(self, account_client: AccountRedisClient, market_client: MarketRedisClient, postgres_client: AsyncPostgresClient):
        self.account_client = account_client
        self.market_client = market_client
        self.postgres_client = postgres_client
        
        # Inject the shared calculations service
        self.calculations = CalculationsService(account_client, market_client)



    def is_liquidation_candidate(self, equity: Decimal, maintenance_required: Decimal) -> bool:
        """Check if account should be liquidated (pure function)"""
        return equity < maintenance_required

    async def record_liquidation(self, account_id: int, reason: str):
        """Record liquidation event in PostgreSQL"""
        liquidation = Liquidation(
            account_id=account_id,
            reason=reason
        )
        
        await self.postgres_client.insert_model(liquidation, "liquidations")

    async def get_liquidation_history(self, account_id: Optional[int] = None, limit: int = 100) -> List[Liquidation]:
        """Get liquidation history, optionally filtered by account"""
        if account_id:
            query = """
                SELECT id, account_id, reason, timestamp
                FROM liquidations 
                WHERE account_id = $1 
                ORDER BY timestamp DESC 
                LIMIT $2
            """
            return await self.postgres_client.fetch_models(Liquidation, query, account_id, limit)
        else:
            query = """
                SELECT id, account_id, reason, timestamp
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
            equity = await self.calculations.calculate_equity(account_id)
            maintenance_required = await self.calculations.calculate_maintenance_margin(account_id)
            utilisation = self.calculations.calculate_margin_utilisation(equity, maintenance_required)
            is_liquidation = self.is_liquidation_candidate(equity, maintenance_required)
            
            account_detail = {
                "account_id": account_id,
                "equity": equity,
                "maintenance_margin_required": maintenance_required,
                "margin_utilisation_pct": utilisation,
                "liquidation_risk": is_liquidation
            }
            
            accounts_detail.append(account_detail)
            
            # Handle liquidation
            if is_liquidation:
                liquidation_candidates.append(account_id)
                reason = f"Equity ({equity}) below maintenance margin ({maintenance_required})"
                await self.record_liquidation(account_id, reason)

        return {
            "total_accounts": len(all_accounts),
            "liquidation_candidates": liquidation_candidates,
            "accounts_detail": accounts_detail
        }
