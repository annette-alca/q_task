from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Trade(BaseModel):
    """Model for trade history stored in Postgres"""
    id: Optional[int] = None
    account_id: int
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float
    timestamp: datetime = datetime.utcnow()


class Liquidation(BaseModel):
    """Model for liquidation events stored in Postgres"""
    id: Optional[int] = None
    account_id: int
    reason: str
    timestamp: datetime = datetime.utcnow()


# SQL table creation queries
TRADES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

LIQUIDATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS liquidations (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);
"""
