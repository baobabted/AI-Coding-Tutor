# Phase 5: Production Deployment

**Visible result:** The application is live on a public URL with HTTPS. All features work end-to-end in production.

**Prerequisite:** Phase 4 complete (application is robust and tested locally).

---

## What This Phase Delivers

- Production Docker images for frontend and backend.
- A production Docker Compose file orchestrating all services.
- Nginx reverse proxy with HTTPS.
- CI/CD pipeline via GitHub Actions.
- Environment variable validation on startup.

---

## 1. Production Dockerfiles

### Backend Dockerfile (`backend/Dockerfile`)

Already exists from Phase 1 for development. For production, ensure:

- Uses a slim Python base image (`python:3.11-slim`).
- Installs only production dependencies (no test packages).
- Runs Uvicorn with `--workers 2` (or more, based on server CPU).
- Sets `--host 0.0.0.0 --port 8000`.
- Does not mount source code (image contains a copy).

### Frontend Dockerfile (`frontend/Dockerfile`)

Multi-stage build:

**Stage 1 — Build:**
- Uses `node:20-alpine`.
- Copies `package.json` and `package-lock.json`, runs `npm ci`.
- Copies source code, runs `npm run build`.
- Output: `dist/` directory with static files.

**Stage 2 — Serve:**
- Uses `nginx:alpine`.
- Copies the `dist/` output from stage 1 into Nginx's HTML directory.
- Copies a custom Nginx config (see below).

---

## 2. Nginx Configuration

Nginx serves two roles: reverse proxy for the backend, and static file server for the frontend.

```
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Frontend static files
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;   # SPA fallback
    }

    # JupyterLite static files (large WASM files need increased limits)
    location /jupyterlite/ {
        root /usr/share/nginx/html;
        add_header Cross-Origin-Opener-Policy same-origin;
        add_header Cross-Origin-Embedder-Policy require-corp;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket endpoints
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;   # Keep WebSocket alive for 24h
    }
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}
```

**Important headers for JupyterLite:** The `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers are required for JupyterLite's SharedArrayBuffer support, which Pyodide needs for threading.

---

## 3. Production Docker Compose

**`docker-compose.prod.yml`**:

```yaml
services:
  db:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ai_tutor
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      retries: 5

  backend:
    build: ./backend
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@db:5432/ai_tutor
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      LLM_PROVIDER: ${LLM_PROVIDER}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      CORS_ORIGINS: '["https://yourdomain.com"]'
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
      - certbot_certs:/etc/letsencrypt
    depends_on:
      - backend
    restart: always

  certbot:
    image: certbot/certbot
    volumes:
      - certbot_certs:/etc/letsencrypt
      - ./frontend/dist:/var/www/html
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do sleep 12h; certbot renew; done'"

volumes:
  pgdata:
  certbot_certs:
```

---

## 4. Environment Variable Validation

In `backend/app/config.py`, add startup validation:

- If `LLM_PROVIDER` is set but the corresponding API key is empty, raise an error immediately at startup rather than failing silently on the first LLM call.
- If `JWT_SECRET_KEY` is the default or too short, raise an error.
- If `DATABASE_URL` is not set, raise an error.

This "fail fast" approach prevents deploying a misconfigured application.

---

## 5. CI/CD with GitHub Actions

**`.github/workflows/ci.yml`**:

```yaml
name: CI
on: [push, pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/ -v
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:test@localhost:5432/test_db
          JWT_SECRET_KEY: test-secret-key-for-ci
          LLM_PROVIDER: mock

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: cd frontend && npm ci
      - run: cd frontend && npm run build
      - run: cd frontend && npx tsc --noEmit
```

---

## 6. HTTPS Setup

For the initial deployment on a VPS:

1. Point your domain's DNS A record to the server's IP.
2. Start the stack without HTTPS first (Nginx on port 80 only).
3. Run Certbot to obtain certificates:
   ```bash
   docker compose -f docker-compose.prod.yml run certbot certonly --webroot -w /var/www/html -d yourdomain.com
   ```
4. Update the Nginx config to enable the HTTPS server block.
5. Restart Nginx.
6. The Certbot container automatically renews certificates every 12 hours.

---

## 7. Deployment Steps (VPS)

1. Provision a VPS (e.g. DigitalOcean Droplet, 2 CPU, 4 GB RAM).
2. Install Docker and Docker Compose.
3. Clone the repository.
4. Create a `.env` file with production values (strong JWT secret, real API keys, etc.).
5. Run `docker compose -f docker-compose.prod.yml up -d`.
6. Set up HTTPS (step 6 above).
7. Verify all features work via the public URL.

---

## 8. Database Backups

Add a cron job on the VPS to back up the PostgreSQL database daily:

```bash
# /etc/cron.d/ai-tutor-backup
0 3 * * * docker exec ai-tutor-db pg_dump -U $DB_USER ai_tutor | gzip > /backups/ai_tutor_$(date +\%Y\%m\%d).sql.gz
```

Keep the last 30 days of backups. This is critical — the database contains all user work and chat history.

---

## Verification Checklist

- [ ] `docker compose -f docker-compose.prod.yml up -d` starts all services without errors.
- [ ] The application loads on `https://yourdomain.com`.
- [ ] HTTPS certificate is valid (check with browser padlock icon).
- [ ] User can register, log in, chat, open modules, use the workspace — full end-to-end test.
- [ ] WebSocket connections work through Nginx (chat streams correctly).
- [ ] JupyterLite loads and executes Python code in production.
- [ ] CI pipeline passes on push to main.
- [ ] Health endpoint returns 200 from the public URL.
- [ ] Database backup cron job runs and produces valid backups.
