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
import { fileURLToPath } from 'url';
import { generateText } from 'ai';
import { anthropic } from "@ai-sdk/anthropic";
import { experimental_createMCPClient as createMCPClient } from '@ai-sdk/mcp';
import dotenv from 'dotenv';
import path from 'path';
import * as readline from 'node:readline/promises';
import type { CoreMessage } from 'ai';


// --- Environment Loading ---
// Point to the root .env file for unified configuration
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '../../../.env') });

async function main() {
  console.log("Hello World! 🚀");
  console.log("\nMCP CLI Chat Client");
  console.log("===================\n");

  const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY

  // Creating readline interface for CLI interaction
  const terminal = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  
  // Creating MCP Client
  let mcpClient;
  console.log("Init MCP Client...");
  try {
	mcpClient = await createMCPClient({
		transport: {
			type: 'http',
			url: 'http://localhost:8080/mcp',
		},
	});
	console.log("MCP Client initialized successfully!");
  } catch (error) {
	console.error("Failed to initialize MCP Client:", error);
	process.exit(1);
  }
  
  try {
  	// Get tools from MCP server
  	console.log("Listing available tools...");
  	const tools = await mcpClient.tools();
  	console.log("Available Tools:", Object.keys(tools));
  	console.log("Tools loaded successfully!\n");
  
  	// Main chat loop
  	const messages: CoreMessage[] = [];
  	while (true) {
  		const userInput = await terminal.question('You: ');
  
  		if (userInput.toLowerCase() === '/exit' || userInput.toLowerCase() === '/quit') {
  			break;
  		}
  
  		// Add message to history
  		messages.push({ role: 'user', content: userInput });
  
  		// Query MCP client with tools
  		console.log("🤖 Processing your request...");
  		const response = await generateText({
  			model: anthropic("claude-4-sonnet-20250514"),
  			messages: messages,
  			tools: tools,
  			maxSteps: 5, // Allow tool calls
  			stopWhen: ({ steps }) => steps.length >= 4, // This enables multi-step!
  		})
  
  		// Display tool results if any were called
  		if (response.toolResults && response.toolResults.length > 0) {
  			console.log('\n🔧 Tool calls made:');
  			response.toolResults.forEach((result, i) => {
  				console.log(`${i + 1}. ${result.toolName}:`);
  				console.log(`   Input:`, result.args);
  				console.log(`   Result:`, typeof result.result === 'string' ? result.result.substring(0, 200) + '...' : result.result);
  				console.log('');
  			});
  		}
  
  		process.stdout.write('\nAssistant: ');
  		process.stdout.write(response.text);
  		process.stdout.write('\n\n');
  
  		// Add assistant response to history (simplified for now)
  		messages.push({ role: 'assistant', content: response.text });
  	}
  
  } catch (error) {
  	console.error("Error:", error);
  } finally {
  	// Always close the MCP client and terminal
  	terminal.close();
  	await mcpClient.close();
  	console.log('🔒 MCP client closed');
  }
}

main().catch(console.error);
