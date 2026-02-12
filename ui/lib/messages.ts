import {
  appendResponseMessages,
  createDataStream,
  experimental_createMCPClient as createMCPClient,
  smoothStream,
  streamText,
  type CoreAssistantMessage,
  type CoreToolMessage,
} from 'ai';
import { saveMessages } from '@/lib/db/queries';
import { generateUUID, getTrailingMessageId } from '@/lib/utils';
import { myProvider } from '@/lib/ai/providers';
import { ChatSDKError } from '@/lib/errors';
import { createAuthToken } from '@/lib/mcp/auth';
// eslint-disable-next-line import/namespace -- prompts module is a plain-string prompt, not a namespace.
import { podcastSystemPrompt } from '@/lib/ai/prompts';

export function logErrorAndEndSpan(
  output: unknown,
) {
  // No-op for now as tracing is removed
  console.error(output);
}

export function toChatErrorResponse(
  output: unknown,
  errorCode: ConstructorParameters<typeof ChatSDKError>[0],
) {
  logErrorAndEndSpan(output);
  return new ChatSDKError(errorCode).toResponse();
}

export async function streamTextOnFinishHandler(
  response: any,
  chatId: string,
  session: any,
  userMessage: any,
): Promise<void> {

  if (session.user?.id) {
    const assistantId = getTrailingMessageId({
      messages: response.messages.filter(
        (message: (CoreToolMessage | CoreAssistantMessage) & { id: string }) =>
          message.role === 'assistant',
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
          attachments: assistantMessage.experimental_attachments ?? [],
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
}: {
  chatId: string;
  messages: Array<any>;
  selectedChatModel: string;
  session: any;
  userMessage: any;
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
                await streamTextOnFinishHandler(
                  response,
                  chatId,
                  session,
                  userMessage,
                );
              } catch (e) {
                console.error(e);
                console.error('Failed to save chat :/');
              } finally {
                if (mcpClient) await mcpClient.close();
              }
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
        logErrorAndEndSpan(error);
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
