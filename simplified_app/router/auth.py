from simplified_app.auth.session_cookie import AuthSessionCookie, get_auth_session_cookie
from simplified_app.core.config import settings
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated



router = APIRouter(
    prefix="/auth",
    tags=["Passphrase authentication"],
)



@router.post("/sign-in-user")
async def sign_in_user(auth: Annotated[AuthSessionCookie, Depends(get_auth_session_cookie)]):
    pass


@router.post("/sign-up-new-user")
async def sign_up_new_user(auth: Annotated[AuthSessionCookie, Depends(get_auth_session_cookie)]):
    if settings.
