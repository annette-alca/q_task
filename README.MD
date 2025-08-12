# Trading & Margining System - Interview Task

## Overview
You are tasked with building a simplified trading and margining service for a derivatives platform.  
You will trade a single perpetual future `BTC-PERP` in `USDT` (margin).   
The system will:

1. **Perform pre-trade checks** for:
   - Initial margin
   - Maintenance margin
2. **Book trades** and update positions/balances
3. **Expose APIs** to:
   - Execute a trade
   - Query positions and P&L
   - Update the mark price for a symbol
   - Report margin utilisation and accounts that should be liquidated

This is a simplified model of a real trading system — keep it clean, well-structured, and production-minded.

**Key Difference from Typical CRUD:**  
All *current state* (balances, positions, mark prices) should be stored in **Redis** for fast updates and reads.  
**Postgres** should be used for **history only** (immutable trade log, liquidation log).

## Margin Requirements

For this simplified system:

- **Initial Margin Requirement**: **20%** of the notional value of the position
- **Maintenance Margin Requirement**: **10%** of the notional value of the position
- **Equity (USDT)** = `cash balance + sum(positions pnl)`

Definitions:
- **Initial Margin**: The minimum amount of equity required to open a position.
- **Maintenance Margin**: The minimum amount of equity that must be maintained to keep the position open.
- **Equity**: The total value of the account, including cash and unrealized P&L from positions.

**Notes**:
- Pre-trade checks should ensure the account has at least the initial margin available **before** opening or increasing a position.
- During margin utilisation checks, if an account’s equity falls below the maintenance margin level, it should be flagged for liquidation.
- Notional value = `price * quantity` of the position (candidate must work out exact usage in calculations).


---

## Requirements

### Packages
- **Poetry** for dependency management
- **psycopg2** for Postgres connection
- **redis** for Redis connection
- **FastAPI** for the API layer
- **pydantic** for data models and validation


### Functional
1. **Pre-Trade Checks**
   - Use Redis to get the account's current equity and used margin.
   - Check if free margin is sufficient for the trade.
2. **Trade Booking**
   - Update positions and balances in Redis.
   - Append the trade to Postgres `trades` table.
3. **Mark Prices**
   - Store current mark price per symbol in Redis.
   - Use mark price to calculate Unrealized P&L.
4. **Margin Utilisation**
   - Identify accounts with equity < maintenance margin as liquidation candidates.
   - Record liquidation events in Postgres `liquidations` table.
5. **APIs**
   - `POST /trade` → Executes trade (pre-check, update Redis, persist to Postgres history)
   - `GET /positions/{account_id}` → Returns current positions & P&L from Redis
   - `POST /mark-price` → Updates mark price in Redis
   - `GET /margin-report` → Returns margin utilisation for all accounts from Redis & list of liquidation candidates

---


## Data Model

### Redis (current state)
- `account:{id}:balance` (float)
- `account:{id}:equity` (float)
- `account:{id}:used_margin` (float)
- `positions:{account_id}` (hash: `{symbol: quantity, avg_price}`)
- `mark_price:{symbol}` (float)

### Postgres (history)
#### `trades`
| id | account_id | symbol | side | quantity | price | timestamp |

#### `liquidations`
| id | account_id | reason | timestamp |

---

## Evaluation Criteria
- Correctness of margin checks
- Proper use of Redis for state and Postgres for history
- Code clarity and structure
- API correctness
- Tests for core logic

---

## Starter Provided
- FastAPI project scaffold
- Docker Compose with Redis + Postgres
- Example SQLAlchemy models for history tables
- Redis helper for common operations

---

---

## **Project Structure**

```plaintext
app/
  main.py
  api.py
  database.py          # SQLAlchemy/Postgres
  redis_client.py      # Redis connection + helpers
  models.py            # Postgres models (history tables)
  services/
    trading.py         # Pre-trade check, booking logic
    margin.py          # Margin utilisation & liquidation logic
docker-compose.yml
pyproject.toml
README.md