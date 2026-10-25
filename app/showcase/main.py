"""A tiny in-memory notes app: one HTML page and a small JSON API."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from fastapi import FastAPI, Form, HTTPException
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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
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
</body>
</html>"""


@app.post("/notes")
def add_note_form(text: str = Form(...)) -> RedirectResponse:
    try:
        store.add(text)
    except ValueError:
        pass
    return RedirectResponse(url="/", status_code=303)
