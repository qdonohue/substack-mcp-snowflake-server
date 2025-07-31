import asyncio
import logging
import time
import uuid
from typing import Any

from snowflake.snowpark import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("mcp_snowflake_server")


class SnowflakeDB:
    AUTH_EXPIRATION_TIME = 1800

    def __init__(self, connection_config: dict):
        # Force externalbrowser authentication
        connection_config['authenticator'] = 'externalbrowser'
        connection_config['cache_mfa_token'] = True
        # This should cache tokens in ~/.snowflake/
        logger.info("Using externalbrowser authentication with token caching")
        
        self.connection_config = connection_config
        self.session = None
        self.insights: list[str] = []
        self.auth_time = 0
        self.init_task = None  # To store the task reference

    async def _init_database(self):
        """Initialize connection to the Snowflake database"""
        try:
            # Log connection configuration (excluding sensitive data)
            config_to_log = {k: v for k, v in self.connection_config.items() 
                           if k not in ['password', 'token', 'private_key']}
            logger.info(f"Initializing Snowflake connection with config: {config_to_log}")
            
            # Log externalbrowser authentication
            logger.info("Authentication method: externalbrowser")
            logger.info("A browser window should open for authentication...")
            logger.info("If no browser opens, check that you're running in an interactive session")
            
            # Create session without setting specific database and schema
            logger.info("Creating Snowflake session...")
            logger.info("Calling Session.builder.configs().create()...")
            
            # Add more detailed logging around session creation
            try:
                self.session = Session.builder.configs(self.connection_config).create()
                logger.info("Snowflake session created successfully")
            except Exception as session_error:
                logger.error(f"Session creation failed: {type(session_error).__name__}")
                logger.error(f"Session error details: {str(session_error)}")
                # Check for common externalbrowser issues
                if 'browser' in str(session_error).lower():
                    logger.error("Browser authentication failed - possible causes:")
                    logger.error("1. Browser popup was blocked")
                    logger.error("2. Running in non-interactive environment (e.g., Claude Desktop)")
                    logger.error("3. Browser authentication timed out")
                    logger.error("4. Token expired - run manually to re-authenticate")
                raise

            # Set initial warehouse if provided, but don't set database or schema
            if "warehouse" in self.connection_config:
                logger.info(f"Setting warehouse to: {self.connection_config['warehouse'].upper()}")
                self.session.sql(f"USE WAREHOUSE {self.connection_config['warehouse'].upper()}")

            self.auth_time = time.time()
            logger.info("Database initialization completed successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Snowflake: {type(e).__name__}: {str(e)}")
            raise ValueError(f"Failed to connect to Snowflake database: {e}")

    def start_init_connection(self):
        """Start database initialization in the background"""
        # Create a task that runs in the background
        loop = asyncio.get_event_loop()
        self.init_task = loop.create_task(self._init_database())
        return self.init_task

    async def execute_query(self, query: str) -> tuple[list[dict[str, Any]], str]:
        """Execute a SQL query and return results as a list of dictionaries"""
        # SAFETY CHECK: Block common write operations
        query_upper = query.strip().upper()
        write_keywords = ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE', 'MERGE']
        first_word = query_upper.split()[0] if query_upper else ''
        if first_word in write_keywords:
            raise ValueError(f"SAFETY: {first_word} operations are not allowed in this read-only server")
        
        # If init_task exists and isn't done, wait for it to complete
        if self.init_task and not self.init_task.done():
            await self.init_task
        # If session doesn't exist or has expired, initialize it and wait
        elif not self.session or time.time() - self.auth_time > self.AUTH_EXPIRATION_TIME:
            await self._init_database()

        logger.debug(f"Executing query: {query}")
        try:
            result = self.session.sql(query).to_pandas()
            result_rows = result.to_dict(orient="records")
            data_id = str(uuid.uuid4())

            return result_rows, data_id

        except Exception as e:
            logger.error(f'Database error executing "{query}": {e}')
            raise

    def add_insight(self, insight: str) -> None:
        """Add a new insight to the collection"""
        self.insights.append(insight)

    def get_memo(self) -> str:
        """Generate a formatted memo from collected insights"""
        if not self.insights:
            return "No data insights have been discovered yet."

        memo = "📊 Data Intelligence Memo 📊\n\n"
        memo += "Key Insights Discovered:\n\n"
        memo += "\n".join(f"- {insight}" for insight in self.insights)

        if len(self.insights) > 1:
            memo += f"\n\nSummary:\nAnalysis has revealed {len(self.insights)} key data insights that suggest opportunities for strategic optimization and growth."

        return memo
