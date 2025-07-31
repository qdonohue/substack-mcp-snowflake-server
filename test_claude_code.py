#!/usr/bin/env python3
"""
Test the Claude Code integration tools
Run with: python test_claude_code.py
"""
import asyncio
import sys
import os

# Add the src directory to Python path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_snowflake_server.claude_code import (
    handle_analytics_codebase_query,
    handle_general_codebase_query
)

async def test_tools():
    print("🚀 Testing Claude Code Integration Tools\n")
    
    while True:
        print("Available tools:")
        print("1. Analytics Query (database schemas, tables, events)")
        print("2. General Codebase Query (development questions)")
        print("3. Exit")
        
        choice = input("\nSelect a tool (1-3): ").strip()
        
        if choice == "3":
            print("👋 Goodbye!")
            break
        elif choice not in ["1", "2"]:
            print("❌ Invalid choice. Please select 1, 2, or 3.")
            continue
            
        query = input("\nEnter your query: ").strip()
        if not query:
            print("❌ Query cannot be empty.")
            continue
            
        print(f"\n🔄 Processing your query...")
        print("=" * 50)
        
        from mcp_snowflake_server.claude_code import ANALYTICS_SYSTEM_PROMPT, GENERAL_SYSTEM_PROMPT, SUBSTACK_CODEBASE_PATH
        import shlex
        
        try:
            if choice == "1":
                print("📊 Analytics Mode Command\n")
                full_prompt = f"{ANALYTICS_SYSTEM_PROMPT}\n\nUser Query: {query}"
                system_name = "ANALYTICS"
            else:  # choice == "2"
                print("🔧 General Codebase Mode Command\n")
                full_prompt = f"{GENERAL_SYSTEM_PROMPT}\n\nUser Query: {query}"
                system_name = "GENERAL"
            
            # Show the command that would be run
            print(f"Working Directory: {SUBSTACK_CODEBASE_PATH}")
            print(f"Command to run:")
            print("-" * 50)
            
            # Use shlex.quote to properly escape the prompt
            escaped_prompt = shlex.quote(full_prompt)
            command = f"cd {shlex.quote(SUBSTACK_CODEBASE_PATH)} && claude --print --output-format json {escaped_prompt}"
            
            print(command)
            print("-" * 50)
            
            print(f"\n📝 {system_name} System Prompt Preview:")
            print("-" * 30)
            if choice == "1":
                print(ANALYTICS_SYSTEM_PROMPT[:200] + "...")
            else:
                print(GENERAL_SYSTEM_PROMPT[:200] + "...")
            print("-" * 30)
            
            print(f"\n💬 Your Query: {query}")
            print("\n✨ You can copy and run the command above to test manually!")
                
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        print("\n" + "=" * 50)
        
        # Ask if they want to continue
        continue_choice = input("Would you like to ask another question? (y/n): ").strip().lower()
        if continue_choice not in ['y', 'yes']:
            print("👋 Goodbye!")
            break
        print()

if __name__ == "__main__":
    asyncio.run(test_tools())