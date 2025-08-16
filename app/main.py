from fastapi import FastAPI
from .api import router, initialise_services
from .redis_client import AccountRedisClient, MarketRedisClient
from .postgres import AsyncPostgresClient
from .services.trading import TradingService
from .services.margin import MarginService
import uvicorn

app = FastAPI(title="Trading Platform", version="1.0.0")

# Initialise clients
account_client = AccountRedisClient(host="localhost", port=6379)
market_client = MarketRedisClient(host="localhost", port=6379)
postgres_client = AsyncPostgresClient(
    user="user",
    password="pass", 
    database="trading",
    host="localhost",
    port=5432
)

# Initialise services with dependency injection
trading_service = TradingService(account_client, market_client, postgres_client)
margin_service = MarginService(account_client, market_client, postgres_client)

@app.on_event("startup")
async def startup_event():
    # Connect to services
    await account_client.connect()
    await market_client.connect()
    await postgres_client.connect()
    
    # Initialise API services with dependency injection
    initialise_services(trading_service, margin_service, market_client)
    
    # Set some test data
    await account_client.set_balance(1, 10000.0)
    await account_client.set_balance(2, 5000.0)
    await market_client.set_mark_price("BTC-PERP", 50000.0)
    
    print("Trading platform started successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    await account_client.close()
    await market_client.close()
    await postgres_client.close()
    print("Trading platform shutdown complete!")

# Include API routes
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Trading Platform API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0", 
        port=8000,
        reload=True
    )
