# Phase 3: Learning Modules and Workspace

**Visible result:** User can browse learning modules, select one, and open a split-panel workspace with a JupyterLite notebook on the left and the AI tutor on the right. The tutor can see the student's code and errors. Notebook progress is saved.

**Prerequisite:** Phase 2 complete (chat + pedagogy engine working).

---

## What This Phase Delivers

- `learning_modules` and `user_module_progress` database tables.
- REST endpoints for listing modules and tracking progress.
- Pre-built JupyterLite served as static files with pre-made notebooks.
- A split-panel workspace page with resizable panes.
- A `postMessage` bridge to extract code and errors from JupyterLite.
- A tutor WebSocket endpoint (`/ws/tutor`) identical to `/ws/chat` but with notebook context injected.
- Notebook state persistence (auto-save + save on close).

---

## Backend Work

### 1. Module database model

**`backend/app/models/module.py`**:

#### `LearningModule`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `title` | VARCHAR(255) | e.g. "Introduction to NumPy" |
| `description` | TEXT | Brief summary |
| `notebook_filename` | VARCHAR(255) | e.g. "module_01_intro_to_numpy.ipynb" |
| `order` | INTEGER | Display order, indexed |

### 2. Progress database model

**`backend/app/models/progress.py`**:

#### `UserModuleProgress`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → `users.id` |
| `module_id` | UUID | FK → `learning_modules.id` |
| `status` | VARCHAR(20) | `"not_started"`, `"in_progress"`, `"completed"` |
| `notebook_state` | JSONB | Full notebook JSON (the student's work) |
| `attempt_count` | INTEGER | Total tutor interactions for this module |
| `updated_at` | TIMESTAMP | Auto-updated |

**Unique constraint:** `(user_id, module_id)`.
**Indexes:** Index on `user_id`.

### 3. Schemas

**`backend/app/schemas/module.py`**:
- `ModuleOut`: id, title, description, notebook_filename, order
- `ModuleListOut`: list of `ModuleOut`, each augmented with the user's progress status

**`backend/app/schemas/progress.py`**:
- `ProgressUpdate`: status (optional), notebook_state (optional JSONB)
- `ProgressOut`: id, module_id, status, attempt_count, updated_at

### 4. Module service

**`backend/app/services/module_service.py`**:
- `list_modules() -> list[LearningModule]` — Returns all modules ordered by `order`.
- `get_module(module_id) -> LearningModule` — Returns a single module or raises 404.

### 5. Progress service

**`backend/app/services/progress_service.py`**:
- `get_progress(user_id, module_id) -> UserModuleProgress | None`
- `get_all_progress(user_id) -> list[UserModuleProgress]`
- `update_progress(user_id, module_id, status?, notebook_state?) -> UserModuleProgress` — Creates the record if it does not exist (upsert).

### 6. Module router

**`backend/app/routers/modules.py`**:

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/modules` | GET | Returns all modules with the current user's progress status for each |
| `/api/modules/{module_id}` | GET | Returns a single module's details |

### 7. Progress router

**`backend/app/routers/progress.py`**:

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/progress/{module_id}` | GET | Returns the user's progress for a specific module |
| `/api/progress/{module_id}` | PUT | Updates progress (status and/or notebook state) |

### 8. Tutor WebSocket endpoint

**`backend/app/routers/tutor.py`** — `WebSocket /ws/tutor?token=<jwt>&module_id=<uuid>`:

This is nearly identical to `/ws/chat` from Phase 2. The differences are:

1. **Module context:** The connection requires a `module_id` query parameter. The backend loads the module details to include the topic in the system prompt.
2. **Notebook context injection:** Each client message includes additional fields:
   ```json
   {
     "content": "Why is my matrix multiplication wrong?",
     "cell_code": "import numpy as np\nA = np.array([[1,2],[3,4]])\nresult = A * B",
     "error_output": "NameError: name 'B' is not defined",
     "cell_code_hash": "a1b2c3..."
   }
   ```
3. **Context builder usage:** The `cell_code` and `error_output` are passed to `context_builder.build_messages()`, which appends them to the system prompt as hidden context (the student sees them in their notebook, the AI sees them in the prompt, but they are not shown as chat messages).
4. **Error classification:** If `error_output` is present, the pedagogy engine classifies the error type and includes the appropriate teaching instructions in the prompt.
5. **Attempt counting:** The tutor also increments the `attempt_count` on the `user_module_progress` record, providing a lifetime count of tutor interactions per module.

### 9. Database seed script

**`backend/app/db/init_db.py`** — Add module seeding:

Seed 2–3 initial modules:
1. "Introduction to NumPy" — `module_01_intro_to_numpy.ipynb`
2. "Linear Algebra Basics" — `module_02_linear_algebra.ipynb`
3. "Interpolation Methods" — `module_03_interpolation.ipynb`

### 10. Alembic migration

Create migration for `learning_modules` and `user_module_progress` tables.

---

## JupyterLite Setup

### 11. Build JupyterLite

JupyterLite is a static site that runs Jupyter entirely in the browser using WebAssembly (Pyodide). You need to build it once and place the output in `frontend/public/jupyterlite/`.

```bash
pip install jupyterlite-core jupyterlite-pyodide-kernel
jupyter lite build --output-dir frontend/public/jupyterlite
```

This produces a directory of static HTML/JS/WASM files that the browser loads.

### 12. Pre-made notebooks

Create 2–3 `.ipynb` files in `notebooks/`:

- Each notebook has a title, introduction cells (markdown), and exercise cells (code) with comments guiding the student.
- Exercise cells contain starter code or empty cells with instructions.

Copy them into `frontend/public/jupyterlite/files/` so JupyterLite serves them.

### 13. JupyterLite limitations to be aware of

- **Available libraries:** NumPy, SciPy, Pandas, Matplotlib, SymPy are available via Pyodide. Libraries requiring C extensions not compiled for WASM (e.g. scikit-learn, TensorFlow) are unavailable.
- **Memory:** Limited by the browser's WebAssembly memory (typically 2–4 GB). Large datasets will not work.
- **Speed:** Python execution via WASM is roughly 3–10x slower than native CPython.
- **No network access:** Code running in Pyodide cannot make HTTP requests or access the filesystem.
- **No persistent storage by default:** All state is lost on page refresh unless explicitly saved (which is why we implement notebook state persistence).

---

## Frontend Work

### 14. Module list page

**`frontend/src/modules/ModuleListPage.tsx`**:
- Fetches `GET /api/modules` on mount.
- Displays a grid of module cards.

**`frontend/src/modules/ModuleCard.tsx`**:
- Shows module title, description, and a progress badge ("Not Started", "In Progress", "Completed").
- Clicking navigates to `/workspace/{module_id}`.

### 15. Workspace page

**`frontend/src/workspace/WorkspacePage.tsx`**:
- Uses `react-split` to create a horizontally-split layout.
- Default split: 60% notebook (left), 40% tutor (right).
- Minimum pane width: 300px.
- Reads `module_id` from the URL parameter.
- Passes it to both child panels.

### 16. Notebook panel

**`frontend/src/workspace/NotebookPanel.tsx`**:

- Renders an `<iframe>` pointing to `/jupyterlite/lab/index.html?path=files/{notebook_filename}`.
- Implements a `postMessage` bridge:

**Extracting code from JupyterLite:**

JupyterLite does not have a built-in postMessage API for external communication. The approach is:

1. Inject a small JavaScript extension into the JupyterLite build that listens for `postMessage` events and responds with the current cell's code and any error output.
2. Alternatively, use the JupyterLite `ServiceWorker` approach or a custom Jupyter extension.
3. The simplest MVP approach: use `iframe.contentWindow.document` to read the DOM of the notebook iframe (only works if same-origin — which it is, since JupyterLite is served from the same domain).

**The bridge exposes:**
- `getCurrentCellCode() -> string` — Returns the code of the currently selected cell.
- `getErrorOutput() -> string | null` — Returns the error output of the last cell execution, if any.
- `getNotebookState() -> object` — Returns the full notebook JSON.
- `setNotebookState(state: object)` — Restores notebook content from saved state.

**Auto-save logic:**
- Every 60 seconds, call `getNotebookState()` and `PUT /api/progress/{module_id}` with the state.
- On `window.beforeunload`, trigger one final save (use `navigator.sendBeacon` or a synchronous XHR as a fallback, since `fetch` may be cancelled during page unload).
- On cell execution, save as well (triggered by listening for execution events via the bridge).

**Restore logic:**
- On mount, fetch `GET /api/progress/{module_id}`.
- If `notebook_state` exists, call `setNotebookState()` to restore the student's previous work.
- If no saved state, the default notebook from the module loads.

### 17. Tutor panel

**`frontend/src/workspace/TutorPanel.tsx`**:

Nearly identical to `ChatPage` from Phase 2, with these additions:

- Before sending each message, calls `getCurrentCellCode()` and `getErrorOutput()` from the notebook bridge.
- Includes these as additional fields in the WebSocket message.
- Computes `cell_code_hash` (SHA-256 of the normalised cell code) on the frontend before sending.
- Connects to `/ws/tutor?token=<jwt>&module_id=<uuid>` instead of `/ws/chat`.

### 18. Module selector

**`frontend/src/workspace/ModuleSelector.tsx`** — A dropdown or sidebar within the workspace that allows switching modules without leaving the workspace page. On switch, saves current notebook state, then loads the new module's notebook.

### 19. Update routing and navigation

- Add `/modules` route → `ModuleListPage`.
- Add `/workspace/:moduleId` route → `WorkspacePage`.
- Update `Navbar` to link to Modules.

---

## Verification Checklist

- [ ] Module list page displays 2–3 modules with progress badges.
- [ ] Clicking a module opens the workspace with the correct notebook loaded in JupyterLite.
- [ ] JupyterLite loads and Python code can be executed (test `import numpy as np; print(np.__version__)`).
- [ ] The divider between notebook and tutor panels can be dragged to resize.
- [ ] Asking the tutor a question sends the current cell code as context (verify in backend logs).
- [ ] The tutor's responses reference the student's code when relevant.
- [ ] The tutor uses graduated hints (same escalation as the general chat).
- [ ] Notebook state is saved periodically (verify by checking the database).
- [ ] Closing the browser and reopening the module restores the student's previous notebook state.
- [ ] The `beforeunload` save fires (verify by making a change, immediately closing, and reopening).
- [ ] Module progress updates to "In Progress" when opened, can be marked "Completed".
