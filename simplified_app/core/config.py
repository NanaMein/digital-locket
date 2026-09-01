import os
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI

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

    separator = os.getenv("SEPARATOR")

    def __init__(self):
        self.is_personal_folder_new = not self.MY_PERSONAL_FOLDER_LOCATION.is_dir()
        self.is_vault_new = not self.MY_VAULT_LOCATION.is_dir()
        self.MY_PERSONAL_FOLDER_LOCATION.mkdir(
            parents=True,
            exist_ok=True
        )
        self.MY_VAULT_LOCATION.mkdir(
            parents=True,
            exist_ok=True
        )
        self.config = self.get_settings_config()


    def get_settings_config(self):
        toml_file = BASE_DIR / "settings_config.toml"
        try:
            with open(toml_file, "rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"Configuration file not found at {toml_file}")
        except Exception as e:
            raise RuntimeError(f"Error parsing config.toml: {e}")

settings: Settings | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        print("Starting lifespan")
        global settings
        settings = Settings()

        yield
    finally:
        print("End lifespan")


class SettingsV1:
    _app_config: dict[str, Any] | None = None

    def __init__(self):
        self.load_config()
        self.is_working_directory_new = not self.directories["working_directory"].is_dir()
        self.is_secret_vault_directory_new = not self.directories["secret_vault_directory"].is_dir()


    @property
    def app_config(self) -> dict[str, Any]:
        return self._app_config

    @classmethod
    def load_config(cls):
        if cls._app_config is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            with open(base_dir / "settings_config.toml", "rb") as f:
                cls._app_config = tomllib.load(f)
        return cls._app_config

    @property
    def directories(self):
        return self.app_config["directories"]