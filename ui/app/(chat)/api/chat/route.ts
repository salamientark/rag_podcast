import {appendClientMessage } from 'ai';
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
import {
	LangfuseMessage,
	logErrorAndEndSpan,
	toChatErrorResponse,
	toLangfuseMessages,
	logLangfuseInput,
	logLangfuseOutput,
	streamTextOnFinishHandler,
	createChatStream,
} from '@/lib/messages';
import { generateUUID } from '@/lib/utils';
import { generateTitleFromUserMessage } from '../../actions';
import { after } from 'next/server';
import { trace } from '@opentelemetry/api';
import { observe } from '@langfuse/tracing';
import { langfuseSpanProcessor } from '@/instrumentation';
import { entitlementsByUserType } from '@/lib/ai/entitlements';
import { postRequestBodySchema, type PostRequestBody } from './schema';
import { ChatSDKError } from '@/lib/errors';
// eslint-disable-next-line import/namespace -- prompts module is a plain-string prompt, not a namespace.

export const runtime = 'nodejs';
export const maxDuration = 60;


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
