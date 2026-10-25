# Blacksmith showcase

A deliberately small FastAPI "notes" app that exists to exercise the
[agentic blacksmith](https://github.com/s0b0lev/agentic-blacksmith) template. Keep changes
small and self-contained; the point is to watch the agent plan, build, preview, verify and
open a pull request.

## Layout

- `app/showcase/main.py` — the whole backend: JSON API under `/api/v1/` (Swagger at `/api/v1/docs`), SPA shell at `/`.
- `app/showcase/static/index.html` — the Vue 3 (CDN) single-page UI that calls the API.
- `app/tests/` — pytest tests using FastAPI's `TestClient`.
- `app/Dockerfile`, `docker-compose.yml` — the service the preview runs (port 8000).
- `blacksmith.yml`, `.github/workflows/blacksmith.yml` — template configuration.

## Commands

All commands run from `app/` with [uv](https://docs.astral.sh/uv/):

```sh
uv sync                              # install (dev deps included)
uv run pytest -q                     # tests
uv run ruff check . && uv run ruff format --check .   # lint and format
uv run uvicorn showcase.main:app --reload             # run locally on :8000
```

From the repository root, `docker compose up --build` runs the same thing in a container.

## Conventions

- Notes, users and login sessions live in memory on purpose (a restart clears them); do not add a database unless an issue asks for one.
- Keep dependencies in `app/pyproject.toml` and refresh `app/uv.lock` with `uv lock`
  whenever they change; the Dockerfile installs with `--frozen`.
- Every behaviour change gets a test in `app/tests/`.
- Escape anything user-supplied before putting it in HTML.
