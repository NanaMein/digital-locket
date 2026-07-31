from fastapi import Request, Response, HTTPException, status
from secrets import token_urlsafe
from cachetools import TTLCache
from typing import Optional, Final

__all__: Final = ["AuthSessionCookie", "get_auth_session_cookie"]


class AuthSessionCookie:
    _ttl_cache: Optional[TTLCache] = None

    def __init__(self, request: Request, response: Response):
        self.request = request
        self.response = response

    @property
    def session_cache(self) -> TTLCache:
        if self._ttl_cache is None:
            self._ttl_cache = TTLCache(maxsize=1, ttl=1800)
        return self._ttl_cache

    def create_session(self, user_id: str):
        new_token = token_urlsafe(32)
        self.session_cache.setdefault(new_token, user_id)
        self.response.set_cookie(
            key="session",
            value=new_token,
            max_age=1800,
            httponly=True,
            samesite="strict",
            secure=False
        )
        return new_token


    def get_user_id(self, rotate: bool = False) -> str:
        current_token = self.request.cookies.get("session")
        if not current_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing session cookie"
            )

        user_id = self.session_cache.get(current_token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session"
            )
        if rotate:
            self.create_session(user_id=user_id)

        return user_id


def get_auth_session_cookie(
        request: Request,
        response: Response
) -> AuthSessionCookie:
    return AuthSessionCookie(request=request, response=response)