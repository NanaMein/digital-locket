import base64
import os
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

def shred_and_delete(file_path: Path):
    """
    Overwrites the file contents with random garbage data ('ruining' it) 
    before deleting, preventing recovery from Recycle Bin/disk carve tools.
    """
    if file_path.is_file():
        file_size = file_path.stat().st_size
        try:
            with open(file_path, "wb") as f:
                if file_size > 0:
                    f.write(os.urandom(file_size))  # Overwrite with random bytes
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"Warning: Could not securely shred {file_path}: {e}")
        
        # Delete the ruined file
        file_path.unlink()

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

# ==================== EXAMPLE USAGE ====================
if __name__ == "__main__":
    PASSPHRASE = "my_super_secret_passphrase123"
    SOURCE_FOLDER = "./my_secret_docs"
    VAULT_FOLDER = "./my_vault"
    RESTORE_FOLDER = "./my_restored_docs"

    # # --- Setup a dummy file to test ---
    # os.makedirs(SOURCE_FOLDER, exist_ok=True)
    # with open(os.path.join(SOURCE_FOLDER, "confidential.txt"), "w") as f:
    #     f.write("Top Secret Passwords and Notes: 12345")

    # print("--- STEP 1: LOCKING FILES ---")
    # lock_files(SOURCE_FOLDER, VAULT_FOLDER, PASSPHRASE)

    # print("\n--- STEP 2: SHOWING (DECRYPTING) FILES ---")
    # show_files(VAULT_FOLDER, RESTORE_FOLDER, PASSPHRASE)


    print(Path(VAULT_FOLDER).absolute())
