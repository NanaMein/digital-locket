# AGENTS.md

FastAPI app (“digital-locket”) for passphrase-protected file/folder locking. **Many operations are destructive** (shredding on success).

## Environment & commands

- Use `uv` (Python 3.12 from `.python-version` / `pyproject.toml`); run as `uv ...` (never `pip` / manual venv).
- Run: `uv run python main.py` (UI at `127.0.0.1:8000`) or `uv run uvicorn main:app --reload`.
- Lint: `uv run ruff check .` (no dedicated config; baseline includes 1 `BLE001` in `app/services/lock_logic_service.py`).
- No tests are configured; prefer smoke-testing via the running server.

## Git commit convention (required)

Use this exact format:

```
Feature: Agent decision
- Added ...
- Description of what/why ...
```

- First line must be `<Type>: Agent decision` (keep `Agent decision` literally).
- `<Type>` is `Feature|Chore|Refactor|Docs` (if borderline, prefer `Feature`).
- Group changes by `<Type>`; never commit secrets or vault contents (`./vaults/` is gitignored).

## Runtime wiring (easy to miss)

- `main.py` mounts only `app.routers.vault.router` and serves `app/static/` at `/`; any new router must be wired in `main.py` explicitly.
- `app/routers/auth.py` exists but is **not** mounted by `main.py` (treat as unused unless you mount it too).

## Paths + state (drives real data)

- Real filesystem roots are defined in `app/core/paths.py`:
  - `FILES_DIR = .../Locket Files` (staging + unload destination)
  - `VAULTS_ROOT = .../vaults` (encrypted store)
- Locket status lives in `vaults/.state.json` as `{ "status": "open|locked", "clean": true|false }`.
  - `open` enables staging; `locked` blocks staging (`POST /api/stage` returns 409).
  - `clean` controls the **startup wipe** of `FILES_DIR`.

- `app/core/lifespan.py` clears the in-memory `token_store` on startup, runs the wipe, then clears `token_store` again on shutdown.

## Auth (in-memory only)

- Owner session is an in-memory TTL LRU in `app/core/tokens.py` (`token_store`); the passphrase is never persisted.
- Cookies used by `app/routers/vault.py`: `dl_access` (5 min) + `dl_refresh` (30 min), `HttpOnly`, `SameSite=Lax`.
- Because the store is RAM-only: process restart invalidates sessions → strict `401`.

## API entrypoints (single owner API)

- `GET /api/state` is public.
- `POST /api/setup` (first run) + `POST /api/login` are public.
- All other routes require session auth (`dl_access`/`dl_refresh` via `get_auth`).
- Key behaviors to preserve:
  - `POST /api/stage`: accepts multipart `files` plus repeated `dirs` for empty folders; filenames are sanitized by `_safe_relpath` (rejects empty, `..`, and `:` components).
  - `POST /api/encrypt`: encrypts `FILES_DIR` into the vault and mirrors (fresh re-encrypt; removes stale `*.enc`).
  - `POST /api/unload?clean=true|false`: decrypts vault → `FILES_DIR`; `clean=true` empties the folder first (UI confirms before sending).

## Crypto/storage format (do not change)

- `app/services/lock_logic_service.py`:
  - Argon2id params: `time_cost=2`, `memory_cost=65536` (64MB), `parallelism=1`, `hash_len=32`.
  - Encrypt format: 16-byte random salt prepended to Fernet ciphertext; Fernet key is derived with the above KDF.
  - Vault layout:
    - files: `vaults/<name>.enc`
    - top-level folders archived to zip + stored as `vaults/folders/<name>.enc`
  - `shred_and_delete()` overwrites in 1 MiB chunks, `fsync`s, then unlinks; never delete without overwriting.
- Changing KDF params or the on-disk format makes existing vaults undecryptable.

## Logging + legacy notes

- Prefer `app_logger` from `app/core/logger.py` over `print` in app code.
- Legacy CLI paths (`lock_files`/`show_files`) still use `print` and are not the main server flow; keep focus on `lock_folder_files()` / `unload_files()`.
