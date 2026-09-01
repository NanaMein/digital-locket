from simplified_app.core.config import settings
from simplified_app.services.cryptography_service import KeyDerivationService
from cryptography.fernet import Fernet
import io
import os



class LockFilesService:
    def __init__(self):
        self.key_derive = KeyDerivationService()

    def lock_file(self, user_id: str):
        salt = os.urandom(16)
        key = self.key_derive.get_key(
            user_id=user_id, salt=salt
        )

        try:
            working_folder = settings.MY_PERSONAL_FOLDER_LOCATION
            buffer = io.BytesIO()
            files = [
                f for f in working_folder.rglob("*") if f.is_file()
            ]
            for f in files:
                rel_path = f.relative_to(working_folder).as_posix().encode()
                buffer.write(self.settings.separator)
                buffer.write(rel_path)
                buffer.write(self.settings.separator)
                buffer.write(f.read_bytes())

            encrypted = Fernet(key).encrypt(buffer.getvalue())
            self.settings.master_vault_file.write_bytes(salt + encrypted)
