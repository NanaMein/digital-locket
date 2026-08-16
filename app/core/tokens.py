import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass

ACCESS_TTL_SECONDS = 300
REFRESH_TTL_SECONDS = 1800
MAX_SESSIONS = 128


@dataclass
class _Entry:
    session_id: str
    passphrase: str
    kind: str  # "access" | "refresh"
    expires_at: float


class TokenStore:
    """In-memory LRU cache mapping opaque tokens to the owner passphrase.

    - Login issues an access (5 min) + refresh (30 min) token pair.
    - A valid access-token use slides the refresh TTL forward.
    - Once the access expires but the refresh is still alive, both rotate.
    - Idle sessions expire on their own; the LRU drops the oldest when full.
    """

    def __init__(
        self,
        maxsize: int = MAX_SESSIONS,
        access_ttl: float = ACCESS_TTL_SECONDS,
        refresh_ttl: float = REFRESH_TTL_SECONDS,
    ):
        self._maxsize = maxsize
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._tokens: OrderedDict[str, _Entry] = OrderedDict()

    def _now(self) -> float:
        return time.monotonic()

    def _prune(self) -> None:
        now = self._now()
        for token in [t for t, e in self._tokens.items() if e.expires_at < now]:
            del self._tokens[token]
        while len(self._tokens) > self._maxsize:
            self._tokens.popitem(last=False)

    def _store(self, session_id: str, passphrase: str, kind: str, ttl: float) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = _Entry(session_id, passphrase, kind, self._now() + ttl)
        return token

    def create(self, passphrase: str) -> tuple[str, str]:
        """Issue a fresh access + refresh pair for the passphrase."""
        self._prune()
        session_id = secrets.token_urlsafe(16)
        access = self._store(session_id, passphrase, "access", self._access_ttl)
        refresh = self._store(session_id, passphrase, "refresh", self._refresh_ttl)
        return access, refresh

    def _invalidate_session(self, session_id: str) -> None:
        for token in [t for t, e in self._tokens.items() if e.session_id == session_id]:
            del self._tokens[token]

    def _rotate(self, session_id: str, passphrase: str) -> tuple[str, str]:
        self._invalidate_session(session_id)
        access = self._store(session_id, passphrase, "access", self._access_ttl)
        refresh = self._store(session_id, passphrase, "refresh", self._refresh_ttl)
        return access, refresh

    def _slide_refresh(self, session_id: str) -> None:
        for entry in self._tokens.values():
            if entry.session_id == session_id and entry.kind == "refresh":
                entry.expires_at = self._now() + self._refresh_ttl
                return

    def validate_access(
        self, access_token: str
    ) -> tuple[str, tuple[str, str] | None] | None:
        """Validate an access token.

        Returns (passphrase, rotated_pair) where rotated_pair is set when the
        access expired but the refresh was still alive, or None when the whole
        session is dead.
        """
        self._prune()
        entry = self._tokens.get(access_token)
        if entry is None or entry.kind != "access":
            return None
        if entry.expires_at >= self._now():
            self._slide_refresh(entry.session_id)
            return entry.passphrase, None
        rotated = self._rotate(entry.session_id, entry.passphrase)
        return entry.passphrase, rotated

    def validate_refresh(
        self, refresh_token: str
    ) -> tuple[str, tuple[str, str]] | None:
        """Rotate via a still-live refresh token."""
        self._prune()
        entry = self._tokens.get(refresh_token)
        if entry is None or entry.kind != "refresh" or entry.expires_at < self._now():
            return None
        rotated = self._rotate(entry.session_id, entry.passphrase)
        return entry.passphrase, rotated