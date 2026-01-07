import { customProvider } from 'ai';
import { openai } from '@ai-sdk/openai';
import { anthropic } from '@ai-sdk/anthropic';
// import { google } from '@ai-sdk/google';

export const myProvider = customProvider({
  languageModels: {
    'chat-model': openai('gpt-5.2'),
    // 'chat-model': anthropic('claude-4-sonnet-20250514'),
    // 'chat-model-reasoning': anthropic('claude-opus-4-20250514'),
    'chat-model-reasoning': openai('gpt-5.2'),
    // 'chat-model-reasoning': google('gemini-2.5-pro'),
    'title-model': anthropic('claude-4-sonnet-20250514'),
    'artifact-model': anthropic('claude-3-5-haiku-latest'),
    gpt: openai('gpt-5.2'),
    // 'title-model': openai('gpt-4o'),
    // 'artifact-model': openai('gpt-3.5-turbo'),
  },
  imageModels: {
    'small-model': openai.image('dall-e-3'),
  },
});
