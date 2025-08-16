from fastapi import FastAPI
from contextlib import asynccontextmanager
from .api import router, initialise_services
from .redis_client import AccountRedisClient, MarketRedisClient
from .postgres import AsyncPostgresClient
from .services.trading import TradingService
from .services.margin import MarginService
from .config import config
import uvicorn

# Global variables for services
account_client = None
market_client = None
postgres_client = None
trading_service = None
margin_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global account_client, market_client, postgres_client, trading_service, margin_service
    
    # Initialise clients
    account_client = AccountRedisClient(
        host=config.REDIS_HOST, 
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD if config.REDIS_PASSWORD else None,
        db=config.REDIS_DB
    )
    market_client = MarketRedisClient(
        host=config.REDIS_HOST, 
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD if config.REDIS_PASSWORD else None,
        db=config.REDIS_DB
    )
    postgres_client = AsyncPostgresClient(
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD, 
        database=config.POSTGRES_DATABASE,
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT
    )

    # Initialise services with dependency injection
    trading_service = TradingService(account_client, market_client, postgres_client)
    margin_service = MarginService(account_client, market_client, postgres_client)

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
    
    yield
    
    # Shutdown
    await account_client.close()
    await market_client.close()
    await postgres_client.close()
    print("Trading platform shutdown complete!")

app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan)

# Include API routes
app.include_router(router)

@app.get("/")
async def root():
    return {"message": config.APP_NAME, "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=config.HOST, 
        port=config.PORT,
        reload=config.DEBUG
    )
