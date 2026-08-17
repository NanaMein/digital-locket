import base64
import io
import os
import shutil
import uuid
import zipfile
from pathlib import Path

import argon2.low_level
from cryptography.fernet import Fernet, InvalidToken

from app.core.logger import app_logger


def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte raw key from a passphrase using Argon2id, encoded for Fernet."""
    raw_key = argon2.low_level.hash_secret_raw(
        secret=passphrase.encode('utf-8'),
        salt=salt,
        time_cost=2,
        memory_cost=65536,  # 64 MB
        parallelism=1,
        hash_len=32,
        type=argon2.low_level.Type.ID
    )
    # Fernet requires a 32-byte URL-safe base64-encoded key
    return base64.urlsafe_b64encode(raw_key)

def encrypt_bytes(plaintext: bytes, passphrase: str) -> bytes:
    """Encrypt bytes and return the 16-byte salt prepended to the Fernet ciphertext."""
    salt = os.urandom(16)
    key = derive_key(passphrase, salt)
    return salt + Fernet(key).encrypt(plaintext)

def decrypt_bytes(data: bytes, passphrase: str) -> bytes:
    """Decrypt a salt+ciphertext blob for a given passphrase."""
    salt, ciphertext = data[:16], data[16:]
    try:
        key = derive_key(passphrase, salt)
        return Fernet(key).decrypt(ciphertext)
    except InvalidToken as e:
        raise ValueError("Wrong passphrase or corrupted data") from e

OWNER_CONSTANT = b"digital-locket-owner"


def create_owner_marker(passphrase: str) -> str:
    """Return a URL-safe base64 owner verifier; the passphrase itself is never stored."""
    return base64.urlsafe_b64encode(encrypt_bytes(OWNER_CONSTANT, passphrase)).decode("ascii")


def verify_owner_marker(marker_b64: str, passphrase: str) -> bool:
    """Return True when the passphrase can decrypt the owner verifier."""
    try:
        data = base64.urlsafe_b64decode(marker_b64)
    except (ValueError, TypeError):
        return False
    try:
        return decrypt_bytes(data, passphrase) == OWNER_CONSTANT
    except ValueError:
        return False

_SHRED_CHUNK_SIZE = 1024 * 1024


def shred_and_delete(file_path: Path) -> bool:
    """Overwrite the file's bytes in place with random data (1 MiB chunks) and fsync,
    then delete it so consumer recovery tools (undelete / disk carving) cannot resurrect it.

    Returns True when the file was overwritten and removed. On failure the file is left
    in place — it is never deleted without being ruined.
    """
    if not file_path.is_file():
        return False
    file_size = file_path.stat().st_size
    try:
        with open(file_path, "r+b") as f:
            remaining = file_size
            while remaining > 0:
                chunk = min(_SHRED_CHUNK_SIZE, remaining)
                f.write(os.urandom(chunk))
                remaining -= chunk
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        app_logger.warning("Could not securely shred %s: %s", file_path, e)
        return False
    file_path.unlink(missing_ok=True)
    return True


def shred_folder_contents(path: Path) -> int:
    """Shred every file under path (deepest first) and prune the empty subdirectories.

    The root folder itself is kept so it stays usable as the working area. Returns the
    number of files shredded; files that could not be opened are left in place.
    """
    count = 0
    if not path.is_dir():
        return count
    for child in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if child.is_file():
            if shred_and_delete(child):
                count += 1
        elif child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass
    return count


def lock_files(source_dir: str, vault_dir: str, passphrase: str):
    """LOCK logic: Encrypts files, saves them to a vault, ruins & deletes originals."""
    source = Path(source_dir)
    vault = Path(vault_dir)
    vault.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        print(f"Error: Source path '{source}' does not exist.")
        return

    files_to_lock = [p for p in source.rglob('*') if p.is_file()]
    if not files_to_lock:
        print("No files found to lock.")
        return

    for file_path in files_to_lock:
        print(f"🔒 Locking: {file_path.relative_to(source)}")
        
        # 1. Read original content
        with open(file_path, "rb") as f:
            plaintext = f.read()

        # 2+3. Encrypt data with a fresh salt (prepended to the ciphertext)
        encrypted = encrypt_bytes(plaintext, passphrase)

        # 4. Store [Salt (16 bytes) + Ciphertext] into vault (preserving relative structure)
        rel_path = file_path.relative_to(source)
        vault_file_path = vault / f"{rel_path}.enc"
        vault_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(vault_file_path, "wb") as vf:
            vf.write(encrypted)

        # 5. Ruin and delete original file
        shred_and_delete(file_path)

    print("\n✅ LOCK complete: Files encrypted, stored in vault, and originals securely shredded.")

def show_files(vault_dir: str, target_dir: str, passphrase: str):
    """SHOW logic: Decrypts .enc files from the vault and restores them to target path."""
    vault = Path(vault_dir)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if not vault.exists():
        print(f"Error: Vault path '{vault}' does not exist.")
        return

    enc_files = [p for p in vault.rglob('*.enc') if p.is_file()]
    if not enc_files:
        print("No encrypted files found in the vault.")
        return

    for enc_file_path in enc_files:
        print(f"🔓 Unlocking: {enc_file_path.relative_to(vault)}")

        with open(enc_file_path, "rb") as vf:
            data = vf.read()

        try:
            # Re-derive key and decrypt
            plaintext = decrypt_bytes(data, passphrase)
        except ValueError as e:
            app_logger.error("Failed to decrypt %s. %s", enc_file_path.name, e)
            continue
        except Exception as e:
            app_logger.error("Failed to decrypt %s. Unexpected error: %s", enc_file_path.name, e)
            raise RuntimeError(f"Failed to decrypt {enc_file_path.name}. Unexpected error: {e}")

        # Restore to original directory structure (stripping the '.enc' suffix)
        rel_path = enc_file_path.relative_to(vault).with_suffix('')
        restored_file_path = target / rel_path
        restored_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(restored_file_path, "wb") as tf:
            tf.write(plaintext)

    print("\n✅ SHOW complete: Files successfully decrypted and restored.")

def _clear_folder(path: Path) -> None:
    """Delete every file inside path and prune the empty subdirectories (root kept)."""
    if not path.is_dir():
        return
    for child in path.rglob("*"):
        if child.is_file():
            child.unlink(missing_ok=True)
    for directory in sorted((p for p in path.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def _archive_dir(path: Path) -> tuple[int, bytes]:
    """Zip a directory tree into memory, returning (total_content_size, zip_bytes)."""
    buffer = io.BytesIO()
    total_size = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = file_path.relative_to(path).as_posix()
            zf.write(file_path, arcname=rel)
            total_size += file_path.stat().st_size
    return total_size, buffer.getvalue()


def _shred_tree(path: Path) -> None:
    """Shred every file under path (deepest first), then remove the empty directories."""
    shred_folder_contents(path)
    try:
        path.rmdir()
    except OSError:
        pass


def _extract_folder(blob: bytes, out_dir: Path) -> bool:
    """Extract an archived folder blob into out_dir atomically. Returns True on success."""
    tmp = out_dir.parent / f".locket-tmp-{uuid.uuid4().hex}"
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for member in zf.namelist():
                if member.startswith("/") or ":" in member or ".." in Path(member).parts:
                    return False
            zf.extractall(tmp)
        out_dir.mkdir(parents=True, exist_ok=True)
        for child in tmp.iterdir():
            shutil.move(str(child), out_dir / child.name)
        return True
    except (OSError, zipfile.BadZipFile, ValueError, RuntimeError):
        app_logger.error("Failed to extract folder into %s", out_dir)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def unload_files(
    vault_dir: str, target_dir: str, passphrase: str, clean: bool = False
) -> tuple[int, int]:
    """Decrypt every .enc from the vault into target_dir.

    When clean=True the target folder is emptied first, so freshly decrypted files always
    land instead of being skipped by an older copy. File blobs (vaults/*.enc) are written as
    files; folder blobs (vaults/folders/*.enc) are extracted back to a directory of the same
    name, restoring contents and inner structure.

    Returns (unloaded, skipped). With clean=True, skipped counts only entries that could not
    be decrypted/restored. With clean=False, entries already present in the target are left
    untouched and counted as skipped.
    """
    vault = Path(vault_dir)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if clean:
        _clear_folder(target)

    if not vault.exists():
        return 0, 0

    unloaded = 0
    skipped = 0

    for enc_file in sorted(vault.glob("*.enc")):
        out_file = target / enc_file.stem
        if out_file.exists():
            app_logger.warning("Skipped %s: already present in %s", out_file.name, target)
            skipped += 1
            continue
        try:
            plaintext = decrypt_bytes(enc_file.read_bytes(), passphrase)
        except ValueError as e:
            app_logger.error("Failed to unload %s. %s", enc_file.name, e)
            skipped += 1
            continue
        out_file.write_bytes(plaintext)
        unloaded += 1

    folders_vault = vault / "folders"
    if folders_vault.is_dir():
        for enc_file in sorted(folders_vault.glob("*.enc")):
            out_dir = target / enc_file.stem
            if out_dir.exists():
                app_logger.warning("Skipped folder %s: already present in %s", out_dir.name, target)
                skipped += 1
                continue
            try:
                blob = decrypt_bytes(enc_file.read_bytes(), passphrase)
            except ValueError as e:
                app_logger.error("Failed to unload %s. %s", enc_file.name, e)
                skipped += 1
                continue
            if _extract_folder(blob, out_dir):
                unloaded += 1
            else:
                skipped += 1

    return unloaded, skipped


def lock_folder_files(
    source_dir: str, vault_dir: str, passphrase: str
) -> tuple[list[tuple[str, int]], list[str]]:
    """Encrypt every file and top-level folder in source_dir into vault_dir, shredding each original on success.

    Files become vaults/<name>.enc; a top-level folder is archived to a single blob stored as
    vaults/folders/<name>.enc, so the vault always knows a folder from a file of the same name.
    Always re-encrypts fresh (overwriting any existing .enc) and removes stale .enc entries whose
    plaintext is no longer in the folder — the vault mirrors the folder. With an empty folder,
    nothing is touched.

    Returns (locked, failed) where locked is a list of (name, plaintext_size) and failed holds
    entries that could not be read/archived/encrypted; those are left in place, never shredded.
    """
    source = Path(source_dir)
    vault = Path(vault_dir)
    vault.mkdir(parents=True, exist_ok=True)

    locked: list[tuple[str, int]] = []
    failed: list[str] = []
    if not source.is_dir():
        return locked, failed

    entries = sorted(source.iterdir())
    names = [entry.name for entry in entries]
    if not names:
        return locked, failed

    for entry in entries:
        name = entry.name
        if entry.is_file():
            try:
                plaintext = entry.read_bytes()
            except OSError as e:
                app_logger.error("Failed to read %s. %s", name, e)
                failed.append(name)
                continue
            try:
                (vault / f"{name}.enc").write_bytes(encrypt_bytes(plaintext, passphrase))
            except OSError as e:
                app_logger.error("Failed to encrypt %s. %s", name, e)
                failed.append(name)
                continue
            if not shred_and_delete(entry):
                app_logger.warning("%s could not be shredded — left in place", name)
                failed.append(name)
                continue
            locked.append((name, len(plaintext)))
            app_logger.info("Locked %s", name)
        elif entry.is_dir():
            try:
                total_size, blob = _archive_dir(entry)
            except OSError as e:
                app_logger.error("Failed to archive %s. %s", name, e)
                failed.append(name)
                continue
            folders_vault = vault / "folders"
            folders_vault.mkdir(parents=True, exist_ok=True)
            try:
                (folders_vault / f"{name}.enc").write_bytes(encrypt_bytes(blob, passphrase))
            except OSError as e:
                app_logger.error("Failed to encrypt folder %s. %s", name, e)
                failed.append(name)
                continue
            _shred_tree(entry)
            locked.append((name, total_size))
            app_logger.info("Locked folder %s (%d bytes)", name, total_size)

    for enc in sorted(vault.glob("*.enc")):
        if enc.stem not in names:
            enc.unlink(missing_ok=True)
            app_logger.info("Removed stale %s", enc.name)
    folders_vault = vault / "folders"
    if folders_vault.is_dir():
        for enc in sorted(folders_vault.glob("*.enc")):
            if enc.stem not in names:
                enc.unlink(missing_ok=True)
                app_logger.info("Removed stale folder %s", enc.name)
        if not any(folders_vault.iterdir()):
            folders_vault.rmdir()

    return locked, failed
