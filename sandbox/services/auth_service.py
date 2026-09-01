from fastapi import Response, Request
from datetime import timedelta
from cachetools import TTLCache
import secrets as __secrets



def generate_id():
    return __secrets.token_urlsafe(32)


class AccessTokenService:
    max_age = int(timedelta(minutes=5).total_seconds())
    # test_max_age = 2

    def __init__(self, request: Request, response: Response):
        self.request = request
        self.response = response

    @property
    def cache(self) -> TTLCache:
        return self.request.app.state.access_cache


    def create_token(self, subject: str):
        try:
            new_id = generate_id()
            self.cache[new_id] = subject
            self.response.set_cookie(
                key="access_token",
                value=new_id,
                httponly=True,
                samesite="lax",
                max_age=self.max_age,
                secure=False,
                path="/"
            )
        except Exception as e:
            raise e

    def get_token(self):
        try:
            token = self.request.cookies.get("access_token")
            if not token:
                return None

            try:
                return self.cache[token]
            except KeyError:
                self.cache.expire()
                return None

        except Exception as e:
            raise e

    def get_token_and_id(self):
        try:
            token = self.request.cookies.get("access_token")
            if not token:
                return None, None

            try:
                return token, self.cache[token]
            except KeyError:
                self.cache.expire()
                return None, None
        except Exception as e:
            raise e

class RefreshTokenService:
    max_age = int(timedelta(hours=1).total_seconds())
    # test_max_age = 15

    def __init__(self, request: Request, response: Response):
        self.request = request
        self.response = response

    @property
    def cache(self) -> TTLCache:
        return self.request.app.state.refresh_cache

    def create_token(self, subject: str):
        try:
            new_id = generate_id()
            self.cache[new_id] = subject
            self.response.set_cookie(
                key="refresh_token",
                value=new_id,
                httponly=True,
                samesite="strict",
                max_age=self.max_age,
                secure=False,
                path="/"
            )
        except Exception as e:
            raise e

    def get_token(self):
        try:
            token = self.request.cookies.get("refresh_token")
            if not token:
                return None

            try:
                return self.cache[token]
            except KeyError:
                self.cache.expire()
                return None

        except Exception as e:
            raise e

    def reset_cache(self, token: str):
        self.cache.pop(token, None)
        self.cache.expire()


    def get_token_and_id(self):
        try:
            token = self.request.cookies.get("refresh_token")
            if not token:
                return None, None

            try:
                return token, self.cache[token]
            except KeyError:
                self.cache.expire()
                return None, None
        except Exception as e:
            raise e
