# Phase 4: Testing, Hardening, and Cost Control

**Prerequisite:** Phase 3 complete (modules and workspace working end to end).

**Visible result:** The application runs reliably with rate limiting, a comprehensive automated test suite, structured logging, and cost visibility. All tests pass in CI.

---

## What This Phase Delivers

- Per-user message rate limiting and concurrent WebSocket connection limits.
- Cost estimation per LLM call with an admin visibility endpoint.
- An automated test suite covering auth, chat, pedagogy, context building, modules, and progress.
- Structured JSON logging for all significant events.
- Improved error handling on both frontend and backend.

**Already complete from Phase 2 (not repeated here):** Daily token usage tracking (`daily_token_usage` table), health check endpoint (`GET /api/health/ai`), and database indexes on `users.email`, `chat_sessions(user_id, session_type)`, `chat_messages(session_id, created_at)`, and `daily_token_usage(user_id, date)`.

---

## 1. Rate Limiting

### Per-user message rate limit

Add a rate limiter in `backend/app/dependencies.py` or as a utility used by the WebSocket endpoints.

Each user may send at most **20 messages per minute** across all their WebSocket connections. The limiter uses an in-memory sliding window: a dictionary mapping each `user_id` to a list of message timestamps. On each message, expired timestamps (older than 60 seconds) are pruned. If 20 or more timestamps remain, the message is rejected with a WebSocket error:

```json
{"type": "error", "message": "Rate limit reached. Please wait before sending another message."}
```

### Global LLM rate limit

As a cost safety net, add a **global limit of 200 LLM API calls per minute** across all users. This is a simple counter in `backend/app/ai/llm_factory.py` that resets every 60 seconds. If the counter is exceeded, the WebSocket returns an error instead of calling the LLM.

### Why in-memory

For a single-process deployment, an in-memory dictionary is sufficient and avoids introducing Redis as a dependency. If the application later scales to multiple backend processes, replace the in-memory store with Redis. Note this as a known limitation in the code comments.

---

## 2. Concurrent WebSocket Connection Limit

Add connection tracking in `backend/app/routers/chat.py` (and `tutor.py`).

Maintain an in-memory dictionary mapping each `user_id` to a set of active WebSocket connection IDs. On connect, check the set size. If it is already 3 or more, reject the new connection:

```python
await websocket.close(code=4002, reason="Too many connections")
```

On disconnect, remove the connection ID from the set. This allows students to use multiple browser tabs (up to 3) without creating excessive server load.

---

## 3. Cost Visibility

### Per-request cost estimation

Add provider pricing constants to `backend/app/config.py`:

```python
LLM_PRICING = {
    "anthropic": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "google":    {"input_per_mtok": 2.00, "output_per_mtok": 12.00},
    "openai":    {"input_per_mtok": 1.75, "output_per_mtok": 14.00},
}
```

After each LLM response, calculate the estimated cost:

```
cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
```

Log the estimate alongside the LLM call details (see Section 7).

### Admin usage endpoint

**`GET /api/admin/usage`** (protected by an `ADMIN_API_KEY` environment variable checked via a header).

Returns aggregated usage data:

```json
{
  "today": {"requests": 142, "input_tokens": 285000, "output_tokens": 310000, "estimated_cost_usd": 0.52},
  "this_week": {"requests": 890, "input_tokens": 1780000, "output_tokens": 1950000, "estimated_cost_usd": 3.28},
  "this_month": {"requests": 3200, "input_tokens": 6400000, "output_tokens": 7000000, "estimated_cost_usd": 11.80}
}
```

This is not a billing system. It is a visibility tool that helps prevent surprise bills during development and early deployment.

---

## 4. Automated Test Suite

### Test infrastructure

**`backend/tests/conftest.py`**

Shared fixtures for all test files:

- **Async test database.** Create an in-memory SQLite database (using `aiosqlite`) or spin up a test PostgreSQL instance. Run `Base.metadata.create_all()` before each test session. Roll back transactions between tests.
- **Test HTTP client.** Use `httpx.AsyncClient` with `app=app` for testing REST endpoints without starting a real server.
- **Authenticated user fixture.** Register a test user, obtain an access token, and provide both the user object and the token as fixtures.
- **`MockLLMProvider`.** A mock implementation of `LLMProvider` that yields a list of predetermined tokens from `generate_stream()` and returns fixed counts from `count_tokens()`. Accepts configurable responses so each test can specify what the "AI" says.
- **`MockEmbeddingService`.** Returns fixed embedding vectors. Allows tests to control greeting, off-topic, and same-problem detection outcomes without calling a real embedding API.

**Test dependencies** (add to `requirements.txt` under a `[test]` section or directly):
- `pytest`
- `pytest-asyncio`
- `aiosqlite` (if using SQLite for tests)

`httpx` is already in `requirements.txt`.

### `test_auth.py` (7 test cases)

| # | Test | Expected |
|---|------|----------|
| 1 | `test_register_new_user` | POST `/api/auth/register` with valid data returns 200 and an access token. |
| 2 | `test_register_duplicate_email` | POST `/api/auth/register` with an already-used email returns 400 with "Email already registered". |
| 3 | `test_login_correct_credentials` | POST `/api/auth/login` returns 200 and an access token. Response sets a refresh cookie. |
| 4 | `test_login_wrong_password` | POST `/api/auth/login` with incorrect password returns 401. |
| 5 | `test_get_profile_with_valid_token` | GET `/api/auth/me` with a valid Bearer token returns the user profile including email and username. |
| 6 | `test_get_profile_with_invalid_token` | GET `/api/auth/me` with an expired or malformed token returns 401. |
| 7 | `test_refresh_token_flow` | POST `/api/auth/refresh` with a valid refresh cookie returns a new access token and rotates the refresh cookie. |

### `test_chat.py` (6 test cases)

All tests use `MockLLMProvider` and `MockEmbeddingService` to avoid external API calls.

| # | Test | Expected |
|---|------|----------|
| 1 | `test_websocket_connect_valid_token` | Connect to `/ws/chat?token=<valid>`. Connection is accepted. |
| 2 | `test_websocket_connect_invalid_token` | Connect to `/ws/chat?token=invalid`. Connection is closed with code 4001. |
| 3 | `test_send_message_receives_stream` | Send a message via WebSocket. Receive one or more `token` events followed by a `done` event. The assembled tokens match the mock response. |
| 4 | `test_message_persisted_in_database` | After receiving a `done` event, query the `chat_messages` table. Both the user message and the assistant response are present. |
| 5 | `test_daily_limit_blocks_messages` | Set the user's daily token usage to the maximum. Send a message. Receive an error event containing "Daily token limit reached". |
| 6 | `test_session_listing` | After sending a message, call GET `/api/chat/sessions`. The response includes the new session with a preview matching the first 80 characters of the user's message. |

### `test_pedagogy.py` (6 test cases)

These are the most important tests in the project. They verify the core teaching logic.

| # | Test | Expected |
|---|------|----------|
| 1 | `test_hint_escalation` | Configure `MockEmbeddingService` so that same-problem detection returns True on every message. Send 5 messages. Assert hint levels are 1, 2, 3, 4, 5. |
| 2 | `test_hint_reset_on_new_problem` | Send 3 messages (same problem). Then configure the mock so the next message is detected as a new problem. Assert the hint level returns to the calculated starting level. |
| 3 | `test_hint_cap_at_five` | Send 7 messages on the same problem. Assert the hint level reaches 5 and stays at 5 for messages 6 and 7. |
| 4 | `test_greeting_returns_canned_response` | Configure `MockEmbeddingService.check_greeting()` to return True. Call `process_message()`. Assert the result has `filter_result="greeting"` and `canned_response` contains the student's username. |
| 5 | `test_off_topic_returns_rejection` | Configure `MockEmbeddingService.check_off_topic()` to return True. Call `process_message()`. Assert the result has `filter_result="off_topic"`. |
| 6 | `test_ema_level_update` | Create a `StudentState` with `effective_programming_level=3.0`. Simulate completing a problem at difficulty 4 with hint level 2. Run `_update_effective_levels()`. Assert the new level equals `3.0 * 0.8 + 3.2 * 0.2 = 3.04`. |

### `test_context_builder.py` (3 test cases)

| # | Test | Expected |
|---|------|----------|
| 1 | `test_token_budget_truncation` | Provide 50 messages of history totalling well above the token budget. Assert the returned list contains only the current message and the most recent messages that fit within the budget. |
| 2 | `test_compression_triggers` | Provide a history that exceeds 80% of the budget. Mock the LLM to return a summary string. Assert the output starts with a summary message followed by recent messages and the current message. |
| 3 | `test_empty_history` | Call `build_context_messages()` with an empty history list. Assert the output is a single-element list containing only the current user message. |

### `test_modules.py` (3 test cases, requires Phase 3)

| # | Test | Expected |
|---|------|----------|
| 1 | `test_list_modules` | Seed 3 modules. GET `/api/modules` returns all three in order. |
| 2 | `test_get_module_by_id` | GET `/api/modules/{id}` with a valid ID returns the module details. |
| 3 | `test_get_nonexistent_module` | GET `/api/modules/{random_uuid}` returns 404. |

### `test_progress.py` (3 test cases, requires Phase 3)

| # | Test | Expected |
|---|------|----------|
| 1 | `test_update_creates_record` | PUT `/api/progress/{module_id}` for a module the user has not started. A new record is created with the provided status. |
| 2 | `test_update_existing_record` | PUT `/api/progress/{module_id}` with `notebook_state`. The existing record is updated. |
| 3 | `test_get_unstarted_progress` | GET `/api/progress/{module_id}` for a module with no record. Returns a default response with status `"not_started"`. |

### `test_llm.py` (3 test cases)

| # | Test | Expected |
|---|------|----------|
| 1 | `test_mock_provider_yields_tokens` | Create a `MockLLMProvider` with tokens `["Hello", " world"]`. Iterate `generate_stream()`. Collect output and assert it equals `"Hello world"`. |
| 2 | `test_factory_returns_configured_provider` | Set `LLM_PROVIDER=anthropic` with a key. Call `get_llm_provider()`. Assert the returned instance is `AnthropicProvider`. |
| 3 | `test_factory_fallback` | Set `LLM_PROVIDER=anthropic` with no Anthropic key but a valid OpenAI key. Call `get_llm_provider()`. Assert the returned instance is `OpenAIProvider`. |

### Running the tests

```bash
cd backend
pytest tests/ -v --asyncio-mode=auto
```

The `test_semantic_thresholds.py` file in the same directory is a manual calibration script (not a pytest test). It is run separately:

```bash
cd backend
python -m tests.test_semantic_thresholds
```

---

## 5. Error Handling

### Backend

All route handlers catch exceptions and return structured error responses:

```json
{"detail": "Human-readable error message", "code": "ERROR_CODE"}
```

Standard error codes:

| Code | Meaning |
|------|---------|
| `AUTH_INVALID` | Token is missing, expired, or malformed |
| `AUTH_FORBIDDEN` | User does not own the requested resource |
| `RATE_LIMITED` | Message rate limit exceeded |
| `DAILY_LIMIT` | Daily token budget exhausted |
| `LLM_UNAVAILABLE` | All LLM providers failed after retry |
| `NOT_FOUND` | Resource does not exist |
| `VALIDATION` | Request body failed Pydantic validation |

LLM failures (after retry and fallback are exhausted) send a WebSocket message:

```json
{"type": "error", "message": "The AI service is temporarily unavailable. Please try again in a moment."}
```

Database connection failures return HTTP 503.

### Frontend

- **WebSocket disconnection:** A banner appears at the top of the chat area: "Connection lost. Reconnecting..." The frontend attempts to reconnect automatically with exponential backoff (1, 2, 4, 8 seconds, up to 3 retries).
- **LLM errors from the backend:** Displayed as a system message in the chat, styled differently from user and assistant messages (e.g. amber background).
- **REST call failures:** A toast notification appears briefly at the top of the page with the error message.

---

## 6. Structured Logging

Use Python's built-in `logging` module with a JSON formatter. Configure in `backend/app/main.py` at startup.

```python
import logging
logger = logging.getLogger("ai_tutor")
```

Log the following events at minimum:

| Event | Fields |
|-------|--------|
| LLM call | provider, model, input_tokens, output_tokens, estimated_cost, latency_ms, success (bool) |
| WebSocket connect | user_id, session_id, timestamp |
| WebSocket disconnect | user_id, session_id, duration_seconds |
| Auth event | event_type (login, register, refresh, logout), user_id, success (bool) |
| Error | logger name, level, message, full traceback |

In development, also log to stdout in a human-readable format. In production (detected via an environment variable), log as structured JSON.

---

## 7. Database Index Audit

The following indexes already exist from Phase 2 migrations. Do not recreate them.

| Table | Index | Created in |
|-------|-------|------------|
| `users` | Unique on `email` | Migration 001 |
| `users` | On `username` | Migration 002 |
| `chat_sessions` | On `(user_id, session_type)` | Migration 002 |
| `chat_messages` | On `(session_id, created_at)` | Migration 002 |
| `daily_token_usage` | Unique on `(user_id, date)` | Migration 002 |

Add these indexes for Phase 3 tables (via the Phase 3 Alembic migration):

| Table | Index | Why |
|-------|-------|-----|
| `learning_modules` | On `order` | Sort modules for listing |
| `user_module_progress` | Unique on `(user_id, module_id)` | Upsert progress |
| `user_module_progress` | On `user_id` | List all progress for a student |

---

## Verification Checklist

- [ ] Sending more than 20 messages in one minute returns a rate limit error.
- [ ] Opening a 4th browser tab with the chat page rejects the WebSocket connection with code 4002.
- [ ] All tests pass: `pytest backend/tests/ -v --asyncio-mode=auto`.
- [ ] Pedagogy tests confirm hint escalation 1, 2, 3, 4, 5 and reset on new problem.
- [ ] The health endpoint at `/api/health/ai` returns 200.
- [ ] Backend logs show structured JSON entries for LLM calls with cost estimates.
- [ ] When the LLM API key is deliberately invalidated, the user sees a clear error message (not a crash or traceback).
- [ ] The admin usage endpoint returns accurate daily token totals.
- [ ] Database queries on indexed columns complete in under 10ms (verify with `EXPLAIN ANALYZE`).
