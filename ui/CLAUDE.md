# CLAUDE.md — Codebase Documentation (for CodeRabbit / AI Review)

This repository contains a Next.js (App Router) web UI for a “Podcast AI” chat application. It combines:

- **Next.js App Router** (server components + route handlers)
- **AI SDK** (`ai`, `@ai-sdk/react`) for streaming chat + tool calls
- **NextAuth (Auth.js v5 beta)** for authentication (credentials + guest + OAuth)
- **Drizzle ORM + Postgres** for persistence (chats, messages, votes, documents/artifacts, suggestions, streams)
- **SWR** for client-side caching and optimistic updates
- **Artifacts UI** (text/code/image/sheet) rendered alongside chat, with versioning and diffing

This document is intended to help automated reviewers (CodeRabbit) and humans quickly understand the architecture, data flow, and where changes should be made safely.

---

## 1) High-level product behavior

### Core user experience

- Users chat with an AI assistant about a podcast.
- The assistant can call tools (via MCP server) to query podcast content, list episodes, fetch episode info, etc.
- The UI supports “Artifacts”: side-by-side documents (text/code/image/sheet) that can be created/updated by the assistant and edited by the user.
- Chats are persisted per user; guests have limited entitlements.

### Authentication modes

- **Guest**: auto-created user record with email like `guest-<timestamp>`. Guests can chat but have lower rate limits.
- **Regular**: email/password or OAuth (Google/Discord). Regular users have higher entitlements.

### Visibility

- Chats can be **private** or **public**.
- Private chats require the owner session to view.
- Public chats can be viewed by others (read-only).

---

## 2) Repository layout (UI)

Key directories (under `ui/`):

- `app/` — Next.js App Router pages and API route handlers
- `components/` — React UI components (chat, messages, artifacts, sidebar, etc.)
- `hooks/` — Client hooks (artifact state, scroll, visibility, auto-resume)
- `lib/` — Shared logic: AI tools, prompts, providers, DB schema/queries, utilities, errors
- `lib/db/migrations/` — Drizzle migrations + snapshots
- `tests/` — Playwright tests and helpers (not all files are included in chat, but referenced)

---

## 3) Data model (Drizzle / Postgres)

Defined in: `ui/lib/db/schema.ts`

### User

- `User(id uuid, email varchar(64), password varchar(64) nullable)`
- Guests are stored as normal users with special email pattern.

### Chat

- `Chat(id uuid, createdAt timestamp, title text, userId uuid, visibility varchar('public'|'private'))`

### Message (v2)

- `Message_v2(id uuid, chatId uuid, role varchar, parts json, attachments json, createdAt timestamp)`
- `parts` is the AI SDK “message parts” array (text, reasoning, tool-invocation, etc.)
- `attachments` is an array of AI SDK attachments (currently images)

> Note: There is also a deprecated `Message` table (`messageDeprecated`) used for older migrations.

### Vote (v2)

- `Vote_v2(chatId uuid, messageId uuid, isUpvoted boolean)`
- Composite PK: `(chatId, messageId)`

### Document (Artifacts)

- `Document(id uuid, createdAt timestamp, title text, content text nullable, kind varchar enum ['text','code','image','sheet'], userId uuid)`
- Composite PK: `(id, createdAt)` to support version history.

### Suggestion

- Suggestions are tied to a specific document version via `(documentId, documentCreatedAt)`.

### Stream

- `Stream(id uuid, chatId uuid, createdAt timestamp)`
- Used to track stream IDs (useful for resuming / telemetry / debugging).

---

## 4) Server-side API routes (Next.js route handlers)

### 4.1 Chat streaming endpoint

File: `ui/app/(chat)/api/chat/route.ts`

**POST** `/api/chat`

- Validates request body with Zod (`ui/app/(chat)/api/chat/schema.ts`).
- Authenticates via `auth()` from `ui/app/(auth)/auth.ts`.
- Enforces rate limits based on `entitlementsByUserType` (`ui/lib/ai/entitlements.ts`).
- Creates chat if missing:
  - Generates title via `generateTitleFromUserMessage` (`ui/app/(chat)/actions.ts`).
  - Saves chat with visibility.
- Loads previous messages from DB and appends the new user message.
- Persists the user message to DB (`saveMessages`).
- Creates a `streamId` record.
- Creates a streaming response using AI SDK `createDataStream` + `streamText`.
- Connects to MCP server via `experimental_createMCPClient` and exposes MCP tools to the model.
- Uses `podcastSystemPrompt` (`ui/lib/ai/prompts.ts`) as the system prompt.
- On finish:
  - Extracts assistant message ID from response messages.
  - Persists assistant message parts/attachments to DB.
  - Closes MCP client.

**DELETE** `/api/chat?id=<chatId>`

- Auth required; only owner can delete.
- Deletes votes/messages/streams then chat.

**GET** returns 204 (no-op).

#### Important notes for reviewers

- The server stores **message parts** (not `content`) in DB.
- The client uses `sendExtraMessageFields: true` and sends `parts` and attachments.
- Tool calls are handled by MCP tools; artifacts tools are separate (see below).

### 4.2 History pagination

File: `ui/app/(chat)/api/history/route.ts`

**GET** `/api/history?limit=...&starting_after=...&ending_before=...`

- Auth required.
- Returns `{ chats, hasMore }` from `getChatsByUserId`.
- Enforces that only one of `starting_after` or `ending_before` is provided.

Used by sidebar infinite scroll.

### 4.3 Votes

File: `ui/app/(chat)/api/vote/route.ts`

**GET** `/api/vote?chatId=...`

- Auth required; only owner can view votes for that chat.

**PATCH** `/api/vote`

- Body: `{ chatId, messageId, type: 'up'|'down' }`
- Auth required; only owner can vote.
- Updates/creates vote record.

### 4.4 Documents (Artifacts persistence)

File: `ui/app/(chat)/api/document/route.ts`

**GET** `/api/document?id=<documentId>`

- Auth required.
- Ensures the document belongs to the session user.
- Returns all versions (ordered by createdAt).

**POST** `/api/document?id=<documentId>`

- Auth required.
- Saves a new document version (or first version) with `{ title, content, kind }`.
- Enforces ownership if document already exists.

**DELETE** `/api/document?id=<documentId>&timestamp=<iso>`

- Auth required.
- Deletes document versions after timestamp (and related suggestions).
- Used by “Restore this version” flow.

### 4.5 Suggestions

File: `ui/app/(chat)/api/suggestions/route.ts`

**GET** `/api/suggestions?documentId=...`

- Auth required.
- Returns suggestions for that document, but checks ownership by inspecting the first suggestion’s `userId`.

### 4.6 File upload (attachments)

File: `ui/app/(chat)/api/files/upload/route.ts`

**POST** `/api/files/upload`

- Auth required (any session).
- Accepts multipart form-data with `file`.
- Validates:
  - size <= 5MB
  - type in `image/jpeg` or `image/png`
- Uploads to Vercel Blob via `put` with public access.
- Returns blob metadata including `url`, `pathname`, `contentType`.

---

## 5) Authentication (NextAuth)

### Main auth config

Files:

- `ui/app/(auth)/auth.ts`
- `ui/app/(auth)/auth.config.ts`

Providers:

- Google OAuth
- Discord OAuth (configured but UI may be commented in login page)
- Credentials (email/password)
- Credentials “guest” provider (creates guest user)

JWT callback:

- For credentials: sets `token.id` and `token.type`.
- For OAuth: ensures a DB user exists (creates if missing), sets `token.id`, `token.type='regular'`.

Session callback:

- Adds `session.user.id` and `session.user.type`.

Guest route:

- `ui/app/(auth)/api/auth/guest/route.ts`:
  - If already authenticated, redirect to `/`.
  - Otherwise `signIn('guest', redirectTo=redirectUrl)`.

Guest detection:

- `guestRegex` in `ui/lib/constants.ts` is `/^guest-\d+$/`.

---

## 6) Client-side architecture

### 6.1 Chat page entry points

- New chat: `ui/app/(chat)/page.tsx`
  - Generates a new UUID and renders `<Chat ... />` with empty messages.
- Existing chat: `ui/app/(chat)/chat/[id]/page.tsx`
  - Loads chat + messages from DB.
  - Enforces visibility rules:
    - If private: must be owner.
    - If public: can be read-only for non-owner.
  - Converts DB messages to UI messages (parts + attachments).

Both pages render:

- `<Chat ... />` (main UI)
- `<DataStreamHandler id={id} />` (artifact streaming deltas)

### 6.2 Main Chat component

File: `ui/components/chat.tsx`

Responsibilities:

- Uses `useChat` from `@ai-sdk/react` to manage messages, streaming status, and request sending.
- Uses `experimental_prepareRequestBody` to send:
  - `id` (chat id)
  - `message` (last user message)
  - `selectedChatModel`
  - `selectedVisibilityType`
- Handles guest auto-redirect:
  - If no session, redirect to `/api/auth/guest?redirectUrl=...` and preserve query.
- Updates sidebar history cache on finish via SWR `mutate(unstable_serialize(getChatHistoryPaginationKey))`.
- Loads votes via SWR when there are at least 2 messages.
- Manages attachments state for the input.
- Integrates `useAutoResume` to resume streaming if last message is user and `autoResume` is enabled.

### 6.3 Messages rendering

Files:

- `ui/components/messages.tsx`
- `ui/components/message.tsx`
- `ui/hooks/use-messages.tsx`
- `ui/hooks/use-scroll-to-bottom.tsx`

Key behaviors:

- `Messages` renders:
  - `<Greeting />` when no messages
  - `<PreviewMessage />` for each message
  - `<ThinkingMessage />` when user submitted and assistant hasn’t responded yet
- `PreviewMessage` supports:
  - Text parts (rendered via Markdown)
  - Reasoning parts (collapsible)
  - Tool invocations:
    - Weather tool UI
    - Document create/update/suggestions preview UIs
    - Poker solver UI
    - Podcast query / episode info / list episodes UIs
- User messages can be edited (if not read-only) via `MessageEditor`:
  - Deletes trailing messages in DB after the edited message timestamp
  - Updates local messages
  - Calls `reload()` to regenerate assistant response

Scroll behavior:

- `useScrollToBottom` uses SWR keys:
  - `messages:is-at-bottom`
  - `messages:should-scroll`
- `useMessages` resets scroll on chatId change and sets `hasSentMessage` on submit.

### 6.4 Sidebar and history

Files:

- `ui/components/app-sidebar.tsx`
- `ui/components/sidebar-history.tsx`
- `ui/components/sidebar-history-item.tsx`
- `ui/components/sidebar-user-nav.tsx`
- `ui/components/ui/sidebar.tsx`

History:

- Uses `useSWRInfinite` with `getChatHistoryPaginationKey`.
- Groups chats by date buckets (today/yesterday/last week/last month/older).
- Supports delete with confirmation dialog.
- Supports visibility toggling per chat via `useChatVisibility`.

User nav:

- Shows avatar and email (or “Guest”).
- Theme toggle.
- “Login to your account” for guests, “Sign out” for regular.

### 6.5 Visibility state

Files:

- `ui/components/visibility-selector.tsx`
- `ui/hooks/use-chat-visibility.ts`
- `ui/app/(chat)/actions.ts` (server action `updateChatVisibility`)

Mechanism:

- Local SWR key: `${chatId}-visibility`
- Also reads from cached `/api/history` data if present to keep sidebar and header consistent.
- Updates:
  - Optimistically updates local SWR
  - Mutates history pagination cache
  - Calls server action to persist

---

## 7) Artifacts system (Documents UI)

Artifacts are “documents” shown in a right-side panel (or inline preview) and can be created/updated by tools.

### 7.1 Artifact state store

File: `ui/hooks/use-artifact.ts`

- Uses SWR key `artifact` to store a `UIArtifact`:
  - `{ documentId, content, kind, title, status, isVisible, boundingBox }`
- Also stores per-document metadata under key `artifact-metadata-${documentId}`.

### 7.2 Artifact container

File: `ui/components/artifact.tsx`

Responsibilities:

- Renders the artifact overlay panel when `artifact.isVisible`.
- Fetches document versions via SWR:
  - `/api/document?id=${artifact.documentId}` when not streaming.
- Maintains:
  - `mode`: `'edit' | 'diff'`
  - `currentVersionIndex`
  - `document` (most recent)
  - `isContentDirty` and debounced saving
- Saving:
  - `handleContentChange` posts to `/api/document?id=...` to create a new version.
  - Debounced by 2 seconds via `useDebounceCallback`.
- Versioning:
  - `handleVersionChange('prev'|'next'|'toggle'|'latest')`
  - When viewing old version, shows `VersionFooter` with “Restore this version” (DELETE versions after timestamp).
- Renders artifact-specific content component from `artifactDefinitions`:
  - text/code/image/sheet artifacts (client definitions are imported from `@/artifacts/.../client` which are not included in this chat; treat as external modules).

### 7.3 Document preview in chat

File: `ui/components/document-preview.tsx`

- Used when the assistant calls `createDocument` tool.
- Shows a compact preview card; clicking opens the artifact panel.
- Fetches the document via `/api/document?id=...` when result exists.
- For streaming artifacts, uses current artifact state as a temporary document.

### 7.4 Artifact actions and toolbar

Files:

- `ui/components/artifact-actions.tsx`
- `ui/components/toolbar.tsx`
- `ui/components/create-artifact.tsx`

- `ArtifactActions` renders action buttons defined by the artifact kind.
- `Toolbar` is a floating tool palette shown in the artifact panel (only for current version).
- Tool actions append messages to chat (e.g., adjust reading level).

### 7.5 Artifact streaming deltas

File: `ui/components/data-stream-handler.tsx`

- Subscribes to `useChat({ id })` data stream.
- Processes new deltas since last index.
- For each delta:
  - Calls artifactDefinition.onStreamPart(...) for kind-specific handling.
  - Updates global artifact state for generic delta types:
    - `id`, `title`, `kind`, `clear`, `finish`
- Delta types include:
  - `text-delta`, `code-delta`, `sheet-delta`, `image-delta` (handled by artifact-specific code)
  - `suggestion` (also artifact-specific)
  - `finish` sets artifact status to idle

> Important: The artifact kind used to route `onStreamPart` is `artifact.kind` at the time of processing. The stream also sends a `kind` delta; ordering matters.

---

## 8) AI tools and prompts

### 8.1 Provider configuration

File: `ui/lib/ai/providers.ts`

- Uses `customProvider` to define:
  - `chat-model` (Anthropic Claude Sonnet)
  - `chat-model-reasoning` (OpenAI o3)
  - `title-model` (Claude Sonnet)
  - `artifact-model` (Claude Haiku)
  - `gpt` (OpenAI GPT-4o)
- Image model: DALL·E 3

### 8.2 Prompts

File: `ui/lib/ai/prompts.ts`

- `podcastSystemPrompt`: instructs tool usage for podcast queries and episode info.
- Also includes generic artifact prompts (used elsewhere in template; current chat route uses `podcastSystemPrompt`).

### 8.3 Artifact tools (server-side)

Files:

- `ui/lib/ai/tools/create-document.ts`
- `ui/lib/ai/tools/update-document.ts`
- `ui/lib/ai/tools/request-suggestions.ts`

These tools:

- Emit data stream events (`kind`, `id`, `title`, `clear`, `finish`, `suggestion`, etc.)
- Delegate to `documentHandlersByArtifactKind` (`ui/lib/artifacts/server.ts`) which:
  - Calls artifact-specific create/update logic (not included here)
  - Persists the resulting content to DB via `saveDocument`

### 8.4 Other tools

- Weather: `ui/lib/ai/tools/get-weather.ts`
- Poker solver: `ui/lib/ai/tools/poker-solver.ts` (calls external solver API with JWT auth)

---

## 9) Error handling

File: `ui/lib/errors.ts`

- Defines `ChatSDKError` with:
  - `type` (bad_request/unauthorized/forbidden/not_found/rate_limit/offline)
  - `surface` (chat/auth/api/stream/database/history/vote/document/suggestions)
  - `statusCode`
- `toResponse()`:
  - For `database` surface, logs details and returns generic message.
  - For others, returns `{ code, message, cause }`.

Client usage:

- `fetcher` and `fetchWithErrorHandlers` in `ui/lib/utils.ts` throw `ChatSDKError` when response is not ok.
- `Chat` component `useChat` `onError` shows toast for `ChatSDKError`.

---

## 10) UI components overview (selected)

### Greeting

File: `ui/components/greeting.tsx`

- French UI copy for initial empty chat state.

### Multimodal input

File: `ui/components/multimodal-input.tsx`

- Textarea with Enter-to-send (Shift+Enter for newline).
- Attachment upload pipeline:
  - Uploads to `/api/files/upload`
  - Stores attachments in state and sends via `experimental_attachments`
- Shows suggested actions when no messages and no attachments.
- Shows “scroll to bottom” button when not at bottom.

### Markdown rendering

File: `ui/components/markdown.tsx`

- Uses `react-markdown` + `remark-gfm`.
- Custom code block renderer (`ui/components/code-block.tsx`).

### Toasts

File: `ui/components/toast.tsx`

- Custom wrapper around `sonner` to render consistent toast UI.

---

## 11) Conventions and “gotchas” for reviewers

### 11.1 Message content vs parts

- DB stores `parts` (JSON) and attachments.
- UIMessage `content` is often empty in server-rendered conversion; rendering uses `parts`.
- When editing a user message, code updates both `content` and `parts` to keep UI consistent.

### 11.2 SWR cache keys

Common keys:

- `/api/history` (infinite pagination uses derived keys)
- `/api/vote?chatId=...`
- `/api/document?id=...`
- `artifact` (global artifact state)
- `artifact-metadata-${documentId}`
- `${chatId}-visibility`
- `messages:is-at-bottom`, `messages:should-scroll`

When changing behavior, ensure cache keys remain stable or update all call sites.

### 11.3 Visibility enforcement

- Server enforces ownership for:
  - history
  - votes
  - documents
- Chat page server component enforces private chat access.
- Public chats are read-only for non-owner; many UI actions check `isReadonly`.

### 11.4 Artifact streaming ordering

- `DataStreamHandler` routes deltas based on current `artifact.kind`.
- If a stream sends deltas before `kind`, the handler might route incorrectly.
- Artifact tools typically send `kind` early; keep this invariant if modifying tools.

### 11.5 Document versioning

- Every save creates a new row (version) in `Document` table.
- “Restore this version” deletes versions after a timestamp.
- Suggestions are tied to a specific document version; deleting versions also deletes suggestions after that version.

### 11.6 Rate limiting

- Enforced server-side in `/api/chat` based on message count in last 24 hours.
- Guests have lower limits.

---

## 12) How to run / test (UI)

From `ui/package.json`:

- `pnpm dev` — Next dev server (turbo)
- `pnpm build` / `pnpm start`
- `pnpm migrate` — runs Drizzle migrations via `tsx lib/db/migrate`
- `pnpm test` — Playwright tests (requires env vars)

Environment variables template: `ui/.env.example`

---

## 13) Review checklist (for CodeRabbit)

When reviewing changes, pay special attention to:

1. **Auth boundaries**
   - Any route handler must validate session and ownership where appropriate.
   - Guest flows should not accidentally grant access to private resources.

2. **Message persistence**
   - Ensure both user and assistant messages are saved with correct `parts` and `attachments`.
   - Avoid relying on deprecated `content` field.

3. **Streaming correctness**
   - `createDataStream` + `streamText` must always close MCP client.
   - `onFinish` should be resilient to missing IDs.

4. **Artifacts**
   - Document handler selection by `kind` must remain consistent.
   - Versioning logic should not corrupt history.

5. **SWR cache consistency**
   - If you change API response shapes, update all consumers and optimistic updates.

6. **Type safety**
   - Many places use `any` for tool results; consider tightening types when feasible, but ensure UI doesn’t break on unexpected tool output.

---

## 14) Key files index (quick map)

### Chat + streaming

- `app/(chat)/api/chat/route.ts` — main streaming endpoint
- `app/(chat)/api/chat/schema.ts` — request validation
- `components/chat.tsx` — client chat orchestration
- `components/messages.tsx`, `components/message.tsx` — rendering
- `hooks/use-auto-resume.ts` — resume logic

### Auth

- `app/(auth)/auth.ts` — NextAuth config
- `app/(auth)/api/auth/guest/route.ts` — guest sign-in redirect
- `components/auth-button.tsx` — login/signout button

### DB

- `lib/db/schema.ts` — Drizzle schema
- `lib/db/queries.ts` — DB access layer
- `lib/db/migrations/*` — migrations

### Artifacts

- `components/artifact.tsx` — artifact panel
- `components/document-preview.tsx` — inline preview
- `components/data-stream-handler.tsx` — stream delta handler
- `lib/ai/tools/create-document.ts`, `update-document.ts`, `request-suggestions.ts`
- `lib/artifacts/server.ts` — handler registry

### UI primitives

- `components/ui/*` — shadcn/radix wrappers

---

If you need deeper documentation for a specific subsystem (e.g., MCP tool contract, artifact handler implementations under `@/artifacts/*`), add those files to the chat and I’ll extend this document with their details.
