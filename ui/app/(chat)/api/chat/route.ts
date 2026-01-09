import {
  appendClientMessage,
  appendResponseMessages,
  createDataStream,
  experimental_createMCPClient as createMCPClient,
  generateText,
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
import { isProductionEnvironment } from '@/lib/constants';
import { myProvider } from '@/lib/ai/providers';
import { entitlementsByUserType } from '@/lib/ai/entitlements';
import { z } from 'zod';
import { postRequestBodySchema, type PostRequestBody } from './schema';
import { ChatSDKError } from '@/lib/errors';
import { createAuthToken } from '@/lib/mcp/auth';
// eslint-disable-next-line import/namespace -- prompts module is a plain-string prompt, not a namespace.
import { ALLOWED_PODCASTS, podcastSystemPrompt } from '@/lib/ai/prompts';

export const maxDuration = 60;

const gateSchema = z.object({
  scope: z.enum(['single', 'multi']),
  confidence: z.number().min(0).max(1).optional(),
});

type GateDecision = z.infer<typeof gateSchema>;

type PodcastName = (typeof ALLOWED_PODCASTS)[number];

function getTextFromParts(parts: Array<{ type: string; text?: string }> | undefined) {
  return (
    parts
      ?.filter((part) => part.type === 'text')
      .map((part) => part.text ?? '')
      .join('\n')
      .trim() ?? ''
  );
}

function getMessageText(message: { parts?: Array<{ type: string; text?: string }> }) {
  return getTextFromParts(message.parts);
}

function findPodcastInConversation(messages: Array<{ parts?: Array<{ type: string; text?: string }> }>):
  | PodcastName
  | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const text = getMessageText(messages[i]);
    for (const podcast of ALLOWED_PODCASTS) {
      if (text.includes(podcast)) return podcast;
    }
  }
  return null;
}

function extractFirstJsonObject(text: string): unknown {
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) {
    throw new Error('No JSON object found');
  }
  const jsonText = text.slice(firstBrace, lastBrace + 1);
  return JSON.parse(jsonText);
}

async function classifyScope(userText: string): Promise<GateDecision> {
  const system = `You are a strict classifier. Return JSON only.

Classify the user's request as:
- scope: "single" if answering requires content from one specific episode.
- scope: "multi" if answering requires content from multiple episodes.

Output format (JSON): {"scope":"single"|"multi","confidence":number}
Do not add any extra keys, prose, or code fences.`;

  const { text } = await generateText({
    model: myProvider.languageModel('classifier-model'),
    system,
    prompt: userText,
    temperature: 0,
    maxTokens: 50,
  });

  const parsed = gateSchema.safeParse(extractFirstJsonObject(text));
  if (!parsed.success) {
    // Safe fallback: treat as multi to avoid transcript spam.
    return { scope: 'multi', confidence: 0 };
  }

  return parsed.data;
}

export async function POST(request: Request) {
  let requestBody: PostRequestBody;

  try {
    const json = await request.json();
    requestBody = postRequestBodySchema.parse(json);
  } catch (_) {
    return new ChatSDKError('bad_request:api').toResponse();
  }

  try {
    const { id, message, selectedChatModel, selectedVisibilityType } =
      requestBody;

    const session = await auth();

    if (!session?.user)
      return new ChatSDKError('unauthorized:chat').toResponse();

    const userType: UserType = session.user.type;

    const messageCount = await getMessageCountByUserId({
      id: session.user.id,
      differenceInHours: 24,
    });

    if (messageCount > entitlementsByUserType[userType].maxMessagesPerDay) {
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
        return new ChatSDKError('forbidden:chat').toResponse();
      }
    }

    const previousMessages = await getMessagesByChatId({ id });

    const messages = appendClientMessage({
      // @ts-expect-error: todo add type conversion from DBMessage[] to UIMessage[]
      messages: previousMessages,
      message,
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

    const userText = getMessageText(message);
    const gateDecision = await classifyScope(userText);
    const conversationPodcast =
      findPodcastInConversation(messages) ?? 'Le rendez-vous Tech';

    const streamId = generateUUID();
    await createStreamId({ streamId, chatId: id });

    const stream = createDataStream({
      execute: async (dataStream) => {
        const authToken = await createAuthToken();

        const serverUrl = process.env.MCP_SERVER_URL;
        if (!serverUrl) {
          throw new Error('MCP_SERVER_URL environment variable is not set');
        }
        const mcpClient = await createMCPClient({
          transport: {
            type: 'sse',
            url: serverUrl,
            headers: {
              Authorization: `Bearer ${authToken}`,
            },
          },
        });

        const tools = await mcpClient.tools();

        const allowedToolNames =
          gateDecision.scope === 'multi'
            ? ['ask_podcast', 'list_episodes', 'get_episode_info']
            : ['get_episode_transcript', 'list_episodes', 'get_episode_info'];

        const gatedTools = Object.fromEntries(
          Object.entries(tools).filter(([toolName]) =>
            allowedToolNames.includes(toolName),
          ),
        );

		const systemPrompt = `${podcastSystemPrompt}

IMPORTANT: For this scope you will only have access to the following tools:
${Object.keys(gatedTools).map((name) => `- ${name}`).join('\n')}

Dont't try to use any other tools as those mentionned above.
`

        const result = streamText({
          model: myProvider.languageModel(selectedChatModel),
          messages,
          maxSteps: 15,
          system: systemPrompt,
          tools: gatedTools,
          experimental_activeTools: Object.keys(gatedTools),
          experimental_transform: smoothStream({ chunking: 'word' }),
          experimental_generateMessageId: generateUUID,
          onFinish: async ({ response }) => {
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
            await mcpClient.close();
          },
          experimental_telemetry: {
            isEnabled: isProductionEnvironment,
            functionId: 'stream-text',
          },
        });

        result.consumeStream();

        result.mergeIntoDataStream(dataStream, {
          sendReasoning: true,
        });
      },
      onError: () => {
        return 'Oops, an error occurred!';
      },
    });

    return new Response(stream);
  } catch (error) {
    console.error('Chat API error:', error);
    if (error instanceof ChatSDKError) {
      return error.toResponse();
    }
    return new Response(JSON.stringify({ error: 'Internal server error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

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
