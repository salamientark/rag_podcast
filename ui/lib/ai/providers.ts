import { customProvider } from 'ai';
import { openai } from '@ai-sdk/openai';
import { anthropic } from '@ai-sdk/anthropic';
// import { google } from '@ai-sdk/google';

export const myProvider = customProvider({
  languageModels: {
    'chat-model': openai('gpt-5.2'),
    'chat-model-reasoning': openai('gpt-5.2'),
    'title-model': openai('gpt-5-nano'),
    'artifact-model': openai('gpt-5-nano'),
  },
  imageModels: {
    'small-model': openai.image('dall-e-3'),
  },
});
