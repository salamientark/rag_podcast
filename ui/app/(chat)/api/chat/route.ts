import {
  appendClientMessage,
  appendResponseMessages,
  createDataStream,
  experimental_createMCPClient as createMCPClient,
  smoothStream,
  streamText,
} from 'ai';
import { auth, type UserType } from '@/app/(auth)/auth';
import {
  createStreamId,
  deleteChatById,
  getChatById,
  getMessageCountByUserId,
  getMessagesByChatId,
  saveChat,
  saveMessages,
} from '@/lib/db/queries';
import { generateUUID, getTrailingMessageId } from '@/lib/utils';
import { generateTitleFromUserMessage } from '../../actions';
import { after } from 'next/server';
import { trace } from '@opentelemetry/api';
import {
  observe,
  updateActiveObservation,
  updateActiveTrace,
} from '@langfuse/tracing';
import { langfuseSpanProcessor } from '@/instrumentation';
import { myProvider } from '@/lib/ai/providers';
import { entitlementsByUserType } from '@/lib/ai/entitlements';
import { postRequestBodySchema, type PostRequestBody } from './schema';
import { ChatSDKError } from '@/lib/errors';
import { createAuthToken } from '@/lib/mcp/auth';
// eslint-disable-next-line import/namespace -- prompts module is a plain-string prompt, not a namespace.
import { podcastSystemPrompt } from '@/lib/ai/prompts';

export const runtime = 'nodejs';
export const maxDuration = 60;

interface LangfuseMessage {
  role: string;
  parts: unknown[];
}


const handler = async (request: Request) => {
  after(async () => await langfuseSpanProcessor.forceFlush());
  const rootSpan = trace.getActiveSpan();

  let requestBody: PostRequestBody;

  try {
    const json = await request.json();
    requestBody = postRequestBodySchema.parse(json);
  } catch (error) {
    updateActiveObservation({ output: error, level: 'ERROR' });
    updateActiveTrace({ name: 'ui.chat.request', output: error });
    rootSpan?.end();
    return new ChatSDKError('bad_request:api').toResponse();
  }

  try {
    const { id, message, selectedChatModel, selectedVisibilityType } =
      requestBody;

    const session = await auth();

    if (!session?.user) {
      updateActiveObservation({ output: 'unauthorized', level: 'ERROR' });
      updateActiveTrace({ name: 'ui.chat.request', output: 'unauthorized' });
      rootSpan?.end();
      return new ChatSDKError('unauthorized:chat').toResponse();
    }

    const userType: UserType = session.user.type;

    const messageCount = await getMessageCountByUserId({
      id: session.user.id,
      differenceInHours: 24,
    });

    if (messageCount > entitlementsByUserType[userType].maxMessagesPerDay) {
      updateActiveObservation({ output: 'rate_limited', level: 'ERROR' });
      updateActiveTrace({ name: 'ui.chat.request', output: 'rate_limited' });
      rootSpan?.end();
      return new ChatSDKError('rate_limit:chat').toResponse();
    }

    const chat = await getChatById({ id });

    if (!chat) {
      const title = await generateTitleFromUserMessage({
        message,
      });

      await saveChat({
        id,
        userId: session.user.id,
        title,
        visibility: selectedVisibilityType,
      });
    } else {
      if (chat.userId !== session.user.id) {
        updateActiveObservation({ output: 'forbidden', level: 'ERROR' });
        updateActiveTrace({ name: 'ui.chat.request', output: 'forbidden' });
        rootSpan?.end();
        return new ChatSDKError('forbidden:chat').toResponse();
      }
    }

    const previousMessages = await getMessagesByChatId({ id });

    const messages = appendClientMessage({
      // @ts-expect-error: todo add type conversion from DBMessage[] to UIMessage[]
      messages: previousMessages,
      message,
    });

	const langfuseMessages: LangfuseMessage[] = messages.map((msg) => ({
	  role: msg.role,
	  parts: msg.parts,
	}));

    updateActiveObservation({
      input: {
        messages: langfuseMessages,
        system: podcastSystemPrompt,
        selectedChatModel,
      },
    });

    updateActiveTrace({
      name: 'ui.chat.request',
      sessionId: id,
      userId: session.user.id,
      input: {
        messages: langfuseMessages,
        system: podcastSystemPrompt,
        selectedChatModel,
      },
      metadata: {
        selectedVisibilityType,
      },
    });

    await saveMessages({
      messages: [
        {
          chatId: id,
          id: message.id,
          role: 'user',
          parts: message.parts,
          attachments: message.experimental_attachments ?? [],
          createdAt: new Date(),
        },
      ],
    });

    const streamId = generateUUID();
    await createStreamId({ streamId, chatId: id });

    const stream = createDataStream({
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
                  const langfuseResponseMessages = response.messages.map(
                    (msg: any) => ({
                      role: msg.role,
                      parts: msg.parts,
                    }),
                  );

                  updateActiveObservation({ output: langfuseResponseMessages });
                  updateActiveTrace({ output: langfuseResponseMessages });

                  if (session.user?.id) {
                    try {
                      const assistantId = getTrailingMessageId({
                        messages: response.messages.filter(
                          (message) => message.role === 'assistant',
                        ),
                      });

                      if (!assistantId) throw new Error('No message ID found!');

                      const [, assistantMessage] = appendResponseMessages({
                        messages: [message],
                        responseMessages: response.messages,
                      });

                      await saveMessages({
                        messages: [
                          {
                            id: assistantId,
                            chatId: id,
                            role: assistantMessage.role,
                            parts: assistantMessage.parts,
                            attachments:
                              assistantMessage.experimental_attachments ?? [],
                            createdAt: new Date(),
                          },
                        ],
                      });
                    } catch (e) {
                      console.error(e);
                      console.error('Failed to save chat :/');
                    }
                  }
                } finally {
                  rootSpan?.end();
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
          updateActiveObservation({ output: error, level: 'ERROR' });
          updateActiveTrace({ name: 'ui.chat.request', output: error });
          rootSpan?.end();
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

    return new Response(stream);
  } catch (error) {
    console.error('Chat API error:', error);

    updateActiveObservation({ output: error, level: 'ERROR' });
    updateActiveTrace({ name: 'ui.chat.request', output: error });
    rootSpan?.end();

    if (error instanceof ChatSDKError) {
      return error.toResponse();
    }
    return new Response(JSON.stringify({ error: 'Internal server error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
};

export const POST = observe(handler, {
  name: 'ui.chat.request',
  endOnExit: false,
});

export async function GET(_: Request) {
  return new Response(null, { status: 204 });
}

export async function DELETE(request: Request) {
  const { searchParams } = new URL(request.url);
  const id = searchParams.get('id');

  if (!id) {
    return new ChatSDKError('bad_request:api').toResponse();
  }

  const session = await auth();

  if (!session?.user) {
    return new ChatSDKError('unauthorized:chat').toResponse();
  }

  const chat = await getChatById({ id });

  if (chat.userId !== session.user.id) {
    return new ChatSDKError('forbidden:chat').toResponse();
  }

  const deletedChat = await deleteChatById({ id });

  return Response.json(deletedChat, { status: 200 });
}
