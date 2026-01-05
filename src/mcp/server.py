import argparse
import os

# Disable tokenizer parallelism to avoid fork issues with FastMCP
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from .config import mcp

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rag podcast MCP Server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for HTTP server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Port for HTTP server (default: 9000).",
    )
    args = parser.parse_args()

    # Testing: Use HTTP transport to confirm SSE is necessary
    mcp.run(transport="sse", host=args.host, port=args.port)
    # mcp.run(transport="http", host=args.host, port=args.port)
