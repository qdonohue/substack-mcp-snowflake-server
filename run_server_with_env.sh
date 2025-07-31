#!/bin/bash

# Load NVM and ensure claude is in PATH
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Add claude to PATH if it's installed globally via npm
export PATH="$HOME/.nvm/versions/node/v20.18.0/bin:$PATH"

# Debug logging
echo "=== Environment Debug ===" >&2
echo "PATH: $PATH" >&2
echo "Which claude: $(which claude)" >&2
echo "Claude version: $(claude --version 2>&1)" >&2
echo "========================" >&2

# Run the actual server
exec /opt/homebrew/bin/uv --directory /Users/quinndonohue/Development/mcp/substack-mcp-snowflake-server run mcp_snowflake_server