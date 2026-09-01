from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken
from argon2.low_level import hash_secret_raw, Type
import base64
import os
import io
from app.core.config import settings

# load_dotenv()

# class ConfigResources:
#     separator = b"---80f8a4b0-0b4b-4623-ba12-0a711208f7b0---"
#     input_dir = Path("my_secrets")
#     vault_dir = Path("the_vault")
#     secrets_dir = Path("unlock_secrets")
#     master_vault_file = vault_dir / "123456master.vault"
#     validation_file = vault_dir / "123456validation.vault"
#     working_dir = Path("sandbox_folder")
#
# config = ConfigResources()


# class LockResources:
#     separator = b"---80f8a4b0-0b4b-4623-ba12-0a711208f7b0---"
#     input_dir = Path("my_secrets")
#     vault_dir = Path("the_vault")
#     output_file = vault_dir / "master.vault"
#     validation_file = vault_dir / "validation.vault"
#
# lock_res = LockResources()

class DeriveKeyService:

    def get_key(self, passphrase: bytes | str, salt: bytes):
        if isinstance(passphrase, str):
            passphrase = passphrase.encode()

        raw = hash_secret_raw(
            secret=passphrase,
            salt=salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            type=Type.ID
        )
        return base64.urlsafe_b64encode(raw)


class EncryptFileService:
    def __init__(self, derive_key_service: DeriveKeyService):
        self._derive_key_service = derive_key_service

    def _create_canary_vault(self, passphrase: bytes | str, salt: bytes):
        canary_derive_key = self._derive_key_service.get_key(
            passphrase=passphrase,
            salt=salt
        )
        canary_fernet = Fernet(canary_derive_key)
        canary_token = canary_fernet.encrypt(b"CANARY_VALID")
        settings.validation_vault_file.write_bytes(salt + canary_token)

    def _create_master_vault(self, passphrase: bytes | str, salt: bytes):
        master_derive_key = self._derive_key_service.get_key(
            passphrase=passphrase,
            salt=salt
        )
        master_fernet = Fernet(master_derive_key)

        buffer = io.BytesIO()

        files =[f for f in settings.working_dir.rglob("*") if f.is_file()]

        for f in files:

            rel_path = f.relative_to(settings.working_dir).as_posix().encode()
            buffer.write(settings.separator)
            buffer.write(rel_path)
            buffer.write(settings.separator)
            buffer.write(f.read_bytes())

        encrypted = master_fernet.encrypt(buffer.getvalue())

        settings.master_vault_file.write_bytes(salt + encrypted)
        return files, settings.master_vault_file

    def _manage_file_permissions(self):
        try:

            vault_dir = settings.master_vault_dir
            vault_dir.mkdir(parents=True, exist_ok=True)
            test_file = vault_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except PermissionError as e:
            raise PermissionError(
                f"\n❌ WRITE ACCESS DENIED!\n"
                f"   Cannot write to {settings.master_vault_dir}\n"
                f"   Check folder permissions before proceeding."
            ) from e

    def _check_all_encrypted_file_exists(self):

        valid_vault_file_exists = settings.validation_vault_file.exists()
        master_vault_file_exists = settings.master_vault_file.exists()

        if valid_vault_file_exists != master_vault_file_exists:
            raise RuntimeError(
                f"\n⚠️ VAULT CORRUPTED!\n"
                f"   Found {'only canary' if valid_vault_file_exists else 'only master vault'}.\n"
                f"   Both files must exist together. Manual cleanup required."
            )
        return valid_vault_file_exists

    def _check_validation_vault(self, passphrase):

        existing_file = settings.validation_vault_file.read_bytes()
        test_salt = existing_file[:16]
        test_encrypted = existing_file[16:]

        try:
            test_key = self._derive_key_service.get_key(passphrase, test_salt)
            test_fernet = Fernet(test_key)
            test_fernet.decrypt(test_encrypted)

            print("✅ Passphrase verified. Safe to overwrite.")
        except InvalidToken:
            raise PermissionError("❌ Wrong passphrase! Vault locked.")
        except Exception:
            raise PermissionError("❌ Wrong passphrase or corrupted canary! Vault locked.")

    def _check_input_dir_exist(self):

        if not settings.working_dir.exists() or not any(settings.working_dir.rglob("*")):
            raise ValueError(f"❌ Input directory '{settings.working_dir}' is missing or empty!")



    def lock_my_files(self, passphrase):
        try:
            self._manage_file_permissions()

            is_exist = self._check_all_encrypted_file_exists()

            if is_exist:
                self._check_validation_vault(passphrase)

            self._check_input_dir_exist()

            salt = os.urandom(16)

            self._create_canary_vault(passphrase, salt)

            self._create_master_vault(passphrase, salt)
            return True

        except Exception as ex:
            raise ex

    # def check_my_files(self, passphrase):
    #     if not self.lock_resources.validation_file.exists() or not self.lock_resources.output_file.exists():
    #         return False
    #     try:
    #         self._check_validation_vault(passphrase)
    #         return True
    #     except (InvalidToken, Exception):
    #         return False
    #
    # def check_vaults(self, passphrase):
    #     if not self.lock_resources.validation_file.exists():
    #         salt = os.urandom(16)
    #         self._create_canary_vault(passphrase, salt)





class DecryptFileService:
    def __init__(self, derive_key_service: DeriveKeyService):
        self._derive_key_service = derive_key_service

    def unlock_my_files(self, passphrase):


        data = settings.master_vault_file.read_bytes()
        salt, encrypted = data[:16], data[16:]

        key = self._derive_key_service.get_key(passphrase, salt)

        decrypted = Fernet(key).decrypt(encrypted)

        parts = decrypted.split(settings.separator)

        count = 0

        for i in range(1, len(parts), 2):
            name = parts[i].decode()
            content = parts[i + 1]
            file_path = settings.working_dir / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            count += 1
        print(f"🔓 Restored {count} files → {settings.working_dir}/")




