# Phase 4: Robustness, Cost Control, Testing, and Monitoring

**Visible result:** The application runs reliably locally with rate limiting, cost caps, comprehensive error handling, tests passing, and structured logging.

**Prerequisite:** Phase 3 complete (full application working end-to-end).

---

## What This Phase Delivers

- Per-user rate limiting and concurrent connection limits.
- Daily usage caps with cost tracking.
- Comprehensive test suite for the pedagogy engine and API endpoints.
- Structured logging and health-check endpoints.
- Database index optimisation.

---

## 1. Rate Limiting and Resource Control

### Per-user rate limiting

Add a middleware or dependency in `backend/app/dependencies.py`:

- **Message rate limit:** Each user can send at most **20 messages per minute** across all their WebSocket connections. Enforced via an in-memory sliding window counter (dict of `user_id → list[timestamp]`). When exceeded, the WebSocket returns an error message instead of calling the LLM.
- **Concurrent connection limit:** Already introduced in Phase 2 (max 3 WebSocket connections per user). Verify it works correctly.

### Why in-memory, not Redis

For the MVP with a single backend process, an in-memory dict is sufficient and avoids adding infrastructure. If the application scales to multiple processes, replace with Redis. Document this as a known scaling limitation.

### Global rate limiting

As a safety net, add a **global limit of 200 LLM API calls per minute** across all users. This prevents runaway costs if the application is accidentally exposed to heavy traffic. Implemented as a simple counter in `llm_factory.py` that resets every 60 seconds.

---

## 2. Cost Control

### Per-user daily usage cap

Add a `daily_message_count` tracking mechanism:

1. Add a column `daily_message_count` and `daily_count_reset_at` to the `users` table (or a separate `usage` table).
2. Each time a user sends a message that triggers an LLM call, increment their count.
3. If the count exceeds the daily cap (default: **100 messages per day**), reject the message with a clear error: "You have reached your daily usage limit. It resets at midnight UTC."
4. Reset the count when `daily_count_reset_at` is in the past.

### Cost monitoring

Add a simple cost estimation:

- After each LLM response, estimate the cost based on input + output tokens and the provider's pricing (stored as constants in `config.py`).
- Log the estimated cost per request.
- Add an admin endpoint `GET /api/admin/usage` (protected by a simple admin key in env vars) that returns total estimated cost for the current day/week/month.

This is not a billing system — it is a visibility tool to prevent surprise bills.

---

## 3. Database Index Optimisation

Add these indexes (via Alembic migration) if not already present:

| Table | Index | Why |
|-------|-------|-----|
| `users` | Unique on `email` | Fast login lookups |
| `chat_sessions` | On `(user_id, session_type)` | List user's sessions |
| `chat_messages` | On `(session_id, created_at)` | Fetch recent messages in order |
| `learning_modules` | On `order` | Sort modules for listing |
| `user_module_progress` | Unique on `(user_id, module_id)` | Upsert progress |
| `user_module_progress` | On `user_id` | List all progress for a user |

---

## 4. Testing

### Test structure

```
backend/
├── tests/
│   ├── conftest.py          # Shared fixtures: test DB, test client, test user
│   ├── test_auth.py         # Auth endpoint tests
│   ├── test_chat.py         # Chat WebSocket tests
│   ├── test_modules.py      # Module endpoint tests
│   ├── test_progress.py     # Progress endpoint tests
│   ├── test_pedagogy.py     # Pedagogy engine unit tests
│   ├── test_context_builder.py  # Context builder unit tests
│   └── test_llm.py          # LLM abstraction tests (with mocked API)
```

### Key test cases

#### Pedagogy engine (`test_pedagogy.py`)

These are the most important tests in the project — they verify the core teaching logic:

1. **Hint escalation:** Send 5 messages with the same code hash. Assert hint levels go 1 → 2 → 3 → 4 → 5.
2. **Hint reset on new problem:** Send 3 messages, then change the code hash. Assert hint level resets to 1.
3. **Hint level cap:** Send 10 messages with the same hash. Assert hint level stays at 5 after the 5th.
4. **Student level adaptation:** Create student states with different programming/maths levels. Assert the system prompt contains the correct adaptation instructions.
5. **Error classification:** Pass various Python tracebacks. Assert correct error type classification (syntax, runtime, logic).
6. **Normalisation for hash:** Test that adding whitespace does not change the hash, but changing actual code does.

#### Context builder (`test_context_builder.py`)

1. **Token budget:** Provide 50 messages of history but set a low token limit. Assert only the most recent messages that fit are included.
2. **Notebook context injection:** Provide cell code and error output. Assert they appear in the assembled prompt.
3. **Empty history:** Assert the builder works with zero history messages.

#### Auth endpoints (`test_auth.py`)

1. Register a new user → 201.
2. Register with duplicate email → 409.
3. Login with correct credentials → 200 + token.
4. Login with wrong password → 401.
5. Access `/api/auth/me` with valid token → 200.
6. Access `/api/auth/me` with expired/invalid token → 401.
7. Refresh token flow → new access token.

#### Chat WebSocket (`test_chat.py`)

1. Connect with valid token → connection accepted.
2. Connect with invalid token → connection rejected (4001).
3. Send a message → receive streamed response (mock the LLM).
4. Message is stored in the database after response completes.
5. Exceed connection limit → connection rejected (4002).

### Test tooling

Add to `requirements.txt`: `pytest`, `pytest-asyncio`, `httpx` (for `TestClient`).

The LLM should be mocked in all tests using a simple `MockLLMProvider` that yields predetermined tokens.

---

## 5. Error Handling

### Backend

- All route handlers should catch exceptions and return structured error responses:
  ```json
  {"detail": "Human-readable error message", "code": "ERROR_CODE"}
  ```
- LLM failures (after retry + fallback exhausted) return a WebSocket message:
  ```json
  {"type": "error", "content": "The AI service is temporarily unavailable. Please try again in a moment."}
  ```
- Database connection failures trigger a 503 response.

### Frontend

- WebSocket disconnections show a banner: "Connection lost. Reconnecting..."
- LLM error messages from the backend are displayed in the chat as a system message (styled differently from AI messages).
- Network failures on REST calls show a toast notification.

---

## 6. Logging and Monitoring

### Structured logging

Use Python's built-in `logging` module with JSON formatting:

```python
import logging
logger = logging.getLogger("ai_tutor")
```

Log at minimum:
- Every LLM call: provider, model, input tokens, output tokens, estimated cost, latency, success/failure.
- Every WebSocket connection: user_id, connect/disconnect, duration.
- Every auth event: login success/failure, registration, token refresh.
- Every error: full traceback.

### Health-check endpoint

Add `GET /api/health` (no auth required):

```json
{
  "status": "ok",
  "database": "connected",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

This is used by Docker health checks and monitoring tools to verify the service is running.

---

## Verification Checklist

- [ ] Sending more than 20 messages in one minute returns a rate limit error.
- [ ] Sending more than 100 messages in one day returns a daily cap error.
- [ ] Opening a 4th browser tab with the chat rejects the WebSocket connection.
- [ ] All tests pass: `pytest backend/tests/ -v`.
- [ ] Pedagogy tests confirm hint escalation 1→2→3→4→5 and reset on new problem.
- [ ] The health endpoint returns 200 with status "ok".
- [ ] Backend logs show structured JSON entries for LLM calls with cost estimates.
- [ ] When the LLM API key is deliberately invalidated, the user sees a clear error message (not a crash).
- [ ] Database queries are fast (verify with `EXPLAIN ANALYZE` on key queries).
