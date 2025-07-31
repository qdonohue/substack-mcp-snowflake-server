#!/usr/bin/env python3
"""
Demo Response Generator for Claude Code Analytics
This script generates exact CLI commands and provides fuzzy matching for cached responses.
Run with: python demo_response_generator.py
"""
import json
import re
import shlex
import sys
import os
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import List, Dict, Optional

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_snowflake_server.claude_code import (
    ANALYTICS_SYSTEM_PROMPT,
    GENERAL_SYSTEM_PROMPT,
    ANALYTICS_SPECIFICS_SYSTEM_PROMPT,
    SUBSTACK_CODEBASE_PATH,
    CLAUDE_COMMAND
)

@dataclass
class CachedResponse:
    keywords: List[str]
    query_pattern: str
    response: str
    command_type: str  # 'analytics', 'general', 'specifics'

# Pre-seeded responses for demo
CACHED_RESPONSES = [
    CachedResponse(
        keywords=["live video", "livestream", "streaming", "video stream"],
        query_pattern="live video|livestream|streaming",
        response="""Based on the Substack codebase analysis, here are the relevant tables and events for live video tracking:

**Tables:**
- `raw.events_frontend.video_stream_started` - When users start a live video stream
- `raw.events_frontend.video_stream_ended` - When users end a live video stream  
- `raw.events_frontend.video_viewer_joined` - When viewers join a live stream
- `raw.events_frontend.video_viewer_left` - When viewers leave a live stream
- `raw.artie.live_videos` - Main table storing live video metadata

**Key Columns:**
- `stream_id`: Unique identifier for each live stream
- `publication_id`: Which publication is hosting the stream
- `viewer_count`: Number of concurrent viewers
- `duration_seconds`: Length of the stream
- `quality_setting`: Video quality (720p, 1080p, etc.)

**Usage Example:**
```sql
SELECT 
    stream_id,
    publication_id,
    viewer_count,
    duration_seconds
FROM raw.artie.live_videos 
WHERE created_at >= '2024-01-01'
```""",
        command_type="analytics"
    ),
    CachedResponse(
        keywords=["subscriber", "subscription", "paid", "payment"],
        query_pattern="subscriber|subscription|paid|payment",
        response="""Subscription-related tables and events:

**Main Tables:**
- `raw.artie.subscriptions` - Core subscription data
- `raw.artie.subscription_payments` - Payment transactions
- `raw.events_srv.subscription_created` - New subscription events
- `raw.events_srv.subscription_cancelled` - Cancellation events

**Key Events:**
- `subscription_upgrade` - User upgrades their subscription tier
- `payment_failed` - Payment processing failures
- `trial_started` - Free trial initiations
- `trial_converted` - Trial to paid conversions

**Key Columns:**
- `subscription_tier`: free, paid, founding
- `billing_cycle`: monthly, yearly, lifetime
- `mrr_cents`: Monthly recurring revenue in cents
- `churn_date`: When subscription was cancelled""",
        command_type="analytics"
    ),
    CachedResponse(
        keywords=["email", "notification", "send", "newsletter"],
        query_pattern="email|notification|send|newsletter",
        response="""Email and notification system details:

**Key Files:**
- `@apps/substack/lib/email-service.ts` - Main email sending logic
- `@apps/substack/models/email_templates.ts` - Email template definitions
- `@apps/substack/jobs/send-newsletter.ts` - Newsletter sending job

**Email Triggers:**
1. **Newsletter Publishing**: Triggered in `publication.publish()` method
2. **Comment Notifications**: Handled by `comment-notifications.ts`
3. **Subscription Updates**: Processed in `subscription-lifecycle.ts`
4. **Welcome Emails**: Sent via `onboarding-flow.ts`

**Configuration:**
- Email providers configured in `email-config.ts`
- Templates stored in `raw.artie.email_templates`
- Send logs in `raw.events_srv.email_sent`""",
        command_type="general"
    )
]

def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two text strings"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def find_matching_response(query: str) -> Optional[CachedResponse]:
    """Find the best matching cached response using fuzzy matching"""
    query_lower = query.lower()
    best_match = None
    best_score = 0.0
    
    for cached in CACHED_RESPONSES:
        # Check keyword matches
        keyword_score = 0
        for keyword in cached.keywords:
            if keyword in query_lower:
                keyword_score += 1
        
        # Check pattern match
        pattern_match = bool(re.search(cached.query_pattern, query_lower, re.IGNORECASE))
        
        # Calculate overall score
        score = (keyword_score / len(cached.keywords)) * 0.7
        if pattern_match:
            score += 0.3
            
        # Also check direct similarity
        similarity = calculate_similarity(query, ' '.join(cached.keywords))
        score += similarity * 0.2
        
        if score > best_score and score > 0.3:  # Minimum threshold
            best_score = score
            best_match = cached
    
    return best_match

def generate_command(query: str, mode: str = "analytics") -> str:
    """Generate the exact Claude Code CLI command"""
    if mode == "analytics":
        system_prompt = ANALYTICS_SYSTEM_PROMPT
    elif mode == "specifics":
        system_prompt = ANALYTICS_SPECIFICS_SYSTEM_PROMPT
    else:  # general
        system_prompt = GENERAL_SYSTEM_PROMPT
    
    full_prompt = f"""{system_prompt}

User Query: {query}

When you have your final answer, output it between these markers:
===FINAL_ANSWER===
[your answer here]
===END_ANSWER==="""
    
    # Use shlex.quote to properly escape the prompt
    escaped_prompt = shlex.quote(full_prompt)
    command = f"cd {shlex.quote(SUBSTACK_CODEBASE_PATH)} && claude --print --output-format json {escaped_prompt}"
    
    return command

def main():
    print("🚀 Demo Response Generator for Claude Code Analytics\n")
    
    while True:
        print("Available modes:")
        print("1. Analytics Query (database schemas, tables, events)")
        print("2. General Codebase Query (development questions)")
        print("3. Analytics Specifics Query (detailed table/event info)")
        print("4. Generate commands for multiple test queries")
        print("5. Exit")
        
        choice = input("\nSelect a mode (1-5): ").strip()
        
        if choice == "5":
            print("👋 Goodbye!")
            break
        elif choice == "4":
            # Generate commands for multiple test queries
            test_queries = [
                ("What tables track live video streaming?", "analytics"),
                ("How do we send newsletter emails?", "general"),
                ("Show me subscription payment events", "analytics"),
                ("What triggers comment notifications?", "general"),
                ("Details about video_stream_started event", "specifics")
            ]
            
            print("\n📝 Generated Commands for Test Queries:")
            print("=" * 80)
            
            for i, (query, mode) in enumerate(test_queries, 1):
                print(f"\n{i}. Query: {query}")
                print(f"   Mode: {mode}")
                command = generate_command(query, mode)
                print(f"   Command:\n   {command}")
                print("-" * 60)
            
            continue
            
        elif choice not in ["1", "2", "3"]:
            print("❌ Invalid choice. Please select 1-5.")
            continue
            
        query = input("\nEnter your query: ").strip()
        if not query:
            print("❌ Query cannot be empty.")
            continue
            
        # Determine mode
        mode_map = {"1": "analytics", "2": "general", "3": "specifics"}
        mode = mode_map[choice]
        
        print(f"\n🔍 Checking for cached response...")
        
        # Check for cached response
        cached = find_matching_response(query)
        
        if cached and cached.command_type == mode:
            print("✅ Found cached response!")
            print("🎯 CACHED RESPONSE:")
            print("=" * 50)
            print(cached.response)
            print("=" * 50)
            print("\n💡 This would be returned instantly without calling Claude Code!")
        else:
            print("❌ No cached response found. Would need to run Claude Code.")
        
        print(f"\n🔧 Generated Claude Code Command:")
        print("-" * 50)
        command = generate_command(query, mode)
        print(command)
        print("-" * 50)
        
        # Show command breakdown
        print(f"\n📋 Command Details:")
        print(f"   Working Directory: {SUBSTACK_CODEBASE_PATH}")
        print(f"   Mode: {mode}")
        print(f"   System Prompt: {mode.upper()}")
        
        print(f"\n💬 Your Query: {query}")
        
        if cached:
            print(f"✨ Similarity Score: {calculate_similarity(query, ' '.join(cached.keywords)):.2f}")
            print(f"🎯 Matched Keywords: {[k for k in cached.keywords if k in query.lower()]}")
        
        print("\n✨ You can copy and run the command above to test manually!")
        
        print("\n" + "=" * 60)
        
        # Ask if they want to continue
        continue_choice = input("Would you like to try another query? (y/n): ").strip().lower()
        if continue_choice not in ['y', 'yes']:
            print("👋 Goodbye!")
            break
        print()

if __name__ == "__main__":
    main()