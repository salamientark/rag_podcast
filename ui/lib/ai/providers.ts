import { customProvider } from 'ai';
import { openai } from '@ai-sdk/openai';
import { anthropic } from '@ai-sdk/anthropic';
// import { google } from '@ai-sdk/google';

export const myProvider = customProvider({
  languageModels: {
    // 'chat-model': openai('gpt-5.2'),
    // 'chat-model-reasoning': openai('gpt-5.2'),
    // 'title-model': openai('gpt-5-nano'),
    // 'artifact-model': openai('gpt-5-nano'),
    'chat-model': anthropic('claude-haiku-4-5'),
    'chat-model-reasoning': anthropic('claude-haiku-4-5'),
    'title-model': anthropic('claude-haiku-4-5'),
    'artifact-model': anthropic('claude-haiku-4-5'),
  },
  imageModels: {
    'small-model': openai.image('dall-e-3'),
  },
});
