from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.logger import app_logger
from app.services.lock_logic_service import decrypt_bytes, encrypt_bytes

router = APIRouter()

VAULTS_ROOT = Path("vaults")


def _user_vault_dir(user: str) -> Path:
    safe = "".join(c for c in user if c.isalnum() or c in "-_").strip("._") or "default"
    return VAULTS_ROOT / safe


def _safe_name(name: str) -> str:
    return Path(name).name


@router.post("/lock")
async def lock_files(
    user: Annotated[str, Form()],
    passphrase: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
):
    vault = _user_vault_dir(user)
    vault.mkdir(parents=True, exist_ok=True)

    stored = []
    for upload in files:
        name = _safe_name(upload.filename or "unnamed")
        encrypted = encrypt_bytes(await upload.read(), passphrase)
        target = vault / f"{name}.enc"
        target.write_bytes(encrypted)
        app_logger.info("Locked %s -> %s", name, target)
        stored.append(f"{name}.enc")

    return {"user": vault.name, "locked": len(stored), "files": stored}


@router.get("/vault/{user}")
async def list_vault(user: str):
    vault = _user_vault_dir(user)
    if not vault.is_dir():
        return {"user": vault.name, "files": []}
    files = sorted(p.name for p in vault.glob("*.enc"))
    return {"user": vault.name, "files": files}


@router.get("/vault/{user}/{file_name}")
async def unlock_file(user: str, file_name: str, passphrase: str):
    vault = _user_vault_dir(user)
    name = _safe_name(file_name)
    if name != file_name or not name.endswith(".enc"):
        raise HTTPException(status_code=400, detail="Invalid vault file name")

    target = vault / name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in vault")

    try:
        plaintext = decrypt_bytes(target.read_bytes(), passphrase)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return Response(
        content=plaintext,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name[:-4]}"'},
    )