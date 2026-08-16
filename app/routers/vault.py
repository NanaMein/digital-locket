import json
import os
from pathlib import Path
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.logger import app_logger
from app.core.tokens import TokenStore
from app.services.lock_logic_service import (
    create_owner_marker,
    lock_folder_files,
    unload_files,
    verify_owner_marker,
)

router = APIRouter()

token_store = TokenStore()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FILES_DIR = PROJECT_ROOT.parent / "Locket Files"
VAULTS_ROOT = PROJECT_ROOT / "vaults"
OWNER_FILE = VAULTS_ROOT / ".owner.json"
INDEX_FILE = VAULTS_ROOT / ".index.json"


class AuthResult:
    def __init__(self, passphrase: str, access_token: str | None = None, refresh_token: str | None = None):
        self.passphrase = passphrase
        self.access_token = access_token
        self.refresh_token = refresh_token


class SetupRequest(BaseModel):
    name: str | None = None
    passphrase: str


class LoginRequest(BaseModel):
    passphrase: str


class LockRequest(BaseModel):
    files: list[UploadFile]


def get_auth(authorization: Annotated[str | None, Header()] = None) -> AuthResult:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    result = token_store.validate_access(token)
    if result is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    passphrase, rotated = result
    if rotated:
        return AuthResult(passphrase, rotated[0], rotated[1])
    return AuthResult(passphrase)


def _auth_headers(auth: AuthResult) -> dict[str, str]:
    if auth.access_token:
        return {"X-Access-Token": auth.access_token, "X-Refresh-Token": auth.refresh_token}
    return {}


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


def _safe_name(name: str) -> str:
    return Path(name).name


@router.get("/api/state")
async def get_state():
    return {"owned": OWNER_FILE.is_file()}


@router.post("/api/setup")
async def setup(req: SetupRequest):
    if OWNER_FILE.is_file():
        raise HTTPException(status_code=409, detail="Vault already owned")
    owner = {"name": req.name, "verifier": create_owner_marker(req.passphrase)}
    VAULTS_ROOT.mkdir(parents=True, exist_ok=True)
    OWNER_FILE.write_text(json.dumps(owner, indent=2))
    app_logger.info("Vault ownership created for %s", req.name or "anonymous owner")
    return {"owned": True}


@router.post("/api/login")
async def login(req: LoginRequest):
    owner = _load_owner()
    if owner is None:
        raise HTTPException(status_code=400, detail="Vault not set up yet")
    if not verify_owner_marker(owner["verifier"], req.passphrase):
        raise HTTPException(status_code=401, detail="Wrong passphrase")
    access, refresh = token_store.create(req.passphrase)
    return {"access_token": access, "refresh_token": refresh}


@router.post("/api/stage")
async def stage_files(
    payload: Annotated[LockRequest, Form()],
    auth: Annotated[AuthResult, Depends(get_auth)],
):
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    staged = []
    for upload in payload.files:
        name = _safe_name(upload.filename or "unnamed")
        (FILES_DIR / name).write_bytes(await upload.read())
        app_logger.info("Staged %s into %s", name, FILES_DIR.name)
        staged.append(name)
    return JSONResponse({"staged": staged}, headers=_auth_headers(auth))


@router.post("/api/encrypt")
async def encrypt_staged(auth: Annotated[AuthResult, Depends(get_auth)]):
    locked, skipped = await anyio.to_thread.run_sync(
        lock_folder_files, str(FILES_DIR), str(VAULTS_ROOT), auth.passphrase
    )
    index = _load_index()
    for name, size in locked:
        index[name] = size
    _save_index(index)
    return JSONResponse(
        {"locked": [name for name, _ in locked], "skipped": skipped},
        headers=_auth_headers(auth),
    )


@router.get("/api/files")
async def list_files(auth: Annotated[AuthResult, Depends(get_auth)]):
    index = _load_index()
    staged = []
    if FILES_DIR.is_dir():
        for p in sorted(FILES_DIR.iterdir()):
            if p.is_file():
                staged.append({"name": p.name, "size": p.stat().st_size})
    locked = []
    if VAULTS_ROOT.is_dir():
        for p in sorted(VAULTS_ROOT.glob("*.enc")):
            name = p.name[:-4]
            locked.append({"name": name, "size": index.get(name, p.stat().st_size)})
    return JSONResponse({"staged": staged, "locked": locked}, headers=_auth_headers(auth))


@router.post("/api/unload")
async def unload(auth: Annotated[AuthResult, Depends(get_auth)]):
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    unloaded, skipped = await anyio.to_thread.run_sync(
        unload_files, str(VAULTS_ROOT), str(FILES_DIR), auth.passphrase
    )
    await anyio.to_thread.run_sync(os.startfile, str(FILES_DIR))
    app_logger.info("Unloaded %d files to %s", unloaded, FILES_DIR)
    return JSONResponse(
        {"unloaded": unloaded, "skipped": skipped, "folder": str(FILES_DIR)},
        headers=_auth_headers(auth),
    )