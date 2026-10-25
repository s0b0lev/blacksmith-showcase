"""A tiny in-memory notes app: one HTML page and a small JSON API."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from html import escape

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"

app = FastAPI(title="Blacksmith showcase")


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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/notes")
def list_notes() -> dict[str, object]:
    return {"notes": list(store.notes), "count": len(store.notes)}


@app.post("/api/notes", status_code=201)
def create_note(payload: dict[str, str]) -> dict[str, str]:
    try:
        text = store.add(payload.get("text", ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"text": text}


def count_label(n: int) -> str:
    if n == 0:
        return "No notes yet"
    return "1 note" if n == 1 else f"{n} notes"


def current_user(request: Request) -> str | None:
    return users.current(request.cookies.get(SESSION_COOKIE))


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def start_session(username: str) -> RedirectResponse:
    res = redirect("/")
    res.set_cookie(SESSION_COOKIE, users.login(username), httponly=True, samesite="lax")
    return res


def page(title: str, body: str, user: str | None = None) -> str:
    navbar = ""
    if user is not None:
        navbar = f"""
  <nav class="navbar navbar-expand bg-body-tertiary border-bottom mb-4">
    <div class="container">
      <a class="navbar-brand" href="/">Blacksmith showcase</a>
      <div class="dropdown ms-auto">
        <button class="btn btn-outline-secondary dropdown-toggle" type="button"
                data-bs-toggle="dropdown" aria-expanded="false">{escape(user)}</button>
        <ul class="dropdown-menu dropdown-menu-end">
          <li><a class="dropdown-item" href="/profile">Profile</a></li>
          <li>
            <form method="post" action="/logout" class="m-0">
              <button class="dropdown-item" type="submit">Logout</button>
            </form>
          </li>
        </ul>
      </div>
    </div>
  </nav>"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - Blacksmith showcase</title>
  <link href="{BOOTSTRAP_CSS}" rel="stylesheet">
</head>
<body>{navbar}
  <main class="container" style="max-width: 40rem">
{body}
  </main>
  <script src="{BOOTSTRAP_JS}"></script>
</body>
</html>"""


def auth_page(kind: str, error: str = "", status_code: int = 200) -> HTMLResponse:
    login = kind == "login"
    title = "Log in" if login else "Register"
    alert = f'<div class="alert alert-danger" role="alert">{escape(error)}</div>' if error else ""
    other = (
        'No account? <a href="/register">Register</a>'
        if login
        else 'Already registered? <a href="/login">Log in</a>'
    )
    body = f"""    <h1 class="h3 mb-3">{title}</h1>
    {alert}
    <form method="post" action="/{kind}">
      <div class="mb-3">
        <label class="form-label" for="username">Username</label>
        <input class="form-control" id="username" name="username" required autofocus>
      </div>
      <div class="mb-3">
        <label class="form-label" for="password">Password</label>
        <input class="form-control" id="password" name="password" type="password" required>
      </div>
      <button class="btn btn-primary w-100" type="submit">{title}</button>
    </form>
    <p class="mt-3">{other}</p>"""
    return HTMLResponse(page(title, body), status_code=status_code)


@app.get("/login", response_class=HTMLResponse, response_model=None)
def login_page(request: Request) -> Response:
    if current_user(request):
        return redirect("/")
    return auth_page("login")


@app.post("/login", response_model=None)
def login(username: str = Form(""), password: str = Form("")) -> Response:
    name = users.authenticate(username, password)
    if name is None:
        return auth_page("login", "Invalid username or password.", 401)
    return start_session(name)


@app.get("/register", response_class=HTMLResponse, response_model=None)
def register_page(request: Request) -> Response:
    if current_user(request):
        return redirect("/")
    return auth_page("register")


@app.post("/register", response_model=None)
def register(username: str = Form(""), password: str = Form("")) -> Response:
    try:
        name = users.register(username, password)
    except ValueError as exc:
        status = 409 if "taken" in str(exc) else 400
        return auth_page("register", str(exc), status)
    return start_session(name)


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    users.logout(request.cookies.get(SESSION_COOKIE))
    res = redirect("/login")
    res.delete_cookie(SESSION_COOKIE)
    return res


@app.get("/profile", response_class=HTMLResponse, response_model=None)
def profile(request: Request) -> Response:
    user = current_user(request)
    if user is None:
        return redirect("/login")
    body = f"""    <h1 class="h3 mb-3">Profile</h1>
    <p>Signed in as <strong id="profile-username">{escape(user)}</strong></p>"""
    return HTMLResponse(page("Profile", body, user))


@app.get("/", response_class=HTMLResponse, response_model=None)
def index(request: Request) -> Response:
    user = current_user(request)
    if user is None:
        return redirect("/login")
    items = "".join(f'<li class="list-group-item">{escape(n)}</li>' for n in store.notes)
    items = items or '<li class="list-group-item text-muted"><em>No notes yet.</em></li>'
    body = f"""    <h1 class="h3">Notes</h1>
    <p id="count" class="text-muted">{count_label(len(store.notes))}</p>
    <form method="post" action="/notes" class="input-group mb-3">
      <input class="form-control" name="text" placeholder="Write a note" required autofocus>
      <button class="btn btn-primary" type="submit">Add</button>
    </form>
    <ul id="notes" class="list-group">{items}</ul>"""
    return HTMLResponse(page("Notes", body, user))


@app.post("/notes")
def add_note_form(request: Request, text: str = Form(...)) -> RedirectResponse:
    if current_user(request) is None:
        return redirect("/login")
    try:
        store.add(text)
    except ValueError:
        pass
    return redirect("/")
