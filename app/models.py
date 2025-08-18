from datetime import datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel


class Trade(BaseModel):
    """Model for trade history stored in Postgres"""
    id: Optional[int] = None
    account_id: int
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: Decimal
    price: Decimal
    timestamp: Optional[datetime] = None


class Liquidation(BaseModel):
    """Model for liquidation events stored in Postgres"""
    id: Optional[int] = None
    account_id: int
    reason: str
    timestamp: Optional[datetime] = None


