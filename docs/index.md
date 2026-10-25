---
title: Agentic blacksmith, end to end
---

# Agentic blacksmith, end to end

This page describes what happens between adding the `blacksmith` label to a GitHub issue and
closing the pull request that comes out of it. It is written for engineers who want to
understand the machinery before adopting the
[agentic-blacksmith](https://github.com/s0b0lev/agentic-blacksmith) template, or who need to
reason about a run that did something unexpected. The
[adoption guide](https://github.com/s0b0lev/agentic-blacksmith/blob/master/docs/adopting.md)
covers setup; the
[operations guide](https://github.com/s0b0lev/agentic-blacksmith/blob/master/docs/operations.md)
covers debugging. This page covers the flow itself.

## In one paragraph

You label an issue. A GitHub Actions workflow in your repository calls a reusable workflow in
the template repository, which runs Terraform to create one DigitalOcean droplet for that
issue. The droplet bootstraps itself, clones your repository, and runs a Python runner that
drives Claude Code through six stages: plan, build, preview, verify, design, and pull request.
The preview is your app, started with Docker Compose behind Caddy and basic auth, on a public
hostname. The pull request carries screenshots, the preview link and login, and the
verification report. From then on, every comment you leave on the pull request starts a
review round on the same droplet. Closing the pull request runs the tear-down workflow, which
destroys the droplet. Nothing runs on your machine.

## The pieces

| Piece | Where it lives | What it does |
|---|---|---|
| Adopter workflow | `.github/workflows/blacksmith.yml` in your repo | Listens for label, pull request and dispatch events; calls the template's reusable workflows with your secrets |
| Config | `blacksmith.yml` in your repo | Droplet size, time limits, setup and check commands, how to preview the app |
| Reusable workflows | `spin-up.yml` and `tear-down.yml` in the template | Run Terraform against DigitalOcean; post the first and last comments |
| Terraform state | A private DigitalOcean Spaces bucket | One workspace per issue; holds the SSH key and tokens |
| Droplet | DigitalOcean, one per issue | Ubuntu 24.04 with Docker, Chrome, uv, Node 22, Claude Code, and the runner |
| Runner | `agent/blacksmith/` in the template, copied to the droplet | Orchestrates stages, deploys the preview, talks to GitHub, polls for review comments |
| Prompts and skills | `agent/prompts/` and `agent/skills/` in the template | What Claude Code is told at each stage |
| Preview | Docker Compose plus a Caddy container on the droplet | Your app on `https://pr-<n>...`, behind basic auth |

## The lifecycle

```text
 you                    GitHub Actions              DigitalOcean               the droplet
 ───                    ──────────────              ────────────               ───────────
 add label ──────────▶ spin-up workflow
                        terraform apply ──────────▶ droplet + firewall
                        comment "working on this"   + ssh key (+ DNS)
                                                                              cloud-init pulls the template,
                                                                              runs bootstrap (9 steps)
                                                                              runner first pass:
                                                                                plan ─▶ progress comment
                                                                                build ─▶ push branch
                                                                                preview ─▶ compose up + Caddy
                                                                                verify ─▶ checks + browser walk
                                                                                design ─▶ Figma compare (optional)
                                                                                pr ─▶ open pull request
 review the PR ───────────────────────────────────────────────────────────▶   poll timer (every 60 s)
 leave comments                                                               review round: reply, commit,
                                                                              push, redeploy preview
 close the PR ────────▶ tear-down workflow
                        terraform destroy ────────▶ droplet gone
                        delete assets branch
                        comment "destroyed"
```

Three things end a droplet's life: closing the pull request, removing the label before a pull
request exists, or the lifetime timer on the droplet itself.

## Phase 1: the trigger and the spin-up workflow

Adding the `blacksmith` label fires the `issues` event with action `labeled`. Your workflow's
`spin-up` job runs only for that label and calls the template's reusable `spin-up.yml`, passing
the issue number, the state bucket name, the optional preview zone, and the five secrets. The
reusable workflow then:

1. Checks that every required secret is present and fails early if not.
2. Checks out your repository's config and the template at the pinned ref.
3. Reads `blacksmith.yml` with the template's own loader, so a typo fails here, not on the droplet.
4. Confirms the issue is still open and still labelled.
5. Resolves the base branch: the `base_branch` input, or your default branch.
6. Runs `terraform init` against the Spaces bucket and selects or creates the workspace `issue-<n>`.
7. Runs `terraform apply`, which creates a generated SSH key, the droplet, a firewall that
   allows inbound TCP 22, 80 and 443 only, and, if a preview zone is set, an A record
   `pr-<n>.<zone>`. Without a zone, the hostname is `pr-<n>-<ip-with-dashes>.nip.io`.
8. Posts the first comment on the issue: "Blacksmith is working on this. Preview will be at
   …", with a link to the workflow run.
9. Writes a job summary with the preview URL, the droplet IP, the workspace name and an SSH
   hint.

The droplet's user data carries the tokens, the runner config and the config file contents.
Changing any secret changes the user data, so a later spin-up for the same issue replaces
the droplet.

## Phase 2: bootstrap on the droplet

Cloud-init downloads the template at the pinned ref into `/opt/blacksmith` and runs
`bootstrap.sh` as root. It logs to `/var/log/blacksmith-bootstrap.log` and runs nine steps:

1. **User, secrets and lifetime cap.** Creates the unprivileged `blacksmith` user, writes
   the secrets to a `0640` env file, and installs the lifetime timer first, so a droplet whose
   bootstrap fails later still destroys itself.
2. **Packages.** Docker, Google Chrome or Chromium for headless screenshots, uv, Node 22.
3. **Claude Code.** Installs it and runs a one-turn smoke test with your subscription token.
   An invalid token fails here with a comment on the issue, not an hour later.
4. **Preview host.** Records the hostname and adds an `iptables` rule so containers cannot
   reach the droplet metadata service, which would expose the tokens.
5. **Clone, branch and push guard.** Clones your repository, creates `blacksmith/issue-<n>`
   from the base branch, and installs a pre-push hook that only allows pushes to that branch
   and to `blacksmith-assets/issue-<n>`.
6. **Skills and MCP.** Copies the blacksmith skills into the agent's Claude Code
   configuration; enables your `.mcp.json` servers only when Figma is configured.
7. **Setup commands.** Runs each line of `setup:` from `blacksmith.yml` in a login shell, in
   the repository root, as the agent user. A failure stops bootstrap and the agent never starts.
8. **Fetch issue.** Writes the issue title, body and comments to `.blacksmith/issue.md`.
   This is a snapshot: comments added to the issue later are not seen by the first pass.
9. **Runner config and systemd units.** Installs the run, poll and lifetime units and starts
   the first pass.

If any step fails, the issue gets a "Blacksmith bootstrap failed at step N" comment.

## Phase 3: the first pass

The runner (`python3 -m blacksmith run`) executes six stages in order. Each stage that uses
Claude Code gets a prompt from `agent/prompts/`, a turn cap (`limits.max_turns_per_stage`),
and a slice of the wall-clock budget `limits.first_run_minutes`:

| Stage | Budget share | Claude Code writes | Runner does afterwards |
|---|---|---|---|
| plan | 10% | `plan.md`: goal, acceptance criteria, files, open questions with chosen answers | Posts the plan into the progress comment on the issue |
| build | 45% | Commits on the work branch | Pushes the branch |
| preview | 5% (fixes only) | Nothing unless the preview fails | Deploys the compose stack; on failure asks the agent to fix it, up to twice |
| verify | 20% | `verify.md`: `RESULT: pass` or `fail`, check interpretation, browser walk, findings | Runs your checks first; on failure runs a build-fix session, pushes and redeploys, up to twice |
| design | 10% | `design.md` comparing screenshots with Figma frames | Skips with a reason unless Figma is enabled, the key is set and design paths changed |
| pr | 5% | `pr.md`: title, summary with screenshots, "What I was unsure about" | Pushes screenshots to an assets branch, opens the pull request, requests the issue author's review |

Every stage prompt begins with the same rule: the agent runs unattended and never asks a
human a question. Ambiguity is resolved in writing instead (see below).

**The progress comment.** One comment on the issue, headed "**Blacksmith** is working on this
issue on branch …", is edited in place as milestones arrive: the plan, "Preview is up at …"
with the login, and finally "Opened <PR URL>". Its last line shows the current stage.

**How the preview is built.** The runner never edits your compose file. It generates an
override that removes every published port, replaces the `image:` of each service listed under
`preview.build` with a build from the work branch, applies your `images`, `reset`, `overrides`
and `drop` settings, and adds a `caddy` container publishing 80 and 443. Caddy gets a TLS
certificate for the hostname, routes paths to services as listed in `preview.routes`, and
enforces basic auth with user `preview` and a password generated once per droplet. `.env` is
written from your `env_example` with empty and `change-me` values replaced by random strings,
then `preview.env` on top. Services under `infra` start first, then `seed` runs, then the rest.
The preview counts as up when `preview.ready` answers 2xx or 3xx within ten minutes.

**Verification.** The runner runs `checks_setup` and `checks` itself and hands the results
table to the agent. The agent then walks the preview in headless Chrome, screenshots every
state the acceptance criteria name, and writes the report. A required check failing or any
criterion unmet means `RESULT: fail`, which triggers a fix loop.

**Salvage.** If a stage cannot produce what the next one needs, or the budget runs out, the
runner commits and pushes whatever exists and opens a draft pull request titled
`[blacksmith] <issue title> (incomplete)` with the reason and the last 200 lines of its log.
The droplet stays up so you can inspect it.

## Phase 4: review rounds

Once a pull request exists, a systemd timer runs the poll command every 60 seconds. Each
poll fetches issue comments, inline review comments and submitted reviews on the pull request
that are newer than the last round, and ignores everything carrying the hidden
`<!-- blacksmith:… -->` marker, which is how the agent recognises its own output. Any other
comment, including from CI bots, counts as feedback.

When there is feedback, one round runs under a lock, with its own budget
`limits.review_round_minutes`:

1. Claude Code reads the comments, the plan, the issue and your `CLAUDE.md` files.
2. For each comment it either makes the change, runs the relevant tests and commits, or
   declines with a reason. Questions are answered from the code.
3. It writes `replies.json`; the runner posts one reply per comment, ending with the commit
   sha when code changed.
4. The runner pushes the branch and redeploys the preview.
5. It posts or updates a comment `Round <n>: addressed <k> comment(s) in <sha>; preview ok`.

Rounds continue for as long as the droplet lives. A pending, unsubmitted review is not
feedback yet.

## Phase 5: end of life and tear-down

Three events reach the `resolve` and `tear-down` jobs in your workflow:

- **Pull request closed**, merged or not, on a branch starting with `blacksmith/issue-`.
- **Label removed** from the issue. This only tears down while no pull request is open; once
  one exists, closing it is the way to stop.
- **Repository dispatch `blacksmith-self-destruct`**, sent by the droplet itself when the
  lifetime timer (`limits.lifetime_hours`, counted from boot) fires. The droplet first posts
  an expiry notice on the pull request or issue. If the runner cannot run, a plain `curl`
  sends the dispatch anyway.

The tear-down workflow selects the issue's Terraform workspace, runs `terraform destroy`,
which removes the droplet, firewall, SSH key and DNS record, deletes the workspace, deletes
the `blacksmith-assets/issue-<n>` branch that held the screenshots, and posts "Preview server
destroyed." on the pull request. Screenshot links in the pull request body stop working at
that point. The work branch is left for you to merge or delete.

## What you see on GitHub, in order

| When | Where | What |
|---|---|---|
| ~2 min after labelling | Issue | "Blacksmith is working on this. Preview will be at …" from the workflow |
| ~10 min | Issue | Progress comment gains a `### Plan` section with acceptance criteria and chosen answers to open questions |
| During the build | Repository | Commits appear on `blacksmith/issue-<n>`, authored `blacksmith[bot]` |
| After the build | Issue | Progress comment gains "Preview is up at …" with the login |
| Within the first-run budget | Pull requests | A pull request with summary, screenshots, preview link and login, verification and design reports in collapsible sections |
| After each of your comments | Pull request | A reply per comment and a `Round <n>:` summary; a new commit; the preview reflects it |
| After closing the pull request | Pull request | "Preview server destroyed." |

## How the agent handles missing details

It never asks. The plan stage lists every ambiguity under "Open questions" with the reading it
chose, and that list is posted to the issue within minutes. The pull request repeats the
assumptions under "What I was unsure about". If an assumption is wrong, say so in a pull
request comment and a review round corrects it. If the plan is wrong enough that building on
it is a waste, remove the label (which tears the droplet down while no pull request exists),
sharpen the issue text, and label it again.

Precise issues get precise work: state the acceptance criteria as behaviours a test can assert
or a screenshot can show, and name what you do not want. Conventions that apply to every
issue belong in `CLAUDE.md`, which every stage reads.

## Guardrails

- The agent runs as an unprivileged user. The GitHub token is kept out of the Claude Code
  session's environment, which prevents accidents rather than a determined agent.
- The pre-push hook limits pushes to the work branch and the assets branch. It is a guard
  against mistakes, not a security boundary.
- Containers cannot reach the droplet metadata service that holds the user data.
- Every comment the runner posts is scrubbed for the secret values before it leaves the
  droplet.
- The preview is public, protected only by basic auth whose credentials appear in the pull
  request body and the issue comment. Anyone who can read the repository can open it.
- Anyone who can add the label can start a droplet, which costs money and uses your Claude
  subscription. Restrict triage access accordingly.

## Limits and costs

| Setting | Default | Governs |
|---|---|---|
| `limits.first_run_minutes` | 120 | Wall clock for plan through pr, split by the shares above |
| `limits.review_round_minutes` | 45 | Each review round's agent session |
| `limits.max_turns_per_stage` | 200 | Agent turns per session |
| `limits.lifetime_hours` | 168 | Time from boot to self-destruct |
| `droplet.size` | `s-4vcpu-8gb` | DigitalOcean hourly price and build speed |

There is no dollar cap. Claude usage counts against the subscription behind
`CLAUDE_CODE_OAUTH_TOKEN`, the same as your own Claude Code use. The droplet bills until it is
destroyed, so close pull requests you are done with.

## When something goes wrong

Look in this order: the issue's progress comment, the pull request, the workflow run's
summary, and then the droplet over SSH, where the bootstrap log, the runner log, the state
file and one transcript per agent session are kept. The operations guide lists every path and
command.

## This repository's configuration

The showcase runs a single FastAPI service from `app/`, built from the work branch and routed
at `/` on port 8000. Setup is `uv sync --frozen`; ruff is a soft check and pytest a required
one; the readiness URL is `/api/health`. The first run is capped at 60 minutes, review rounds
at 30, and the droplet lives at most 48 hours. Both workflow `uses:` lines are pinned to the
template's `master` branch until it publishes a `v1` tag.
