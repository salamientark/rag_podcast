import { anthropic } from '@ai-sdk/anthropic';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { createOpenAI, openai } from '@ai-sdk/openai';
import { xai } from '@ai-sdk/xai';
import { customProvider, type LanguageModel } from 'ai';

/**
 * Models are chosen with environment variables, each holding a
 * `provider:model` spec, e.g. `CHAT_MODEL=google:gemini-3-flash-preview`.
 *
 * | Variable             | Role                                  |
 * |----------------------|---------------------------------------|
 * | CHAT_MODEL           | "Chat model" in the model selector    |
 * | CHAT_REASONING_MODEL | "Reasoning model" (default selection) |
 * | TITLE_MODEL          | Chat title generation                 |
 * | ARTIFACT_MODEL       | Document suggestions                  |
 *
 * The chat models must support tool calling: they call the podcast MCP tools.
 */
const DEFAULT_MODEL_SPECS = {
  'chat-model': 'openai:gpt-5.2',
  'chat-model-reasoning': 'openai:gpt-5.2',
  'title-model': 'anthropic:claude-haiku-4-5',
  'artifact-model': 'anthropic:claude-haiku-4-5',
} as const;

const MODEL_ENV_VARS = {
  'chat-model': 'CHAT_MODEL',
  'chat-model-reasoning': 'CHAT_REASONING_MODEL',
  'title-model': 'TITLE_MODEL',
  'artifact-model': 'ARTIFACT_MODEL',
} as const;

type ModelRole = keyof typeof DEFAULT_MODEL_SPECS;

/** Each provider reads its API key from the environment variable noted here. */
const PROVIDERS: Record<string, (modelId: string) => LanguageModel> = {
  // OPENAI_API_KEY
  openai: (modelId) => openai(modelId),
  // ANTHROPIC_API_KEY
  anthropic: (modelId) => anthropic(modelId),
  // GOOGLE_GENERATIVE_AI_API_KEY, or GEMINI_API_KEY as used by the backend
  google: (modelId) =>
    createGoogleGenerativeAI({
      apiKey:
        process.env.GOOGLE_GENERATIVE_AI_API_KEY ?? process.env.GEMINI_API_KEY,
    })(modelId),
  // XAI_API_KEY
  xai: (modelId) => xai(modelId),
  // DEEPSEEK_API_KEY (OpenAI-compatible API)
  deepseek: (modelId) =>
    createOpenAI({
      name: 'deepseek',
      baseURL: 'https://api.deepseek.com/v1',
      apiKey: process.env.DEEPSEEK_API_KEY,
      compatibility: 'compatible',
    })(modelId),
};

function resolveModel(role: ModelRole): LanguageModel {
  const envVar = MODEL_ENV_VARS[role];
  const spec = process.env[envVar]?.trim() || DEFAULT_MODEL_SPECS[role];
  const separator = spec.indexOf(':');
  const providerName = spec.slice(0, separator);
  const modelId = spec.slice(separator + 1);
  const createModel = PROVIDERS[providerName];

  if (separator < 1 || !modelId || !createModel) {
    throw new Error(
      `Invalid ${envVar}="${spec}". Expected "provider:model" with provider one of: ${Object.keys(PROVIDERS).join(', ')}.`,
    );
  }
  return createModel(modelId);
}

export const myProvider = customProvider({
  languageModels: {
    'chat-model': resolveModel('chat-model'),
    'chat-model-reasoning': resolveModel('chat-model-reasoning'),
    'title-model': resolveModel('title-model'),
    'artifact-model': resolveModel('artifact-model'),
  },
  imageModels: {
    'small-model': openai.image('dall-e-3'),
  },
});
