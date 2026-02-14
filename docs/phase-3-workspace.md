# Phase 3: Notebook Workspace and Learning Hub

**Prerequisite:** Phase 2 complete (AI chat with file uploads working).

**Visible result:** Students can upload their own Jupyter notebooks, run Python code in the browser via JupyterLite, and ask an AI tutor for help — all in a single split-panel workspace. Administrators can create public learning zones with curated notebooks that every user can browse and work through.

Development is split into two parts: Part A delivers personal notebook uploads with an executable JupyterLite workspace and chatbot-assisted learning. Part B adds an admin-managed learning hub visible to all users.

---

## What This Phase Delivers

### Part A — Personal Notebook Workspace

- A pre-built JupyterLite static site served from the frontend, giving every user a browser-based Python environment with no server-side computation.
- A `postMessage` bridge between the parent page and the JupyterLite iframe for loading notebooks, reading cell code and errors, detecting edits, and saving/restoring state.
- A `user_notebooks` database table for permanently stored user uploads.
- REST endpoints for uploading, listing, deleting, and saving personal notebooks.
- A split-panel workspace page: JupyterLite on the left, AI tutor chat on the right.
- Notebook-aware chat sessions where the AI can see the student's current cell code and error output.
- Dirty-checked auto-save that persists the student's notebook state to the backend only when changes are detected.

### Part B — Admin Learning Hub

- An `is_admin` flag on the `users` table and an admin-only dependency guard.
- `learning_zones`, `zone_notebooks`, and `zone_notebook_progress` database tables.
- Admin REST endpoints for creating zones, uploading notebooks, and replacing notebook content.
- A public learning zone browser where all logged-in users can see zones and open notebooks.
- Per-user progress tracking for zone notebooks (each user gets their own working copy).
- A reset mechanism for students to discard their progress and start a zone notebook from scratch.
- The same split-panel workspace reused for zone notebooks.

---

## JupyterLite Setup (Shared by Both Parts)

### Overview

JupyterLite is a static site that runs Jupyter entirely in the browser using WebAssembly (Pyodide). It requires no server-side computation. The build is done once and placed in the frontend's public directory.

### Build

A build script at the project root automates the process:

**`scripts/build-jupyterlite.sh`**

```bash
#!/usr/bin/env bash
set -e
pip install jupyterlite-core jupyterlite-pyodide-kernel
cd jupyterlite-bridge && jlpm && jlpm build && cd ..
jupyter lite build \
  --output-dir frontend/public/jupyterlite \
  --federated-extensions jupyterlite-bridge/
```

This produces a directory of static HTML, JavaScript, and WASM files. Vite serves them alongside the React app at `/jupyterlite/`.

**When to rebuild:** Only when upgrading the JupyterLite version or modifying the bridge extension. The build output does not need to be regenerated for day-to-day development.

**Git.** Add `frontend/public/jupyterlite/` to `.gitignore`. The output is a generated artefact and should not be committed.

### postMessage bridge extension

JupyterLite runs inside an `<iframe>` on the same origin as the main application. The parent page and the iframe communicate via the `postMessage` API.

A small JupyterLite lab extension is required to handle incoming messages. The extension source lives in `jupyterlite-bridge/` at the project root.

**Extension directory structure:**

```
jupyterlite-bridge/
├── package.json          # Extension metadata, build scripts, JupyterLab version
├── tsconfig.json         # TypeScript config
├── src/
│   └── index.ts          # Extension entry point — registers the postMessage listener
└── style/
    └── base.css          # Empty (no styling needed)
```

**Key file: `src/index.ts`.** The extension implements `ILabShellExtension` and:

1. On activation, posts a `{ command: "ready" }` message to `window.parent` so the host page knows the iframe is initialised.
2. Registers `window.addEventListener('message', handler)` to respond to commands from the parent.

**Build:** `cd jupyterlite-bridge && jlpm && jlpm build`

The extension responds to the following commands:

| Command | Direction | Payload | Response |
|---------|-----------|---------|----------|
| `load-notebook` | Parent → iframe | `{ notebook_json: object }` | Writes the notebook to the virtual filesystem via the Contents API and opens it in the editor. |
| `get-notebook-state` | Parent → iframe | (none) | Returns `{ notebook_json: object }` — the full notebook including any edits and outputs. |
| `get-current-cell` | Parent → iframe | (none) | Returns `{ code: string, cell_index: number }` — the source of the currently selected cell. |
| `get-error-output` | Parent → iframe | (none) | Returns `{ error: string \| null }` — the traceback from the most recent cell execution, or `null` if no error. |
| `notebook-dirty` | Iframe → parent | (none) | Fired whenever the user edits a cell. The parent uses this to track whether unsaved changes exist. |

Each response is sent via `window.parent.postMessage()` and includes a `command` field matching the original request so the parent can route callbacks.

### Limitations

These constraints apply to all code running inside the Pyodide kernel:

- **Available libraries:** NumPy, SciPy, Pandas, Matplotlib, and SymPy are available out of the box. Libraries that require C extensions not compiled for WASM (such as scikit-learn and TensorFlow) are unavailable.
- **Memory:** Limited by the browser's WebAssembly allocation, typically 2–4 GB.
- **Speed:** Python execution via WASM is roughly 3–10× slower than native CPython.
- **No network access:** Code in Pyodide cannot make HTTP requests or access the local filesystem.
- **No persistent storage by default:** All state is lost on page refresh. This is why the application saves notebook state to the backend.

---

## Part A — Personal Notebook Workspace

### Backend Work

#### 1. Notebook database model

**`backend/app/models/notebook.py`**

##### `UserNotebook`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to `users.id`, cascade delete |
| `title` | VARCHAR(255) | Derived from the original filename (without extension) |
| `original_filename` | VARCHAR(255) | The filename as uploaded |
| `stored_filename` | VARCHAR(255) | Unique, randomised name on disc |
| `storage_path` | VARCHAR(500) | Full path to the stored file |
| `notebook_json` | TEXT | The current `.ipynb` JSON string — updated on every save |
| `extracted_text` | TEXT | Plain text extracted from all cells, used as chat context |
| `size_bytes` | INTEGER | File size at upload time |
| `created_at` | TIMESTAMP | Server default |

**Index:** On `user_id` for listing a user's notebooks.

Unlike the temporary uploads from Phase 2, user notebooks are stored permanently (no `expires_at`). They persist until the user explicitly deletes them. The `notebook_json` column stores the student's latest working state, not just the original upload.

#### 2. Notebook schemas

**`backend/app/schemas/notebook.py`**

- `NotebookOut`: id, title, original_filename, size_bytes, created_at. Uses `from_attributes = True`.
- `NotebookDetail`: Extends `NotebookOut` with `notebook_json`. Returned when opening a notebook in the workspace.
- `NotebookSave`: notebook_json (dict). Used for saving notebook state.

#### 3. Notebook service

**`backend/app/services/notebook_service.py`**

- `save_notebook(db, user_id, file) -> UserNotebook`: Validates the file is a valid `.ipynb` (must parse as JSON with a `cells` array). Stores the file on disc. Saves `notebook_json` (the full JSON string) and `extracted_text` (all cell sources concatenated). Reuses `_extract_ipynb_text()` from `upload_service.py` for text extraction.
- `list_notebooks(db, user_id) -> list[UserNotebook]`: Returns all notebooks for the user, ordered by `created_at` descending.
- `get_notebook(db, user_id, notebook_id) -> UserNotebook | None`: Returns a single notebook if it belongs to the user.
- `update_notebook_state(db, user_id, notebook_id, notebook_json) -> UserNotebook | None`: Validates that the JSON is a valid `.ipynb` structure (must contain a `cells` key) and that its serialised size does not exceed `NOTEBOOK_MAX_SIZE_MB`. Overwrites `notebook_json` only. Does **not** re-extract `extracted_text` — that is done lazily when the student sends a chat message (see Section 5). Returns `None` if the notebook does not belong to the user.
- `refresh_extracted_text(db, user_id, notebook_id) -> str | None`: Re-extracts `extracted_text` from the current `notebook_json` and saves it. Returns the updated text. Called by the chat handler before building the system prompt, so extraction only happens when the student actually asks a question — not on every auto-save.
- `delete_notebook(db, user_id, notebook_id) -> bool`: Deletes the database record and the file from disc. Returns `False` if not found.

**Validation rules:**

- File extension must be `.ipynb`.
- File must parse as valid JSON containing a `cells` key.
- Maximum file size: 5 MB (configurable via `NOTEBOOK_MAX_SIZE_MB` in settings).
- Maximum notebooks per user: 20 (configurable via `NOTEBOOK_MAX_PER_USER` in settings).

#### 4. Notebook router

**`backend/app/routers/notebooks.py`**, prefix `/api/notebooks`:

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/notebooks` | GET | Lists all notebooks for the current user. |
| `/api/notebooks` | POST | Uploads a new `.ipynb` file. Accepts `multipart/form-data`. |
| `/api/notebooks/{notebook_id}` | GET | Returns the full notebook detail including `notebook_json`. |
| `/api/notebooks/{notebook_id}` | PUT | Saves notebook state. Accepts `{ "notebook_json": {...} }` in the body. |
| `/api/notebooks/{notebook_id}` | DELETE | Deletes a notebook. |

All endpoints require authentication. Users can only access their own notebooks.

#### 5. Notebook-aware chat

Rather than creating a separate WebSocket endpoint, the existing `/ws/chat` endpoint is extended to support notebook context.

**Changes to the WebSocket message format.** The client can include optional notebook context fields when sending a message:

```json
{
  "content": "Why is my matrix multiplication wrong?",
  "notebook_id": "uuid-of-the-notebook",
  "cell_code": "import numpy as np\nA = np.array([[1,2],[3,4]])\nresult = A * B",
  "error_output": "NameError: name 'B' is not defined"
}
```

The `notebook_id` identifies which notebook the student is working on. The `cell_code` and `error_output` come from the postMessage bridge and represent the student's currently selected cell and its most recent error.

**Backend handling.** When `notebook_id` is present in a message:

1. Call `refresh_extracted_text()` to ensure the notebook's `extracted_text` is up to date with the latest `notebook_json`. This is the only time extraction runs — not on every auto-save.
2. Truncate `extracted_text` to `NOTEBOOK_MAX_CONTEXT_TOKENS` tokens (default 4000). The `cell_code` and `error_output` are always included in full since they are small.
3. Build a context block and inject it into the system prompt as hidden context (not stored as a chat message):

```
--- Student's Notebook ---
{extracted_text (truncated)}
--- End of Notebook ---

--- Current Cell ---
{cell_code}
--- End of Current Cell ---

--- Error Output ---
{error_output}
--- End of Error Output ---
```

The `cell_code` and `error_output` sections are omitted if the client does not provide them.

4. Create the chat session with `session_type = "notebook"` and `module_id` set to the notebook's UUID. This separates notebook chat sessions from general chat sessions in the sidebar.

**Changes to `context_builder.py`.** Add a `notebook_context` parameter to `build_system_prompt()`. When present, append the notebook context after the base system prompt but before the conversation history.

**Changes to `chat.py` router.** In the WebSocket handler, check for `notebook_id`, `cell_code`, and `error_output` in incoming messages. If `notebook_id` is present, call `refresh_extracted_text()`, then pass the text and cell context to the context builder.

**Chat session filtering.** The existing `GET /api/chat/sessions` endpoint must filter to `session_type = "general"` only. Notebook and zone sessions should not appear in the general chat sidebar — they are only accessible from within their respective workspaces.

#### 6. Alembic migration

Create migration `004_add_user_notebooks_table.py`:

- Creates the `user_notebooks` table with an index on `user_id`.

#### 7. Configuration additions

Add to `backend/app/config.py` (structure only — values come from `.env`):

```python
# Notebooks (Phase 3A)
notebook_storage_dir: str
notebook_max_size_mb: int
notebook_max_per_user: int
notebook_max_context_tokens: int

# Admin (Phase 3B)
admin_email: str
```

The corresponding values are already defined in `.env.example` and `.env`.

---

### Frontend Work

#### 8. Notebook panel component

**`frontend/src/workspace/NotebookPanel.tsx`**

Renders an `<iframe>` pointing to `/jupyterlite/lab/index.html`. Once the iframe loads, the component uses the postMessage bridge to load and manage the notebook.

**Bridge helper.** A utility module `frontend/src/workspace/notebookBridge.ts` wraps the `postMessage` calls into Promise-based functions:

```typescript
export function loadNotebook(iframe: HTMLIFrameElement, notebookJson: object): void;
export function getNotebookState(iframe: HTMLIFrameElement): Promise<object>;
export function getCurrentCell(iframe: HTMLIFrameElement): Promise<{ code: string; cellIndex: number }>;
export function getErrorOutput(iframe: HTMLIFrameElement): Promise<string | null>;
```

Each function posts a message to the iframe and listens for the corresponding response via a one-time `message` event listener with a timeout (5 seconds).

**Loading.** On mount, the component:

1. Displays a loading spinner with the text "Starting Python environment..." over the iframe area. Pyodide (the WebAssembly Python runtime) takes 5–10 seconds to initialise on first visit; subsequent visits are faster due to browser caching.
2. Waits for the JupyterLite iframe to signal it is ready (the bridge extension posts a `ready` message on initialisation). If no `ready` message arrives within 30 seconds, display an error: "Failed to load the notebook environment. Please refresh the page."
3. Fetches `GET /api/notebooks/{notebook_id}` to get the notebook JSON.
4. Calls `loadNotebook()` to inject the notebook into JupyterLite's virtual filesystem and open it. Hides the loading spinner once the notebook is loaded.

**Auto-save with dirty checking.** The component saves the student's work only when changes are detected:

1. Listen for `notebook-dirty` messages from the iframe. When received, set a `dirty` flag to `true`.
2. A 30-second interval timer checks the flag. If `dirty === true` and no save request is currently in-flight, call `getNotebookState()` and send the result to `PUT /api/notebooks/{notebook_id}`. On success, reset the flag.
3. If a save is already in-flight, skip the current tick — do not queue concurrent saves.
4. On `window.beforeunload`, if `dirty === true`, perform one final save using `fetch` with `keepalive: true`. This ensures the request completes even as the page unloads, and unlike `navigator.sendBeacon`, it supports custom headers (the JWT `Authorization` header is required).

**Save status indicator.** The workspace toolbar displays the current save state:

- **"Saved"** — shown after a successful save, with a subtle checkmark.
- **"Saving..."** — shown while a save request is in-flight.
- **"Unsaved changes"** — shown when the `dirty` flag is `true` but no save has started yet.

This gives students confidence that their work is being preserved.

**Exposing cell context to the chat panel.** The component exposes a `getCellContext()` method (via a React ref or callback prop) that returns the current cell code and error output. The chat panel calls this before sending each message.

#### 9. My Notebooks page

**`frontend/src/notebook/MyNotebooksPage.tsx`**

Fetches `GET /api/notebooks` on mount. Displays a list of the user's uploaded notebooks as cards. Each card shows the title, filename, size, and upload date.

**Actions on each card:**

- **Open**: Navigates to `/notebook/{notebook_id}`, which opens the workspace.
- **Delete**: Calls `DELETE /api/notebooks/{notebook_id}` with a confirmation dialogue.

**Upload button.** A prominent "Upload Notebook" button at the top opens a file picker filtered to `.ipynb` files. On selection, the file is uploaded via `POST /api/notebooks`. The list refreshes after a successful upload.

**Empty state.** When the user has no notebooks, show a message explaining they can upload `.ipynb` files to study with AI assistance.

#### 10. Notebook workspace page

**`frontend/src/workspace/NotebookWorkspacePage.tsx`**

Uses `react-split` (new frontend dependency) to create a horizontally split layout.

| Property | Value |
|----------|-------|
| Default split | 60% notebook, 40% chat |
| Minimum pane width | 300px |
| Drag handle | Visible divider that can be dragged to resize |

Reads `notebook_id` from the URL parameter and passes it to both child panels.

**Left panel:** The `NotebookPanel` component (JupyterLite iframe with the student's notebook loaded).

**Right panel:** The existing chat interface (reuse `ChatMessageList`, `ChatInput`, `ChatBubble`). Before sending each message, the chat panel calls `NotebookPanel.getCellContext()` to get the current cell code and error output, then includes them alongside `notebook_id` in the WebSocket message.

**Chat session retrieval.** The workspace chat does not use the general session list. Instead, it queries for the existing session with `session_type = "notebook"` and `module_id` matching the current notebook. If no session exists, a new one is created on the first message. If the user returns to the same notebook later, the previous chat session and its history are restored.

#### 11. Update routing and navigation

- Add `/my-notebooks` route pointing to `MyNotebooksPage` (protected).
- Add `/notebook/:notebookId` route pointing to `NotebookWorkspacePage` (protected).
- Update `Navbar.tsx`: replace the disabled "Modules" span with two links — "My Notebooks" and "Learning Hub" (the latter disabled until Part B, with tooltip "Coming in Phase 3B").

#### 12. New frontend dependencies

Add `react-split` to `package.json` for the resizable split-panel layout.

---

### Part A Verification Checklist

- [ ] JupyterLite build script (`scripts/build-jupyterlite.sh`) runs without errors.
- [ ] `frontend/public/jupyterlite/` is in `.gitignore`.
- [ ] A loading spinner is shown while JupyterLite initialises.
- [ ] JupyterLite loads in the iframe and Python code executes (test: `import numpy as np; print(np.__version__)`).
- [ ] User can upload a `.ipynb` file from the My Notebooks page.
- [ ] Invalid files (non-JSON, missing `cells` key, oversized) are rejected with a clear error.
- [ ] Uploaded notebooks appear in the list with correct title, size, and date.
- [ ] Clicking a notebook opens the workspace with the notebook loaded in JupyterLite.
- [ ] The student can edit cells and run code inside JupyterLite.
- [ ] The divider between notebook and chat panels can be dragged to resize.
- [ ] Asking the tutor a question sends the current cell code as context (verify in backend logs).
- [ ] If the current cell has an error, the error output is included in the tutor context.
- [ ] The tutor's responses reference the student's code and errors when relevant.
- [ ] The tutor uses the same graduated hint system as the general chat.
- [ ] The save status indicator shows "Saved", "Saving...", or "Unsaved changes" correctly.
- [ ] Auto-save only fires when the notebook has been edited (verify no `PUT` calls when idle).
- [ ] Notebook state is saved when changes exist (verify in the database via `PUT` calls).
- [ ] A save payload that exceeds `NOTEBOOK_MAX_SIZE_MB` is rejected with a clear error.
- [ ] Closing the browser and reopening the same notebook restores the student's previous work.
- [ ] Returning to the same notebook restores the previous chat session.
- [ ] Notebook sessions do not appear in the general chat sidebar.
- [ ] User can delete a notebook from the list.
- [ ] Upload is rejected when the user reaches the 20-notebook limit.

---

## Part B — Admin Learning Hub

### Backend Work

#### 13. Admin role

Add an `is_admin` boolean column to the `users` table (default `False`). The admin account is controlled by the `ADMIN_EMAIL` environment variable in `.env`.

**How it works:**

1. On app startup (`init_db.py`), if a user with the `ADMIN_EMAIL` address already exists, set their `is_admin` flag to `True`.
2. During registration (`auth_service.py`), if the new user's email matches `ADMIN_EMAIL`, set `is_admin = True` on creation.

This means the operator simply sets `ADMIN_EMAIL=alice@example.com` in `.env`. When Alice registers (or if she has already registered), she automatically becomes admin. No manual SQL or seed scripts are needed.

**`backend/app/dependencies.py`** — add a `get_admin_user` dependency:

```python
async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user
```

Any endpoint that uses `Depends(get_admin_user)` is restricted to administrators.

#### 14. Learning zone database model

**`backend/app/models/zone.py`**

##### `LearningZone`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `title` | VARCHAR(255) | e.g. "Linear Algebra" |
| `description` | TEXT | Brief summary shown on the zone card |
| `order` | INTEGER | Display order, indexed |
| `created_at` | TIMESTAMP | Server default |

##### `ZoneNotebook`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `zone_id` | UUID | Foreign key to `learning_zones.id`, cascade delete |
| `title` | VARCHAR(255) | Display title for the notebook |
| `description` | TEXT | Optional short description |
| `original_filename` | VARCHAR(255) | The filename as uploaded |
| `stored_filename` | VARCHAR(255) | Unique, randomised name on disc |
| `storage_path` | VARCHAR(500) | Full path to the stored file |
| `notebook_json` | TEXT | The original `.ipynb` JSON string (never modified by students) |
| `extracted_text` | TEXT | Plain text for chat context |
| `size_bytes` | INTEGER | File size |
| `order` | INTEGER | Display order within the zone |
| `created_at` | TIMESTAMP | Server default |

**Index:** On `zone_id` for listing notebooks within a zone.

**Cascade behaviour:** When a zone notebook is deleted, all `ZoneNotebookProgress` records for that notebook are cascade-deleted. This means student progress is lost. The admin dashboard warns about this before confirming deletion.

##### `ZoneNotebookProgress`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to `users.id`, cascade delete |
| `zone_notebook_id` | UUID | Foreign key to `zone_notebooks.id`, cascade delete |
| `notebook_state` | TEXT | The student's working copy of the notebook JSON |
| `created_at` | TIMESTAMP | Server default |
| `updated_at` | TIMESTAMP | Auto-updated on each write |

**Unique constraint** on `(user_id, zone_notebook_id)`.

**Index:** On `user_id` for listing a student's progress across all zone notebooks.

When a student opens a zone notebook for the first time, no progress record exists and JupyterLite loads the original notebook from `ZoneNotebook.notebook_json`. Once the student makes changes and the auto-save fires, a `ZoneNotebookProgress` record is created. On subsequent visits, the saved state is loaded instead of the original.

#### 15. Zone schemas

**`backend/app/schemas/zone.py`**

- `ZoneCreate`: title (str), description (str).
- `ZoneUpdate`: title (optional str), description (optional str), order (optional int).
- `ZoneOut`: id, title, description, order, created_at, notebook_count (integer). Uses `from_attributes = True`.
- `ZoneNotebookOut`: id, zone_id, title, description, original_filename, size_bytes, order, created_at, has_progress (bool, default `false` — set to `true` if the requesting user has a `ZoneNotebookProgress` record).
- `ZoneNotebookDetail`: Extends `ZoneNotebookOut` with `notebook_json`. When the requesting user has saved progress, `notebook_json` contains their working copy instead of the original.
- `ZoneProgressSave`: notebook_state (dict). Used for saving zone notebook progress.

#### 16. Zone service

**`backend/app/services/zone_service.py`**

- `create_zone(db, title, description) -> LearningZone`: Creates a new zone. Sets `order` to the current count + 1.
- `list_zones(db) -> list[LearningZone]`: Returns all zones ordered by the `order` column.
- `get_zone(db, zone_id) -> LearningZone | None`: Returns a single zone.
- `update_zone(db, zone_id, **fields) -> LearningZone | None`: Updates the specified fields.
- `delete_zone(db, zone_id) -> bool`: Deletes the zone and all its notebooks (cascade). Removes notebook files from disc.
- `add_notebook(db, zone_id, title, description, file) -> ZoneNotebook`: Validates the `.ipynb` file (same rules as personal notebooks), stores it, and links it to the zone.
- `replace_notebook_content(db, notebook_id, file) -> ZoneNotebook | None`: Replaces `notebook_json` and `extracted_text` on an existing zone notebook with content from a new `.ipynb` file. Existing `ZoneNotebookProgress` records are preserved — students keep their working copies, but new students (or students who reset) get the updated original.
- `list_zone_notebooks(db, zone_id) -> list[ZoneNotebook]`: Returns all notebooks in a zone, ordered by `order`.
- `get_zone_notebook(db, notebook_id, user_id=None) -> ZoneNotebook`: Returns a single zone notebook. If `user_id` is provided and the user has saved progress, substitutes `notebook_json` with the user's working copy.
- `save_zone_progress(db, user_id, zone_notebook_id, notebook_state) -> ZoneNotebookProgress`: Validates structure and size (same rules as `update_notebook_state`). Creates or updates the progress record (upsert).
- `reset_zone_progress(db, user_id, zone_notebook_id) -> bool`: Deletes the student's progress record. The next time they open the notebook, JupyterLite loads the original. Returns `False` if no progress existed.
- `delete_zone_notebook(db, notebook_id) -> bool`: Deletes the notebook record and file. All student progress is cascade-deleted.
- `reorder_zone_notebooks(db, zone_id, notebook_ids: list[UUID])`: Updates the `order` column based on the position in the provided list.

#### 17. Admin router

**`backend/app/routers/admin.py`**, prefix `/api/admin`:

All endpoints use `Depends(get_admin_user)`.

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/admin/zones` | GET | Lists all zones with notebook counts. |
| `/api/admin/zones` | POST | Creates a new learning zone. |
| `/api/admin/zones/{zone_id}` | PUT | Updates zone title, description, or order. |
| `/api/admin/zones/{zone_id}` | DELETE | Deletes a zone and all its notebooks. |
| `/api/admin/zones/{zone_id}/notebooks` | POST | Uploads a notebook to a zone. Accepts `multipart/form-data` with `title`, `description`, and `file` fields. |
| `/api/admin/zones/{zone_id}/notebooks` | GET | Lists all notebooks in a zone (admin view with ordering controls). |
| `/api/admin/notebooks/{notebook_id}` | PUT | Replaces the notebook content with a new `.ipynb` file. Existing student progress is preserved. |
| `/api/admin/notebooks/{notebook_id}` | DELETE | Deletes a single notebook from a zone. All student progress is cascade-deleted. |
| `/api/admin/zones/{zone_id}/notebooks/reorder` | PUT | Accepts an ordered list of notebook IDs and updates display order. |

#### 18. Public zone router

**`backend/app/routers/zones.py`**, prefix `/api/zones`:

These endpoints are available to all authenticated users (read-only, except for progress operations).

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/zones` | GET | Lists all zones with notebook counts. |
| `/api/zones/{zone_id}` | GET | Returns zone details and its list of notebooks. Each notebook includes a `has_progress` boolean indicating whether the current user has saved work on it. |
| `/api/zones/{zone_id}/notebooks/{notebook_id}` | GET | Returns full notebook detail. If the user has saved progress, returns their working copy in `notebook_json`; otherwise returns the original. |
| `/api/zones/{zone_id}/notebooks/{notebook_id}/progress` | PUT | Saves the user's notebook state. Accepts `{ "notebook_state": {...} }` in the body. |
| `/api/zones/{zone_id}/notebooks/{notebook_id}/progress` | DELETE | Resets the user's progress. Deletes their working copy so the next open loads the original notebook. |

#### 19. Zone notebook chat

Zone notebooks use the same chat mechanism as personal notebooks. When a user opens a zone notebook in the workspace, the client includes `zone_notebook_id` instead of `notebook_id` in WebSocket messages:

```json
{
  "content": "What does the eigenvalue decomposition in cell 5 do?",
  "zone_notebook_id": "uuid-of-the-zone-notebook",
  "cell_code": "eigenvalues, eigenvectors = np.linalg.eig(A)",
  "error_output": null
}
```

The backend loads the `ZoneNotebook` record and injects its `extracted_text` into the system prompt, identically to personal notebook chat. The `cell_code` and `error_output` from the postMessage bridge are appended as live context. The chat session is created with `session_type = "zone"`.

**Note:** For zone notebooks, the chat context always uses the original `extracted_text` from `ZoneNotebook` (the curated content), not the student's modified copy. This ensures the tutor's understanding of the material stays consistent with what the admin intended.

#### 20. Alembic migration

Create migration `005_add_admin_and_zones.py`:

- Adds `is_admin` column to the `users` table (default `False`).
- Creates the `learning_zones` table with an index on `order`.
- Creates the `zone_notebooks` table with an index on `zone_id`.
- Creates the `zone_notebook_progress` table with a unique constraint on `(user_id, zone_notebook_id)` and an index on `user_id`.

#### 21. Auth endpoint update

Extend `GET /api/auth/me` to include `is_admin` in the response. The frontend uses this flag to conditionally show the admin link in the navbar.

---

### Frontend Work

#### 22. Learning Hub browse page

**`frontend/src/zones/LearningHubPage.tsx`**

Fetches `GET /api/zones` on mount. Displays a grid of zone cards. Each card shows the zone title, description, and the number of notebooks it contains.

Clicking a zone card navigates to `/zones/{zone_id}`, which shows the zone's notebooks.

#### 23. Zone detail page

**`frontend/src/zones/ZoneDetailPage.tsx`**

Fetches `GET /api/zones/{zone_id}` on mount. Displays the zone title, description, and a list of notebook cards. Each card shows the notebook title, description, and file size. If the student has saved progress on a notebook, a small "In Progress" badge appears on the card.

Clicking a notebook card navigates to `/zone-notebook/{zoneId}/{notebookId}`, which opens the workspace.

#### 24. Zone notebook workspace page

**`frontend/src/workspace/ZoneNotebookWorkspacePage.tsx`**

Identical split-panel layout to the personal `NotebookWorkspacePage` from Part A. The differences are:

1. Fetches notebook JSON from `GET /api/zones/{zone_id}/notebooks/{notebook_id}` (which returns the user's saved progress if it exists, or the original notebook otherwise).
2. Auto-save calls `PUT /api/zones/{zone_id}/notebooks/{notebook_id}/progress` instead of `PUT /api/notebooks/{notebook_id}`.
3. The chat panel sends `zone_notebook_id` instead of `notebook_id` in WebSocket messages.
4. A "Reset to Original" button is shown in the toolbar. On click, it calls `DELETE /api/zones/{zone_id}/notebooks/{notebook_id}/progress` with a confirmation dialogue, then reloads the original notebook into JupyterLite.

This component reuses `NotebookPanel`, `ChatMessageList`, `ChatInput`, and `ChatBubble` directly.

#### 25. Admin dashboard page

**`frontend/src/admin/AdminDashboardPage.tsx`**

Accessible only to admin users (check `user.is_admin` from auth context; redirect non-admins to `/chat`).

Displays all learning zones in an editable list. Each zone shows its title, description, notebook count, and action buttons (Edit, Delete).

**Zone management:**

- **Create Zone** button opens an inline form with title and description fields.
- **Edit** opens the same form pre-filled with current values.
- **Delete** shows a confirmation dialogue warning that all notebooks and student progress in the zone will be removed.

Clicking a zone expands it to show its notebooks in a reorderable list (drag-and-drop or up/down buttons).

#### 26. Admin notebook upload and replacement

Within the expanded zone view on the admin dashboard, an "Add Notebook" button opens a form with:

- **Title** (text input): the display name for the notebook.
- **Description** (text area, optional): a short summary of what the notebook covers.
- **File** (file picker): filtered to `.ipynb` files.

On submission, the form calls `POST /api/admin/zones/{zone_id}/notebooks`.

Each notebook in the list shows its title, description, a **Replace** button, and a **Delete** button.

- **Replace** opens a file picker. On selection, calls `PUT /api/admin/notebooks/{notebook_id}` with the new file. Existing student progress is preserved (students keep their working copies).
- **Delete** shows a confirmation dialogue warning that all student progress for this notebook will be removed.

#### 27. Update routing and navigation

- Add `/learning-hub` route pointing to `LearningHubPage` (protected).
- Add `/zones/:zoneId` route pointing to `ZoneDetailPage` (protected).
- Add `/zone-notebook/:zoneId/:notebookId` route pointing to `ZoneNotebookWorkspacePage` (protected).
- Add `/admin` route pointing to `AdminDashboardPage` (protected, admin-only).
- Update `Navbar.tsx`: enable the "Learning Hub" link (replacing the "Coming in Phase 3B" placeholder from Part A). Add an "Admin" link visible only when `user.is_admin` is `true`.

---

### Part B Verification Checklist

- [ ] Non-admin users cannot access `/api/admin/*` endpoints (403 returned).
- [ ] Admin can create a new learning zone with title and description.
- [ ] Admin can upload `.ipynb` files to a zone with title and description.
- [ ] Admin can replace a zone notebook's content and existing student progress is preserved.
- [ ] Admin can delete a zone and all notebooks and student progress are removed.
- [ ] Admin can delete individual notebooks and their student progress is removed.
- [ ] Admin can reorder notebooks within a zone.
- [ ] All logged-in users can see the Learning Hub page with all zones listed.
- [ ] Clicking a zone shows its notebooks.
- [ ] Clicking a zone notebook opens the workspace with JupyterLite and the notebook loaded.
- [ ] The student can edit and run code in a zone notebook.
- [ ] The AI chat receives zone notebook context (including current cell and errors) and answers contextually.
- [ ] Zone notebook sessions do not appear in the general chat sidebar.
- [ ] Closing the browser and reopening the same zone notebook restores the student's progress.
- [ ] A different student opening the same zone notebook gets a fresh copy (not another student's work).
- [ ] Student can reset a zone notebook to the original via the "Reset to Original" button.
- [ ] After reset, opening the notebook loads the admin's original content.
- [ ] Zone detail page shows "In Progress" badges on notebooks the student has started.
- [ ] Non-admin users see no admin link in the navbar.
- [ ] Admin users see the admin link in the navbar.
- [ ] The `is_admin` flag is returned in the `/api/auth/me` response.
