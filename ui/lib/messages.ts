import {
  appendResponseMessages,
  createDataStream,
  experimental_createMCPClient as createMCPClient,
  smoothStream,
  streamText,
} from 'ai';
import { saveMessages } from '@/lib/db/queries';
import { generateUUID, getTrailingMessageId } from '@/lib/utils';
import { trace } from '@opentelemetry/api';
import {
  updateActiveObservation,
  updateActiveTrace,
} from '@langfuse/tracing';
import { ChatSDKError } from '@/lib/errors';
import { createAuthToken } from '@/lib/mcp/auth';
// eslint-disable-next-line import/namespace -- prompts module is a plain-string prompt, not a namespace.
import { podcastSystemPrompt } from '@/lib/ai/prompts';

export interface LangfuseMessage {
  role: string;
  parts: unknown[];
}

export function logErrorAndEndSpan(rootSpan: ReturnType<typeof trace.getActiveSpan>, output: unknown) {
  updateActiveObservation({ output, level: 'ERROR' });
  updateActiveTrace({ name: 'ui.chat.request', output });
  rootSpan?.end();
}

export function toChatErrorResponse(
  rootSpan: ReturnType<typeof trace.getActiveSpan>,
  output: unknown,
  errorCode: ConstructorParameters<typeof ChatSDKError>[0],
) {
  logErrorAndEndSpan(rootSpan, output);
  return new ChatSDKError(errorCode).toResponse();
}

export function toLangfuseMessages(messages: Array<any>): Array<LangfuseMessage> {
  return messages.map((message) => ({
    role: message.role,
    parts: message.parts ?? [],
  }));
}

export function logLangfuseInput({
  chatId,
  userId,
  selectedChatModel,
  selectedVisibilityType,
  langfuseMessages,
}: {
  chatId: string;
  userId: string;
  selectedChatModel: string;
  selectedVisibilityType: string;
  langfuseMessages: Array<LangfuseMessage>;
}) {
  const input = {
    messages: langfuseMessages,
    system: podcastSystemPrompt,
    selectedChatModel,
  };

  updateActiveObservation({ input });

  updateActiveTrace({
    name: 'ui.chat.request',
    sessionId: chatId,
    userId,
    input,
    metadata: {
      selectedVisibilityType,
    },
  });
}

export function logLangfuseOutput(output: unknown) {
  updateActiveObservation({ output });
  updateActiveTrace({ output });
}

export async function streamTextOnFinishHandler(
	response: any,
	chatId: string,
	session: any,
	userMessage: any,
	rootSpan: ReturnType<typeof trace.getActiveSpan>)
{
  const langfuseResponseMessages = response.messages.map(
    (msg: any) => ({
  	role: msg.role,
  	parts: msg.parts,
    }),
  );
  
  logLangfuseOutput(langfuseResponseMessages);
  
  if (session.user?.id) {
  	const assistantId = getTrailingMessageId({
  	  messages: response.messages.filter(
  		(message) => message.role === 'assistant',
  	  ),
  	});
  
  	if (!assistantId) throw new Error('No message ID found!');
  
  	const [, assistantMessage] = appendResponseMessages({
  	  messages: [userMessage],
  	  responseMessages: response.messages,
  	});
  
  	await saveMessages({
  	  messages: [
  		{
  		  id: assistantId,
  		  chatId: chatId,
  		  role: assistantMessage.role,
  		  parts: assistantMessage.parts,
  		  attachments:
  			assistantMessage.experimental_attachments ?? [],
  		  createdAt: new Date(),
  		},
  	  ],
  	});
  }
}

export function createChatStream({
  chatId,
  messages,
  selectedChatModel,
  session,
  userMessage,
  rootSpan,
}: {
  chatId: string;
  messages: Array<any>;
  selectedChatModel: string;
  session: any;
  userMessage: any;
  rootSpan: ReturnType<typeof trace.getActiveSpan>;
}) {
  return createDataStream({
    execute: async (dataStream) => {
      let mcpClient: Awaited<ReturnType<typeof createMCPClient>> | null = null;
      try {
        const authToken = await createAuthToken();

        const serverUrl = process.env.MCP_SERVER_URL;
        if (!serverUrl) {
          throw new Error('MCP_SERVER_URL environment variable is not set');
        }

        mcpClient = await createMCPClient({
          transport: {
            type: 'sse',
            url: serverUrl,
            headers: {
              Authorization: `Bearer ${authToken}`,
            },
          },
        });

        try {
          const tools = await mcpClient.tools();
          const result = streamText({
            model: myProvider.languageModel(selectedChatModel),
            messages,
            maxSteps: 15,
            system: podcastSystemPrompt,
            tools,
            experimental_activeTools: Object.keys(tools),
            experimental_transform: smoothStream({ chunking: 'word' }),
            experimental_generateMessageId: generateUUID,
            onFinish: async ({ response }) => {
			  try {
				streamTextOnFinishHandler(
					response,
					chatId,
					session,
					userMessage,
					rootSpan
				);
			  } catch (e) {
			    console.error(e);
			    console.error('Failed to save chat :/');
			  } finally {
			    rootSpan?.end();
			    if (mcpClient) await mcpClient.close();
			  }
    //           try {
    //             const langfuseResponseMessages = response.messages.map(
    //               (msg: any) => ({
    //                 role: msg.role,
    //                 parts: msg.parts,
    //               }),
    //             );
				//
    //             logLangfuseOutput(langfuseResponseMessages);
				//
    //             if (session.user?.id) {
    //                 const assistantId = getTrailingMessageId({
    //                   messages: response.messages.filter(
    //                     (message) => message.role === 'assistant',
    //                   ),
    //                 });
				//
    //                 if (!assistantId) throw new Error('No message ID found!');
				//
    //                 const [, assistantMessage] = appendResponseMessages({
    //                   messages: [userMessage],
    //                   responseMessages: response.messages,
    //                 });
				//
    //                 await saveMessages({
    //                   messages: [
    //                     {
    //                       id: assistantId,
    //                       chatId: chatId,
    //                       role: assistantMessage.role,
    //                       parts: assistantMessage.parts,
    //                       attachments:
    //                         assistantMessage.experimental_attachments ?? [],
    //                       createdAt: new Date(),
    //                     },
    //                   ],
    //                 });
    //             }
			 //  } catch (e) {
				// console.error(e);
				// console.error('Failed to save chat :/');
    //           } finally {
    //             rootSpan?.end();
    //             if (mcpClient) await mcpClient.close();
    //           }
            },
            experimental_telemetry: {
              isEnabled: true,
              functionId: 'stream-text',
            },
          });

          result.consumeStream();

          result.mergeIntoDataStream(dataStream, {
            sendReasoning: true,
          });
        } catch (streamError) {
          await mcpClient.close();
          throw streamError;
        }
      } catch (error) {
        logErrorAndEndSpan(rootSpan, error);
        if (mcpClient) {
          await mcpClient.close();
        }
        throw error;
      }
    },
    onError: () => {
      return 'Oops, an error occurred!';
    },
  });
}
