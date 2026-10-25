"""A tiny in-memory notes app: a JSON API under /api/v1 and a Vue SPA shell at /."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

app = FastAPI(
    title="Blacksmith showcase",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url=None,
)


@dataclass
class Store:
    """Notes live in memory; a restart clears them."""

    notes: list[str] = field(default_factory=list)

    def add(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("note must not be empty")
        self.notes.append(text)
        return text

    def clear(self) -> None:
        self.notes.clear()


store = Store()

SESSION_COOKIE = "session"
USERNAME_MIN, USERNAME_MAX, PASSWORD_MIN = 3, 32, 8


@dataclass
class Users:
    """Users and sessions live in memory too; a restart logs everyone out."""

    # lowercased username -> (display name, salt, password hash)
    users: dict[str, tuple[str, bytes, bytes]] = field(default_factory=dict)
    # session token -> lowercased username
    sessions: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)

    def register(self, username: str, password: str) -> str:
        username = username.strip()
        if not username or not password.strip():
            raise ValueError("username and password must not be blank")
        if not USERNAME_MIN <= len(username) <= USERNAME_MAX:
            raise ValueError(f"username must be {USERNAME_MIN}-{USERNAME_MAX} characters")
        if len(password) < PASSWORD_MIN:
            raise ValueError(f"password must be at least {PASSWORD_MIN} characters")
        key = username.lower()
        if key in self.users:
            raise ValueError("username is already taken")
        salt = secrets.token_bytes(16)
        self.users[key] = (username, salt, self._hash(password, salt))
        return username

    def authenticate(self, username: str, password: str) -> str | None:
        record = self.users.get(username.strip().lower())
        if record is None:
            return None
        name, salt, digest = record
        if hmac.compare_digest(digest, self._hash(password, salt)):
            return name
        return None

    def login(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token] = username.strip().lower()
        return token

    def current(self, token: str | None) -> str | None:
        key = self.sessions.get(token or "")
        record = self.users.get(key) if key else None
        return record[0] if record else None

    def logout(self, token: str | None) -> None:
        self.sessions.pop(token or "", None)

    def clear(self) -> None:
        self.users.clear()
        self.sessions.clear()


users = Users()


class Credentials(BaseModel):
    username: str = ""
    password: str = ""


class NoteIn(BaseModel):
    text: str = ""


def session_user(request: Request) -> str | None:
    return users.current(request.cookies.get(SESSION_COOKIE))


def require_user(request: Request) -> str:
    user = session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def session_response(username: str, status_code: int) -> Response:
    res = Response(
        content=json.dumps({"username": username}),
        media_type="application/json",
        status_code=status_code,
    )
    res.set_cookie(SESSION_COOKIE, users.login(username), httponly=True, samesite="lax")
    return res


v1 = APIRouter(prefix="/api/v1")


@v1.get("/", include_in_schema=False)
def v1_root() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/docs", status_code=307)


@v1.get("/health")
def health_v1() -> dict[str, str]:
    return {"status": "ok"}


@v1.post("/auth/register", status_code=201)
def register(creds: Credentials) -> Response:
    try:
        name = users.register(creds.username, creds.password)
    except ValueError as exc:
        status = 409 if "taken" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return session_response(name, 201)


@v1.post("/auth/login")
def login(creds: Credentials) -> Response:
    name = users.authenticate(creds.username, creds.password)
    if name is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return session_response(name, 200)


@v1.get("/auth/me")
def me(user: str = Depends(require_user)) -> dict[str, str]:
    return {"username": user}


@v1.post("/auth/logout", status_code=204)
def logout(request: Request) -> Response:
    users.logout(request.cookies.get(SESSION_COOKIE))
    res = Response(status_code=204)
    res.delete_cookie(SESSION_COOKIE)
    return res


@v1.get("/notes")
def list_notes(_: str = Depends(require_user)) -> dict[str, object]:
    return {"notes": list(store.notes), "count": len(store.notes)}


@v1.post("/notes", status_code=201)
def create_note(payload: NoteIn, _: str = Depends(require_user)) -> dict[str, str]:
    try:
        text = store.add(payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"text": text}


app.include_router(v1)


@app.get("/api/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    return INDEX_HTML
