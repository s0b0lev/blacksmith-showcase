# Blacksmith showcase

A tiny FastAPI notes app wired up to the
[agentic blacksmith](https://github.com/s0b0lev/agentic-blacksmith) template. It exists to
debug and demonstrate the template: label an issue `blacksmith`, and a DigitalOcean droplet
spins up where Claude Code plans, builds, previews, verifies and opens a pull request.

## How it is wired

- `.github/workflows/blacksmith.yml` calls the template's reusable `spin-up` and `tear-down`
  workflows. Both are pinned to `@master` (with `template_ref: master`) until the template
  publishes its `v1` tag.
- `blacksmith.yml` tells the droplet how to set up (`uv sync`), what to check (ruff is soft,
  pytest is required) and how to preview (`docker-compose.yml`, service `web` on port 8000,
  everything behind basic auth).
- `app/` is the app itself. See [CLAUDE.md](CLAUDE.md) for commands and conventions.

## One-time setup still needed on GitHub

Follow the template's [adoption guide](https://github.com/s0b0lev/agentic-blacksmith/blob/master/docs/adopting.md)
to create the tokens, then in Settings → Secrets and variables → Actions add:

| Secret | Source |
|---|---|
| `BLACKSMITH_GITHUB_TOKEN` | fine-grained PAT for this repo: Contents, Pull requests, Issues (read/write) |
| `DIGITALOCEAN_TOKEN` | DigitalOcean API token |
| `SPACES_ACCESS_KEY_ID`, `SPACES_SECRET_ACCESS_KEY` | DigitalOcean Spaces key pair |
| `CLAUDE_CODE_OAUTH_TOKEN` | output of `claude setup-token` |

| Variable | Value |
|---|---|
| `BLACKSMITH_STATE_BUCKET` | name of the private Spaces bucket for Terraform state (region `fra1`) |
| `BLACKSMITH_PREVIEW_ZONE` | optional delegated DNS zone; leave unset to use nip.io |

The `blacksmith` label already exists. Once the secrets are in place, open an issue describing
a small change to the notes app and add the label.

## Running locally

```sh
cd app && uv sync && uv run pytest -q
docker compose up --build        # http://localhost:8000
```
