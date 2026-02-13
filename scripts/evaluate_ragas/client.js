import * as dotenv from 'dotenv';
import fs from 'node:fs';
import { parse } from 'csv-parse';
import * as jose from 'jose';

// LANGFUSE SETUP START
import { NodeSDK } from "@opentelemetry/sdk-node";
import { LangfuseSpanProcessor } from "@langfuse/otel";
import { startActiveObservation, getActiveTraceId } from "@langfuse/tracing";

// VERCEL AI-SDK SETUP
import { experimental_createMCPClient as createMCPClient, generateText, streamText } from 'ai';
import { openai } from '@ai-sdk/openai';

dotenv.config();

const DATASET_PATH = '../../data/testset.csv';

/**
 * Create JWT auth token for MCP server authentication
 * @returns {Promise<string>} JWT token
 */
async function createAuthToken() {
  const privateKeyPem = process.env.MCP_PRIVATE_KEY;
  if (!privateKeyPem) {
    throw new Error('MCP_PRIVATE_KEY environment variable not set.');
  }

  try {
    // The private key might be in a single line in the .env file,
    // so we replace escaped newlines with actual newlines.
    const decodedKey = Buffer.from(privateKeyPem, 'base64').toString('utf8');
    const privateKey = await jose.importPKCS8(decodedKey, 'RS256');

    const jwt = await new jose.SignJWT({})
      .setProtectedHeader({ alg: 'RS256' })
      .setIssuedAt()
      .setIssuer('urn:notpatrick:client')
      .setAudience('urn:notpatrick:server')
      .setExpirationTime('1m')
      .sign(privateKey);

    return jwt;
  } catch (error) {
    console.error('Error creating auth token:', error);
    throw error;
  }
}

function init_sdk() {
	// LANGFUSE SETUP START
	const sdk = new NodeSDK({
		spanProcessors: [new LangfuseSpanProcessor()],
	});
	sdk.start();
	return sdk
}

/**
 * Load CSV dataset from file path using streaming parser
 * @param {string} path - Path to the CSV file
 * @returns {Promise<Array<Object>>} Array of objects representing CSV rows
 */
async function loadDataSet(path) {
	const rows = [];

	return new Promise((resolve, reject) => {
		// Check if file exists
		if (!fs.existsSync(path)) {
			reject(new Error(`CSV file not found: ${path}`));
			return;
		}

		fs.createReadStream(path)
			.pipe(parse({ 
				columns: true,        // Use first row as column headers
				skip_empty_lines: true, // Skip empty lines
				trim: true,           // Trim whitespace from values
				cast: true            // Auto-cast values (numbers, booleans)
			}))
			.on('data', (row) => {
				rows.push(row);
			})
			.on('end', () => {
				console.log(`✅ Loaded ${rows.length} rows from ${path}`);
				resolve(rows);
			})
			.on('error', (error) => {
				reject(new Error(`Failed to parse CSV: ${error.message}`));
			});
	});
}

const PROMPT = 'Use the ask_podcast tool to answer the question: What have been said about Activision in 2025?'

try {
	const sdk = init_sdk();
	console.log("Langfuse SDK initialized");

	// Load dataset
	const dataset = await loadDataSet(DATASET_PATH);
	const questions = dataset.map(row => row.user_input);
	console.log("Dataset loaded:", dataset.length, "rows");

	for (const question of questions) {
		let mcpClient = null;
		
		try {
			console.log("Starting client execution...");

			await startActiveObservation("Client Execution", async (rootSpan) => {
				console.log("Root span started:", rootSpan.id);

				const trace_id = getActiveTraceId();
				console.log("Current Trace ID:", trace_id);

				// Generate auth token for MCP client
				const authToken = await createAuthToken();
				console.log("Auth token generated");

				// Create MCP client with auth headers
				mcpClient = await createMCPClient({
				  transport: {
					type: 'sse',
					url: 'http://localhost:8080/sse',
					headers: {
						Authorization: `Bearer ${authToken}`,
						'trace-id': trace_id
					}
				  },
				});

				const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
				const response = await generateText({
				  apiKey: OPENAI_API_KEY,
				  model: openai('gpt-4o'),
				  tools: await mcpClient.tools(), // use MCP tools
				  maxSteps: 5,
				  // prompt: 'What tools do you have access to?',
				  prompt: question,
				  experimental_telemetry: { isEnabled: true },
				});

				rootSpan.update({ input: question });

				console.log(response.text)

				// var final_answer = "";
				// for await (const part of response.fullStream) {
				// 	if (part.type === 'text-delta') {
				// 		final_answer += part.textDelta;
				// 		process.stdout.write(part.textDelta);
				// 	} else if (part.type === 'tool-call') {
				// 		console.log(`\n[Tool Call] ${part.toolName}: ${JSON.stringify(part.args)}`);
				// 	} else if (part.type === 'tool-result') {
				// 		console.log(`\n[Tool Result] ${part.toolName}: ${JSON.stringify(part.result)}`);
				// 	}
				// }

				rootSpan.update({ output: response.text });

				console.log("\n\nDone")
				console.log(rootSpan.id)
			}, {
				input: { 
					prompt: question,
				},
			});
		} finally {
			// Always close the MCP client to avoid connection leaks
			if (mcpClient) {
				await mcpClient.close();
				console.log("MCP client closed");
			}
		}
	}

	await sdk.shutdown();

	process.exit(0);

} catch (error) {
	console.error("Error:", error);
	process.exit(1);
}
