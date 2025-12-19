import asyncio
from fastmcp import Client


# Testing: Use HTTP/MCP endpoint to confirm SSE is necessary
SERVER_URL = "http://localhost:9000/mcp"

# Create client with longer timeout for LLM operations (in seconds)
client = Client(SERVER_URL, timeout=120.0)


async def main():
    try:
        async with client:
            print(f"Starrrting client ping")
            await client.ping()

            tools = await client.list_tools()
            print(f"Available tools: {tools}")

            print(f"Calling tool")
            result = await client.call_tool(
                "query_db", {"question": "Resume moi les 2 derniers episodes"}
            )

            print(f"response: {result}")

        # from src.query import QueryEngine, QueryConfig
        # config = QueryConfig()
        # engine = QueryEngine(config)
        # # response = await engine.query_engine.aquery("Resume moi les 2 derniers episodes")
        # response = engine.query_engine.query("Resume moi les 2 derniers episodes")

        # print(f"response: {response}")


        print("Success")
    except Exception as e:
        print(f"Fatal error : {e}")


if __name__ == "__main__":
    asyncio.run(main())
