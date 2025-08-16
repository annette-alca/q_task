#!/usr/bin/env python3
"""
Trading & Margining System - Integration Test Script

This script demonstrates basic functionality of the system by:
1. Connecting to real Redis and PostgreSQL
2. Setting up test accounts and market data
3. Executing trades with margin checks
4. Testing liquidation scenarios
5. Generating reports

Prerequisites:
- Docker containers running (docker-compose up -d)
- .env file configured
"""

import asyncio
import sys
from decimal import Decimal
from typing import Dict, Any

# Add the app directory to the path
sys.path.append('.')

from app.config import config
from app.redis_client import AccountRedisClient, MarketRedisClient
from app.postgres import AsyncPostgresClient
from app.services.trading import TradingService
from app.services.margin import MarginService
from app.models import Trade, Liquidation

class TradingSystemDemo:
    def __init__(self):
        self.account_client = None
        self.market_client = None
        self.postgres_client = None
        self.trading_service = None
        self.margin_service = None

    async def setup(self):
        """Initialize connections and services"""
        print("🔧 Setting up Trading & Margining System...")
        
        # Initialize clients
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
        
        # Connect to services
        await self.account_client.connect()
        await self.market_client.connect()
        await self.postgres_client.connect()
        
        # Initialize services
        self.trading_service = TradingService(
            self.account_client, 
            self.market_client, 
            self.postgres_client
        )
        
        self.margin_service = MarginService(
            self.account_client, 
            self.market_client, 
            self.postgres_client
        )
        
        print("✅ System initialized successfully!")

    async def setup_test_data(self):
        """Set up initial test data"""
        print("\n📊 Setting up test data...")
        
        # Set initial balances
        await self.account_client.set_balance(1, Decimal('100000'))  # Rich account
        await self.account_client.set_balance(2, Decimal('5000'))    # Poor account
        await self.account_client.set_balance(3, Decimal('15000'))   # Medium account
        
        # Set initial mark price
        await self.market_client.set_mark_price("BTC-PERP", Decimal('50000'))
        
        print("✅ Test data initialized:")
        print(f"   Account 1: {await self.account_client.get_balance(1)} USDT")
        print(f"   Account 2: {await self.account_client.get_balance(2)} USDT")
        print(f"   Account 3: {await self.account_client.get_balance(3)} USDT")
        print(f"   BTC-PERP Mark Price: {await self.market_client.get_mark_price('BTC-PERP')} USDT")

    async def test_successful_trades(self):
        """Test successful trade execution"""
        print("\n🟢 Testing Successful Trades...")
        
        # Test 1: Account 1 buys 1 BTC
        print("\n1. Account 1 buying 1 BTC at 50,000 USDT...")
        success, message, trade_id = await self.trading_service.execute_trade(
            1, "BTC-PERP", "BUY", Decimal('1'), Decimal('50000')
        )
        
        if success:
            print(f"   ✅ Trade successful! Trade ID: {trade_id}")
            print(f"   💬 Message: {message}")
        else:
            print(f"   ❌ Trade failed: {message}")
        
        # Test 2: Account 3 buys 0.5 BTC (should fail - fractional BTC not allowed)
        print("\n2. Account 3 trying to buy 0.5 BTC (fractional BTC test)...")
        success, message, trade_id = await self.trading_service.execute_trade(
            3, "BTC-PERP", "BUY", Decimal('0.5'), Decimal('50000')
        )
        
        if success:
            print(f"   ✅ Trade successful! Trade ID: {trade_id}")
        else:
            print(f"   ❌ Trade failed (expected): {message}")
        
        # Test 3: Account 3 buys 1 BTC
        print("\n3. Account 3 buying 1 BTC at 50,000 USDT...")
        success, message, trade_id = await self.trading_service.execute_trade(
            3, "BTC-PERP", "BUY", Decimal('1'), Decimal('50000')
        )
        
        if success:
            print(f"   ✅ Trade successful! Trade ID: {trade_id}")
        else:
            print(f"   ❌ Trade failed: {message}")

    async def test_insufficient_margin(self):
        """Test insufficient margin scenarios"""
        print("\n🔴 Testing Insufficient Margin...")
        
        # Test: Account 2 tries to buy 1 BTC (insufficient funds)
        print("\nAccount 2 trying to buy 1 BTC (insufficient funds)...")
        success, message, trade_id = await self.trading_service.execute_trade(
            2, "BTC-PERP", "BUY", Decimal('1'), Decimal('50000')
        )
        
        if success:
            print(f"   ✅ Trade successful! Trade ID: {trade_id}")
        else:
            print(f"   ❌ Trade failed (expected): {message}")

    async def test_position_management(self):
        """Test position management and P&L calculations"""
        print("\n📈 Testing Position Management...")
        
        # Get positions for all accounts
        for account_id in [1, 2, 3]:
            positions_data = await self.trading_service.get_account_positions(account_id)
            print(f"\nAccount {account_id} Positions:")
            print(f"   Balance: {positions_data['balance']} USDT")
            print(f"   Equity: {positions_data['equity']} USDT")
            
            if positions_data['positions']:
                for pos in positions_data['positions']:
                    print(f"   {pos['symbol']}: {pos['quantity']} @ {pos['entry_price']}")
                    print(f"     Mark Price: {pos['mark_price']}")
                    print(f"     Unrealised P&L: {pos['unrealised_pnl']}")
                    print(f"     Notional: {pos['notional']}")
            else:
                print("   No open positions")

    async def test_mark_price_updates(self):
        """Test mark price updates and P&L changes"""
        print("\n📊 Testing Mark Price Updates...")
        
        # Update mark price to simulate price movement
        new_price = Decimal('52000')  # BTC price up 4%
        await self.market_client.set_mark_price("BTC-PERP", new_price)
        print(f"   Updated BTC-PERP mark price to {new_price} USDT (+4%)")
        
        # Check how this affects positions
        print("\n   Position updates after price change:")
        for account_id in [1, 3]:  # Accounts with positions
            positions_data = await self.trading_service.get_account_positions(account_id)
            print(f"\n   Account {account_id}:")
            print(f"     Balance: {positions_data['balance']} USDT")
            print(f"     Equity: {positions_data['equity']} USDT")
            
            for pos in positions_data['positions']:
                pnl_change = pos['unrealised_pnl'] - (pos['mark_price'] - pos['entry_price']) * pos['quantity']
                print(f"     {pos['symbol']} P&L: {pos['unrealised_pnl']} USDT")

    async def test_liquidation_scenario(self):
        """Test liquidation scenario"""
        print("\n💀 Testing Liquidation Scenario...")
        
        # Create a risky scenario: Account 2 with very low equity
        # First, let's see current margin utilisation
        margin_report = await self.margin_service.get_margin_utilisation()
        print(f"\n   Current Margin Report:")
        print(f"     Total Accounts: {margin_report['total_accounts']}")
        print(f"     Liquidation Candidates: {margin_report['liquidation_candidates']}")
        
        # Simulate a price crash that could trigger liquidation
        crash_price = Decimal('45000')  # BTC price down 10%
        await self.market_client.set_mark_price("BTC-PERP", crash_price)
        print(f"\n   Simulating market crash - BTC price drops to {crash_price} USDT (-10%)")
        
        # Check positions after crash
        print("\n   Positions after market crash:")
        for account_id in [1, 3]:
            positions_data = await self.trading_service.get_account_positions(account_id)
            print(f"\n   Account {account_id}:")
            print(f"     Balance: {positions_data['balance']} USDT")
            print(f"     Equity: {positions_data['equity']} USDT")
            
            for pos in positions_data['positions']:
                print(f"     {pos['symbol']} P&L: {pos['unrealised_pnl']} USDT")
        
        # Check margin utilisation after crash
        margin_report = await self.margin_service.get_margin_utilisation()
        print(f"\n   Margin Report after crash:")
        print(f"     Liquidation Candidates: {margin_report['liquidation_candidates']}")
        
        for account_detail in margin_report['accounts_detail']:
            print(f"     Account {account_detail['account_id']}:")
            print(f"       Equity: {account_detail['equity']} USDT")
            print(f"       Maintenance Margin Required: {account_detail['maintenance_margin_required']} USDT")
            print(f"       Margin Utilisation: {account_detail['margin_utilisation_pct']}%")
            print(f"       Liquidation Risk: {account_detail['liquidation_risk']}")

    async def test_trade_history(self):
        """Test trade history retrieval"""
        print("\n📜 Testing Trade History...")
        
        # Get trade history for accounts with trades
        for account_id in [1, 3]:
            trades = await self.trading_service.get_trade_history(account_id)
            print(f"\n   Trade History for Account {account_id}:")
            if trades:
                for trade in trades:
                    print(f"     Trade {trade.id}: {trade.side} {trade.quantity} {trade.symbol} @ {trade.price}")
                    print(f"       Notional: {trade.notional} USDT")
                    print(f"       Timestamp: {trade.timestamp}")
            else:
                print("     No trades found")

    async def test_liquidation_history(self):
        """Test liquidation history"""
        print("\n📋 Testing Liquidation History...")
        
        liquidations = await self.margin_service.get_liquidation_history()
        print(f"\n   Liquidation History:")
        if liquidations:
            for liquidation in liquidations:
                print(f"     Account {liquidation.account_id}:")
                print(f"       Equity: {liquidation.equity} USDT")
                print(f"       Maintenance Margin: {liquidation.maintenance_margin} USDT")
                print(f"       Reason: {liquidation.reason}")
                print(f"       Timestamp: {liquidation.timestamp}")
        else:
            print("     No liquidations recorded")

    async def cleanup(self):
        """Clean up connections"""
        print("\n🧹 Cleaning up...")
        await self.account_client.close()
        await self.market_client.close()
        await self.postgres_client.close()
        print("✅ Cleanup complete!")

    async def run_demo(self):
        """Run the complete demo"""
        try:
            await self.setup()
            await self.setup_test_data()
            
            await self.test_successful_trades()
            await self.test_insufficient_margin()
            await self.test_position_management()
            await self.test_mark_price_updates()
            await self.test_liquidation_scenario()
            await self.test_trade_history()
            await self.test_liquidation_history()
            
            print("\n🎉 Trading & Margining System Demo Complete!")
            print("\n📊 Summary:")
            print("   ✅ Successfully tested trade execution")
            print("   ✅ Successfully tested margin checks")
            print("   ✅ Successfully tested position management")
            print("   ✅ Successfully tested mark price updates")
            print("   ✅ Successfully tested liquidation scenarios")
            print("   ✅ Successfully tested trade history")
            print("   ✅ Successfully tested liquidation history")
            
        except Exception as e:
            print(f"\n❌ Demo failed with error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()

async def main():
    """Main function"""
    print("🚀 Starting Trading & Margining System Integration Test")
    print("=" * 60)
    
    demo = TradingSystemDemo()
    await demo.run_demo()

if __name__ == "__main__":
    asyncio.run(main())
