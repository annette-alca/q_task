 Production-minded async derivatives trading platform built with FastAPI, Redis, and PostgreSQL.

This system was built following [these instructions](instructions.md).


## Features

- **Real-time trading** with pre-trade margin checks
- **Position management** with P&L calculations  
- **Margin monitoring** and liquidation detection
- **Async operations** for high performance
- **Redis state storage** for fast reads/writes
- **PostgreSQL history** for audit trails
- **Comprehensive testing** with isolated units

## Margin System

- **Initial Margin**: 20% of notional value (checked against **equity**, not just balance)
- **Maintenance Margin**: 10% of notional value  
- **Equity = Balance + Position P&L**
- **Liquidation**: When equity < maintenance margin

## Redis Data Structure

### AccountRedisClient
```
balances -> hash: {account_id: balance}
position:{account_id}:{symbol} -> hash: {quantity, entry_price}
```

### MarketRedisClient  
```
mark_prices -> hash: {symbol: price}
```

## API Endpoints

- `POST /trade` - Execute trades with margin checks
- `GET /positions/{account_id}` - Get positions and P&L
- `POST /mark-price` - Update mark prices
- `GET /margin-report` - Margin utilisation report
- `GET /trades/{account_id}` - Get trade history using Trade models
- `GET /liquidations` - Get liquidation history using Liquidation models


## Quick Start

1. **Start services:**
```bash
docker-compose up -d
```

2. **Install and run:**
```bash
poetry install
poetry run python -m app.main
```

3. **Run tests:**
```bash
poetry run pytest tests/ -v
```

4. **Run integration test (optional):**
```bash
poetry run python test_integration.py
```

The integration test demonstrates the full system functionality by:
- Connecting to real Redis and PostgreSQL
- Setting up test accounts and market data
- Executing trades with margin checks
- Testing liquidation scenarios
- Generating comprehensive reports

## Example Usage

```bash
# Execute a trade
curl -X POST "http://localhost:8000/trade" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "symbol": "BTC-PERP", 
    "side": "BUY",
    "quantity": 0.1,
    "price": 50000
  }'

# Check positions  
curl "http://localhost:8000/positions/1"

# Update mark price
curl -X POST "http://localhost:8000/mark-price" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC-PERP", "price": 51000}'
```

## Key Improvements Made

### 1. **Redis Client Subclasses**
- `BaseRedisClient`: Core connection logic
- `AccountRedisClient`: Account-specific operations (balances, positions)
- `MarketRedisClient`: Market data operations (mark prices)

### 2. **Service Encapsulation**  
- Database operations moved into services
- Clear separation between data access and business logic
- Pure functions for calculations where possible

### 3. **API Layer Cleanup**
- Removed business logic from API endpoints
- API now only handles HTTP concerns (validation, response formatting)
- All calculations delegated to services

### 4. **Testability**
- Dependency injection throughout
- Pure functions for core calculations
- Easy to mock external dependencies
- Isolated unit tests for each component


## Project Structure

```plaintext
q_test2/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── api.py               # API routes and request/response models
│   ├── config.py            # Environment configuration
│   ├── models.py            # Pydantic models for database entities
│   ├── postgres.py          # Async PostgreSQL client
│   ├── redis_client.py      # Async Redis clients (Account & Market)
│   └── services/
│       ├── __init__.py
│       ├── trading.py       # Trading service (pre-trade checks, execution)
│       └── margin.py        # Margin service (utilisation, liquidation)
├── tests/
│   ├── test_trading_service.py
│   ├── test_margin_service.py
│   ├── test_redis_clients.py
│   └── test_config.py
├── test_integration.py      # End-to-end integration test with real databases
├── docker-compose.yaml      # Redis + PostgreSQL services
├── init.sql                 # Database schema initialization
├── env.example              # Environment variables template
├── pyproject.toml           # Poetry configuration
├── poetry.lock              # Dependency lock file
├── instructions.md          # Original task requirements
└── README.md               # This file
```

## Architecture Overview

### Clean Architecture Implementation
```
┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐
│   API Layer     │───▶│  Services Layer  │───▶│ Data Access Layer │
│ (FastAPI)       │    │ (Business Logic) │    │ (Redis/Postgres)  │
│                 │    │                  │    │                   │
│ • Request/      │    │ • TradingService │    │ • AccountRedis    │
│   Response      │    │ • MarginService  │    │   Client          │
│ • Validation    │    │ • Pure Functions │    │ • MarketRedis     │
│ • Error Handling│    │                  │    │   Client          │
│                 │    │                  │    │ • PostgresClient  │
└─────────────────┘    └──────────────────┘    └───────────────────┘
```

### Key Design Principles

1. **Single Responsibility**: Each class has one clear purpose
2. **Dependency Injection**: Services receive their dependencies, making testing easy
3. **Pure Functions**: Business logic separated from I/O operations where possible
4. **Separation of Concerns**: API layer only handles HTTP, services handle business logic

## Testing Strategy

### Pure Functions (Easy to Test)
```python
# No mocking needed
def test_calculate_initial_margin():
    result = service.calculate_initial_margin_required(Decimal('1'), Decimal('50000'))
    assert result == Decimal('10000')
```

### Async Functions (Mock Dependencies)
```python  
# Mock external dependencies only
@pytest.mark.asyncio
async def test_calculate_equity(trading_service, mock_clients):
    # Mock the data access layer
    account_client.get_balance.return_value = Decimal('10000')
    # Test the business logic
    equity = await trading_service.calculate_equity(1)
```

## Environment Configuration

The application uses a centralized configuration approach with environment variables. Copy the example file and modify as needed:

```bash
cp env.example .env
```

### Key Environment Variables

- **PostgreSQL**: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE`
- **Redis**: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`
- **Application**: `APP_NAME`, `APP_VERSION`, `DEBUG`, `HOST`, `PORT`

### Configuration Benefits

- **Type Safety**: Automatic conversion of strings to appropriate types (int, bool)
- **Default Values**: Sensible defaults if environment variables are not set
- **Centralized**: All configuration in one place (`app/config.py`)
- **Testable**: Easy to mock configuration for testing