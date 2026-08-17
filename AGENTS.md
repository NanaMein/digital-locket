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
- `app/routers/vault.py` is the single-owner API: `GET /api/state` (public: `owned` + `status`), `POST /api/setup` (first-run), `POST /api/login` (sets HttpOnly session cookies), `POST /api/stage` (multipart `files` parsed into the pydantic `LockRequest` form model; each filename is a sanitized relative path so folders keep their tree, plus repeated `dirs` fields for empty folders → writes plaintext into the Locket Files folder; returns 409 while the locket is locked), `POST /api/encrypt` (locks everything in that folder into the vault — files as `vaults/<name>.enc`, top-level folders archived+encrypted as `vaults/folders/<name>.enc` — shredding each original only on success, vault mirrors the folder), `GET /api/files` (returns `staged` + `locked` + `status`, each row tagged `kind: file|folder`), `POST /api/unload` (optional `?clean=true` empties the folder first, decrypts everything to the Locket Files folder and calls `os.startfile` to open Explorer). All routes except `state`/`setup`/`login` require a valid session.
- **Locket status**: `vaults/.state.json` holds `{"status": "open" | "locked"}`. `open` = folder is the editable working area; `locked` = everything is encrypted in the vault and the folder is empty. `setup` and `unload` set `open`; a non-empty `encrypt` sets `locked`. While `locked`, staging is blocked (UI + `409`) and the UI prioritizes the vault list.
- **Folder layout (USB)**: `PROJECT_ROOT` is anchored to the app folder; `FILES_DIR = PROJECT_ROOT.parent / "Locket Files"` (the USB-root sibling, the user-facing folder that both stages inputs and receives unloads), `VAULTS_ROOT = PROJECT_ROOT / "vaults"` (encrypted store, gitignored). Paths are anchored to `PROJECT_ROOT`, never CWD.
- **Fresh encrypt & mirror**: `lock_folder_files` always re-encrypts fresh (overwriting any existing `name.enc`) so the vault holds the latest version, and deletes stale `.enc` entries whose plaintext is no longer in the folder — the vault mirrors the folder at encrypt time. Files live as `vaults/<name>.enc`; a top-level folder is archived to a single zip blob at `vaults/folders/<name>.enc`, so a file and folder of the same name never collide in the vault. An empty folder is a no-op (never wipes the vault). Files that fail to read/encrypt are left in place, never shredded. `unload_files` skips files already in the Locket Files folder unless `clean=True`, which empties the folder (and empty subdirs) first so decrypted files always land; folder blobs are decrypted + extracted atomically (temp dir → move). The UI confirms before sending `clean=true`.
- **Auth**: `app/core/tokens.py` is an in-memory LRU `TokenStore` — a TTL cache that is the only place the passphrase ever lives (never on disk). Access tokens live 5 min, refresh 30 min; on access expiry the refresh rotates both. Tokens travel in HttpOnly `SameSite=Lax` cookies (`dl_access`/`dl_refresh`) set on login and on rotation; `get_auth` reads them and falls back to the refresh cookie when the access cookie is gone. Because the store is in-memory, a process restart (or stolen machine / different OS user) invalidates every session → strict `401` → re-login. There is no `/refresh` endpoint.
- Ownership: `vaults/.owner.json` stores a display `name` + base64 `verifier` (Fernet encryption of `b"digital-locket-owner"` under the passphrase). `vaults/.index.json` tracks original file sizes for the file list. `vaults/.state.json` tracks the `open`/`locked` status.
- The UI (`app/static/`: `index.html`, `main.js`, `style.css`) is plain vanilla JS — no build step. Auth rides on the HttpOnly cookies automatically (no `Authorization` header, no token state in JS), so a page reload stays logged in while the process is alive. The topbar shows an Open/Locked badge; while locked, drag & drop and the file input are blocked and the vault list takes priority. Folders are staged by dragging them in (browser `FileSystemEntry` walk when supported, empty subfolders included) or via the "Choose a folder" picker (`webkitdirectory`); browsers that can't drag folders in (Firefox) show a note pointing at the picker.
- `app/routers/playground.py` is an explicit scratchpad for prototyping before writing real code; treat it as throwaway.
- `app/vault/` is a Python package (empty `__init__.py`) — **not** the on-disk vault where `.enc` files are stored (`./vaults/`). Don't conflate them.
- Logging: use the shared `app_logger` from `app/core/logger.py` (Asia/Manila timestamps) instead of `print` in app code. `lock_logic_service.py` still has a few `print`s (CLI path) — converting them (and the `BLE001` below) is expected.

## Crypto & destructive operations

- Encryption in `app/services/lock_logic_service.py`: Argon2id (time_cost=2, 64 MB, parallelism=1) → 32-byte key → URL-safe base64 → Fernet. Files are stored as `vaults/<name>.enc` with the 16-byte salt prepended to the ciphertext. Use `encrypt_bytes()`/`decrypt_bytes()` for single-blob work, `create_owner_marker()`/`verify_owner_marker()` for ownership, `lock_folder_files()` for the folder→vault encrypt path, and `unload_files()` for the decrypt-to-folder path; `lock_files()`/`show_files()` are the older directory-based CLI path.
- Do **not** change the KDF params or storage format — existing vaults would become undecryptable.
- `lock_files()` overwrites and securely deletes the source files. Never point it at real data during development.
