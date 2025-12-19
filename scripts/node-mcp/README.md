# MCP CLI Chat Client

A TypeScript CLI client for interacting with MCP servers using the AI SDK.

## Setup

```bash
# Install dependencies
pnpm install

# Run in development mode
pnpm dev

# Build
pnpm build

# Run production build
pnpm start
```

## Project Structure

```
scripts/node-mcp/
├── src/
│   └── index.ts       # Main entry point
├── dist/              # Compiled output (generated)
├── package.json
├── tsconfig.json
└── README.md
```

## Tasks for Intern

### 1. Install Required Dependencies

```bash
pnpm add ai @ai-sdk/openai @modelcontextprotocol/sdk
```

### 2. Build the CLI Chat Interface

Create a chat loop that:
- Connects to the MCP server at `http://localhost:9000/mcp`
- Takes user input from the terminal
- Uses AI SDK to interact with an LLM (OpenAI)
- Calls the `query_db` tool via MCP when needed
- Displays responses to the user

### 3. MCP Server Information

- **Server URL**: `http://localhost:9000/mcp`
- **Transport**: HTTP (Streamable HTTP protocol)
- **Available Tool**: `query_db(question: string)`
  - Queries a French podcast database
  - Returns relevant information about episodes

### 4. Resources

- **AI SDK Documentation**: https://ai-sdk.dev/
- **MCP Protocol**: https://modelcontextprotocol.io/
- **MCP SDK**: https://github.com/modelcontextprotocol/typescript-sdk

### 5. Example Flow

```
User: Resume moi les 2 derniers episodes
  ↓
AI SDK processes query
  ↓
Calls MCP tool: query_db("Resume moi les 2 derniers episodes")
  ↓
MCP Server responds with podcast summaries
  ↓
AI SDK formats response
  ↓
Display to user in CLI
```

## Environment Variables

Create a `.env` file:

```bash
OPENAI_API_KEY=your_openai_api_key_here
MCP_SERVER_URL=http://localhost:9000/mcp
```

## Testing

Start the MCP server first:

```bash
# From the root of rag_podcast project
uv run -m src.mcp.server
```

Then run this client:

```bash
pnpm dev
```
