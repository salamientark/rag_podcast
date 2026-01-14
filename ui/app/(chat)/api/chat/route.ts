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

function logErrorAndEndSpan(rootSpan: ReturnType<typeof trace.getActiveSpan>, output: unknown) {
  updateActiveObservation({ output, level: 'ERROR' });
  updateActiveTrace({ name: 'ui.chat.request', output });
  rootSpan?.end();
}

function toChatErrorResponse(
  rootSpan: ReturnType<typeof trace.getActiveSpan>,
  output: unknown,
  errorCode: ConstructorParameters<typeof ChatSDKError>[0],
) {
  logErrorAndEndSpan(rootSpan, output);
  return new ChatSDKError(errorCode).toResponse();
}

function toLangfuseMessages(messages: Array<any>): Array<LangfuseMessage> {
  return messages.map((message) => ({
    role: message.role,
    parts: message.parts ?? [],
  }));
}

function logLangfuseInput({
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

function logLangfuseOutput(output: unknown) {
  updateActiveObservation({ output });
  updateActiveTrace({ output });
}

async function streamTextOnFinishHandler(
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

function createChatStream({
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

const handler = async (request: Request) => {
  after(async () => await langfuseSpanProcessor.forceFlush());
  const rootSpan = trace.getActiveSpan();

  let requestBody: PostRequestBody;

  try {
    const json = await request.json();
    requestBody = postRequestBodySchema.parse(json);
  } catch (error) {
    return toChatErrorResponse(rootSpan, error, 'bad_request:api');
  }

  try {
    const { id, message, selectedChatModel, selectedVisibilityType } =
      requestBody;

    const session = await auth();

    if (!session?.user) {
      return toChatErrorResponse(rootSpan, 'unauthorized', 'unauthorized:chat');
    }

    const userType: UserType = session.user.type;

    const messageCount = await getMessageCountByUserId({
      id: session.user.id,
      differenceInHours: 24,
    });

    if (messageCount > entitlementsByUserType[userType].maxMessagesPerDay) {
      return toChatErrorResponse(rootSpan, 'rate_limited', 'rate_limit:chat');
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
        return toChatErrorResponse(rootSpan, 'forbidden', 'forbidden:chat');
      }
    }

    const previousMessages = await getMessagesByChatId({ id });

    const messages = appendClientMessage({
      messages: previousMessages as any,
      message,
    });

    const langfuseMessages = toLangfuseMessages(messages);

    logLangfuseInput({
      chatId: id,
      userId: session.user.id,
      selectedChatModel,
      selectedVisibilityType,
      langfuseMessages,
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

    const stream = createChatStream({
      chatId: id,
      messages,
      selectedChatModel,
      session,
      userMessage: message,
      rootSpan,
    });

    return new Response(stream);
  } catch (error) {
    console.error('Chat API error:', error);

    logErrorAndEndSpan(rootSpan, error);

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
