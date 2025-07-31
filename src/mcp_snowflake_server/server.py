import importlib.metadata
import json
import logging
import os
import sys
from functools import wraps
from typing import Any, Callable

import mcp.server.stdio
import mcp.types as types
import yaml
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from pydantic import AnyUrl, BaseModel

from .claude_code import (
    handle_analytics_codebase_query,
    handle_analytics_specifics_codebase_query,
    handle_general_codebase_query,
)
from .db_client import SnowflakeDB
from .write_detector import SQLWriteDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("mcp_snowflake_server")


def data_to_yaml(data: Any) -> str:
    return yaml.dump(data, indent=2, sort_keys=False)


# Custom serializer that checks for 'date' type
def data_json_serializer(obj):
    from datetime import date, datetime

    if isinstance(obj, date) or isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj


def handle_tool_errors(func: Callable) -> Callable:
    """Decorator to standardize tool error handling"""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> list[types.TextContent]:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    return wrapper


class Tool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[
        [str, dict[str, Any] | None],
        list[types.TextContent | types.ImageContent | types.EmbeddedResource],
    ]
    tags: list[str] = []


# Tool handlers
async def handle_list_databases(arguments, db, *_, exclusion_config=None):
    query = "SELECT DATABASE_NAME FROM INFORMATION_SCHEMA.DATABASES"
    data, data_id = await db.execute_query(query)

    # Filter out excluded databases
    if (
        exclusion_config
        and "databases" in exclusion_config
        and exclusion_config["databases"]
    ):
        filtered_data = []
        for item in data:
            db_name = item.get("DATABASE_NAME", "")
            exclude = False
            for pattern in exclusion_config["databases"]:
                if pattern.lower() in db_name.lower():
                    exclude = True
                    break
            if not exclude:
                filtered_data.append(item)
        data = filtered_data

    output = {
        "type": "data",
        "data_id": data_id,
        "data": data,
    }
    yaml_output = data_to_yaml(output)
    json_output = json.dumps(output)
    return [
        types.TextContent(type="text", text=yaml_output),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=f"data://{data_id}",
                text=json_output,
                mimeType="application/json",
            ),
        ),
    ]


async def handle_list_schemas(arguments, db, *_, exclusion_config=None):
    if not arguments or "database" not in arguments:
        raise ValueError("Missing required 'database' parameter")

    database = arguments["database"]
    query = f"SELECT SCHEMA_NAME FROM {database.upper()}.INFORMATION_SCHEMA.SCHEMATA"
    data, data_id = await db.execute_query(query)

    # Filter out excluded schemas
    if (
        exclusion_config
        and "schemas" in exclusion_config
        and exclusion_config["schemas"]
    ):
        filtered_data = []
        for item in data:
            schema_name = item.get("SCHEMA_NAME", "")
            exclude = False
            for pattern in exclusion_config["schemas"]:
                if pattern.lower() in schema_name.lower():
                    exclude = True
                    break
            if not exclude:
                filtered_data.append(item)
        data = filtered_data

    output = {
        "type": "data",
        "data_id": data_id,
        "database": database,
        "data": data,
    }
    yaml_output = data_to_yaml(output)
    json_output = json.dumps(output)
    return [
        types.TextContent(type="text", text=yaml_output),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=f"data://{data_id}",
                text=json_output,
                mimeType="application/json",
            ),
        ),
    ]


async def handle_list_tables(arguments, db, *_, exclusion_config=None):
    if (
        not arguments
        or "database" not in arguments
        or "schema" not in arguments
    ):
        raise ValueError("Missing required 'database' and 'schema' parameters")

    database = arguments["database"]
    schema = arguments["schema"]

    query = f"""
        SELECT table_catalog, table_schema, table_name, comment 
        FROM {database}.information_schema.tables 
        WHERE table_schema = '{schema.upper()}'
    """
    data, data_id = await db.execute_query(query)

    # Filter out excluded tables
    if (
        exclusion_config
        and "tables" in exclusion_config
        and exclusion_config["tables"]
    ):
        filtered_data = []
        for item in data:
            table_name = item.get("TABLE_NAME", "")
            exclude = False
            for pattern in exclusion_config["tables"]:
                if pattern.lower() in table_name.lower():
                    exclude = True
                    break
            if not exclude:
                filtered_data.append(item)
        data = filtered_data

    output = {
        "type": "data",
        "data_id": data_id,
        "database": database,
        "schema": schema,
        "data": data,
    }
    yaml_output = data_to_yaml(output)
    json_output = json.dumps(output)
    return [
        types.TextContent(type="text", text=yaml_output),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=f"data://{data_id}",
                text=json_output,
                mimeType="application/json",
            ),
        ),
    ]


async def handle_describe_table(arguments, db, *_):
    if not arguments or "table_name" not in arguments:
        raise ValueError("Missing table_name argument")

    table_spec = arguments["table_name"]
    split_identifier = table_spec.split(".")

    # Parse the fully qualified table name
    if len(split_identifier) < 3:
        raise ValueError(
            "Table name must be fully qualified as 'database.schema.table'"
        )

    database_name = split_identifier[0].upper()
    schema_name = split_identifier[1].upper()
    table_name = split_identifier[2].upper()

    query = f"""
        SELECT column_name, column_default, is_nullable, data_type, comment 
        FROM {database_name}.information_schema.columns 
        WHERE table_schema = '{schema_name}' AND table_name = '{table_name}'
    """
    data, data_id = await db.execute_query(query)

    output = {
        "type": "data",
        "data_id": data_id,
        "database": database_name,
        "schema": schema_name,
        "table": table_name,
        "data": data,
    }
    yaml_output = data_to_yaml(output)
    json_output = json.dumps(output)
    return [
        types.TextContent(type="text", text=yaml_output),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=f"data://{data_id}",
                text=json_output,
                mimeType="application/json",
            ),
        ),
    ]


async def handle_read_query(arguments, db, write_detector, *_):
    if not arguments or "query" not in arguments:
        raise ValueError("Missing query argument")

    if write_detector.analyze_query(arguments["query"])["contains_write"]:
        raise ValueError(
            "Calls to read_query should not contain write operations"
        )

    data, data_id = await db.execute_query(arguments["query"])

    output = {
        "type": "data",
        "data_id": data_id,
        "data": data,
    }
    yaml_output = data_to_yaml(output)
    json_output = json.dumps(output, default=data_json_serializer)
    return [
        types.TextContent(type="text", text=yaml_output),
        types.EmbeddedResource(
            type="resource",
            resource=types.TextResourceContents(
                uri=f"data://{data_id}",
                text=json_output,
                mimeType="application/json",
            ),
        ),
    ]


async def handle_append_insight(arguments, db, _, __, server):
    if not arguments or "insight" not in arguments:
        raise ValueError("Missing insight argument")

    db.add_insight(arguments["insight"])
    await server.request_context.session.send_resource_updated(
        AnyUrl("memo://insights")
    )
    return [types.TextContent(type="text", text="Insight added to memo")]


async def handle_write_query(arguments, db, _, allow_write, __):
    # PERMANENTLY DISABLED FOR SAFETY
    raise ValueError(
        "Write operations are permanently disabled in this server for safety"
    )
    # if not allow_write:
    #     raise ValueError("Write operations are not allowed for this data connection")
    # if arguments["query"].strip().upper().startswith("SELECT"):
    #     raise ValueError("SELECT queries are not allowed for write_query")
    #
    # results, data_id = await db.execute_query(arguments["query"])
    # return [types.TextContent(type="text", text=str(results))]


async def handle_create_table(arguments, db, _, allow_write, __):
    # PERMANENTLY DISABLED FOR SAFETY
    raise ValueError(
        "Table creation is permanently disabled in this server for safety"
    )
    # if not allow_write:
    #     raise ValueError("Write operations are not allowed for this data connection")
    # if not arguments["query"].strip().upper().startswith("CREATE TABLE"):
    #     raise ValueError("Only CREATE TABLE statements are allowed")
    #
    # results, data_id = await db.execute_query(arguments["query"])
    # return [types.TextContent(type="text", text=f"Table created successfully. data_id = {data_id}")]


async def main(
    allow_write: bool = False,
    connection_args: dict = None,
    log_dir: str = None,
    prefetch: bool = False,
    log_level: str = "INFO",
    exclude_tools: list[str] = [],
    config_file: str = "runtime_config.json",
    exclude_patterns: dict = None,
):
    # Setup logging
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        logger.handlers.append(
            logging.FileHandler(
                os.path.join(log_dir, "mcp_snowflake_server.log")
            )
        )
    if log_level:
        logger.setLevel(log_level)

    logger.info("Starting Snowflake MCP Server")
    logger.info("Allow write operations: %s", allow_write)
    logger.info("Prefetch table descriptions: %s", prefetch)
    logger.info("Excluded tools: %s", exclude_tools)

    # Debug environment
    logger.info("=== ENVIRONMENT DEBUG ===")
    logger.info(f"Python executable: {sys.executable}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"PATH: {os.environ.get('PATH', 'NOT SET')}")
    logger.info(f"NODE_PATH: {os.environ.get('NODE_PATH', 'NOT SET')}")
    logger.info(f"NVM_DIR: {os.environ.get('NVM_DIR', 'NOT SET')}")
    logger.info(f"Working directory: {os.getcwd()}")

    # Check if claude command is available
    import subprocess

    try:
        claude_path = subprocess.run(
            ["which", "claude"], capture_output=True, text=True
        )
        logger.info(f"Claude command location: {claude_path.stdout.strip()}")

        # Check claude version
        claude_version = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True
        )
        logger.info(f"Claude version: {claude_version.stdout.strip()}")
    except Exception as e:
        logger.error(f"Error checking claude command: {e}")
    logger.info("========================")

    # Load configuration from file if provided
    config = {}
    #
    if config_file:
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.error(f"Error loading configuration file: {e}")

    # Merge exclude_patterns from parameters with config file
    exclusion_config = config.get("exclude_patterns", {})
    if exclude_patterns:
        # Merge patterns from parameters with those from config file
        for key, patterns in exclude_patterns.items():
            if key in exclusion_config:
                exclusion_config[key].extend(patterns)
            else:
                exclusion_config[key] = patterns

    # Set default patterns if none are specified
    if not exclusion_config:
        exclusion_config = {"databases": [], "schemas": [], "tables": []}

    # Ensure all keys exist in the exclusion config
    for key in ["databases", "schemas", "tables"]:
        if key not in exclusion_config:
            exclusion_config[key] = []

    logger.info(f"Exclusion patterns: {exclusion_config}")

    db = SnowflakeDB(connection_args)
    db.start_init_connection()
    server = Server("snowflake-manager")
    write_detector = SQLWriteDetector()

    all_tools = [
        Tool(
            name="health_check",
            description="Check if the server is running and authenticated",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=lambda args, db, *_: [
                types.TextContent(
                    type="text",
                    text=f"Server is running. Session active: {db.session is not None}",
                )
            ],
        ),
        Tool(
            name="describe_table",
            description="Get the schema information for a specific table",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Fully qualified table name in the format 'database.schema.table'",
                    },
                },
                "required": ["table_name"],
            },
            handler=handle_describe_table,
        ),
        Tool(
            name="read_query",
            description="Execute a SELECT query.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SELECT SQL query to execute",
                    }
                },
                "required": ["query"],
            },
            handler=handle_read_query,
        ),
        Tool(
            name="query_substack_analytics",
            description="Ask questions about what tables exist in the codebase, or what events we might have. You should prioritize using this tool before digging into specific table schemas, or listing all schemas. This tool may take a while to run, so please be patient. Providing general context is helpful - this is an LLM tool, not a deterministic response. Feel free to ask follow up questions using query_substack_analytics_specifics for more information on a specific event.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Analytics-focused query about database structure, tables, or data models. For example 'how do we track a user log in', 'what event do we have for sending a daily promoted note', or 'what are the possible types for an email'. ",
                    }
                },
                "required": ["query"],
            },
            handler=handle_analytics_codebase_query,
        ),
        Tool(
            name="query_substack_analytics_specifics",
            description="If you are asking about a single table, and not a join, prefer to use the describe_table tool instead. Ask questions about a specific table or event in the codebase. For example 'what columns are in the users table', 'what event do we have for sending a daily promoted note', or 'when do we fire a daily_promoted_note_sent event'. ",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Analytics-focused query about a specific table or event in the codebase.",
                    }
                },
                "required": ["query"],
            },
            handler=handle_analytics_specifics_codebase_query,
        ),
        Tool(
            name="query_substack_codebase",
            description="Ask general development questions about the Substack codebase structure, implementation details, and coding patterns. For example 'what time of day do we send daily promoted notes', 'when is a user eligible for a free trial', or 'how do we handle a user cancelling a subscription'. This tool may take a while to run, so please be patient. Provide general context about what you're trying to do, and expect that the response will also provide some helpful contextual information. Feel free to ask follow up questions using this same tool if you struggle with making queries work, or if you need to know about other columns.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "General development question about the codebase",
                    }
                },
                "required": ["query"],
            },
            handler=handle_general_codebase_query,
        ),
    ]

    exclude_tags = []
    if not allow_write:
        exclude_tags.append("write")
    allowed_tools = [
        tool
        for tool in all_tools
        if tool.name not in exclude_tools
        and not any(tag in exclude_tags for tag in tool.tags)
    ]

    logger.info("Allowed tools: %s", [tool.name for tool in allowed_tools])

    # Register handlers
    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        resources = [
            types.Resource(
                uri=AnyUrl("memo://insights"),
                name="Data Insights Memo",
                description="A living document of discovered data insights",
                mimeType="text/plain",
            )
        ]
        table_brief_resources = [
            types.Resource(
                uri=AnyUrl(f"context://table/{table_name}"),
                name=f"{table_name} table",
                description=f"Description of the {table_name} table",
                mimeType="text/plain",
            )
            for table_name in tables_info.keys()
        ]
        resources += table_brief_resources
        return resources

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> str:
        if str(uri) == "memo://insights":
            return db.get_memo()
        elif str(uri).startswith("context://table"):
            table_name = str(uri).split("/")[-1]
            if table_name in tables_info:
                return data_to_yaml(tables_info[table_name])
            else:
                raise ValueError(f"Unknown table: {table_name}")
        else:
            raise ValueError(f"Unknown resource: {uri}")

    @server.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        return []

    @server.get_prompt()
    async def handle_get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        raise ValueError(f"Unknown prompt: {name}")

    @server.call_tool()
    @handle_tool_errors
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name in exclude_tools:
            return [
                types.TextContent(
                    type="text",
                    text=f"Tool {name} is excluded from this data connection",
                )
            ]

        handler = next(
            (tool.handler for tool in allowed_tools if tool.name == name), None
        )
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        # Pass exclusion_config to the handler if it's a listing function
        if name in ["list_databases", "list_schemas", "list_tables"]:
            return await handler(
                arguments,
                db,
                write_detector,
                allow_write,
                server,
                exclusion_config=exclusion_config,
            )
        else:
            return await handler(
                arguments, db, write_detector, allow_write, server
            )

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        logger.info("Listing tools")
        logger.error(f"Allowed tools: {allowed_tools}")
        tools = [
            types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema,
            )
            for tool in allowed_tools
        ]
        return tools

    # Start server
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Server running with stdio transport")
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="snowflake",
                server_version=importlib.metadata.version(
                    "mcp_snowflake_server"
                ),
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
