# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Next.js AI chatbot application built with the AI SDK, featuring multiple AI model providers, real-time chat, and artifact generation. The project uses xAI's Grok-2 as the default model but supports OpenAI, Anthropic, and other providers.

## Key Technologies

- **Next.js 15** with App Router and React 19 RC
- **AI SDK** for LLM integration with streaming responses
- **Drizzle ORM** with PostgreSQL for data persistence
- **Auth.js** for authentication (email/password, Google, Discord)
- **Vercel Blob** for file storage
- **shadcn/ui** components with Tailwind CSS
- **Biome** for linting and formatting (instead of ESLint/Prettier)
- **Playwright** for E2E testing

## Development Commands

```bash
# Install dependencies
pnpm install

# Development server with Turbo
pnpm dev

# Build and production
pnpm build
pnpm start

# Linting and formatting
pnpm lint              # Next.js lint + Biome lint with auto-fix
pnpm lint:fix          # Force fix all linting issues
pnpm format            # Format code with Biome

# Database operations
pnpm db:generate       # Generate Drizzle migrations
pnpm db:migrate        # Run migrations with drizzle-kit
pnpm db:studio         # Open Drizzle Studio
pnpm db:push           # Push schema changes directly
pnpm migrate           # Custom migration script (tsx lib/db/migrate)

# Testing
pnpm test              # Run Playwright tests (sets PLAYWRIGHT=True env)
```

## Project Architecture

### Core Structure

- `/app` - Next.js App Router with route groups:
  - `(auth)` - Authentication routes and logic
  - `(chat)` - Main chat interface and API routes
- `/lib` - Shared utilities and core logic
- `/components` - React components (UI + business logic)
- `/artifacts` - Artifact generation system (code, text, images, sheets)
- `/hooks` - Custom React hooks

### Key Systems

**Chat System (`/app/(chat)` + `/lib/ai`)**
- Streaming chat responses via AI SDK
- Multiple model provider support (xAI, OpenAI, Anthropic)
- Real-time message handling with optimistic updates
- Chat history persistence with visibility controls

**Artifact Generation (`/artifacts`)**
- Code execution and preview (client/server components)
- Image generation and editing
- Text document creation
- Spreadsheet functionality
- All artifacts have client and server implementations

**Database Layer (`/lib/db`)**
- Drizzle ORM with PostgreSQL
- Migration system in `/lib/db/migrations`
- Schema evolution (Message_v2 replaces deprecated Message table)
- User, Chat, Message, Vote, and Document models

**Authentication (`/app/(auth)`)**
- Auth.js configuration in `auth.config.ts` and `auth.ts`
- Multiple providers: credentials, Google, Discord
- Guest user support via `/api/auth/guest`

### Important Files

- `lib/ai/models.ts` - Model configuration and selection
- `lib/ai/providers.ts` - AI provider implementations
- `lib/ai/prompts.ts` - System prompts and instructions
- `lib/db/schema.ts` - Database schema definitions
- `biome.jsonc` - Code formatting and linting rules
- `drizzle.config.ts` - Database configuration

## Environment Setup

Copy `.env.example` to `.env.local` and configure:
- `AUTH_SECRET` - Random 32-character secret
- `POSTGRES_URL` - PostgreSQL connection string
- `BLOB_READ_WRITE_TOKEN` - Vercel Blob storage token
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` - AI provider keys
- OAuth credentials for Google/Discord
- Optional: `REDIS_URL`, `MCP_API_URL`, `MCP_SECRET`

## Testing

Playwright tests are organized in `/tests`:
- `/tests/e2e` - End-to-end user flows
- `/tests/routes` - API route testing
- Tests require the development server running (`pnpm dev`)
- Test database and environment setup handled automatically

## Code Conventions

- Use Biome for all formatting/linting (configured in `biome.jsonc`)
- TypeScript strict mode enabled
- React Server Components preferred where possible
- Server Actions for data mutations
- Zod schemas for API validation
- Database queries in `/lib/db/queries.ts`

## AI Model Integration

Models are abstracted through the AI SDK with provider-specific implementations in `lib/ai/providers.ts`. The default model configuration uses a generic "chat-model" identifier that maps to the actual provider model in the implementation layer.