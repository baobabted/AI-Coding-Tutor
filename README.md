<p align="center">
  <img src="docs/logo.svg" alt="Guided Cursor logo" width="120" />
</p>

<h1 align="center">Guided Cursor</h1>
<p align="center"><strong>AI Coding Tutor</strong></p>

<p align="center">
  A web application that helps students learn numerical computing. Instead of giving answers immediately, the AI tutor uses a pedagogy engine with graduated hints, guiding students from Socratic questions through to full solutions. Communication style adapts to the student's self-assessed programming and mathematics ability.
</p>

---

## Development Status

| Phase | Milestone                            | Status   | Guide                                                 |
| ----- | ------------------------------------ | -------- | ----------------------------------------------------- |
| 1     | Auth System                          | Complete | [docs/phase-1-auth.md](docs/phase-1-auth.md)             |
| 2A    | AI Chat and Pedagogy Engine          | Complete | [docs/phase-2-chat.md](docs/phase-2-chat.md)             |
| 2B    | File and Image Uploads               | Complete | [docs/phase-2-chat.md](docs/phase-2-chat.md) (Section 5) |
| 3     | Learning Modules and Workspace       | Planned  | [docs/phase-3-workspace.md](docs/phase-3-workspace.md)   |
| 4     | Testing, Hardening, and Cost Control | Planned  | [docs/phase-4-robustness.md](docs/phase-4-robustness.md) |
| 5     | Production Deployment                | Planned  | [docs/phase-5-deployment.md](docs/phase-5-deployment.md) |

Additional reference: [docs/semantic-recognition-testing.md](docs/semantic-recognition-testing.md) records the calibration data for the embedding-based pre-filters.

## Curriculum Coverage

The learning modules (Phase 3) will cover four core topics from the **UCL PHAS0029** Computational Physics course:

- **Linear Algebra**: matrix operations, eigenvalue problems, decompositions
- **Root-Finding Methods**: bisection, Newton-Raphson, secant method
- **Numerical Methods for ODEs**: initial value problems (Euler, Runge-Kutta) and boundary value problems (shooting method, finite differences)
- **Fourier Transforms**: discrete Fourier transform, FFT, spectral analysis

## Features

### Implemented (Phase 1, 2A, and 2B)

- **Graduated Hints**: the AI tutor escalates from Socratic questions to conceptual nudges, structural outlines, concrete examples, and finally full solutions. A complete answer is never given on the first response.
- **Adaptive Student Levels**: hidden effective levels (floating-point, 1.0 to 5.0) update dynamically using an exponential moving average after each completed problem. These levels control the communication style independently from the hint level.
- **Embedding-Based Pre-Filters**: user messages are classified via cosine similarity against pre-embedded anchors before reaching the LLM. Greetings and off-topic messages are handled instantly with no LLM cost. Same-problem detection and elaboration requests control hint escalation.
- **Three-Provider LLM Failover**: supports Anthropic Claude, Google Gemini, and OpenAI GPT with automatic fallback if the primary provider is unavailable.
- **Streaming Responses**: AI responses stream token by token over a WebSocket connection.
- **File and Image Uploads**: users can attach files directly in chat (drag and drop, file picker, or paste screenshots).
- **Attachment Limits per Message**: up to 3 photos and 2 files per message, with clear validation errors when limits are exceeded.
- **Document Parsing**: document context is extracted from PDF, TXT, PY, JS, TS, CSV, and IPYNB uploads before LLM generation.
- **Secure Attachment Access**: uploaded files are served only through authenticated endpoints tied to the current user.
- **Markdown, Code, and LaTeX Rendering**: assistant messages render with syntax-highlighted code blocks and KaTeX formula display.
- **Session Persistence**: chat history and skill assessments are saved per user. Sessions survive page refreshes via httpOnly refresh token cookies.
- **Daily Token Limits**: each user has a daily budget of 50,000 input tokens and 50,000 output tokens, displayed as a usage percentage on the profile page.

### Planned (Phase 3 onwards)

- **JupyterLite Workspace**: in-browser Python notebooks (WebAssembly) with no server-side computation required.
- **Context-Aware Module Tutor**: a tutor panel alongside the notebook that can see the student's code and error output.
- **Rate Limiting and Cost Control**: per-user message rate limits, global LLM call limits, and an admin cost visibility endpoint.
- **Automated Test Suite**: pytest-based tests covering auth, chat, pedagogy, and module endpoints.
- **Production Deployment**: Docker, Nginx, HTTPS, CI/CD, database backups.

## Tech Stack

| Layer      | Tools                                                                    |
| ---------- | ------------------------------------------------------------------------ |
| Frontend   | React 18, TypeScript (strict), Vite, Tailwind CSS v4                     |
| Backend    | FastAPI, Uvicorn, SQLAlchemy 2.0 (async), Alembic, Pydantic v2           |
| Auth       | python-jose (JWT), passlib + bcrypt                                      |
| AI         | Anthropic Claude, Google Gemini, OpenAI GPT (configurable with failover) |
| Embeddings | Cohere embed-v4.0 (primary), Voyage AI voyage-multimodal-3.5 (fallback)  |
| Database   | PostgreSQL 15 with asyncpg                                               |
| DevOps     | Docker, Docker Compose                                                   |

## Architecture

```
Frontend (React + TypeScript + Vite + Tailwind)
  ├── Auth pages (login, register, profile, change password)
  ├── Chat page (WebSocket, streaming, session sidebar)
  └── [Phase 3] Module list + Workspace (JupyterLite + Tutor)
         │
         │  REST + WebSocket (JWT auth)
         ▼
Backend (FastAPI, async Python)
  ├── Auth API (JWT access tokens + httpOnly refresh cookies)
  ├── Chat API (REST for sessions/usage, WebSocket for streaming)
  ├── [Phase 3] Module + Progress API
  └── AI subsystem
       ├── LLM abstraction (3 providers, retry + fallback)
       ├── Embedding service (Cohere/Voyage, pre-filter pipeline)
       ├── Pedagogy engine (graduated hints, difficulty classification, EMA levels)
       └── Context builder (system prompt assembly, token-aware compression)
         │
         ▼
PostgreSQL (users, chat sessions, messages, daily usage, [Phase 3] modules, progress)
```

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- [Node.js](https://nodejs.org/) 18+
- Git

### Setup

1. Clone the repository:

```bash
git clone https://github.com/your-username/AI-Coding-Tutor.git
cd AI-Coding-Tutor
```

2. Create the environment file:

```bash
cp .env.example .env
```

Edit `.env` and set:

- A strong `JWT_SECRET_KEY` (at least 32 random characters).
- Your LLM API key for the chosen provider (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GOOGLE_API_KEY`).
- Your embedding API key (`COHERE_API_KEY` or `VOYAGEAI_API_KEY`).
- `LLM_PROVIDER` to your preferred provider (`anthropic`, `openai`, or `google`).

Keep all keys from `.env.example` in place. `config.py` defines the settings structure only, so missing keys in `.env` will fail startup.

3. Start the database and backend:

```bash
docker compose up db backend
```

4. In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

5. Open http://localhost:5173 in your browser.

### One-Click Start (Windows)

Double-click `start.bat` in the project root. The script:

- checks Docker engine availability first (15-second timeout);
- starts database and backend containers;
- waits for `http://localhost:8000/health`;
- runs `python app/ai/verify_keys.py` in the backend container;
- starts the frontend only if at least one LLM provider passes verification; and
- opens your browser and keeps the startup window open for logs.

If startup fails, the script prints container status and recent backend/database logs before exiting.

### One-Click Update (Windows)

Double-click `update.bat` in the project root. The script:

- fetches and fast-forwards local Git history (`git pull --ff-only`);
- rebuilds database and backend containers;
- rebuilds the database from scratch via `docker compose down -v` (this removes local DB data);
- runs frontend dependency updates (`npm install`); and
- prints current container status at the end.

If you have local uncommitted changes, `git pull --ff-only` may stop with an error. Resolve that first, then rerun `update.bat`.

## Key Design Decisions

- **Embedding before LLM.** Every user message is embedded once. Greetings and off-topic queries are caught by cosine similarity against pre-embedded anchors, saving the cost of an LLM call entirely.
- **Semantic similarity, not hashing.** Same-problem detection uses embedding similarity against the previous Q+A context, which is robust to rephrasing. This replaces the original code-hashing design.
- **Token storage.** Access tokens are stored in memory. Refresh tokens are stored in httpOnly cookies. On page load, the auth context silently calls the refresh endpoint to restore the session.
- **LLM robustness.** Each provider retries with exponential backoff on transient errors. If the primary provider fails, the system falls back to the next available provider automatically.
- **JupyterLite, not JupyterHub.** The notebook environment (Phase 3) runs entirely in the browser via WebAssembly with zero server cost. Limitations include browser memory constraints and some Python libraries being unavailable.
