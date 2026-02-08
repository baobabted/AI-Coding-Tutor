# Phase 3: Learning Modules and Workspace

**Prerequisite:** Phase 2 Part A complete (AI chat with pedagogy engine working).

**Visible result:** Students can browse learning modules, select one, and open a split-panel workspace. The left panel runs a JupyterLite notebook in the browser. The right panel is an AI tutor that can see the student's code and errors. Notebook progress is saved and restored across sessions.

---

## What This Phase Delivers

- `learning_modules` and `user_module_progress` database tables.
- REST endpoints for listing modules and tracking progress.
- A tutor WebSocket endpoint (`/ws/tutor`) that extends the existing `/ws/chat` pipeline with notebook context.
- Pre-built JupyterLite served as static files from the frontend.
- A split-panel workspace page with resizable panes.
- A `postMessage` bridge to extract code and errors from JupyterLite.
- Notebook state persistence with auto-save and restore.

---

## Backend Work

### 1. Module database model

**`backend/app/models/module.py`**

#### `LearningModule`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `title` | VARCHAR(255) | e.g. "Introduction to NumPy" |
| `description` | TEXT | Brief summary shown on the module card |
| `notebook_filename` | VARCHAR(255) | e.g. "module_01_intro_to_numpy.ipynb" |
| `order` | INTEGER | Display order, indexed |

### 2. Progress database model

**`backend/app/models/progress.py`**

#### `UserModuleProgress`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Foreign key to `users.id`, cascade delete |
| `module_id` | UUID | Foreign key to `learning_modules.id` |
| `status` | VARCHAR(20) | `"not_started"`, `"in_progress"`, or `"completed"` |
| `notebook_state` | JSONB | Full notebook JSON containing the student's work |
| `attempt_count` | INTEGER | Default 0. Lifetime count of tutor interactions for this module. |
| `updated_at` | TIMESTAMP | Auto-updated on each write |

**Unique constraint** on `(user_id, module_id)`.

**Indexes:** On `user_id` for listing all progress per student.

### 3. Schemas

**`backend/app/schemas/module.py`**

- `ModuleOut`: id, title, description, notebook_filename, order. Uses `from_attributes = True`.
- `ModuleListItem`: Extends `ModuleOut` with `status` (the user's progress status, or `"not_started"` if no record exists).

**`backend/app/schemas/progress.py`**

- `ProgressUpdate`: status (optional str), notebook_state (optional dict). At least one field must be present.
- `ProgressOut`: id, module_id, status, attempt_count, updated_at. Uses `from_attributes = True`.

### 4. Module service

**`backend/app/services/module_service.py`**

- `list_modules(db) -> list[LearningModule]`: Returns all modules ordered by the `order` column.
- `get_module(db, module_id) -> LearningModule | None`: Returns a single module or None.

### 5. Progress service

**`backend/app/services/progress_service.py`**

- `get_progress(db, user_id, module_id) -> UserModuleProgress | None`: Returns the progress record if it exists.
- `get_all_progress(db, user_id) -> list[UserModuleProgress]`: Returns all progress records for a student.
- `update_progress(db, user_id, module_id, status=None, notebook_state=None) -> UserModuleProgress`: Creates the record if it does not exist (upsert pattern). Updates whichever fields are provided.
- `increment_attempt(db, user_id, module_id)`: Adds 1 to the `attempt_count`. Creates the record if it does not exist.

### 6. Module router

**`backend/app/routers/modules.py`**, prefix `/api/modules`:

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/modules` | GET | Returns all modules. Each item includes the current user's progress status. |
| `/api/modules/{module_id}` | GET | Returns a single module's details. 404 if not found. |

### 7. Progress router

**`backend/app/routers/progress.py`**, prefix `/api/progress`:

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/progress/{module_id}` | GET | Returns the user's progress for one module (or a default "not_started" object). |
| `/api/progress/{module_id}` | PUT | Updates progress. Accepts status and/or notebook_state in the body. Returns the updated record. |

### 8. Tutor WebSocket endpoint

**`backend/app/routers/tutor.py`**

`WebSocket /ws/tutor?token=<jwt>&module_id=<uuid>`

This endpoint reuses the same pipeline as `/ws/chat` from Phase 2. The differences are listed below.

**Module context.** The connection requires a `module_id` query parameter. The backend loads the module details and includes the module title and description in the system prompt so the AI knows which topic the student is working on.

**Notebook context injection.** Each client message includes additional fields alongside the text content:

```json
{
  "content": "Why is my matrix multiplication wrong?",
  "cell_code": "import numpy as np\nA = np.array([[1,2],[3,4]])\nresult = A * B",
  "error_output": "NameError: name 'B' is not defined"
}
```

The `cell_code` and `error_output` are appended to the system prompt as hidden context. They are not shown as chat messages in the conversation history.

**Same-problem detection.** The tutor uses the same embedding-based semantic similarity from Phase 2. There is no code hashing. The embedding of the combined Q+A context determines whether a follow-up is about the same problem.

**Attempt counting.** After each successful LLM response, the endpoint calls `progress_service.increment_attempt()` to record the interaction count for this module.

**Session management.** The tutor creates `chat_sessions` with `session_type="tutor"` and `module_id` set to the active module. This separates tutor sessions from general chat sessions.

### 9. Database seed script

Update `backend/app/db/init_db.py` to seed the initial learning modules if the `learning_modules` table is empty:

1. "Introduction to NumPy" (`module_01_intro_to_numpy.ipynb`)
2. "Linear Algebra Basics" (`module_02_linear_algebra.ipynb`)
3. "Interpolation Methods" (`module_03_interpolation.ipynb`)

### 10. Alembic migration

Create a migration that:

- Creates the `learning_modules` table with an index on `order`.
- Creates the `user_module_progress` table with a unique constraint on `(user_id, module_id)` and an index on `user_id`.

---

## JupyterLite Setup

### 11. Build JupyterLite

JupyterLite is a static site that runs Jupyter entirely in the browser using WebAssembly (Pyodide). Build it once and place the output in the frontend's public directory.

```bash
pip install jupyterlite-core jupyterlite-pyodide-kernel
jupyter lite build --output-dir frontend/public/jupyterlite
```

This produces a directory of static HTML, JavaScript, and WASM files. The browser loads and executes them with no server-side computation.

### 12. Pre-made notebooks

Create three `.ipynb` files in a `notebooks/` directory at the project root. Each notebook contains:

- A title cell (markdown) introducing the topic.
- Explanation cells (markdown) covering the theory.
- Exercise cells (code) with starter code and comments guiding the student.
- Empty cells where students write their solutions.

Copy these into `frontend/public/jupyterlite/files/` so JupyterLite serves them automatically.

**Module 1: Introduction to NumPy.** Array creation, indexing, slicing, broadcasting, basic operations.

**Module 2: Linear Algebra Basics.** Matrix multiplication, determinants, eigenvalue problems using `numpy.linalg`.

**Module 3: Interpolation Methods.** Lagrange interpolation, Newton's divided differences, polynomial fitting.

### 13. JupyterLite limitations

These constraints apply to all code running inside the browser-based Pyodide kernel:

- **Available libraries:** NumPy, SciPy, Pandas, Matplotlib, SymPy are available out of the box. Libraries that require C extensions not compiled for WASM (such as scikit-learn and TensorFlow) are unavailable.
- **Memory:** Limited by the browser's WebAssembly memory allocation, typically 2 to 4 GB. Large datasets will not load.
- **Speed:** Python execution via WASM is roughly 3 to 10 times slower than native CPython.
- **No network access:** Code running in Pyodide cannot make HTTP requests or access the local filesystem.
- **No persistent storage by default:** All state is lost on page refresh. This is why the application implements notebook state persistence through the backend.

---

## Frontend Work

### 14. Module list page

**`frontend/src/modules/ModuleListPage.tsx`**

Fetches `GET /api/modules` on mount. Displays a responsive grid of module cards. Each card shows the module title, a brief description, and a progress badge ("Not Started", "In Progress", or "Completed"). Clicking a card navigates to `/workspace/{module_id}`.

**`frontend/src/modules/ModuleCard.tsx`**

A single card component. Receives module data and the user's progress status as props. The badge colour reflects the status: grey for not started, amber for in progress, green for completed.

### 15. Workspace page

**`frontend/src/workspace/WorkspacePage.tsx`**

Uses `react-split` (add as a frontend dependency) to create a horizontally split layout. The left panel holds the notebook. The right panel holds the tutor chat.

| Property | Value |
|----------|-------|
| Default split | 60% notebook, 40% tutor |
| Minimum pane width | 300px |
| Drag handle | Visible divider that can be dragged to resize |

Reads `module_id` from the URL parameter and passes it to both child panels.

### 16. Notebook panel

**`frontend/src/workspace/NotebookPanel.tsx`**

Renders an `<iframe>` pointing to `/jupyterlite/lab/index.html?path=files/{notebook_filename}`.

**postMessage bridge.** JupyterLite runs on the same origin as the main application (served from the same domain). Communication between the parent page and the iframe uses the `postMessage` API.

The bridge exposes four operations:

- `getCurrentCellCode() -> string`: Returns the code from the currently selected cell.
- `getErrorOutput() -> string | null`: Returns the error output from the most recent cell execution, or null if there was no error.
- `getNotebookState() -> object`: Returns the full notebook JSON representing the student's current work.
- `setNotebookState(state: object)`: Restores notebook content from a previously saved state.

These operations require a small JavaScript extension injected into the JupyterLite build that listens for incoming `postMessage` requests and responds with the requested data.

**Auto-save logic:**

- Every 60 seconds, call `getNotebookState()` and send the result to `PUT /api/progress/{module_id}`.
- On cell execution (detected via the postMessage bridge), trigger an additional save.
- On `window.beforeunload`, perform one final save using `navigator.sendBeacon` as a fallback since `fetch` may be cancelled during page unload.

**Restore logic:**

- On mount, fetch `GET /api/progress/{module_id}`.
- If `notebook_state` is present, call `setNotebookState()` to restore the student's previous work.
- If no saved state exists, the default notebook from the module loads.

### 17. Tutor panel

**`frontend/src/workspace/TutorPanel.tsx`**

This component follows the same structure as `ChatPage` from Phase 2 with two changes:

1. Before sending each message, it calls `getCurrentCellCode()` and `getErrorOutput()` from the notebook bridge and includes them as additional fields in the WebSocket message.
2. It connects to `/ws/tutor?token=<jwt>&module_id=<uuid>` instead of `/ws/chat`.

The tutor panel shares the same streaming display, markdown rendering, and chat input components.

### 18. Update routing and navigation

- Add `/modules` route pointing to `ModuleListPage` (protected).
- Add `/workspace/:moduleId` route pointing to `WorkspacePage` (protected).
- Update `Navbar.tsx` to enable the Modules link (currently disabled with "Coming in Phase 3").

### 19. New frontend dependency

Add `react-split` to `package.json` for the resizable split-panel layout.

---

## Verification Checklist

- [ ] Module list page displays three modules with progress badges.
- [ ] Clicking a module opens the workspace with the correct notebook loaded in JupyterLite.
- [ ] JupyterLite loads and Python code executes (test: `import numpy as np; print(np.__version__)`).
- [ ] The divider between notebook and tutor panels can be dragged to resize.
- [ ] Asking the tutor a question sends the current cell code as context (verify in backend logs).
- [ ] The tutor's responses reference the student's code when relevant.
- [ ] The tutor uses the same graduated hint system as the general chat.
- [ ] Notebook state is saved periodically (verify in the database).
- [ ] Closing the browser and reopening the module restores the student's previous notebook state.
- [ ] Module progress updates to "In Progress" on first open and can be marked "Completed".
