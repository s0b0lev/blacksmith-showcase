"""A tiny in-memory notes app: one HTML page and a small JSON API."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from html import escape
from typing import Any

from fastapi import FastAPI, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

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

logger = logging.getLogger("showcase")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


@dataclass
class Message:
    to: str
    subject: str
    body: str


@dataclass
class Outbox:
    """Records outgoing mail in memory and logs it; sends via SMTP if SMTP_HOST is set."""

    messages: list[Message] = field(default_factory=list)

    def send(self, to: str, subject: str, body: str) -> None:
        self.messages.append(Message(to, subject, body))
        logger.warning("email to %s: %s\n%s", to, subject, body)
        host = os.environ.get("SMTP_HOST")
        if host:
            mail = EmailMessage()
            mail["To"] = to
            mail["From"] = os.environ.get("SMTP_FROM", "noreply@localhost")
            mail["Subject"] = subject
            mail.set_content(body)
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "25"))) as smtp:
                smtp.send_message(mail)

    def clear(self) -> None:
        self.messages.clear()


outbox = Outbox()


@dataclass
class User:
    first_name: str
    last_name: str
    email: str
    salt: bytes
    password_hash: bytes
    verified: bool = False


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


@dataclass
class Accounts:
    """Users, verification tokens and session tokens, all in memory."""

    users: dict[str, User] = field(default_factory=dict)
    verify_tokens: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)

    def register(self, first_name: str, last_name: str, email: str, password: str) -> User:
        first_name, last_name = first_name.strip(), last_name.strip()
        email = email.strip().lower()
        if not (first_name and last_name and email and password.strip()):
            raise ValueError("first name, last name, email and password are required")
        if not EMAIL_RE.match(email):
            raise ValueError("email is not valid")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
        if email in self.users:
            raise KeyError("email is already registered")
        salt = secrets.token_bytes(16)
        user = User(first_name, last_name, email, salt, hash_password(password, salt))
        self.users[email] = user
        token = secrets.token_urlsafe(32)
        self.verify_tokens[token] = email
        outbox.send(
            email,
            "Verify your email",
            f"Hi {first_name},\n\nVerify your account: {os.environ.get('BASE_URL', '').rstrip('/')}/verify?token={token}\n",
        )
        return user

    def verify(self, token: str) -> bool:
        email = self.verify_tokens.pop(token, None)
        if email is None:
            return False
        self.users[email].verified = True
        return True

    def login(self, email: str, password: str) -> str:
        user = self.users.get(email.strip().lower())
        candidate = hash_password(password, user.salt if user else b"\0" * 16)
        if user is None or not hmac.compare_digest(candidate, user.password_hash):
            raise PermissionError("invalid email or password")
        if not user.verified:
            raise ValueError("email is not verified")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = user.email
        return token

    def clear(self) -> None:
        self.users.clear()
        self.verify_tokens.clear()
        self.sessions.clear()


accounts = Accounts()


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/notes")
def list_notes() -> dict[str, list[str]]:
    return {"notes": list(store.notes)}


@app.post("/api/notes", status_code=201)
def create_note(payload: dict[str, str]) -> dict[str, str]:
    try:
        text = store.add(payload.get("text", ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"text": text}


@app.post("/api/register", status_code=201)
def api_register(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        user = accounts.register(
            *(_text(payload, k) for k in ("first_name", "last_name", "email", "password"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=exc.args[0]) from exc
    return {"email": user.email, "verified": user.verified}


@app.post("/api/login")
def api_login(payload: dict[str, Any]) -> dict[str, str]:
    try:
        token = accounts.login(_text(payload, "email"), _text(payload, "password"))
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"token": token}


@app.get("/api/me")
def me(authorization: str | None = Header(default=None)) -> dict[str, str]:
    scheme, _, token = (authorization or "").partition(" ")
    email = accounts.sessions.get(token) if scheme.lower() == "bearer" else None
    if email is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = accounts.users[email]
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
    }


def page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{escape(title)}</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto;">
{body}
</body>
</html>"""
    return HTMLResponse(html, status_code=status_code)


@app.get("/verify", response_class=HTMLResponse)
def verify(token: str = "") -> HTMLResponse:
    if accounts.verify(token):
        return page(
            "Email verified",
            '<h1>Email verified</h1><p><a href="/">Log in</a></p>',
        )
    return page(
        "Verification failed",
        "<h1>Verification failed</h1><p>This link is invalid or was already used.</p>"
        '<p><a href="/">Back home</a></p>',
        400,
    )


def signup_form(error: str = "", values: dict[str, str] | None = None) -> str:
    values = values or {}
    err = f'<p id="error" role="alert" style="color:#b00">{escape(error)}</p>' if error else ""

    def field_html(name: str, label: str, kind: str = "text") -> str:
        value = "" if kind == "password" else escape(values.get(name, ""), quote=True)
        return (
            f'<label>{label} <input name="{name}" type="{kind}" value="{value}" required></label>'
        )

    return f"""<h2>Sign up</h2>
  {err}
  <form method="post" action="/register" style="flex-direction: column;">
    {field_html("first_name", "First name")}
    {field_html("last_name", "Last name")}
    {field_html("email", "Email", "email")}
    {field_html("password", "Password", "password")}
    <button type="submit">Sign up</button>
  </form>"""


def render_index(signup: str) -> str:
    items = "".join(f"<li>{escape(n)}</li>" for n in store.notes)
    items = items or "<li><em>No notes yet.</em></li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blacksmith showcase</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto;
           padding: 0 1rem; }}
    form {{ display: flex; gap: .5rem; }}
    input {{ flex: 1; padding: .5rem; }}
    button {{ padding: .5rem 1rem; }}
  </style>
</head>
<body>
  <h1>Notes</h1>
  <form method="post" action="/notes">
    <input name="text" placeholder="Write a note" required autofocus>
    <button type="submit">Add</button>
  </form>
  <ul id="notes">{items}</ul>
  {signup}
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render_index(signup_form())


@app.post("/register", response_class=HTMLResponse)
def register_form(
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
) -> HTMLResponse:
    values = {"first_name": first_name, "last_name": last_name, "email": email}
    try:
        accounts.register(first_name, last_name, email, password)
    except (ValueError, KeyError) as exc:
        status = 409 if isinstance(exc, KeyError) else 422
        return HTMLResponse(render_index(signup_form(str(exc.args[0]), values)), status_code=status)
    return page(
        "Check your email",
        "<h1>Check your email</h1><p>We sent a verification link to "
        f"{escape(email.strip())}. Click Verify to activate your account.</p>"
        '<p><a href="/">Back home</a></p>',
    )


@app.post("/notes")
def add_note_form(text: str = Form(...)) -> RedirectResponse:
    try:
        store.add(text)
    except ValueError:
        pass
    return RedirectResponse(url="/", status_code=303)
