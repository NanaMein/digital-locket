from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

FOLDER_NAME = os.getenv("MY_PERSONAL_FOLDER_NAME", None)
if not FOLDER_NAME:
    raise ValueError("MY_PERSONAL_FOLDER environment variable not set")


VAULT_NAME = os.getenv("MY_PERSONAL_VAULT_NAME", None)
if not VAULT_NAME:
    raise ValueError("MY_PERSONAL_VAULT_NAME environment variable not set")


class Settings:
    MY_PERSONAL_FOLDER_LOCATION = BASE_DIR.parent / FOLDER_NAME
    MY_VAULT_LOCATION = BASE_DIR / VAULT_NAME

    def __init__(self):
        self.MY_PERSONAL_FOLDER_LOCATION.mkdir(
            parents=True,
            exist_ok=True
        )
        self.MY_VAULT_LOCATION.mkdir(
            parents=True,
            exist_ok=True
        )


settings = Settings()