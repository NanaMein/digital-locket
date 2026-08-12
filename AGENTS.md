# AGENTS.md

FastAPI app ("digital-locket") that encrypts files with a passphrase, stores them in a vault, and shreds the originals. Early stage: code is placeholders, no tests.

## Environment & commands

- Package manager is `uv` (Python 3.12 per `.python-version`, deps in `pyproject.toml`). Always use `uv ...` (e.g. `uv add`, `uv sync`, `uv run`) — never pip/venv directly. `.venv` exists but is gitignored.
- Run the server: `uv run python main.py` (serves at `127.0.0.1:8000`), or `uv run uvicorn main:app --reload`.
- Lint: `uv run ruff check .`. Only dev dependency is ruff and there is no `[tool.ruff]` config, so defaults apply. Note the baseline already has 2 `BLE001` (blind `Exception`) violations in `app/services/lock_logic_service.py`.
- No tests and no test framework configured.

## Architecture gotchas

- `main.py` mounts `auth.router` and `vault.router` via `app.include_router(...)`. Any **new** router must also be wired in `main.py` — nothing auto-registers.
- `app/routers/vault.py` is the real MVP API: `POST /lock` (multipart `user`, `passphrase`, `files`), `GET /vault/{user}` (list `.enc`), `GET /vault/{user}/{file}` (decrypt + download; `passphrase` is a query param). Per-user encrypted files live in `./vaults/<user>/` (gitignored); `user`/`file` names are sanitized to block path traversal.
- `app/routers/playground.py` is an explicit scratchpad for prototyping before writing real code; treat it as throwaway.
- `app/vault/` is a Python package (empty `__init__.py`) — **not** the on-disk vault where `.enc` files are stored (`./vaults/`). Don't conflate them.
- Logging: use the shared `app_logger` from `app/core/logger.py` (Asia/Manila timestamps) instead of `print` in app code. `lock_logic_service.py` still has a few `print`s (CLI path) — converting them (and the `BLE001` below) is expected.

## Crypto & destructive operations

- Encryption in `app/services/lock_logic_service.py`: Argon2id (time_cost=2, 64 MB, parallelism=1) → 32-byte key → URL-safe base64 → Fernet. Files are stored as `<vault>/<relative_path>.enc` with the 16-byte salt prepended to the ciphertext. Use `encrypt_bytes()`/`decrypt_bytes()` for single-blob work; `lock_files()`/`show_files()` are the directory-based CLI path.
- Do **not** change the KDF params or storage format — existing vaults would become undecryptable.
- `lock_files()` overwrites and securely deletes the source files. Never point it at real data during development.
