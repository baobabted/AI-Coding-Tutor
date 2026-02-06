# Phase 2: AI Chat with Pedagogy Engine

**Visible result:** User can chat with an AI assistant. Responses stream in token-by-token. The AI uses graduated hints — first responses are guiding questions, later responses give more concrete help, and after five attempts on the same topic it gives the full answer.

**Prerequisite:** Phase 1 complete (auth system working).

---

## What This Phase Delivers

- `chat_sessions` and `chat_messages` database tables.
- An LLM abstraction layer supporting multiple providers with retry and fallback.
- A pedagogy engine that manages hint levels and student adaptation.
- A WebSocket endpoint (`/ws/chat`) that streams AI responses.
- A frontend chat page with message history, streaming display, and markdown rendering.

---

## Backend Work

### 1. Chat database models

**`backend/app/models/chat.py`** — Two models:

#### `ChatSession`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key → `users.id`, indexed |
| `session_type` | VARCHAR(20) | `"general"` or `"tutor"` |
| `module_id` | UUID | Nullable, FK → `learning_modules.id` (used in Phase 3) |
| `created_at` | TIMESTAMP | Server default |

**Indexes:** Index on `(user_id, session_type)`.

#### `ChatMessage`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `session_id` | UUID | Foreign key → `chat_sessions.id`, indexed |
| `role` | VARCHAR(10) | `"user"` or `"assistant"` |
| `content` | TEXT | Message body |
| `hint_level_used` | INTEGER | Nullable, 1–5 (set by pedagogy engine) |
| `notebook_context` | TEXT | Nullable (used in Phase 3) |
| `cell_code_hash` | VARCHAR(64) | Nullable, SHA-256 of the cell code at time of message (used for same-problem detection) |
| `created_at` | TIMESTAMP | Server default |

**Indexes:** Index on `session_id` + `created_at` (for efficient history retrieval).

### 2. Chat schemas

**`backend/app/schemas/chat.py`**:

- `ChatMessageIn`: content (str), notebook_context (optional str), cell_code_hash (optional str)
- `ChatMessageOut`: id, role, content, hint_level_used, created_at
- `ChatSessionOut`: id, session_type, created_at, messages (list)

### 3. Chat service

**`backend/app/services/chat_service.py`**:

- `create_session(user_id, session_type, module_id=None) -> ChatSession`
- `get_or_create_session(user_id, session_type, module_id=None) -> ChatSession` — Returns the most recent active session, or creates a new one.
- `add_message(session_id, role, content, hint_level=None, notebook_context=None, cell_code_hash=None)`
- `get_recent_messages(session_id, limit=20) -> list[ChatMessage]` — Returns the most recent N messages, ordered chronologically. The default limit of 20 balances context quality against token cost.
- `get_user_sessions(user_id, session_type) -> list[ChatSession]`

### 4. LLM abstraction layer

#### `backend/app/ai/llm_base.py` — Abstract interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class LLMProvider(ABC):
    @abstractmethod
    async def generate_stream(
        self,
        system_prompt: str,
        messages: list[dict],   # [{"role": "user"/"assistant", "content": "..."}]
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Yield response tokens one at a time."""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return approximate token count for the given text."""
        ...
```

#### `backend/app/ai/llm_anthropic.py` — Anthropic Claude implementation

- Uses `httpx` to call the Anthropic Messages API with `stream=True`.
- Reads streamed SSE events and yields content tokens.
- Implements `count_tokens` using a simple heuristic (chars / 4) or the `anthropic` tokeniser if available.
- **Retry logic:** On HTTP 429 (rate limit) or 5xx errors, retries up to 3 times with exponential backoff (1s, 2s, 4s). On timeout (30s default), retries once.
- **Error handling:** Raises a custom `LLMError` exception on unrecoverable failure.

#### `backend/app/ai/llm_openai.py` — OpenAI GPT implementation

- Same interface, calls the OpenAI Chat Completions API with `stream=True`.
- Same retry and error handling logic.

#### `backend/app/ai/llm_factory.py` — Provider selection and fallback

```python
def get_llm_provider(settings) -> LLMProvider:
    """Return the configured primary provider."""

async def get_llm_with_fallback(settings) -> LLMProvider:
    """Try primary provider; if unavailable, return fallback."""
```

- Reads `LLM_PROVIDER` from settings to determine the primary.
- If the primary raises `LLMError`, automatically creates and returns the secondary provider.
- If no secondary is configured (no API key), re-raises the error.

### 5. Token management

The context builder (see below) must ensure the total prompt fits within the model's context window. The approach:

1. Calculate tokens for the system prompt.
2. Calculate tokens for the current user message.
3. Fill remaining space with as many recent messages as fit, starting from the most recent.
4. If even the system prompt + current message exceeds the limit, truncate the current message.

**Configurable limits in `config.py`:**
- `LLM_MAX_CONTEXT_TOKENS`: default 8000 (conservative, works with all models)
- `LLM_MAX_RESPONSE_TOKENS`: default 2048
- `CHAT_HISTORY_LIMIT`: default 20 (max messages to fetch from DB before token filtering)

### 6. Pedagogy engine

**`backend/app/ai/pedagogy_engine.py`**:

#### Student state

```python
class StudentState:
    user_id: str
    programming_level: int      # 1–5, from user profile
    maths_level: int            # 1–5, from user profile
    current_hint_level: int     # 1–5, starts at 1
    attempt_count: int          # interactions on current problem
    current_code_hash: str      # hash of the cell code being discussed
```

#### Hint level escalation

| Attempt | Hint Level | Strategy |
|---------|-----------|----------|
| 1 | Socratic | Ask guiding questions only |
| 2 | Conceptual | Explain the underlying concept |
| 3 | Structural | Name relevant functions/approaches |
| 4 | Concrete | Give partial code or specific syntax |
| 5+ | Full answer | Provide the complete solution with explanation |

#### "Same problem" detection

This is critical to the pedagogy system working correctly. The approach:

1. Each user message can include a `cell_code_hash` — a SHA-256 hash of the current notebook cell code.
2. For general chat (no notebook), the hash is computed from the user's question text instead.
3. When a new message arrives, compare its hash to `current_code_hash` in the student state:
   - **Same hash:** The student is still working on the same problem. Increment `attempt_count`.
   - **Different hash:** The student has moved on. Reset `attempt_count` to 1 and update the hash.
4. The hint level is derived directly from `attempt_count` (capped at 5).

**Why hash-based, not cell-position-based:** A student might completely rewrite the code in the same cell. That is a different problem and should reset the counter. Conversely, making a tiny fix (adding a semicolon) should not reset the counter. The hash approach handles both cases correctly — small edits produce different hashes (resetting the counter), which is acceptable because the student is trying something new and deserves fresh guidance.

**Tolerance for minor edits:** To avoid resetting on trivial whitespace changes, the hash is computed on a normalised version of the code (stripped of leading/trailing whitespace, collapsed internal whitespace).

#### Error type classification

When notebook context includes an error traceback, the pedagogy engine classifies it before building the prompt. This is done by simple pattern matching on the traceback, not by the LLM:

- **SyntaxError, IndentationError** → syntax error
- **NameError, TypeError, AttributeError, IndexError, KeyError** → runtime error
- **No Python error but student says "wrong answer"** → logic error
- **Everything else** → general error

The classification is included in the system prompt so the LLM knows which teaching strategy to use (see prompts below).

#### Student level adaptation

The pedagogy engine passes the student's levels to the prompt builder. The prompt builder adjusts language accordingly:

| Profile | Adaptation |
|---------|-----------|
| Low programming (1–2) | Step-by-step explanations, no jargon, simple examples |
| High programming (4–5) | Concise, technical terms, algorithmic focus |
| Low maths (1–2) | Intuitive explanations, analogies, visual descriptions |
| High maths (4–5) | Formal notation, theorem references |

### 7. Prompts

**`backend/app/ai/prompts.py`** — All system prompts stored as string templates:

- `BASE_SYSTEM_PROMPT`: The tutor persona (applies to both chat and tutor modes).
- `HINT_LEVEL_INSTRUCTIONS[1..5]`: Instructions for each hint level.
- `PROGRAMMING_LEVEL_INSTRUCTIONS[1..5]`: Language adaptation for programming skill.
- `MATHS_LEVEL_INSTRUCTIONS[1..5]`: Language adaptation for maths skill.
- `ERROR_TYPE_INSTRUCTIONS`: Per-error-type teaching strategies.

These are concatenated by the context builder to form the final system prompt.

### 8. Context builder

**`backend/app/ai/context_builder.py`**:

```python
def build_messages(
    system_prompt_parts: list[str],
    chat_history: list[ChatMessage],
    current_message: str,
    notebook_context: str | None,   # used in Phase 3
    error_output: str | None,       # used in Phase 3
    token_counter: Callable,
    max_tokens: int,
) -> tuple[str, list[dict]]:
    """
    Returns (system_prompt, messages_list) that fits within max_tokens.

    1. Joins system_prompt_parts into one system prompt.
    2. Appends notebook context and error output to the current message (if present).
    3. Calculates token budget remaining after system prompt + current message.
    4. Fills in as many recent history messages as fit within the budget.
    """
```

### 9. Chat WebSocket endpoint

**`backend/app/routers/chat.py`** — `WebSocket /ws/chat`:

1. Client connects with JWT as query parameter: `/ws/chat?token=<access_token>`.
2. Backend validates the token. On failure, closes the connection with code 4001.
3. Backend loads or creates a chat session for the user.
4. Backend loads the student state (from user profile + recent message history).
5. On each message from the client:
   a. Parse the JSON message (`{content, cell_code_hash?}`).
   b. Store the user message in DB.
   c. Update student state (hint level, attempt count).
   d. Build the prompt via context builder.
   e. Call the LLM via `get_llm_with_fallback()`.
   f. Stream tokens back to the client as JSON: `{"type": "token", "content": "..."}`.
   g. On stream completion, send `{"type": "done"}`.
   h. Store the full assistant message in DB with the hint level used.
6. On disconnect, clean up.

**Connection limits:** Each user can have at most 3 concurrent WebSocket connections (to handle multiple tabs without excessive resource use). Enforced via an in-memory dict tracking active connections per user ID. Extra connections are rejected with code 4002.

### 10. Alembic migration

Create migration for `chat_sessions` and `chat_messages` tables.

---

## Frontend Work

### 11. WebSocket helper

**`frontend/src/api/ws.ts`**:

```typescript
function connectWebSocket(
  path: string,          // e.g. "/ws/chat"
  token: string,
  onToken: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): { send: (msg: object) => void, close: () => void }
```

- Constructs the WebSocket URL with the token as a query parameter.
- Handles automatic reconnection (up to 3 attempts with backoff) on unexpected disconnect.
- Parses incoming JSON messages and calls the appropriate callback.

### 12. Chat page

**`frontend/src/chat/ChatPage.tsx`** — Full-page layout:

- On mount, connects the WebSocket.
- Displays message history (loaded from the WebSocket's initial messages or a REST endpoint).
- Renders the streaming AI response in real time.

**`frontend/src/chat/ChatMessageList.tsx`** — Scrollable container for messages. Auto-scrolls to the bottom when new content arrives.

**`frontend/src/chat/ChatInput.tsx`** — Text input with a send button. Disabled whilst the AI is responding. Supports Shift+Enter for newlines, Enter to send.

**`frontend/src/chat/ChatBubble.tsx`** — Renders a single message. User messages are plain text. AI messages are rendered as markdown.

### 13. Markdown renderer

**`frontend/src/components/MarkdownRenderer.tsx`** — Renders markdown content with:

- Code blocks with syntax highlighting (use a lightweight library like `react-syntax-highlighter` or `highlight.js`).
- Inline code, bold, italic, lists, links.
- LaTeX/maths rendering if needed (can be added later).

### 14. Update routing

Update `App.tsx` to add the `/chat` route (protected). Update `Navbar.tsx` to link to it.

---

## Verification Checklist

- [ ] Opening the chat page establishes a WebSocket connection (check browser dev tools).
- [ ] Sending a message produces a streamed AI response (tokens appear one by one).
- [ ] The AI's first response to a new topic is a guiding question (hint level 1).
- [ ] Asking follow-up questions on the same topic escalates the hint level.
- [ ] After 5 attempts on the same topic, the AI gives a complete answer.
- [ ] Asking about a different topic resets the hint counter.
- [ ] Refreshing the page shows the previous chat history.
- [ ] AI responses render as formatted markdown (code blocks, bold, etc.).
- [ ] If the primary LLM is unavailable (simulate by setting a wrong API key), the system falls back to the secondary provider (or returns a clear error if none configured).
- [ ] Opening more than 3 tabs with the chat page causes the extra connections to be rejected.
