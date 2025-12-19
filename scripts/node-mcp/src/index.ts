/**
 * MCP CLI Chat Client
 *
 * A TypeScript CLI client for interacting with MCP servers using the AI SDK.
 *
 * TODO for intern:
 * 1. Install AI SDK: pnpm add ai @ai-sdk/openai
 * 2. Install MCP client: pnpm add @modelcontextprotocol/sdk
 * 3. Build a CLI chat interface that:
 *    - Connects to the MCP server at http://localhost:9000/mcp
 *    - Uses AI SDK to interact with an LLM
 *    - Calls the query_db tool via MCP
 *
 * Resources:
 * - AI SDK docs: https://ai-sdk.dev/
 * - MCP SDK: https://modelcontextprotocol.io/
 */

async function main() {
  console.log("Hello World! 🚀");
  console.log("\nMCP CLI Chat Client");
  console.log("===================\n");

  console.log("Next steps:");
  console.log("1. Install dependencies: pnpm add ai @ai-sdk/openai @modelcontextprotocol/sdk");
  console.log("2. Create a chat loop that connects to the MCP server");
  console.log("3. Use AI SDK to process user queries and call MCP tools\n");

  console.log("MCP Server URL: http://localhost:9000/mcp");
  console.log("Available tool: query_db(question: string)");
}

main().catch(console.error);
