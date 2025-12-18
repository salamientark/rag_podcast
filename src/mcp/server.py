import argparse

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

    mcp.run(transport="http", host=args.host, port=args.port)
