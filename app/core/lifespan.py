import json
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI

from app.core.logger import app_logger
from app.core.paths import FILES_DIR, STATE_FILE, VAULTS_ROOT
from app.core.tokens import token_store
from app.services.lock_logic_service import shred_folder_contents


def _load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"status": "open", "clean": True}


def _save_state(state: dict) -> None:
    VAULTS_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _vault_has_content() -> bool:
    if not VAULTS_ROOT.is_dir():
        return False
    if any(VAULTS_ROOT.glob("*.enc")):
        return True
    folders_vault = VAULTS_ROOT / "folders"
    return folders_vault.is_dir() and any(folders_vault.iterdir())


def _run_startup_wipe() -> None:
    """Clean-slate the plaintext folder on boot: shred every file in Locket Files.

    The vault is never touched — it stays the only persistent, encrypted copy. Status is
    synced to 'locked' when the vault holds anything (folder is now empty, vault is the
    source of truth), otherwise 'open'. Skipped entirely when state 'clean' is false.
    """
    state = _load_state()
    if not state.get("clean", True):
        app_logger.info("Startup wipe skipped (clean=false in %s)", STATE_FILE.name)
        return
    if not FILES_DIR.is_dir():
        return
    count = shred_folder_contents(FILES_DIR)
    if count:
        app_logger.warning(
            "Startup security wipe: shredded %d file(s) from %s", count, FILES_DIR.name
        )
    state["status"] = "locked" if _vault_has_content() else "open"
    _save_state(state)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bind the passphrase store and plaintext folder to the process lifetime.

    Startup: start with a clean in-memory token store (no passphrase from a previous run),
    then shred anything left in Locket Files so only encrypted vault copies survive a reboot.
    Shutdown: release the passphrase store from RAM before the process exits.
    """
    token_store.clear()
    await anyio.to_thread.run_sync(_run_startup_wipe)
    state = _load_state()
    app_logger.info(
        "Locket started (status=%s, clean=%s)",
        state.get("status", "open"),
        state.get("clean", True),
    )
    try:
        yield
    finally:
        token_store.clear()
        app_logger.info("Locket stopped - passphrase store released")