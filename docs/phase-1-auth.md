# Phase 1: Project Scaffolding and User Authentication

**Visible result:** User can register, log in, log out, and view their profile in the browser.

---

## What This Phase Delivers

- Docker Compose running FastAPI + PostgreSQL.
- A `users` table with email, hashed password, and self-assessment fields.
- REST endpoints for register, login, token refresh, get current user, and update profile.
- A React frontend with login, register, and profile pages.
- JWT-based auth that survives page refreshes via refresh tokens stored in httpOnly cookies.

---

## Backend Work

### 1. Project skeleton

Create the `backend/` directory with the following files.

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Python 3.11-slim image. Installs system dependencies (`gcc`, `libpq-dev`), Python requirements, and runs Uvicorn. |
| `backend/requirements.txt` | FastAPI, uvicorn[standard], SQLAlchemy[asyncio], asyncpg, alembic, python-jose[cryptography], passlib[bcrypt], bcrypt, pydantic[email], pydantic-settings, httpx |
| `backend/alembic.ini` | Points to the migrations directory. Logging configured for Alembic and SQLAlchemy. |
| `backend/app/__init__.py` | Empty file that marks the directory as a package. |

### 2. Configuration

**`backend/app/config.py`** uses Pydantic `BaseSettings` to load values from environment variables (with `.env` file support):

```python
class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]
    # LLM keys are loaded here but not used until Phase 2
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
```

A single global `settings` instance is created at module level and imported everywhere.

### 3. Database setup

**`backend/app/db/session.py`** creates an async SQLAlchemy engine and session factory:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(settings.database_url, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

`echo=True` logs all SQL queries during development. `expire_on_commit=False` keeps ORM objects usable after a commit without re-querying.

**`backend/app/db/init_db.py`** runs on startup and calls `Base.metadata.create_all()` to create all tables. This is the development approach; in production, Alembic handles migrations.

### 4. User model

**`backend/app/models/user.py`** defines the SQLAlchemy 2.0 declarative base and the `User` ORM model.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key, auto-generated via `uuid.uuid4()` |
| `email` | VARCHAR(255) | Unique, indexed |
| `password_hash` | VARCHAR(255) | Bcrypt hash |
| `programming_level` | INTEGER | 1 to 5, default 3 |
| `maths_level` | INTEGER | 1 to 5, default 3 |
| `created_at` | TIMESTAMP | Server default via `func.now()` |

The `Base` class declared here is imported by all other models and by `init_db.py`.

### 5. User schemas

**`backend/app/schemas/user.py`** contains Pydantic v2 models:

- `UserCreate`: email (validated via `EmailStr`), password (minimum 8 characters), programming_level (optional, default 3, range 1 to 5), maths_level (optional, default 3, range 1 to 5).
- `UserLogin`: email, password.
- `UserProfile`: id, email, programming_level, maths_level, created_at. Uses `from_attributes = True` to map directly from ORM objects.
- `UserAssessment`: programming_level (range 1 to 5), maths_level (range 1 to 5). Used for the `PUT /api/auth/me` endpoint.
- `TokenResponse`: access_token, token_type (defaults to `"bearer"`).

### 6. Auth service

**`backend/app/services/auth_service.py`** contains pure business logic with no HTTP concerns:

- `hash_password(plain: str) -> str`: Hashes a plaintext password using bcrypt.
- `verify_password(plain: str, hashed: str) -> bool`: Verifies a plaintext password against a bcrypt hash.
- `create_access_token(user_id: str) -> str`: Creates a short-lived JWT (30 min by default). The payload includes `sub` (user ID), `exp` (expiry timestamp), and `token_type: "access"`.
- `create_refresh_token(user_id: str) -> str`: Creates a long-lived JWT (7 days by default). Same payload structure with `token_type: "refresh"`.
- `decode_token(token: str) -> dict`: Decodes and validates a JWT. Raises `ValueError` if the token is expired or invalid.

All tokens are signed with HS256 using the `jwt_secret_key` from settings.

### 7. Dependencies

**`backend/app/dependencies.py`**:

- `get_db()`: Async generator that yields an `AsyncSession` and closes it automatically.
- `get_current_user(credentials, db)`: Extracts the Bearer token from the `Authorization` header using FastAPI's `HTTPBearer` scheme. Decodes the token, checks that `token_type` is `"access"`, extracts the user ID from the `sub` claim, and loads the user from the database. Returns the `User` object or raises `401 Unauthorized`.

### 8. Auth router

**`backend/app/routers/auth.py`** is mounted at prefix `/api/auth`.

A helper function `set_refresh_cookie(response, refresh_token)` sets the refresh token as an httpOnly cookie with these properties:

| Property | Value | Notes |
|----------|-------|-------|
| `httponly` | `True` | Prevents JavaScript access |
| `secure` | `False` | Set to `True` in production with HTTPS |
| `samesite` | `"lax"` | CSRF protection |
| `path` | `"/api/auth"` | Cookie is only sent to auth endpoints |
| `max_age` | `604800` | 7 days in seconds |

**Endpoints:**

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/auth/register` | POST | Validates input, checks email uniqueness, hashes password, creates user, returns access token in body and sets refresh token cookie |
| `/api/auth/login` | POST | Validates credentials, returns access token in body and sets refresh token cookie |
| `/api/auth/refresh` | POST | Reads refresh token from cookie, validates it, verifies user still exists, generates a new access token, rotates the refresh token (issues a new one and sets a new cookie), returns new access token |
| `/api/auth/logout` | POST | Deletes the refresh token cookie |
| `/api/auth/me` | GET | Returns the current user's profile (requires Bearer token) |
| `/api/auth/me` | PUT | Updates programming_level and maths_level (requires Bearer token) |

The refresh token cookie is never exposed to JavaScript. The session survives page refreshes because the browser automatically sends the cookie, and `AuthContext` calls `/api/auth/refresh` on mount.

### 9. FastAPI app entry point

**`backend/app/main.py`**:

- Creates the FastAPI app with a `lifespan` async context manager. On startup it calls `init_db(engine)` to create tables. On shutdown it calls `engine.dispose()` to close the database connection pool.
- Configures CORS middleware with origins from settings and `allow_credentials=True`.
- Includes the auth router.
- Provides a `GET /health` endpoint that returns `{"status": "healthy"}` for readiness checks.

### 10. Alembic migration

For production, create the first migration for the `users` table:

```bash
alembic revision --autogenerate -m "create users table"
alembic upgrade head
```

During development, `init_db()` handles table creation on startup, so this step is optional.

### 11. Docker Compose

**`docker-compose.yml`** (project root):

- `db` service: PostgreSQL 15 with a named volume (`postgres_data`) for data persistence. Includes a health check using `pg_isready` (5 second interval, 5 retries). Exposed on port 5432.
- `backend` service: Builds from `backend/Dockerfile`, depends on `db` (waits for healthy status), loads `.env` file, mounts `./backend:/app` for live code reloading, runs Uvicorn with `--reload` on port 8000.

**`.env.example`** (project root): Template with all required environment variables including `DATABASE_URL`, `JWT_SECRET_KEY`, `CORS_ORIGINS`, and LLM API keys.

---

## Frontend Work

### 12. Project skeleton

Initialise with Vite:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install tailwindcss @tailwindcss/vite react-router-dom
```

This project uses **Tailwind CSS v4**, which does not require a separate `tailwind.config.js` file. Tailwind is loaded via the `@tailwindcss/vite` plugin in `vite.config.ts`.

| File | Purpose |
|------|---------|
| `frontend/vite.config.ts` | Vite config with React and Tailwind v4 plugins, API proxy to `localhost:8000`, WebSocket proxy, and `@` path alias |
| `frontend/src/index.css` | Single line: `@import "tailwindcss"` (Tailwind v4 syntax) |
| `frontend/src/main.tsx` | React entry point. Wraps `<App />` in `BrowserRouter` and `AuthProvider` |
| `frontend/src/App.tsx` | React Router setup with four routes (see Section 18) |

### 13. API layer

**`frontend/src/api/http.ts`**: A thin wrapper around `fetch` that manages JWT tokens.

- Stores the access token in memory (not localStorage, for security).
- Attaches the access token to every request as `Authorization: Bearer <token>`.
- Sets `Content-Type: application/json` automatically when a request body is present.
- Includes `credentials: "include"` on all requests so the browser sends httpOnly cookies.
- On a 401 response (except for auth endpoints), automatically calls `/api/auth/refresh`. If the refresh succeeds, retries the original request with the new token. If it fails, redirects to `/login`.
- Handles empty response bodies gracefully (e.g. the logout endpoint).

**`frontend/src/api/types.ts`**: TypeScript interfaces matching the backend schemas: `User`, `TokenResponse`, `LoginCredentials`, `RegisterData`, `UserAssessment`.

### 14. Auth context

**`frontend/src/auth/AuthContext.tsx`**:

React context providing: `user`, `login()`, `register()`, `logout()`, `updateProfile()`, `isLoading`.

- On mount, calls `/api/auth/refresh` to restore the session. If successful, stores the access token in memory and fetches the user profile via `GET /api/auth/me`. If it fails, the user remains logged out.
- `login()` sends credentials to `/api/auth/login`, stores the access token, and fetches the user profile.
- `register()` sends data to `/api/auth/register`, stores the access token, and fetches the user profile.
- `logout()` calls `/api/auth/logout`, then clears the in-memory token and user state.
- `updateProfile()` sends updated skill levels to `PUT /api/auth/me` and updates the local user state.

### 15. Auth pages

**`frontend/src/auth/LoginPage.tsx`**: Form with email and password fields. Calls `login()` from context. Redirects to `/profile` on success. Displays error messages in a red alert box. Submit button is disabled while the request is in progress.

**`frontend/src/auth/RegisterPage.tsx`**: Form with email, password, confirm password, and two range sliders for programming level (1 to 5) and maths level (1 to 5, labelled Beginner to Expert). Validates that the two passwords match and that the password is at least 8 characters before submitting. Calls `register()`. Redirects to `/profile` on success.

**`frontend/src/auth/ProtectedRoute.tsx`**: Wraps routes that require authentication. Shows a `LoadingSpinner` while the session check is in progress. If the user is not logged in, redirects to `/login` and preserves the original location so the user can be sent back after logging in.

### 16. Profile page

**`frontend/src/profile/ProfilePage.tsx`**: Displays the user's email (read-only) and "Member since" date. Provides range sliders for programming_level and maths_level. Calls `updateProfile()` on submit. Shows a green success message or a red error message after saving.

### 17. Shared components

**`frontend/src/components/Navbar.tsx`**: Top bar with the brand text "Guided Cursor: AI Coding Tutor" (teal colour, links to `/`). When logged in, shows disabled placeholder items for Chat ("Coming in Phase 2") and Modules ("Coming in Phase 3"), a Profile link, and a Logout button. When logged out, shows Login and Register links.

**`frontend/src/components/LoadingSpinner.tsx`**: A simple CSS spinner using Tailwind's `animate-spin` utility. Used by `ProtectedRoute` during session restoration.

### 18. Routing

**`frontend/src/App.tsx`** defines four routes:

| Path | Component | Auth required |
|------|-----------|---------------|
| `/login` | `LoginPage` | No |
| `/register` | `RegisterPage` | No |
| `/profile` | `ProfilePage` (wrapped in `ProtectedRoute`) | Yes |
| `/` | Redirects to `/profile` | No (redirect handles auth) |

---

## Verification Checklist

- [ ] `docker-compose up` starts the backend and database without errors.
- [ ] `GET /health` returns `{"status": "healthy"}`.
- [ ] `POST /api/auth/register` creates a user, returns an access token, and sets a refresh cookie.
- [ ] `POST /api/auth/login` returns an access token and sets a refresh cookie.
- [ ] `GET /api/auth/me` returns the user profile with a valid Bearer token.
- [ ] `PUT /api/auth/me` updates skill levels and returns the updated profile.
- [ ] `POST /api/auth/refresh` returns a new access token and rotates the refresh cookie.
- [ ] Frontend register form creates an account and redirects to the profile page.
- [ ] Frontend login form authenticates and redirects to the profile page.
- [ ] Refreshing the page does not log the user out (refresh token works).
- [ ] Clicking logout clears the session; protected pages redirect to login.
- [ ] Profile page displays user info and allows updating skill levels.
