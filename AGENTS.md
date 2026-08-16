# AGENTS.md

FastAPI app ("digital-locket") that encrypts files with a passphrase, stores them in a vault, and shreds the originals. Early stage: code is placeholders, no tests.

## Environment & commands

- Package manager is `uv` (Python 3.12 per `.python-version`, deps in `pyproject.toml`). Always use `uv ...` (e.g. `uv add`, `uv sync`, `uv run`) — never pip/venv directly. `.venv` exists but is gitignored.
- Run the server: `uv run python main.py` (serves the web UI at `127.0.0.1:8000`), or `uv run uvicorn main:app --reload`.
- Lint: `uv run ruff check .`. Only dev dependency is ruff and there is no `[tool.ruff]` config, so defaults apply. Note the baseline already has 2 `BLE001` (blind `Exception`) violations in `app/services/lock_logic_service.py`.
- No tests and no test framework configured (smoke-test with FastAPI's `TestClient`, which needs the `httpx` dev dependency).

## Git commit convention

Use this exact format so every commit is traceable to whether a user or agent made it:

```
Feature: Agent decision
- Added ...
- Description of what/why ...
```

- The first line is `<Type>: Agent decision`. Keep `Agent decision` literally so commits are clearly attributed to an agent run (user-made commits keep `<Type>: <summary>` instead).
- `<Type>` is one of `Feature`, `Chore`, `Refactor`, `Docs`. When it's borderline between Refactor and Feature (new or modified implementation), prefer `Feature`.
- Body bullets describe the *what* and *why*.
- Commit by type: group changes into one commit per `<Type>` (e.g. all Feature changes together, all Chore changes together), in a sensible order (refactor → feature → chore → docs).
- Never commit secrets or test vaults; `./vaults/` is gitignored for this reason.

## Architecture gotchas

- `main.py` mounts `vault.router` via `app.include_router(...)` and serves the UI from `app/static/` with a `StaticFiles` mount at `/` (**mounted last**, so `/api/*` wins). Any **new** router must also be wired in `main.py` — nothing auto-registers. `app/routers/auth.py` was removed; owner auth lives in `vault.py`.
- `app/routers/vault.py` is the single-owner API: `GET /api/state`, `POST /api/setup` (first-run), `POST /api/login`, `POST /api/stage` (multipart `files` parsed into the pydantic `LockRequest` form model → writes plaintext into the Locket Files folder), `POST /api/encrypt` (locks everything in that folder into the vault, shredding each original only on success), `GET /api/files` (returns `staged` + `locked`), `POST /api/unload` (decrypts everything to the Locket Files folder and calls `os.startfile` to open Explorer). All routes except `state`/`setup`/`login` require a `Bearer` token.
- **Folder layout (USB)**: `PROJECT_ROOT` is anchored to the app folder; `FILES_DIR = PROJECT_ROOT.parent / "Locket Files"` (the USB-root sibling, the user-facing folder that both stages inputs and receives unloads), `VAULTS_ROOT = PROJECT_ROOT / "vaults"` (encrypted store, gitignored). Paths are anchored to `PROJECT_ROOT`, never CWD.
- **Overwrite safety**: `lock_folder_files` never overwrites an existing `.enc` (skipped files stay in the folder); `unload_files` never overwrites a file already in the Locket Files folder. Bypassed/manual strays in the folder are left alone and get included in the next encrypt.
- **Auth**: `app/core/tokens.py` is an in-memory LRU `TokenStore` (access 5 min, refresh 30 min). Token value is the owner's passphrase. Rotation is delivered back to the client via `X-Access-Token` / `X-Refresh-Token` response headers — the frontend reads them; there is no `/refresh` endpoint. Both expired → 401 → re-login.
- Ownership: `vaults/.owner.json` stores a display `name` + base64 `verifier` (Fernet encryption of `b"digital-locket-owner"` under the passphrase). `vaults/.index.json` tracks original file sizes for the file list.
- The UI (`app/static/`: `index.html`, `main.js`, `style.css`) is plain vanilla JS — no build step. Tokens live in JS memory only, so reloading the page means re-login.
- `app/routers/playground.py` is an explicit scratchpad for prototyping before writing real code; treat it as throwaway.
- `app/vault/` is a Python package (empty `__init__.py`) — **not** the on-disk vault where `.enc` files are stored (`./vaults/`). Don't conflate them.
- Logging: use the shared `app_logger` from `app/core/logger.py` (Asia/Manila timestamps) instead of `print` in app code. `lock_logic_service.py` still has a few `print`s (CLI path) — converting them (and the `BLE001` below) is expected.

## Crypto & destructive operations

- Encryption in `app/services/lock_logic_service.py`: Argon2id (time_cost=2, 64 MB, parallelism=1) → 32-byte key → URL-safe base64 → Fernet. Files are stored as `vaults/<name>.enc` with the 16-byte salt prepended to the ciphertext. Use `encrypt_bytes()`/`decrypt_bytes()` for single-blob work, `create_owner_marker()`/`verify_owner_marker()` for ownership, `lock_folder_files()` for the folder→vault encrypt path, and `unload_files()` for the decrypt-to-folder path; `lock_files()`/`show_files()` are the older directory-based CLI path.
- Do **not** change the KDF params or storage format — existing vaults would become undecryptable.
- `lock_files()` overwrites and securely deletes the source files. Never point it at real data during development.
