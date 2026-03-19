"""
Google Sheets MCP server — stub.

This will expose append_row and read_sheet tools for Claude agents.
Implement after the core listing flow is working end-to-end.

To implement:
1. pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
2. Set GOOGLE_SHEETS_ID and GOOGLE_CREDENTIALS_PATH in .env
3. Replace the stubs below with real Sheets API calls

For now, the server starts but returns placeholder responses so .mcp.json
doesn't cause a startup error.
"""
import json
import sys

# MCP protocol: read JSON-RPC from stdin, write to stdout
def _respond(id_, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id_, "result": result}) + "\n")
    sys.stdout.flush()


def _error(id_, message):
    sys.stdout.write(json.dumps({
        "jsonrpc": "2.0", "id": id_,
        "error": {"code": -32000, "message": message}
    }) + "\n")
    sys.stdout.flush()


TOOLS = [
    {
        "name": "append_row",
        "description": "Append a listing row to the Google Sheet inventory tracker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "listing": {"type": "object", "description": "The validated listing JSON"}
            },
            "required": ["listing"]
        }
    },
    {
        "name": "read_sheet",
        "description": "Read all rows from the inventory sheet.",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


def handle(request: dict):
    method = request.get("method")
    id_ = request.get("id")

    if method == "initialize":
        _respond(id_, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "sheets", "version": "0.1.0"},
            "capabilities": {"tools": {}}
        })
    elif method == "tools/list":
        _respond(id_, {"tools": TOOLS})
    elif method == "tools/call":
        name = request.get("params", {}).get("name")
        if name == "append_row":
            # TODO: implement real Sheets API call
            _respond(id_, {"content": [{"type": "text", "text": "NOT IMPLEMENTED: sheets_server.py is a stub"}]})
        elif name == "read_sheet":
            _respond(id_, {"content": [{"type": "text", "text": "NOT IMPLEMENTED: sheets_server.py is a stub"}]})
        else:
            _error(id_, f"Unknown tool: {name}")
    else:
        # Ignore notifications (no id)
        if id_ is not None:
            _error(id_, f"Unknown method: {method}")


if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            handle(request)
        except Exception as e:
            sys.stderr.write(f"sheets_server error: {e}\n")
