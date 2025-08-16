-- Initialises the database for the trading system
-- Postgres is used for history and reporting, immutable data
-- File executed by docker-compose.yaml

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    notional DECIMAL(20, 8) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS liquidations (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    equity DECIMAL(20, 8) NOT NULL,
    maintenance_margin DECIMAL(20, 8) NOT NULL,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_account_id ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_liquidations_account_id ON liquidations(account_id);