import json
import os
from pathlib import Path
from typing import Annotated

import anyio
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel

from app.core.logger import app_logger
from app.core.paths import FILES_DIR, INDEX_FILE, OWNER_FILE, STATE_FILE, VAULTS_ROOT
from app.core.tokens import ACCESS_TTL_SECONDS, REFRESH_TTL_SECONDS, token_store
from app.services.lock_logic_service import (
    create_owner_marker,
    lock_folder_files,
    unload_files,
    verify_owner_marker,
)

router = APIRouter()

ACCESS_COOKIE = "dl_access"
REFRESH_COOKIE = "dl_refresh"


class SetupRequest(BaseModel):
    name: str | None = None
    passphrase: str


class LoginRequest(BaseModel):
    passphrase: str


class LockRequest(BaseModel):
    files: list[UploadFile]
    dirs: list[str] = []


def _set_session_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE, value=access, max_age=ACCESS_TTL_SECONDS, httponly=True, samesite="lax"
    )
    response.set_cookie(
        key=REFRESH_COOKIE, value=refresh, max_age=REFRESH_TTL_SECONDS, httponly=True, samesite="lax"
    )


def get_auth(request: Request, response: Response) -> str:
    """Resolve the owner passphrase from the HttpOnly session cookies.

    The passphrase itself only ever lives in the in-memory TokenStore (a TTL cache), so a
    process restart or stolen machine invalidates every session. Access tokens live 5 min,
    refresh tokens 30 min; when the access expires the refresh rotates both. Wrong or stale
    credentials get a strict 401.
    """
    access = request.cookies.get(ACCESS_COOKIE)
    refresh = request.cookies.get(REFRESH_COOKIE)
    if not access and not refresh:
        raise HTTPException(status_code=401, detail="Missing session")

    passphrase: str | None = None
    rotated: tuple[str, str] | None = None
    if access:
        result = token_store.validate_access(access)
        if result is not None:
            passphrase, rotated = result
    if passphrase is None and refresh:
        result = token_store.validate_refresh(refresh)
        if result is not None:
            passphrase, rotated = result
    if passphrase is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    if rotated:
        _set_session_cookies(response, rotated[0], rotated[1])
    return passphrase


def _load_owner() -> dict | None:
    if not OWNER_FILE.is_file():
        return None
    try:
        return json.loads(OWNER_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _load_index() -> dict[str, int]:
    if INDEX_FILE.is_file():
        try:
            return json.loads(INDEX_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_index(index: dict[str, int]) -> None:
    VAULTS_ROOT.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))


def _load_state() -> dict:
    """Read .state.json, defaulting to an open, clean-on-startup state."""
    if STATE_FILE.is_file():
        try:
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"status": "open", "clean": True}


def _load_status() -> str:
    return _load_state().get("status", "open")


def _save_status(status: str) -> None:
    state = _load_state()
    state["status"] = status
    VAULTS_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _safe_relpath(raw: str) -> Path:
    """Sanitize a client-supplied relative path into a safe path under FILES_DIR."""
    parts = [p for p in raw.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts:
        raise HTTPException(status_code=400, detail="Invalid empty path")
    for part in parts:
        if part == ".." or ":" in part:
            raise HTTPException(status_code=400, detail=f"Unsafe path component: {part}")
    return Path(*parts)


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


@router.get("/api/state")
async def get_state():
    state = _load_state()
    return {"owned": OWNER_FILE.is_file(), "status": state.get("status", "open"), "clean": state.get("clean", True)}


@router.post("/api/setup")
async def setup(req: SetupRequest):
    if OWNER_FILE.is_file():
        raise HTTPException(status_code=409, detail="Vault already owned")
    owner = {"name": req.name, "verifier": create_owner_marker(req.passphrase)}
    VAULTS_ROOT.mkdir(parents=True, exist_ok=True)
    OWNER_FILE.write_text(json.dumps(owner, indent=2))
    _save_status("open")
    app_logger.info("Vault ownership created for %s", req.name or "anonymous owner")
    return {"owned": True}


@router.post("/api/login")
async def login(req: LoginRequest, response: Response):
    owner = _load_owner()
    if owner is None:
        raise HTTPException(status_code=400, detail="Vault not set up yet")
    if not verify_owner_marker(owner["verifier"], req.passphrase):
        raise HTTPException(status_code=401, detail="Wrong passphrase")
    access, refresh = token_store.create(req.passphrase)
    _set_session_cookies(response, access, refresh)
    return {"ok": True}


@router.post("/api/stage")
async def stage_files(
    payload: Annotated[LockRequest, Form()],
    auth: Annotated[str, Depends(get_auth)],
):
    if _load_status() == "locked":
        raise HTTPException(status_code=409, detail="Locket is locked — open it first")
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    staged = []
    for upload in payload.files:
        rel = _safe_relpath(upload.filename or "unnamed")
        dest = FILES_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await upload.read())
        app_logger.info("Staged %s into %s", rel.as_posix(), FILES_DIR.name)
        staged.append(rel.as_posix())
    created_dirs = []
    for dir_rel in payload.dirs:
        rel = _safe_relpath(dir_rel)
        (FILES_DIR / rel).mkdir(parents=True, exist_ok=True)
        created_dirs.append(rel.as_posix())
        app_logger.info("Staged folder %s", rel.as_posix())
    return {"staged": staged, "dirs": created_dirs}


@router.post("/api/encrypt")
async def encrypt_staged(auth: Annotated[str, Depends(get_auth)]):
    locked, failed = await anyio.to_thread.run_sync(
        lock_folder_files, str(FILES_DIR), str(VAULTS_ROOT), auth
    )
    index = _load_index()
    keep = {name for name, _ in locked} | set(failed)
    for name, size in locked:
        index[name] = size
    for name in list(index):
        if name not in keep:
            del index[name]
    _save_index(index)
    if locked:
        _save_status("locked")
    return {"locked": [name for name, _ in locked], "failed": failed}


@router.get("/api/files")
async def list_files(auth: Annotated[str, Depends(get_auth)]):
    index = _load_index()
    staged = []
    if FILES_DIR.is_dir():
        for p in sorted(FILES_DIR.iterdir()):
            if p.is_dir():
                staged.append({"name": p.name, "size": _dir_size(p), "kind": "folder"})
            elif p.is_file():
                staged.append({"name": p.name, "size": p.stat().st_size, "kind": "file"})
    locked = []
    if VAULTS_ROOT.is_dir():
        for p in sorted(VAULTS_ROOT.glob("*.enc")):
            name = p.name[:-4]
            locked.append({"name": name, "size": index.get(name, p.stat().st_size), "kind": "file"})
        folders_vault = VAULTS_ROOT / "folders"
        if folders_vault.is_dir():
            for p in sorted(folders_vault.glob("*.enc")):
                name = p.name[:-4]
                locked.append({"name": name, "size": index.get(name, p.stat().st_size), "kind": "folder"})
    return {"staged": staged, "locked": locked, "status": _load_status()}


@router.post("/api/unload")
async def unload(
    auth: Annotated[str, Depends(get_auth)],
    clean: bool = False,
):
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    unloaded, skipped = await anyio.to_thread.run_sync(
        unload_files, str(VAULTS_ROOT), str(FILES_DIR), auth, clean
    )
    await anyio.to_thread.run_sync(os.startfile, str(FILES_DIR))
    app_logger.info("Unloaded %d files to %s", unloaded, FILES_DIR)
    _save_status("open")
    return {"unloaded": unloaded, "skipped": skipped, "folder": str(FILES_DIR)}