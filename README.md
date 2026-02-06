<p align="center">
  <img src="docs/logo.svg" alt="Guided Cursor logo" width="120" />
</p>

<h1 align="center">Guided Cursor</h1>
<p align="center"><strong>AI Coding Tutor</strong></p>

<p align="center">
  A web application that helps students learn numerical computing. Instead of giving answers immediately, the AI tutor uses a pedagogy engine with graduated hints, guiding students from Socratic questions through to full solutions. A split-panel workspace pairs a JupyterLite notebook with a context-aware tutor that can see the student's code and errors.
</p>

---

## Development Status

Phase 1 (User Authentication) is complete. Phase 2 (AI Chat) is currently in development.

| Phase | Milestone | Status | Guide |
|-------|-----------|--------|-------|
| 1 | Auth System | Complete | [docs/phase-1-auth.md](docs/phase-1-auth.md) |
| 2 | AI Chat | In progress | [docs/phase-2-chat.md](docs/phase-2-chat.md) |
| 3 | Learning Workspace | Planned | [docs/phase-3-workspace.md](docs/phase-3-workspace.md) |
| 4 | Robustness and Polish | Planned | [docs/phase-4-robustness.md](docs/phase-4-robustness.md) |
| 5 | Deployment | Planned | [docs/phase-5-deployment.md](docs/phase-5-deployment.md) |

## Curriculum Coverage

The learning modules cover four core topics from the **UCL PHAS0029** Computational Physics course:

- **Linear Algebra**: matrix operations, eigenvalue problems, decompositions
- **Root-Finding Methods**: bisection, Newton-Raphson, secant method
- **Numerical Methods for ODEs**: initial value problems (Euler, Runge-Kutta) and boundary value problems (shooting method, finite differences)
- **Fourier Transforms**: discrete Fourier transform, FFT, spectral analysis

## Features

- **Graduated Hints**: the AI tutor escalates from Socratic questions to conceptual nudges, structural hints, concrete examples, and finally full answers
- **JupyterLite Workspace**: in-browser Python notebooks (WebAssembly), no server required
- **Context-Aware Tutor**: sees the student's notebook code and errors in real time
- **Adaptive Difficulty**: adjusts explanations based on the student's self-assessed programming and maths levels
- **Session Persistence**: chat history, notebook progress, and skill assessments saved to each user's account
- **LLM Flexibility**: supports Anthropic Claude and OpenAI GPT with automatic fallback

## Tech Stack

| Layer | Tools |
|-------|-------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS v4, JupyterLite |
| Backend | FastAPI, Uvicorn, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Auth | python-jose (JWT), passlib + bcrypt |
| AI | Anthropic API (Claude), OpenAI API (GPT), configurable |
| Database | PostgreSQL with asyncpg |
| DevOps | Docker, Docker Compose |

## Architecture

```
Frontend (React + TypeScript + Vite + Tailwind)
  ├── Auth pages (login, register, profile)
  ├── Chat page (WebSocket, streaming)
  ├── Module list page
  └── Workspace page (JupyterLite iframe + Tutor chat)
         │
         │  REST + WebSocket (JWT auth)
         ▼
Backend (FastAPI, async Python)
  ├── Auth API (JWT access + refresh tokens)
  ├── Chat WebSocket (/ws/chat, /ws/tutor)
  ├── Module + Progress REST API
  └── AI subsystem
       ├── LLM abstraction (retry + fallback + token limits)
       ├── Pedagogy engine (graduated hints, student state)
       └── Context builder (system prompt + history + notebook)
         │
         ▼
PostgreSQL (users, chats, modules, progress)
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

Edit `.env` and set a strong `JWT_SECRET_KEY`. Add your LLM API keys when you reach Phase 2.

3. Start the database and backend:

```bash
docker-compose up
```

4. In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

5. Open http://localhost:5173 in your browser.

### One-Click Start (Windows)

Double-click `start.bat` in the project root. It starts the database, backend, and frontend automatically, then opens your browser.

## Key Design Decisions

- **Both chat and tutor use the pedagogy engine.** The tutor adds notebook code and errors as extra context.
- **JupyterLite (not JupyterHub)**: runs in the browser via WebAssembly with zero server cost. Limitations include no GPU, browser memory limits, and some Python libraries being unavailable.
- **Token storage**: access token in memory, refresh token in httpOnly cookie. On page load, the auth context silently calls the refresh endpoint to restore the session.
- **LLM robustness**: retry with exponential backoff on transient errors. Automatic fallback to the secondary provider if the primary is down. Per-user rate limiting and daily usage caps.
