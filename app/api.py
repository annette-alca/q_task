from fastapi.exceptions import HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from .services.trading import TradingService, TradingError, TradeNotApproved
from .services.margin import MarginService
from decimal import Decimal
from .redis_client import MarketRedisClient
from .models import Trade, Liquidation


router = APIRouter()

# Dependency injection will be handled in main.py
trading_service: Optional[TradingService] = None
margin_service: Optional[MarginService] = None
market_client: Optional[MarketRedisClient] = None

def initialise_services(trading_svc: TradingService, margin_svc: MarginService, market_cli: MarketRedisClient):
    """Initialise the services for dependency injection"""
    global trading_service, margin_service, market_client
    trading_service = trading_svc
    margin_service = margin_svc
    market_client = market_cli

# ----------------------------
# Request Models
# ----------------------------
class TradeRequest(BaseModel):
    account_id: int
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: float

class MarkPriceRequest(BaseModel):
    symbol: str
    price: float

# Response Models
class TradeResponse(BaseModel):
    success: bool
    message: str
    trade_id: Optional[int] = None

class Position(BaseModel):
    symbol: str
    quantity: Decimal
    avg_price: Decimal
    mark_price: Decimal
    unrealised_pnl: Decimal

class AccountPositionsResponse(BaseModel):
    account_id: int
    balance: Decimal
    equity: Decimal
    positions: List[Position]

class AccountMarginDetail(BaseModel):
    account_id: int
    equity: Decimal
    maintenance_margin_required: Decimal
    margin_utilisation_pct: Decimal
    liquidation_risk: bool

class MarginReportResponse(BaseModel):
    total_accounts: int
    liquidation_candidates: List[int]
    accounts_detail: List[AccountMarginDetail]

# ----------------------------
# API Endpoints
# ----------------------------
@router.post("/trade", response_model=TradeResponse)
async def execute_trade(req: TradeRequest):
    """Execute trade with pre-trade margin checks"""
    if not trading_service:
        raise HTTPException(status_code=500, detail="Trading service not initialised")
    
    try:
        success, message, trade_id = await trading_service.execute_trade(
            req.account_id, req.symbol, req.side, Decimal(str(req.quantity)), Decimal(str(req.price))
        )
        
        return TradeResponse(success=True, message=message, trade_id=trade_id)
            
    except TradingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TradeNotApproved as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/positions/{account_id}", response_model=AccountPositionsResponse)
async def get_positions(account_id: int):
    """Get current positions and P&L for an account"""
    if not trading_service:
        raise HTTPException(status_code=500, detail="Trading service not initialised")
    
    try:
        account_data = await trading_service.get_account_positions(account_id)
        
        positions = [
            Position(
                symbol=pos["symbol"],
                quantity=pos["quantity"],
                avg_price=pos["avg_price"],
                mark_price=pos["mark_price"],
                unrealised_pnl=pos["unrealised_pnl"]
            )
            for pos in account_data["positions"]
        ]
        
        return AccountPositionsResponse(
            account_id=account_data["account_id"],
            balance=account_data["balance"],
            equity=account_data["equity"],
            positions=positions
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mark-price")
async def update_mark_price(req: MarkPriceRequest):
    """Update mark price for a symbol"""
    if not market_client:
        raise HTTPException(status_code=500, detail="Market client not initialised")
    
    try:
        await market_client.set_mark_price(req.symbol, Decimal(str(req.price)))
        return {"success": True, "message": f"Mark price for {req.symbol} updated to {req.price}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/margin-report", response_model=MarginReportResponse)
async def margin_report():
    """Get margin utilisation report and liquidation candidates"""
    if not margin_service:
        raise HTTPException(status_code=500, detail="Margin service not initialised")
    
    try:
        report_data = await margin_service.get_margin_utilisation()
        
        return MarginReportResponse(
            total_accounts=report_data["total_accounts"],
            liquidation_candidates=report_data["liquidation_candidates"],
            accounts_detail=[
                AccountMarginDetail(**account_detail) 
                for account_detail in report_data["accounts_detail"]
            ]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades/{account_id}")
async def get_trade_history(account_id: int, limit: int = 100):
    """Get trade history for an account"""
    if not trading_service:
        raise HTTPException(status_code=500, detail="Trading service not initialised")
    
    try:
        trades = await trading_service.get_trade_history(account_id, limit)
        return {"trades": [trade.model_dump() for trade in trades]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/liquidations")
async def get_liquidation_history(account_id: Optional[int] = None, limit: int = 100):
    """Get liquidation history, optionally filtered by account"""
    if not margin_service:
        raise HTTPException(status_code=500, detail="Margin service not initialised")
    
    try:
        liquidations = await margin_service.get_liquidation_history(account_id, limit)
        return {"liquidations": [liquidation.model_dump() for liquidation in liquidations]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
