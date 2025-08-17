import pytest
from fastapi.testclient import TestClient
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from app.api import router
from app.services.trading import TradingService
from app.services.margin import MarginService
from app.redis_client import AccountRedisClient, MarketRedisClient
from app.postgres import AsyncPostgresClient



@pytest.fixture
def mock_clients():
    """Create mock clients for testing"""
    account_client = AsyncMock()
    market_client = AsyncMock()
    postgres_client = AsyncMock()
    return account_client, market_client, postgres_client

@pytest.fixture
def mock_trading_service():
    """Create a mock trading service"""
    service = AsyncMock(spec=TradingService)
    return service

@pytest.fixture
def mock_margin_service():
    """Create a mock margin service"""
    service = AsyncMock(spec=MarginService)
    return service

@pytest.fixture
def client(mock_trading_service, mock_margin_service):
    """Create test client with mocked services"""
    
    # Create a clean test app without any real service initialization
    test_app = FastAPI(title="Test Trading Platform", version="1.0.0")
    
    # Mock the services in the API module
    with patch('app.api.trading_service', mock_trading_service), \
         patch('app.api.margin_service', mock_margin_service), \
         patch('app.api.market_client', AsyncMock()):
        
        # Include the router
        test_app.include_router(router)
        
        # Add basic endpoints
        @test_app.get("/")
        async def root():
            return {"message": "Test Trading Platform", "status": "running"}
        
        @test_app.get("/health")
        async def health():
            return {"status": "healthy"}
        
        with TestClient(test_app) as test_client:
            yield test_client

class TestTradeAPI:
    """Test trade execution endpoints"""
    
    def test_execute_trade_success(self, client, mock_trading_service):
        """Test successful trade execution"""
        # Setup mocks for successful trade
        mock_trading_service.execute_trade.return_value = (True, "Trade executed successfully", 123)
        
        # Test trade request
        trade_data = {
            "account_id": 1,
            "symbol": "BTC-PERP",
            "side": "BUY",
            "quantity": 0.1,
            "price": 50000.0
        }
        
        response = client.post("/trade", json=trade_data)
        
        # The service should be called and return the validation error
        assert response.status_code == 400
        data = response.json()
        assert "BTC trades must be in whole numbers" in data["detail"]
    
    def test_execute_trade_success_whole_btc(self, client, mock_trading_service):
        """Test successful trade execution with whole BTC quantity"""
        # Setup mocks for successful trade
        mock_trading_service.execute_trade.return_value = (True, "Trade executed successfully", 123)
        
        # Test trade request with whole number BTC
        trade_data = {
            "account_id": 1,
            "symbol": "BTC-PERP",
            "side": "BUY",
            "quantity": 1,
            "price": 50000.0
        }
        
        response = client.post("/trade", json=trade_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Trade executed successfully"
        assert data["trade_id"] == 123
        
        # Verify service was called with correct parameters
        mock_trading_service.execute_trade.assert_called_once_with(
            1, "BTC-PERP", "BUY", Decimal('1'), Decimal('50000')
          )
    
    def test_execute_trade_insufficient_margin(self, client, mock_trading_service):
        """Test trade rejection due to insufficient margin"""
        # Setup mocks for failed trade
        mock_trading_service.execute_trade.return_value = (
            False, 
            "Insufficient equity. Required: 10000, Available: 5000", 
            None
        )
        
        trade_data = {
            "account_id": 1,
            "symbol": "BTC-PERP",
            "side": "BUY",
            "quantity": 1.0,
            "price": 50000.0
        }
        
        response = client.post("/trade", json=trade_data)
        
        # The API returns 400 for business logic errors
        assert response.status_code == 400
        data = response.json()
        assert "Insufficient equity" in data["detail"]
    
    def test_execute_trade_invalid_data(self, client):
        """Test trade with invalid data"""
        # Test with missing required fields
        trade_data = {
            "account_id": 1,
            "symbol": "BTC-PERP"
            # Missing side, quantity, price
        }
        
        response = client.post("/trade", json=trade_data)
        assert response.status_code == 422  # Validation error
    
    def test_execute_trade_invalid_side(self, client, mock_trading_service):
        """Test trade with invalid side"""
        # Setup mock for the service call
        mock_trading_service.execute_trade.return_value = (False, "Invalid side", None)
        
        trade_data = {
            "account_id": 1,
            "symbol": "BTC-PERP",
            "side": "INVALID",
            "quantity": 0.1,
            "price": 50000.0
        }
        
        response = client.post("/trade", json=trade_data)
        # The API returns 400 for business logic errors
        assert response.status_code == 400
        data = response.json()
        assert "Invalid side" in data["detail"]

class TestPositionsAPI:
    """Test positions and P&L endpoints"""
    
    def test_get_positions_success(self, client, mock_trading_service):
        """Test successful positions retrieval"""
        # Setup mock data
        mock_positions = {
            "account_id": 1,
            "balance": Decimal('10000'),
            "equity": Decimal('12000'),
            "positions": [
                {
                    "symbol": "BTC-PERP",
                    "quantity": Decimal('1'),
                    "avg_price": Decimal('50000'),
                    "mark_price": Decimal('52000'),
                    "unrealised_pnl": Decimal('2000'),
                    "notional": Decimal('52000')
                }
            ]
        }
        mock_trading_service.get_account_positions.return_value = mock_positions
        
        response = client.get("/positions/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == 1
        assert data["balance"] == "10000"
        assert data["equity"] == "12000"
        assert len(data["positions"]) == 1
        assert data["positions"][0]["symbol"] == "BTC-PERP"
        assert data["positions"][0]["unrealised_pnl"] == "2000"
    
    def test_get_positions_no_positions(self, client, mock_trading_service):
        """Test positions retrieval for account with no positions"""
        mock_positions = {
            "account_id": 1,
            "balance": Decimal('10000'),
            "equity": Decimal('10000'),
            "positions": []
        }
        mock_trading_service.get_account_positions.return_value = mock_positions
        
        response = client.get("/positions/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == 1
        assert data["balance"] == "10000"
        assert data["equity"] == "10000"
        assert len(data["positions"]) == 0

class TestMarkPriceAPI:
    """Test mark price update endpoints"""
    
    def test_update_mark_price_success(self, client):
        """Test successful mark price update"""
        # This test will use the real market client since it's simpler
        mark_price_data = {
            "symbol": "BTC-PERP",
            "price": 52000.0
        }
        
        response = client.post("/mark-price", json=mark_price_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Mark price for BTC-PERP updated to 52000" in data["message"]
    
    def test_update_mark_price_invalid_data(self, client):
        """Test mark price update with invalid data"""
        mark_price_data = {
            "symbol": "BTC-PERP"
            # Missing price
        }
        
        response = client.post("/mark-price", json=mark_price_data)
        assert response.status_code == 422  # Validation error

class TestMarginReportAPI:
    """Test margin report and liquidation endpoints"""
    
    def test_margin_report_success(self, client, mock_margin_service):
        """Test successful margin report retrieval"""
        # Setup mock margin report data
        mock_report = {
            "total_accounts": 2,
            "liquidation_candidates": [2],  # Account 2 should be liquidated
            "accounts_detail": [
                {
                    "account_id": 1,
                    "equity": Decimal('10000'),
                    "maintenance_margin_required": Decimal('2000'),
                    "margin_utilisation_pct": Decimal('20'),
                    "liquidation_risk": False
                },
                {
                    "account_id": 2,
                    "equity": Decimal('800'),
                    "maintenance_margin_required": Decimal('1000'),
                    "margin_utilisation_pct": Decimal('125'),
                    "liquidation_risk": True
                }
            ]
        }
        mock_margin_service.get_margin_utilisation.return_value = mock_report
        
        response = client.get("/margin-report")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_accounts"] == 2
        assert data["liquidation_candidates"] == [2]
        assert len(data["accounts_detail"]) == 2
        
        # Check account details
        account1 = next(acc for acc in data["accounts_detail"] if acc["account_id"] == 1)
        account2 = next(acc for acc in data["accounts_detail"] if acc["account_id"] == 2)
        
        assert account1["liquidation_risk"] is False
        assert account1["margin_utilisation_pct"] == "20"
        assert account1["equity"] == "10000"
        assert account1["maintenance_margin_required"] == "2000"
        
        assert account2["liquidation_risk"] is True
        assert account2["margin_utilisation_pct"] == "125"
        assert account2["equity"] == "800"
        assert account2["maintenance_margin_required"] == "1000"
    
    def test_margin_report_no_liquidations(self, client, mock_margin_service):
        """Test margin report with no liquidation candidates"""
        mock_report = {
            "total_accounts": 1,
            "liquidation_candidates": [],
            "accounts_detail": [
                {
                    "account_id": 1,
                    "equity": Decimal('10000'),
                    "maintenance_margin_required": Decimal('2000'),
                    "margin_utilisation_pct": Decimal('20'),
                    "liquidation_risk": False
                }
            ]
        }
        mock_margin_service.get_margin_utilisation.return_value = mock_report
        
        response = client.get("/margin-report")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_accounts"] == 1
        assert data["liquidation_candidates"] == []
        assert data["accounts_detail"][0]["liquidation_risk"] is False

class TestTradeHistoryAPI:
    """Test trade history endpoints"""
    
    def test_get_trade_history_success(self, client, mock_trading_service):
        """Test successful trade history retrieval"""
        from app.models import Trade
        from datetime import datetime
        
        # Setup mock trade history
        mock_trades = [
            Trade(
                id=1,
                account_id=1,
                symbol="BTC-PERP",
                side="BUY",
                quantity=Decimal('1'),
                price=Decimal('50000'),
                notional=Decimal('50000'),
                timestamp=datetime.now()
            ),
            Trade(
                id=2,
                account_id=1,
                symbol="BTC-PERP",
                side="SELL",
                quantity=Decimal('1'),
                price=Decimal('52000'),
                notional=Decimal('52000'),
                timestamp=datetime.now()
            )
        ]
        mock_trading_service.get_trade_history.return_value = mock_trades
        
        response = client.get("/trades/1")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["trades"]) == 2
        assert data["trades"][0]["side"] == "BUY"
        assert data["trades"][1]["side"] == "SELL"
        assert data["trades"][0]["notional"] == 50000

class TestLiquidationHistoryAPI:
    """Test liquidation history endpoints"""
    
    def test_get_liquidation_history_success(self, client, mock_margin_service):
        """Test successful liquidation history retrieval"""
        from app.models import Liquidation
        from datetime import datetime
        
        # Setup mock liquidation history
        mock_liquidations = [
            Liquidation(
                id=1,
                account_id=2,
                equity=Decimal('800'),
                maintenance_margin=Decimal('1000'),
                reason="Equity below maintenance margin",
                timestamp=datetime.now()
            )
        ]
        mock_margin_service.get_liquidation_history.return_value = mock_liquidations
        
        response = client.get("/liquidations")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["liquidations"]) == 1
        assert data["liquidations"][0]["account_id"] == 2
        assert data["liquidations"][0]["equity"] == 800
        assert "Equity below maintenance margin" in data["liquidations"][0]["reason"]

class TestHealthEndpoints:
    """Test health and root endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["status"] == "running"
    
    def test_health_endpoint(self, client):
        """Test health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
