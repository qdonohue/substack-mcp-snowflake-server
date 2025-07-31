#!/usr/bin/env python3
"""Test script to verify MCP server is working correctly"""

import asyncio
import json
import logging
import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_snowflake_server.claude_code import (
    handle_analytics_codebase_query,
    handle_general_codebase_query,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_claude_code_tools(custom_query=None):
    """Test the Claude Code integration tools"""
    
    print("\n=== Testing Claude Code Tools ===\n")
    
    if custom_query:
        # Test with custom query
        print(f"Testing custom analytics query: {custom_query}")
        print("-" * 80)
        try:
            import time
            start_time = time.time()
            
            result = await handle_analytics_codebase_query({
                "query": custom_query
            })
            
            elapsed = time.time() - start_time
            print(f"\nQuery completed in {elapsed:.1f} seconds")
            print("Result:")
            print("-" * 80)
            print(result[0].text)
            print("-" * 80)
            print("✓ Custom query succeeded\n")
        except Exception as e:
            import traceback
            print(f"✗ Custom query failed: {e}")
            print("Full traceback:")
            traceback.print_exc()
            print("\n")
    else:
        # Test analytics query
        print("1. Testing analytics codebase query...")
        try:
            result = await handle_analytics_codebase_query({
                "query": "What tables contain user subscription data?"
            })
            print(f"Analytics query result: {result[0].text[:200]}...")
            print("✓ Analytics query succeeded\n")
        except Exception as e:
            print(f"✗ Analytics query failed: {e}\n")
        
        # Test general query
        print("2. Testing general codebase query...")
        try:
            result = await handle_general_codebase_query({
                "query": "How does the email notification system work?"
            })
            print(f"General query result: {result[0].text[:200]}...")
            print("✓ General query succeeded\n")
        except Exception as e:
            print(f"✗ General query failed: {e}\n")


async def test_snowflake_connection():
    """Test basic Snowflake connection"""
    from mcp_snowflake_server.db_client import SnowflakeDB
    
    print("\n=== Testing Snowflake Connection ===\n")
    
    # Get connection args from environment
    connection_args = {
        'user': os.getenv('SNOWFLAKE_USER', 'quinn.donohue@substackinc.com'),
        'database': os.getenv('SNOWFLAKE_DATABASE', 'RAW'),
        'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE', 'ADHOC'),
        'account': os.getenv('SNOWFLAKE_ACCOUNT', 'hla46235.us-east-1'),
        'schema': os.getenv('SNOWFLAKE_SCHEMA', 'ARTIE'),
        'role': os.getenv('SNOWFLAKE_ROLE', 'ANALYST'),
        'authenticator': 'externalbrowser'
    }
    
    print(f"Connection config: {json.dumps({k: v for k, v in connection_args.items() if k != 'password'}, indent=2)}")
    
    try:
        db = SnowflakeDB(connection_args)
        await db.connect()
        print("✓ Connected to Snowflake successfully\n")
        
        # Test a simple query
        print("Testing a simple query...")
        results, data_id = await db.execute_query("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE()")
        print(f"Query results: {results}")
        print("✓ Query executed successfully\n")
        
    except Exception as e:
        print(f"✗ Snowflake connection failed: {e}\n")


async def main():
    """Run all tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test MCP Snowflake Server')
    parser.add_argument('--query', '-q', type=str, help='Custom analytics query to test')
    parser.add_argument('--skip-snowflake', action='store_true', help='Skip Snowflake connection test')
    args = parser.parse_args()
    
    print("\n🧪 Starting MCP Snowflake Server Tests\n")
    
    # Test Snowflake connection first (unless skipped)
    if not args.skip_snowflake:
        await test_snowflake_connection()
    
    # Test Claude Code tools
    await test_claude_code_tools(custom_query=args.query)
    
    print("\n✅ Tests completed!\n")


if __name__ == "__main__":
    asyncio.run(main())