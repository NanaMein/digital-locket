from argon2.low_level import hash_secret_raw, Type
from base64 import urlsafe_b64encode


class KeyDerivationService:

    @staticmethod
    def _derive_key(secret, salt):
        return urlsafe_b64encode(
            hash_secret_raw(
                secret=secret,
                salt=salt,
                time_cost=3,
                memory_cost=65536,
                parallelism=4,
                hash_len=32,
                type=Type.ID
            )
        )

    def get_key(self, user_id: str | bytes, salt: bytes):
        if isinstance(user_id, str):
            user_id = bytes(user_id, 'utf-8')

        return self._derive_key(user_id, salt)


