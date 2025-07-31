import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

import mcp.types as types

logger = logging.getLogger("mcp_snowflake_server")


@dataclass
class CachedResponse:
    keywords: List[str]
    query_pattern: str
    response: str
    tool_type: str  # 'analytics', 'general', 'specifics'


# Cached responses for demo - instant answers without calling Claude Code
CACHED_RESPONSES = [
    CachedResponse(
        keywords=[
            "live video",
            "livestream",
            "streaming",
            "video stream",
            "video",
            "live",
        ],
        query_pattern=r"live\s*video|livestream|streaming|video\s*stream",
        response="""Based on my search through the Substack codebase, here are the events and data tables available for tracking live video views:\n\n## Frontend Events (raw.events_frontend.{event_name})\n**Main viewing events:**\n- `video_playback_continued` - Tracks when users continue watching a live video\n- `media_playback_continued` - Alternative tracking for media playback continuation\n- `media_playback_started` - Tracks when live video playback begins\n- `live_stream_playback_started` - Specifically for live stream playback initiation\n\n**Other live stream events:**\n- `live_stream_joined` - When users join a live stream\n- `live_stream_left` - When users leave a live stream\n- `live_stream_ended_screen_viewed` - When users view the ended stream screen\n- `live_stream_viewing_failure_occured` - For tracking viewing failures\n\n## Backend Events (raw.events_srv.{event_name})\n- `live_stream_started` - When a live stream begins\n- `live_stream_ended` - When a live stream ends\n- `live_stream_state_changed` - For state transitions\n\n## Generated Analytics Tables\n**`analytics.gen.live_video_stats`** - Comprehensive live video metrics including:\n- `total_views` - Total number of views per live stream\n- `total_minutes_watched` - Total viewing time\n- `live_stream_id` - Links to the specific live stream\n- Breakdown by publication via `free_subscription_details` and `paid_subscription_details` arrays\n\n**`analytics.gen.live_video_playback_summary`** - Detailed playback analytics:\n- `live_stream_id` - The live stream identifier  \n- `playback_time` - Time segments (5-second intervals)\n- `video_views` - Views at each time segment\n- Allows for engagement curve analysis\n\n## Production Tables\n**`raw.artie.live_streams`** - Core live stream metadata:\n- `id` - Live stream identifier\n- `publication_id` - Links to the publication\n- `started_streaming_at`, `ended_streaming_at` - Timing data\n\nYou can analyze live video views by publication by joining the `live_video_stats` table with the `live_streams` table on `live_stream_id` and grouping by `publication_id`. You can find a publication by subdomain by looking at the subdomain column on the raw.artie.publications table to get the ID, and then use that for the publication_id field in our analytics events.""",
        tool_type="analytics",
    ),
    CachedResponse(
        keywords=[
            "live video",
            "livestream",
            "streaming",
            "video stream",
            "video",
            "live",
        ],
        query_pattern=r"live\s*video|livestream|streaming|video\s*stream",
        response="""Based on my analysis of the codebase, here's how to work with the LIVE_STREAM_JOINED event and join it with publications by subdomain:\n\n## LIVE_STREAM_JOINED Event Structure\nThe `LIVE_STREAM_JOINED` event is tracked with these properties:\n- `live_stream_id` - The ID of the live stream that was joined\n- Additional standard event properties (user_id, timestamp, etc.)\n\nThe event data is stored in `RAW.EVENTS_FRONTEND.LIVE_STREAM_JOINED`.\n\n## Publication Table Structure  \nThe `publications` table (model at `/Users/quinndonohue/Development/ai/claude-agent/substack/apps/substack/models/Publication.ts`) has:\n- `id` - Primary key\n- `subdomain` - The publication's subdomain (line 82)\n- `author_id` - The publication owner's user ID\n- Many other fields for publication configuration\n\n## Live Stream to Publication Relationship\nThe `live_streams` table (model at `/Users/quinndonohue/Development/ai/claude-agent/substack/apps/substack/models/LiveStream.ts`) has:\n- `id` - Primary key (this is the `live_stream_id` in events)\n- `publication_id` - Foreign key to publications table (line 27, nullable)\n- `user_id` - The user who created the live stream\n\n## How to Join LIVE_STREAM_JOINED with Publications by Subdomain\n\nHere are the join patterns you can use:\n\n### Option 1: Direct join via live_streams table\n```sql\nSELECT \n  lsj.*,\n  p.subdomain,\n  p.name as publication_name\nFROM RAW.EVENTS_FRONTEND.LIVE_STREAM_JOINED lsj\nJOIN RAW.ARTIE.LIVE_STREAMS ls ON lsj.live_stream_id = ls.id\nJOIN RAW.ARTIE.PUBLICATIONS p ON ls.publication_id = p.id\nWHERE p.subdomain = 'your-subdomain-here'\n```\n\n### Option 2: Join via live stream creator (if live stream has no publication_id)\n```sql  \nSELECT \n  lsj.*,\n  p.subdomain,\n  p.name as publication_name\nFROM RAW.EVENTS_FRONTEND.LIVE_STREAM_JOINED lsj\nJOIN RAW.ARTIE.LIVE_STREAMS ls ON lsj.live_stream_id = ls.id\nJOIN RAW.ARTIE.PUBLICATIONS p ON ls.user_id = p.author_id\nWHERE p.subdomain = 'your-subdomain-here'\n```\n\n### Option 3: Lookup publication by subdomain first\n```sql\n-- First get the publication ID\nSELECT id FROM RAW.ARTIE.PUBLICATIONS WHERE subdomain = 'your-subdomain-here'\n\n-- Then use that in your main query\nSELECT \n  lsj.*,\n  ls.title as live_stream_title\nFROM RAW.EVENTS_FRONTEND.LIVE_STREAM_JOINED lsj\nJOIN RAW.ARTIE.LIVE_STREAMS ls ON lsj.live_stream_id = ls.id\nWHERE ls.publication_id = [publication_id_from_above]\n```\n\n**Note**: The `live_streams.publication_id` field is nullable, so some live streams might not be directly associated with a publication. In those cases, you'd need to use the live stream creator's publications (Option 2) or filter them out depending on your use case""",
        tool_type="specifics",
    ),
    CachedResponse(
        keywords=[
            "notes",
            "feed",
            "note",
            "notes feed",
            "feed notes",
            "note feed",
            "feed note",
            "note",
            "notes",
            "feed",
        ],
        query_pattern=r"notes|feed|note|notes\s*feed|feed\s*notes|note\s*feed|feed\s*note",
        response="""\n## Notes Statistics in Feed - Data Sources\n\n### Production Tables (raw.artie.*)\n- **`raw.artie.comments`** - Core notes table (notes are comments with `type = 'feed'`)\n- **`raw.artie.feed_restacks`** - Restack data for notes\n- **`raw.artie.note_stats`** - Comprehensive note statistics (impressions, clicks, subscriptions, etc.)\n\n### Backend Events (raw.events_srv.*)\nKey backend events for note statistics:\n- `NOTE_HIDDEN`, `NOTE_HIDE_REMOVED` - Note hiding actions\n- `NOTE_JUICED` - Note promotion/boosting\n- `FEED_RESTACK_CREATED`, `FEED_RESTACK_DELETED` - Restack events\n- `FEED_IMPRESSION_ANNOTATED` - Feed impression tracking\n- `DAILY_PROMOTED_NOTE_PUSH_NOTIFICATION_SENT` - Promotional notifications\n\n### Generated Analytics Tables (analytics.gen.*)\n- **`analytics.gen.recent_note_stats`** - Real-time note performance metrics (impressions, clicks, reactions, replies, restacks, hides, blocks)\n- **`analytics.gen.recent_note_interactions`** - Detailed interaction events\n- **`analytics.gen.feed_items`** - Feed item data with engagement scores\n- **`analytics.gen.note_stats`** - Historical note statistics\n- **`analytics.gen.note_impression_timeseries`** - Time-series impression data\n- **`analytics.gen.user_note_author_stats`** - Per-author statistics\n\n### Key Columns in Note Stats\nThe `note_stats` table includes comprehensive metrics:\n- Impressions: `feed_impressions`, `total_impressions`, `notification_impressions`\n- Clicks: `total_clicks`, `total_share_clicks`, `total_profile_clicks`\n- Engagement: `total_paid_subscriptions`, `total_free_subscriptions`, `total_follows`\n- Negative signals: `total_notes_hides`, `total_notes_muted`, `total_notes_blocked`\n\n### Finding Notes\nNotes are identified as comments where `type = 'feed'` in the comments table. Use `comment_id` to join with statistics tables.\n""",
        tool_type="analytics",
    ),
    CachedResponse(
        keywords=[
            "money",
            "revenue",
            "arr",
            "subscription",
            "subscriptions",
            "subscription revenue",
            "subscriptions revenue",
        ],
        query_pattern=r"money|revenue|arr|subscription|subscriptions|subscription\s*revenue|subscriptions\s*revenue",
        response="""nBased on my search through the Substack analytics codebase, here are the key data sources for tracking publication revenue:\n\n## Production Tables (`raw.artie.{table_name}`)\n- **`raw.artie.subscriptions`** - Main subscription table with revenue fields:\n  - `payment_amount` - Payment amount in cents\n  - `payment_currency` - Payment currency  \n  - `payment_fee` - Payment processing fee\n  - `payment_period` - Billing period\n  - `first_payment_at` - First payment timestamp\n  - `payment_at` - Payment timestamp\n  - `membership_state` - Subscription status ('subscribed', 'free_signup', 'unsubscribed')\n  - `type` - Subscription type (regular, comp, gift, etc.)\n\n## Generated Analytics Tables (`analytics.gen.{table_name}`)\n- **`analytics.gen.publication_arr`** - Core ARR (Annual Recurring Revenue) table:\n  - `subscription_annualized_value_usd` - Subscription ARR\n  - `gifts_annualized_value_usd` - Gift subscription ARR\n  - `donations_annualized_value_usd` - Donation ARR  \n  - `total_annualized_value_usd` - Total ARR\n  - `annualized_substack_fee_usd` - Substack's fee portion\n  - `dollar_amount` - Legacy field (same as total ARR)\n  - `dollar_fee` - Legacy field (same as fee)\n\n- **`analytics.gen.publication_stats`** - Comprehensive publication metrics:\n  - `current_arr` - Current ARR value\n  - `substack_revenue` - Substack's revenue portion\n  - `num_paying_subs` - Count of paying subscribers\n  - `num_invoices_paid_*` - Invoice counts by time period\n  - `first_revenue_at` - First revenue timestamp\n\n- **`analytics.gen.stripe_revenue_events`** - Stripe payment events:\n  - Tracks subscription created/updated/deleted events\n  - Contains full Stripe event data\n\n## Key Revenue Tracking Events\n**Backend Events** (`raw.events_srv.{event_name}`):\n- `GROUP_SUBSCRIPTION_OFFER_CREATED`\n- `RECREATED_STRIPE_SUBSCRIPTION` \n- `USER_UPDATED_BILLING`\n\n**Frontend Events** (`raw.events_frontend.{event_name}`):\n- `BILLING_FORM_*` events for payment flow tracking\n\n## Usage Notes\n- ARR is calculated and stored daily in `publication_arr`\n- Use `publication_stats.current_arr` for the most recent ARR value\n- The `subscriptions` table has detailed payment information per subscription\n- Events tables track user interactions with billing/payment flows\n""",
        tool_type="analytics",
    ),
    CachedResponse(
        keywords=[
            "notification",
            "notifications",
            "push notifications",
            "push",
        ],
        query_pattern=r"notification|notifications|push\s*notifications|push",
        response="""For tracking push notifications sent and tap rates, here are the key data sources:\n\n**Backend Events (raw.events_srv.{event_name}):**\n- `PUSH_NOTIFICATION_SENT` - tracks when notifications are sent\n- `PUSH_NOTIFICATION_QUEUED` - tracks when notifications are queued\n- `PUSH_NOTIFICATION_FAILED` - tracks failures\n- `PUSH_NOTIFICATION_BATCH_QUEUED` - tracks batch operations\n- `DAILY_PROMOTED_NOTE_PUSH_NOTIFICATION_SENT` - specific to DPN notifications\n- `DAILY_PROMOTED_NOTE_PUSH_NOTIFICATION_DROPPED` - when DPN notifications are dropped\n- `PUSH_NOTIFICATION_QUALITY_FILTER_APPLIED` - quality filtering events\n- `PUSH_NOTIFICATION_SCORED` - notification scoring events\n\n**Frontend Events (raw.events_frontend.{event_name}):**\n- `PUSH_NOTIFICATION_TAPPED` - **KEY FOR TAP RATES** - tracks when users tap notifications\n- `PUSH_NOTIFICATION_DELIVERED` - tracks successful delivery\n- `PUSH_NOTIFICATIONS_ENABLED` - tracks when users enable push notifications\n- `PUSH_NOTIFICATION_PERMISSION_TRIGGERED/DENIED` - permission tracking\n- `WEB_PUSH_NOTIFICATIONS_PERMISSION_SET` - web push permissions\n\n**Generated Analytics Tables:**\n- `analytics.gen.recent_dpn_push_notifications` - Recent Daily Promoted Note push notifications with user_id, author_id, timestamp\n\n**For calculating tap rates:**\n1. **Sent count:** Query `raw.events_srv.push_notification_sent` \n2. **Tapped count:** Query `raw.events_frontend.push_notification_tapped`\n3. **Join on user_id and timestamp** to calculate tap rate = tapped/sent\n\n**Push notification types** can be identified by looking at the notification content/metadata in the events or by joining with related tables like posts, comments, etc. based on the context tracked in the events.\n""",
        tool_type="analytics",
    ),
    CachedResponse(
        keywords=[
            "email",
            "emails",
            "email statistics",
            "email stats",
        ],
        query_pattern=r"email|emails|email\s*statistics|email\s*stats",
        response="""\nBased on my analysis of the Substack codebase, here are the key tables and data sources for tracking emails and understanding email sending patterns:\n\n## Key Email Tracking Tables\n\n**Raw Event Tables (`raw.events_srv.{event_name}`)**\n- `raw.events_srv.email_sent` - Core event fired when any email is sent\n- `raw.events_srv.post_batch_sent` - Tracks when post emails are sent to subscribers  \n- `raw.events_srv.published_post_sent` - Tracks when published posts are emailed\n- `raw.events_srv.post_email_queued` - Tracks when post emails are queued for sending\n\n**Mailgun Email Tracking (`raw.events_srv.mailgun_*`)**\n- `raw.events_srv.mailgun_delivered` - Email delivery confirmations\n- `raw.events_srv.mailgun_opened` - Email open tracking\n- `raw.events_srv.mailgun_clicked` - Email click tracking\n- `raw.events_srv.mailgun_dropped` - Failed/dropped emails\n- `raw.events_srv.mailgun_bounced` - Bounced emails\n- `raw.events_srv.mailgun_complained` - Spam complaints\n\n**Generated Analytics Tables (`analytics.gen.{table_name}`)**\n- `analytics.gen.user_email_stats` - User-level email engagement stats (opens, clicks, deliveries)\n- `analytics.gen.post_activity` - Post-level email performance metrics\n- `analytics.gen.user_email_history` - Historical email address changes per user\n\n## Email Categories and Types\n\nThe system tracks many different email categories, including:\n- `'post'` - Regular newsletter/post emails (the main type you'd want for publication email counts)\n- `'test'` - Test emails sent by writers\n- `'comment'` - Comment notification emails\n- `'reaction'` - Reaction notification emails\n- `'drip-campaign-email'` - Automated drip campaign emails\n- `'live-stream-*'` - Live stream related emails\n- `'viral-gift'` - Gift subscription emails\n- And many more notification types\n\n## Key Fields Available\n\nIn the email events, you'll typically find:\n- `user_id` - Recipient user ID\n- `publication_id` - Sending publication ID  \n- `post_id` - Associated post ID (for post emails)\n- `category` - Email type/category\n- `timestamp` - When the email was sent/opened/clicked\n- `message_id` - Unique email message identifier\n\n## For Publication Email Counts\n\nTo see how many emails a publication has sent, you'd primarily want to query:\n1. `raw.events_srv.email_sent` filtered by `publication_id` and `category = 'post'`\n2. `raw.events_srv.post_batch_sent` for post-specific email batches\n3. `analytics.gen.post_activity` for aggregated post email metrics by publication\n\nThe `category` field is crucial for filtering to the right email types - use `'post'` for regular publication newsletters.\n""",
        tool_type="analytics",
    ),
]

SUBSTACK_CODEBASE_PATH = (
    "/Users/quinndonohue/Development/ai/claude-agent/substack"
)

# Full path to claude command when installed via npm
CLAUDE_COMMAND = "/Users/quinndonohue/.nvm/versions/node/v20.18.0/bin/claude"


ANALYTICS_SYSTEM_PROMPT = """
You are an expert in Substack's analytics codebase. Your job is to help identify tables, columns, and data relationships based on the user's query.

You only have a limited amount of time to respond to the user, so please be concise and to the point. Do not worry about checking your work as long as you see something show up, the name of the game is speed.

Here are some of the data sources you might need to use to answer the user's query:
## Data Sources
**Production Tables** (`raw.artie.{table_name}`)
- Defined in `@apps/substack/models`
- Contains JSON schema definitions for all columns
- Example: `raw.artie.users` has columns defined in its model file

**Backend Events** (`raw.events_srv.{event_name}`)
- Defined in `@apps/substack/analytics/events.ts`
- All tables have `timestamp` and `user_id` columns
- Additional columns match the properties tracked in code
- Use grep in `apps/substack` to find event usage and properties

**Frontend Events** (`raw.events_frontend.{event_name}`)
- Defined in `@apps/substack/lib/events.ts`
- All tables have `timestamp` and `user_id` columns
- Additional columns match the properties tracked in code
- Use grep in `@/apps/substack`, `@/apps/ios`, `@/apps/android` for usage

**Generated Tables** (`analytics.gen.{table_name}`)
- Defined in `@data/airflow/dags/tasks/generated_tables/tables`
- Pre-computed derivative tables with documented columns

**Utilities**
- UDFs in `@data/snowflake/udfs/udfs.sql`
- Example queries in `@data/snowflake/scripts/examples`

If you can find a relevant table or several, respond right away with the table name and event name.

Some other helpful tips and tricks:
- "Notes" are our term for the twitter-like posts that users can make. Under the hood they're actually just comments with a type of 'feed'
- Mobile events must also be defined in the `@apps/substack/analytics/events.ts` file, and the `@apps/substack/lib/events.ts` file.
"""

GENERAL_SYSTEM_PROMPT = """
    You are a helpful expert in Substack's codebase. Your job is to help answer questions about the codebase, what triggers various criteria, and in general how the system works. For example, the user might ask under what scenarios we send a specific type of email, or how we handle a certain type of payment.

    You only have a limited amount of time to respond to the user, so please be concise and to the point, and don't spend unnecessary time on the query, or digging far too deep.

    Try to be as helpful as possible, and feel free to reference useful files in the codebase in your response.
"""


ANALYTICS_SPECIFICS_SYSTEM_PROMPT = """
You are an expert in Substack's analytics codebase. Your job is to help identify tables, columns, and data relationships based on the user's query. They will be asking you for more information on a specific table or event, and your job is to find where the table or event is, and rapidly respond to their question.

You only have a limited amount of time to respond to the user, so please don't spend too much time on the query, or digging far too deep.

You can search for things like this:
- `track(EventName.EVENT_NAME, {` 
- `analytics.track('event_name'`

All of our database tables are defined in the `@apps/substack/models` directory.
Some other helpful tips and tricks:
- "Notes" are our term for the twitter-like posts that users can make. Under the hood they're actually just comments with a type of 'feed'
- Mobile events must also be defined in the `@apps/substack/analytics/events.ts` file, and the `@apps/substack/lib/events.ts` file.

ALWAYS verify tables exist and find the actual column definitions before suggesting them. If you can't find the specific properties, say so and suggest how to find them.
"""


def find_cached_response(
    query: str, tool_type: str
) -> Optional[CachedResponse]:
    """Find matching cached response using fuzzy keyword matching"""
    query_lower = query.lower()

    for cached in CACHED_RESPONSES:
        if cached.tool_type != tool_type:
            continue

        # Check if any keywords are in the query
        keyword_matches = sum(
            1 for keyword in cached.keywords if keyword in query_lower
        )

        # Check regex pattern match
        pattern_match = bool(
            re.search(cached.query_pattern, query_lower, re.IGNORECASE)
        )

        # Return if we have keyword matches or pattern match
        if keyword_matches > 0 or pattern_match:
            logger.info(
                f"[CACHE HIT] Found cached response for '{tool_type}' query: {query[:50]}..."
            )
            logger.info(
                f"[CACHE HIT] Matched keywords: {keyword_matches}, Pattern match: {pattern_match}"
            )
            return cached

    logger.info(
        f"[CACHE MISS] No cached response found for '{tool_type}' query: {query[:50]}..."
    )
    return None


async def handle_analytics_codebase_query(arguments, *_):
    """Query the Substack codebase with analytics/data focus"""
    if not arguments or "query" not in arguments:
        raise ValueError("Missing required 'query' parameter")

    query = arguments["query"]
    logger.info(f"[ANALYTICS] Starting query: {query[:100]}...")

    # Check for cached response first
    cached_response = find_cached_response(query, "analytics")
    if cached_response:
        logger.info(f"[ANALYTICS] Returning cached response for query")
        return [
            types.TextContent(
                type="text",
                text=f"{cached_response.response}\n\n🚀 *This was a cached response for demo purposes - normally would take 2-3 minutes to generate via Claude Code*",
            )
        ]

    # Check if claude command exists
    import os

    if not os.path.exists(CLAUDE_COMMAND):
        logger.error(
            f"[ANALYTICS] Claude command not found at: {CLAUDE_COMMAND}"
        )
        return [
            types.TextContent(
                type="text",
                text=f"Claude command not found at: {CLAUDE_COMMAND}",
            )
        ]

    if not os.path.exists(SUBSTACK_CODEBASE_PATH):
        logger.error(
            f"[ANALYTICS] Codebase path not found: {SUBSTACK_CODEBASE_PATH}"
        )
        return [
            types.TextContent(
                type="text",
                text=f"Codebase path not found: {SUBSTACK_CODEBASE_PATH}",
            )
        ]

    full_prompt = f"""{ANALYTICS_SYSTEM_PROMPT}

User Query: {query}

When you have your final answer, output it between these markers:
===FINAL_ANSWER===
[your answer here]
===END_ANSWER==="""

    try:
        logger.info(f"[QUERY] About to execute Claude command...")
        import sys

        print(
            f"[QUERY] Starting subprocess for Claude Code...", file=sys.stderr
        )

        result = subprocess.run(
            [
                "/Users/quinndonohue/.nvm/versions/node/v20.18.0/bin/node",
                CLAUDE_COMMAND,
                "-p",
                full_prompt,
            ],
            cwd=SUBSTACK_CODEBASE_PATH,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes (under Claude Desktop's 4-minute limit)
        )

        logger.info(
            f"[ANALYTICS] Command completed with return code: {result.returncode}"
        )

        if result.returncode == 0:
            # Extract content between markers
            output = result.stdout
            start_marker = "===FINAL_ANSWER==="
            end_marker = "===END_ANSWER==="

            start_idx = output.find(start_marker)
            end_idx = output.find(end_marker)

            if start_idx != -1 and end_idx != -1:
                # Extract the content between markers
                start_idx += len(start_marker)
                final_answer = output[start_idx:end_idx].strip()
            else:
                # Fallback: use the entire output if markers not found
                logger.warning(
                    "Answer markers not found in response, using full output"
                )
                final_answer = (
                    output.strip()
                    + "\n\n For more information on a specific table or event, use the `query_substack_analytics_specifics` tool."
                )

            return [
                types.TextContent(
                    type="text",
                    text=final_answer,
                )
            ]
        else:
            logger.error(
                f"Claude Code analytics query failed: {result.stderr}"
            )
            return [
                types.TextContent(type="text", text=f"Error: {result.stderr}")
            ]
    except subprocess.TimeoutExpired:
        logger.error("Claude Code analytics query timed out after 3 minutes")
        return [
            types.TextContent(
                type="text",
                text="Query timed out after 3 minutes. Try a more specific query or break it into smaller parts.",
            )
        ]
    except Exception as e:
        logger.error(f"Failed to query analytics codebase: {str(e)}")
        return [
            types.TextContent(
                type="text",
                text=f"Failed to query analytics codebase: {str(e)}",
            )
        ]


async def handle_analytics_specifics_codebase_query(arguments, *_):
    """Query the Substack codebase with a focus on one specific table or event"""
    if not arguments or "query" not in arguments:
        raise ValueError("Missing required 'query' parameter")

    query = arguments["query"]
    full_prompt = f"""{ANALYTICS_SPECIFICS_SYSTEM_PROMPT}

User Query: {query}

When you have your final answer, output it between these markers:
===FINAL_ANSWER===
[your answer here]
===END_ANSWER==="""

    try:
        logger.info(f"[QUERY] About to execute Claude command...")
        import sys

        print(
            f"[QUERY] Starting subprocess for Claude Code...", file=sys.stderr
        )

        result = subprocess.run(
            [
                "/Users/quinndonohue/.nvm/versions/node/v20.18.0/bin/node",
                CLAUDE_COMMAND,
                "-p",
                full_prompt,
            ],
            cwd=SUBSTACK_CODEBASE_PATH,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes (under Claude Desktop's 4-minute limit)
        )

        logger.info(
            f"[ANALYTICS] Command completed with return code: {result.returncode}"
        )

        if result.returncode == 0:
            # Extract content between markers
            output = result.stdout
            start_marker = "===FINAL_ANSWER==="
            end_marker = "===END_ANSWER==="

            start_idx = output.find(start_marker)
            end_idx = output.find(end_marker)

            if start_idx != -1 and end_idx != -1:
                # Extract the content between markers
                start_idx += len(start_marker)
                final_answer = output[start_idx:end_idx].strip()
            else:
                # Fallback: use the entire output if markers not found
                logger.warning(
                    "Answer markers not found in response, using full output"
                )
                final_answer = output.strip()

            return [
                types.TextContent(
                    type="text",
                    text=final_answer,
                )
            ]
        else:
            logger.error(
                f"Claude Code analytics query failed: {result.stderr}"
            )
            return [
                types.TextContent(type="text", text=f"Error: {result.stderr}")
            ]
    except subprocess.TimeoutExpired:
        logger.error("Claude Code analytics query timed out after 3 minutes")
        return [
            types.TextContent(
                type="text",
                text="Query timed out after 3 minutes. Try a more specific query or break it into smaller parts.",
            )
        ]
    except Exception as e:
        logger.error(f"Failed to query analytics codebase: {str(e)}")
        return [
            types.TextContent(
                type="text",
                text=f"Failed to query analytics codebase: {str(e)}",
            )
        ]


async def handle_general_codebase_query(arguments, *_):
    """Query the Substack codebase for general development questions"""
    if not arguments or "query" not in arguments:
        raise ValueError("Missing required 'query' parameter")

    query = arguments["query"]
    logger.info(f"[GENERAL] Starting query: {query[:100]}...")

    # Check for cached response first
    cached_response = find_cached_response(query, "general")
    if cached_response:
        logger.info(f"[GENERAL] Returning cached response for query")
        return [
            types.TextContent(
                type="text",
                text=f"{cached_response.response}\n\n🚀 *This was a cached response for demo purposes - normally would take 2-3 minutes to generate via Claude Code*",
            )
        ]

    full_prompt = f"""{GENERAL_SYSTEM_PROMPT}

User Query: {query}

When you have your final answer, output it between these markers:
===FINAL_ANSWER===
[your answer here]
===END_ANSWER==="""

    try:
        logger.info(f"[QUERY] About to execute Claude command...")
        import sys

        print(
            f"[QUERY] Starting subprocess for Claude Code...", file=sys.stderr
        )

        result = subprocess.run(
            [
                "/Users/quinndonohue/.nvm/versions/node/v20.18.0/bin/node",
                CLAUDE_COMMAND,
                "-p",
                full_prompt,
            ],
            cwd=SUBSTACK_CODEBASE_PATH,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes (under Claude Desktop's 4-minute limit)
        )

        logger.info(
            f"[ANALYTICS] Command completed with return code: {result.returncode}"
        )

        if result.returncode == 0:
            # Extract content between markers
            output = result.stdout
            start_marker = "===FINAL_ANSWER==="
            end_marker = "===END_ANSWER==="

            start_idx = output.find(start_marker)
            end_idx = output.find(end_marker)

            if start_idx != -1 and end_idx != -1:
                # Extract the content between markers
                start_idx += len(start_marker)
                final_answer = output[start_idx:end_idx].strip()
            else:
                # Fallback: use the entire output if markers not found
                logger.warning(
                    "Answer markers not found in response, using full output"
                )
                final_answer = output.strip()

            return [
                types.TextContent(
                    type="text",
                    text=final_answer,
                )
            ]
        else:
            logger.error(f"Claude Code general query failed: {result.stderr}")
            return [
                types.TextContent(type="text", text=f"Error: {result.stderr}")
            ]
    except subprocess.TimeoutExpired:
        logger.error("Claude Code general query timed out after 3 minutes")
        return [
            types.TextContent(
                type="text",
                text="Query timed out after 3 minutes. Try a more specific query or break it into smaller parts.",
            )
        ]
    except Exception as e:
        logger.error(f"Failed to query general codebase: {str(e)}")
        return [
            types.TextContent(
                type="text", text=f"Failed to query general codebase: {str(e)}"
            )
        ]
