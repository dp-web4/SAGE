#!/bin/bash
# MCP Server Health Check Script
# Checks if the MCP server at 127.0.0.1:8010 is responding
# Logs alerts to journal.md if the server is down

MCP_ENDPOINT="http://127.0.0.1:8010/health"
LOG_FILE="/home/dp/ai-workspace/SAGE/sage/instances/cbp-qwen3.8-distill-4b/journal.md"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP Health Check" >> "$LOG_FILE"

# Attempt to probe the MCP endpoint
if curl -sf --max-time 5 "$MCP_ENDPOINT" > /dev/null 2>&1; then
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP server is UP and responding." >> "$LOG_FILE"
    exit 0
else
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP server is DOWN. Endpoint: $MCP_ENDPOINT" >> "$LOG_FILE"
    echo "ALERT: MCP server at $MCP_ENDPOINT is not responding."
    exit 1
fi
#!/bin/bash
# MCP Server Health Check Script
# Checks if the MCP server at 127.0.0.1:8010 is responding
# Logs alerts to journal.md if the server is down

MCP_ENDPOINT="http://127.0.0.1:8010/health"
LOG_FILE="/home/dp/ai-workspace/SAGE/sage/instances/cbp-qwen3.8-distill-4b/journal.md"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP Health Check" >> "$LOG_FILE"

# Attempt to probe the MCP endpoint
if curl -sf --max-time 5 "$MCP_ENDPOINT" > /dev/null 2>&1; then
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP server is UP and responding." >> "$LOG_FILE"
    exit 0
else
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP server is DOWN. Endpoint: $MCP_ENDPOINT" >> "$LOG_FILE"
    echo "ALERT: MCP server at $MCP_ENDPOINT is not responding."
    exit 1
fi
#!/bin/bash
# MCP Server Health Check Script
# Checks if the MCP server at 127.0.0.1:8010 is responding
# Logs alerts to journal.md if the server is down

MCP_ENDPOINT="http://127.0.0.1:8010/health"
LOG_FILE="/home/dp/ai-workspace/SAGE/sage/instances/cbp-qwen3.8-distill-4b/journal.md"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP Health Check" >> "$LOG_FILE"

# Attempt to probe the MCP endpoint
if curl -sf --max-time 5 "$MCP_ENDPOINT" > /dev/null 2>&1; then
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP server is UP and responding." >> "$LOG_FILE"
    echo "MCP server is UP and responding."
    exit 0
else
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] MCP server is DOWN. Endpoint: $MCP_ENDPOINT" >> "$LOG_FILE"
    echo "ALERT: MCP server at $MCP_ENDPOINT is not responding."
    exit 1
fi
