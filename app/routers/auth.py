
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logger import app_logger

router = APIRouter()


class LoginRequest(BaseModel):
    name: str
    passphrase: str



@router.post(path="/login")
async def login(user_login: LoginRequest):
    app_logger.info(f"Login attempt by user: {user_login.name}")
    return {"message": "login successful"}
