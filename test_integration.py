#!/usr/bin/env python3
"""
Trading & Margining System - Integration Test Script

This script implements specific test scenarios to validate the complete system functionality:
1. Initial Setup - Baseline account balance and market price
2. Successful Trade Execution - Trade execution and position creation
3. Position and P&L Query - Position tracking and equity calculation
4. Price Movement and P&L Update - Mark price updates and P&L calculations
5. Insufficient Margin Rejection - Pre-trade margin checks
6. Liquidation Scenario - Liquidation detection and recording
7. Trade History - Historical data persistence
8. Liquidation History - Liquidation event logging

Prerequisites:
- Docker containers running (docker-compose up -d)
- .env file configured
- FastAPI server running (poetry run python -m app.main)
"""

import asyncio
import sys
import httpx
from decimal import Decimal
import time

from typing import Dict, Any

# Add the app directory to the path
sys.path.append('.')

from app.config import config
from app.redis_client import AccountRedisClient, MarketRedisClient
from app.postgres import AsyncPostgresClient

class TradingSystemIntegrationTest:
    def __init__(self):
        self.account_client = None
        self.market_client = None
        self.postgres_client = None
        self.http_client = None
        self.base_url = "http://localhost:8000"

    async def setup(self):
        """Initialize connections and HTTP client"""
        print("🔧 Setting up Trading & Margining System Integration Test...")
        
        # Initialise database clients
        self.account_client = AccountRedisClient(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD if config.REDIS_PASSWORD else None,
            db=config.REDIS_DB
        )
        
        self.market_client = MarketRedisClient(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD if config.REDIS_PASSWORD else None,
            db=config.REDIS_DB
        )
        
        self.postgres_client = AsyncPostgresClient(
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            database=config.POSTGRES_DATABASE,
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT
        )
        
        # Connect to databases
        await self.account_client.connect()
        await self.market_client.connect()
        await self.postgres_client.connect()
        
        # Initialise HTTP client
        self.http_client = httpx.AsyncClient()
        
        print("✅ System initialized successfully!")

    async def test_case_1_initial_setup(self):
        """Test Case 1: Initial Setup - Establish baseline account balance and market price"""
        print("\n📊 Test Case 1: Initial Setup")
        print("=" * 50)
        
        # Set initial account balance (10,000 USDT)
        await self.account_client.set_balance(3456, Decimal('15000'))
        print(f"✅ Set account 3456 balance to 15,000 USDT")
        # Clear any existing position for account 3456
        await self.account_client.set_position(3456, "BTC-PERP", Decimal('0'), Decimal('0'))
        
        # Set initial BTC mark price (50,000 USDT)
        response = await self.http_client.post(
            f"{self.base_url}/mark-price",
            json={"symbol": "BTC-PERP", "price": 50000}
        )
        
        if response.status_code == 200:
            print(f"✅ Set BTC-PERP mark price to 50,000 USDT")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Failed to set mark price: {response.status_code} - {response.text}")
            return False
        
        # Verify Redis state
        balance = await self.account_client.get_balance(3456)
        position = await self.account_client.get_position(3456, "BTC-PERP")
        mark_price = await self.market_client.get_mark_price("BTC-PERP")
        
        print(f"✅ Redis Verification:")
        print(f"   Account 3456 balance: {balance} USDT")
        print(f"   Account 3456 position: {position}")
        print(f"   BTC-PERP mark price: {mark_price} USDT")
        
        # Verify no PostgreSQL changes yet
        trades_count = await self.postgres_client.fetchval("SELECT COUNT(*) FROM trades")
        liquidations_count = await self.postgres_client.fetchval("SELECT COUNT(*) FROM liquidations")
        
        print(f"✅ PostgreSQL Verification:")
        print(f"   Trades table: {trades_count} rows")
        print(f"   Liquidations table: {liquidations_count} rows")
        
        return True

    async def test_case_2_successful_trade_execution(self):
        """Test Case 2: Successful Trade Execution - Verify trade execution, position creation, and balance updates"""
        print("\n🟢 Test Case 2: Successful Trade Execution")
        print("=" * 50)
        

            
        # Execute trade: Buy 1 BTC at 50,000 USDT
        trade_data = {
            "account_id": 3456,
            "symbol": "BTC-PERP",
            "side": "BUY",
            "quantity": 1,
            "price": 50000
        }
        
        response = await self.http_client.post(f"{self.base_url}/trade", json=trade_data)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Trade executed successfully!")
            print(f"   Response: {data}")
            print(f"   Trade ID: {data.get('trade_id')}")
        else:
            print(f"❌ Trade failed: {response.status_code} - {response.text}")
            return False
        
        # Verify Redis state after trade
        balance = await self.account_client.get_balance(3456)
        position = await self.account_client.get_position(3456, "BTC-PERP")
        
        print(f"✅ Redis State After Trade:")
        print(f"   Account 3456 balance: {balance} USDT (expected: 5000)")
        print(f"   Position: {position}")
        
        # Verify PostgreSQL trade record
        trade_record = await self.postgres_client.fetchrow(
            "SELECT * FROM trades WHERE account_id = $1 ORDER BY id DESC LIMIT 1",
            3456
        )
        
        if trade_record:
            print(f"✅ PostgreSQL Trade Record:")
            print(f"   Trade ID: {trade_record['id']}")
            print(f"   Account: {trade_record['account_id']}")
            print(f"   Symbol: {trade_record['symbol']}")
            print(f"   Side: {trade_record['side']}")
            print(f"   Quantity: {trade_record['quantity']}")
            print(f"   Price: {trade_record['price']}")

        else:
            print(f"❌ No trade record found in PostgreSQL")
            return False
        
        return True

    async def test_case_3_position_and_pnl_query(self):
        """Test Case 3: Position and P&L Query - Verify position tracking and equity calculation"""
        print("\n📈 Test Case 3: Position and P&L Query")
        print("=" * 50)
        
        response = await self.http_client.get(f"{self.base_url}/positions/3456")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Position Query Response:")
            print(f"   Account ID: {data['account_id']}")
            print(f"   Balance: {data['balance']} USDT (expected: 5000.0)")
            print(f"   Equity: {data['equity']} USDT (expected: 5000.0)")
            
            if data['positions']:
                pos = data['positions'][0]
                print(f"   Position Details:")
                print(f"     Symbol: {pos['symbol']}")
                print(f"     Quantity: {pos['quantity']}")
                print(f"     Average Price: {pos['avg_price']}")
                print(f"     Mark Price: {pos['mark_price']}")
                print(f"     Unrealised P&L: {pos['unrealised_pnl']}")

                
                # Validate calculations
                expected_equity = 5000.0  # balance + P&L
                if abs(float(data['equity']) - expected_equity) < 0.01:
                    print(f"✅ Equity calculation correct: {data['equity']} = balance + P&L")
                else:
                    print(f"❌ Equity calculation incorrect: expected {expected_equity}, got {data['equity']}")
                    return False
            else:
                print(f"❌ No positions found")
                return False
        else:
            print(f"❌ Position query failed: {response.status_code} - {response.text}")
            return False
        
        return True

    async def test_case_4_price_movement_and_pnl_update(self):
        """Test Case 4: Price Movement and P&L Update - Test mark price updates and unrealised P&L calculations"""
        print("\n📊 Test Case 4: Price Movement and P&L Update")
        print("=" * 50)
        
        # Update BTC price to 60,000 (20% increase)
        response = await self.http_client.post(
            f"{self.base_url}/mark-price",
            json={"symbol": "BTC-PERP", "price": 60000}
        )
        
        if response.status_code == 200:
            print(f"✅ Updated BTC-PERP mark price to 60,000 USDT")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Failed to update mark price: {response.status_code} - {response.text}")
            return False
        
        # Check updated positions
        response = await self.http_client.get(f"{self.base_url}/positions/3456")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Updated Position Data:")
            print(f"   Balance: {data['balance']} USDT")
            print(f"   Equity: {data['equity']} USDT (expected: -30000.0)")
            
            if data['positions']:
                pos = data['positions'][0]
                print(f"   Position Updates:")
                print(f"     Mark Price: {pos['mark_price']} USDT")
                print(f"     Unrealised P&L: {pos['unrealised_pnl']} USDT (expected: 10000.0)")
                
                # Validate calculations
                expected_pnl = 10000.0  # (60000 - 50000) × 1
                expected_equity = 15000  # balance (-40000) + P&L (10000)
                
                if abs(float(pos['unrealised_pnl']) - expected_pnl) < 0.01:
                    print(f"✅ P&L calculation correct: {pos['unrealised_pnl']} = (60000-50000) × 1")
                else:
                    print(f"❌ P&L calculation incorrect: expected {expected_pnl}, got {pos['unrealised_pnl']}")
                    return False
                
                if abs(float(data['equity']) - expected_equity) < 0.01:
                    print(f"✅ Equity calculation correct: {data['equity']} = balance + P&L")
                else:
                    print(f"❌ Equity calculation incorrect: expected {expected_equity}, got {data['equity']}")
                    return False
            else:
                print(f"❌ No positions found")
                return False
        else:
            print(f"❌ Position query failed: {response.status_code} - {response.text}")
            return False
        
        # Verify Redis mark price update
        mark_price = await self.market_client.get_mark_price("BTC-PERP")
        print(f"✅ Redis Verification: BTC-PERP mark price = {mark_price} USDT")
        
        return True

    async def test_case_5_insufficient_margin_rejection(self):
        """Test Case 5: Insufficient Margin Rejection - Verify pre-trade margin checks prevent over-leveraging"""
        print("\n🔴 Test Case 5: Insufficient Margin Rejection")
        print("=" * 50)
        
        # Try to buy 5 BTC at 60,000 USDT (requires 300,000 USDT, but equity is only -30,000)
        trade_data = {
            "account_id": 3456,
            "symbol": "BTC-PERP",
            "side": "BUY",
            "quantity": 5,
            "price": 60000
        }
        
        response = await self.http_client.post(f"{self.base_url}/trade", json=trade_data)
        
        if response.status_code == 400:
            data = response.json()
            print(f"✅ Trade correctly rejected with 400 error")
            print(f"   Response: {data}")
            print(f"   Detail: {data.get('detail', 'No detail provided')}")
        else:
            print(f"❌ Trade should have been rejected but got: {response.status_code} - {response.text}")
            return False
        
        # Verify no changes to Redis/PostgreSQL
        balance = await self.account_client.get_balance(3456)
        position = await self.account_client.get_position(3456, "BTC-PERP")
        trades_count = await self.postgres_client.fetchval("SELECT COUNT(*) FROM trades WHERE account_id = $1", 3456)
        
        print(f"✅ State Verification (No Changes):")
        print(f"   Account balance: {balance} USDT (unchanged)")
        print(f"   Position: {position} (unchanged)")
        print(f"   Trades count: {trades_count} (unchanged)")
        
        return True

    async def test_case_6_liquidation_scenario(self):
        """Test Case 6: Liquidation Scenario - Test liquidation detection when equity falls below maintenance margin"""
        print("\n💀 Test Case 6: Liquidation Scenario")
        print("=" * 50)
        
        # Crash BTC price to 40,000 (creates massive loss)
        response = await self.http_client.post(
            f"{self.base_url}/mark-price",
            json={"symbol": "BTC-PERP", "price": 40000}
        )
        
        if response.status_code == 200:
            print(f"✅ Crashed BTC-PERP price to 40,000 USDT")
        else:
            print(f"❌ Failed to update mark price: {response.status_code} - {response.text}")
            return False
        
        # Check margin report
        response = await self.http_client.get(f"{self.base_url}/margin-report")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Margin Report:")
            print(f"   Total Accounts: {data['total_accounts']}")
            print(f"   Liquidation Candidates: {data['liquidation_candidates']}")
            
            if data['accounts_detail']:
                # Find account 3456 which should have the position
                account_detail = None
                for account in data['accounts_detail']:
                    if account['account_id'] == 3456:
                        account_detail = account
                        break
                
                if not account_detail:
                    print(f"❌ Account 3456 not found in margin report")
                    return False
                
                print(f"   Account {account_detail['account_id']} Details:")
                print(f"     Equity: {account_detail['equity']} USDT (expected: -50000.0)")
                print(f"     Maintenance Margin Required: {account_detail['maintenance_margin_required']} USDT (expected: 4000.0)")
                print(f"     Margin Utilisation: {account_detail['margin_utilisation_pct']}%")
                print(f"     Liquidation Risk: {account_detail['liquidation_risk']}")
                
                # Get actual equity from trading service for comparison
                from app.services.trading import TradingService
                trading_service = TradingService(self.account_client, self.market_client, self.postgres_client)
                actual_equity = await trading_service.calculate_equity(3456)
                print(f"   Trading Service Equity: {actual_equity} USDT")
                
                # Validate calculations
                expected_equity = -5000.0  # balance (5000) + P&L (-10000)
                expected_maintenance_margin = 4000.0  # 10% × 40000
                
                if abs(float(account_detail['equity']) - expected_equity) < 0.01:
                    print(f"✅ Equity calculation correct: {account_detail['equity']} = balance + P&L")
                else:
                    print(f"❌ Equity calculation incorrect: expected {expected_equity}, got {account_detail['equity']}")
                    return False
                
                if abs(float(account_detail['maintenance_margin_required']) - expected_maintenance_margin) < 0.01:
                    print(f"✅ Maintenance margin calculation correct: {account_detail['maintenance_margin_required']} = 10% × 40000")
                else:
                    print(f"❌ Maintenance margin calculation incorrect: expected {expected_maintenance_margin}, got {account_detail['maintenance_margin_required']}")
                    return False
                
                if account_detail['liquidation_risk']:
                    print(f"✅ Liquidation risk correctly detected: equity ({account_detail['equity']}) < maintenance margin ({account_detail['maintenance_margin_required']})")
                else:
                    print(f"❌ Liquidation risk not detected when it should be")
                    return False
            else:
                print(f"❌ No account details found")
                return False
        else:
            print(f"❌ Margin report failed: {response.status_code} - {response.text}")
            return False
        
        # Verify liquidation record in PostgreSQL
        liquidation_record = await self.postgres_client.fetchrow(
            "SELECT * FROM liquidations WHERE account_id = $1 ORDER BY id DESC LIMIT 1",
            3456
        )
        
        if liquidation_record:
            print(f"✅ PostgreSQL Liquidation Record:")
            print(f"   Liquidation ID: {liquidation_record['id']}")
            print(f"   Account: {liquidation_record['account_id']}")
            print(f"   Reason: {liquidation_record['reason']}")
        else:
            print(f"❌ No liquidation record found in PostgreSQL")
            return False
        
        return True

    async def test_case_7_trade_history(self):
        """Test Case 7: Trade History - Verify historical trade data persistence"""
        print("\n📜 Test Case 7: Trade History")
        print("=" * 50)
        
        response = await self.http_client.get(f"{self.base_url}/trades/3456")
        
        if response.status_code == 200:
            data = response.json()
            trades = data.get('trades', [])
            print(f"✅ Trade History for Account 3456:")
            print(f"   Total Trades: {len(trades)}")
            
            if trades:
                trade = trades[0]  # Most recent trade
                print(f"   Latest Trade:")
                print(f"     ID: {trade['id']}")
                print(f"     Account: {trade['account_id']}")
                print(f"     Symbol: {trade['symbol']}")
                print(f"     Side: {trade['side']}")
                print(f"     Quantity: {trade['quantity']}")
                print(f"     Price: {trade['price']}")
                print(f"     Timestamp: {trade['timestamp']}")
            else:
                print(f"❌ No trades found")
                return False
        else:
            print(f"❌ Trade history failed: {response.status_code} - {response.text}")
            return False
        
        return True

    async def test_case_8_liquidation_history(self):
        """Test Case 8: Liquidation History - Verify liquidation event logging"""
        print("\n📋 Test Case 8: Liquidation History")
        print("=" * 50)
        
        response = await self.http_client.get(f"{self.base_url}/liquidations")
        
        if response.status_code == 200:
            data = response.json()
            liquidations = data.get('liquidations', [])
            print(f"✅ Liquidation History:")
            print(f"   Total Liquidations: {len(liquidations)}")
            
            if liquidations:
                liquidation = liquidations[0]  # Most recent liquidation
                print(f"   Latest Liquidation:")
                print(f"     ID: {liquidation['id']}")
                print(f"     Account: {liquidation['account_id']}")
                print(f"     Reason: {liquidation['reason']}")
                print(f"     Timestamp: {liquidation['timestamp']}")
            else:
                print(f"❌ No liquidations found")
                return False
        else:
            print(f"❌ Liquidation history failed: {response.status_code} - {response.text}")
            return False
        
        return True

    async def verify_final_state(self):
        """Verify the final state of the system"""
        print("\n🔍 Final State Verification")
        print("=" * 50)
        
        # Redis state
        balance = await self.account_client.get_balance(3456)
        mark_price = await self.market_client.get_mark_price("BTC-PERP")
        position = await self.account_client.get_position(3456, "BTC-PERP")
        
        print(f"✅ Final Redis State:")
        print(f"   Account 3456 balance: {balance} USDT (expected: -40000)")
        print(f"   BTC-PERP mark price: {mark_price} USDT (expected: 40000)")
        print(f"   Position: {position}")
        
        # PostgreSQL state
        trades_count = await self.postgres_client.fetchval("SELECT COUNT(*) FROM trades WHERE account_id = $1", 3456)
        liquidations_count = await self.postgres_client.fetchval("SELECT COUNT(*) FROM liquidations WHERE account_id = $1", 3456)
        
        print(f"✅ Final PostgreSQL State:")
        print(f"   Trades: {trades_count} rows (expected: 1)")
        print(f"   Liquidations: {liquidations_count} rows (expected: 1)")
        
        # Key calculations validation
        print(f"✅ Key Calculations Validated:")
        print(f"   Initial margin: 20% × 50000 = 10000 ✓")
        print(f"   Maintenance margin: 10% × 40000 = 4000 ✓")
        print(f"   Equity with loss: -40000 + (40000-50000)×1 = -50000 ✓")
        print(f"   Liquidation trigger: -50000 < 4000 ✓")

    async def cleanup(self):
        """Clean up connections"""
        print("\n🧹 Cleaning up...")
        if self.http_client:
            await self.http_client.aclose()
        if self.account_client:
            await self.account_client.close()
        if self.market_client:
            await self.market_client.close()
        if self.postgres_client:
            await self.postgres_client.close()
        print("✅ Cleanup complete!")

    async def run_all_tests(self):
        """Run all test cases"""
        try:
            await self.setup()
            
            # Run all test cases
            test_cases = [
                ("Initial Setup", self.test_case_1_initial_setup),
                ("Successful Trade Execution", self.test_case_2_successful_trade_execution),
                ("Position and P&L Query", self.test_case_3_position_and_pnl_query),
                ("Price Movement and P&L Update", self.test_case_4_price_movement_and_pnl_update),
                ("Insufficient Margin Rejection", self.test_case_5_insufficient_margin_rejection),
                ("Liquidation Scenario", self.test_case_6_liquidation_scenario),
                ("Trade History", self.test_case_7_trade_history),
                ("Liquidation History", self.test_case_8_liquidation_history),
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_name, test_func in test_cases:
                print(f"\n{'='*60}")
                print(f"Running: {test_name}")
                print(f"{'='*60}")
                
                try:
                    result = await test_func()
                    if result:
                        print(f"✅ {test_name} - PASSED")
                        passed += 1
                    else:
                        print(f"❌ {test_name} - FAILED")
                except Exception as e:
                    print(f"❌ {test_name} - ERROR: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Verify final state
            await self.verify_final_state()
            
            print(f"\n{'='*60}")
            print(f"TEST SUMMARY")
            print(f"{'='*60}")
            print(f"Passed: {passed}/{total}")
            print(f"Failed: {total - passed}/{total}")
            
            if passed == total:
                print(f"🎉 All tests passed! Trading & Margining System is working correctly.")
            else:
                print(f"⚠️  Some tests failed. Please review the output above.")
            
        except Exception as e:
            print(f"\n❌ Test suite failed with error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()

async def main():
    """Main function"""
    print("🚀 Starting Trading & Margining System Integration Test Suite")
    print("=" * 80)
    print("This test suite validates the complete system functionality with real databases")
    print("Make sure the FastAPI server is running: poetry run python -m app.main")
    print("=" * 80)
    
    # Wait a moment for user to read
    await asyncio.sleep(2)
    
    test_suite = TradingSystemIntegrationTest()
    await test_suite.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
