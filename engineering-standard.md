# Engineering Standards

> Portable engineering rules for Python backend repositories and AI-assisted development.

These standards apply to humans and coding agents. They are defaults, not a mandate to rewrite existing working code. Follow established repository conventions where they are coherent; document deliberate exceptions.

## 1. Core Principles

### Required
- Optimize for correctness, clarity, maintainability, and operational simplicity.
- Make the smallest change that fully solves the problem.
- Prefer explicit, boring solutions over clever abstractions.
- Keep business rules independent from frameworks and external SDKs where practical.
- Preserve backward compatibility unless a breaking change is explicitly requested.
- Match existing naming, structure, formatting, and dependency choices.

### Forbidden
- Do not introduce abstractions, dependencies, configuration, or infrastructure without a concrete need.
- Do not refactor unrelated code while implementing a focused change.
- Do not silently change public behavior or remove error handling.
- Do not leave dead code, speculative features, or unexplained workarounds.

## 2. Architecture and Boundaries

### Required
- Separate transport (HTTP, CLI, events), application orchestration, domain logic, and infrastructure concerns.
- Isolate third-party APIs, object storage, brokers, and other external control planes behind small, replaceable adapters (called `Contact` when consistent with the project).
- Define a narrow interface when multiple implementations or test substitution justify one.
- Keep adapters transport-oriented: translate requests/responses and surface meaningful errors; place policy, reconciliation, caching, and business rules above them.
- Inject dependencies explicitly or expose a stable factory/accessor as the patch point.
- Keep module dependencies directional and avoid import cycles.

### Forbidden
- Do not scatter direct external SDK calls throughout domain or application code.
- Do not create an interface and factory for every class by default.
- Do not hide business logic inside serializers, route handlers, ORM hooks, or transport adapters.
- Do not add generic repositories or service layers that only forward calls without adding value.

## 3. Python Code Quality

### Required
- Use type annotations for new or modified public functions and meaningful internal interfaces.
- Prefer standard-library features and existing project dependencies.
- Use descriptive names, small cohesive functions, and early returns when they improve clarity.
- Make resource ownership explicit: close sessions, connections, files, and clients.
- Use context managers for resources and transactions where appropriate.
- Run the repository's configured formatter, linter, type checker, and tests.
- Keep comments focused on *why*, constraints, and non-obvious decisions.

### Forbidden
- Do not suppress type/lint errors without a scoped explanation.
- Do not use mutable default arguments.
- Do not catch broad exceptions unless at a deliberate boundary with appropriate handling.
- Do not use global mutable state for request- or task-specific data.
- Do not introduce unnecessary metaprogramming or complex inheritance.

## 4. API and Error Handling

### Required
- Validate input at trust boundaries and return consistent, documented errors.
- Distinguish validation, authentication, authorization, conflict, transient dependency, and internal failures.
- Preserve stable response contracts and use explicit versioning for breaking changes.
- Set timeouts for outbound network calls.
- Retry only transient failures, with bounded attempts and backoff where appropriate.
- Ensure logs and errors contain useful context without exposing secrets.

### Forbidden
- Do not leak tracebacks, credentials, tokens, or internal implementation details to API clients.
- Do not convert unexpected failures into success responses.
- Do not retry permanent failures blindly or without a limit.

## 5. Database and Transactions

### Required
- Use real PostgreSQL for tests that depend on SQL semantics, transactions, locking, or constraints.
- Enforce critical invariants with database constraints when possible.
- Keep transactions scoped to the smallest consistent unit of work.
- Treat schema changes as deployable migrations; consider existing data and rolling deployments.
- Identify and address N+1 queries and missing indexes when relevant to the change.
- Use optimistic or pessimistic locking when concurrent writes can violate invariants.
- Keep external network calls outside database transactions unless explicitly justified.

### Forbidden
- Do not assume ORM operations are atomic across multiple statements.
- Do not rely on application-only checks for invariants that require concurrency safety.
- Do not add indexes or locks without understanding query patterns and contention.

## 6. Async Work and Background Jobs

### Required
- Design retried tasks and event handlers to be idempotent or explicitly deduplicated.
- Define retryable errors, backoff, maximum attempts, and failure visibility.
- Account for duplicate delivery, partial failure, worker crashes, and stale in-progress state.
- Acknowledge work only in a way consistent with the chosen delivery and recovery guarantees.
- Keep CPU-bound work out of event loops; avoid blocking synchronous I/O in async code.
- Use an outbox or equivalent reliability pattern when database changes and message publication must remain consistent.

### Forbidden
- Do not assume exactly-once execution from Celery or a message broker.
- Do not silently swallow task failures.
- Do not hold database locks across long-running external requests without justification.

## 7. External Contacts and Test Doubles

### Required
- When a reusable external-service boundary exists, test callers through that boundary.
- Provide a mock/fake implementing the same interface when downstream consumers need one.
- Make fakes configurable in domain terms, resettable, and able to record structured calls.
- Cover successful, failed, missing, stale, and mixed-result responses as applicable.
- Test each real adapter against its actual service or a protocol-faithful test environment, with integration tests clearly marked.

### Forbidden
- Do not patch SDK internals when the public adapter boundary can express the scenario.
- Do not place reconciliation or business policy inside transport adapters.
- Do not mistake fake-adapter tests for proof that the real integration works.
- Do not force an adapter abstraction around trivial local code.

## 8. Testing Standards

### Required
- Prefer pytest and the repository's existing test conventions.
- Test observable behavior through public APIs or meaningful module boundaries.
- Assert concrete values, persisted state, emitted events, and externally visible effects.
- Cover edge cases, invalid input, permission checks, failure paths, and concurrency where relevant.
- Prefer realistic domain objects and deterministic fixtures.
- Use real PostgreSQL/Redis for tests that depend on their behavior; mock expensive or unavailable external services at stable boundaries.
- Keep tests isolated and repeatable; explicitly label integration and slow tests.
- Start required Docker services outside the test runner, via documented orchestration (for example `docker compose up -d`).
- Add a regression test for a bug when practical.

### Forbidden
- Do not test only types, response shapes, or trivial private helpers in place of behavior.
- Do not mock internal logic merely to force a branch.
- Do not use production credentials or live production data.
- Do not make pytest unexpectedly start or stop Docker containers.
- Do not use brittle sleeps when synchronization or polling with a deadline is possible.
- Do not weaken assertions merely to make tests pass.

## 9. Security and Configuration

### Required
- Keep secrets in secret stores or environment configuration; provide safe example values.
- Apply least privilege to database users, service credentials, and API permissions.
- Validate authorization on every protected resource access, not just at route entry.
- Parameterize SQL and treat all external input as untrusted.
- Pin/manage dependencies using the repository's chosen tooling; review dependency additions.
- Sanitize sensitive values in logs, traces, exceptions, and test fixtures.

### Forbidden
- Do not commit secrets, private keys, access tokens, or real customer data.
- Do not disable TLS verification or security checks as a shortcut.
- Do not introduce unsafe dynamic code execution for untrusted input.

## 10. Observability and Operations

### Required
- Use structured logs with stable event names and relevant identifiers.
- Expose actionable metrics for latency, error rates, throughput, queue backlog, and retries where applicable.
- Propagate correlation/request IDs across service and task boundaries where practical.
- Set useful health/readiness checks and make background failures visible.
- Document operational changes, configuration, and migration/rollback considerations.

### Forbidden
- Do not log credentials or entire sensitive payloads.
- Do not rely on logs alone for critical silent failure modes.
- Do not add high-cardinality metric labels such as raw user IDs.

## 11. AI Agent Development Workflow

These rules apply to Claude Code, Codex, and other coding agents.

### Before Editing
- Read relevant repository instructions (`AGENTS.md`, this file, README, tooling configuration).
- Inspect the affected call path, existing abstractions, and tests before proposing changes.
- Identify the intended behavior, constraints, and likely failure modes.
- For nontrivial work, provide a concise plan; for small changes, proceed directly.
- Ask for clarification when a consequential product decision or ambiguous contract cannot be inferred safely.

### While Editing
- Make targeted, reviewable changes; follow existing patterns unless they are the source of the bug.
- Prefer adapting existing utilities to introducing parallel implementations.
- Update tests and documentation when behavior or contracts change.
- Do not modify unrelated files, regenerate lockfiles without need, or change dependencies casually.
- Do not invent API behavior, configuration keys, library capabilities, or test results.
- Never access or disclose secrets unnecessarily.

### Before Finishing
- Run focused tests first, then broader checks as appropriate and feasible.
- Review the diff for accidental edits, security issues, compatibility breaks, and unnecessary complexity.
- Report what changed, why, and which commands were actually run.
- Clearly distinguish passing checks, failing checks, and checks not run.
- State remaining risks or follow-up work; do not claim completion if acceptance criteria remain unmet.

### Forbidden
- Do not bypass failing tests by deleting, skipping, or weakening them without explicit justification.
- Do not make destructive database, infrastructure, or git operations without authorization.
- Do not commit, push, deploy, or modify production systems unless explicitly requested.
- Do not silently reinterpret requirements to fit an easier implementation.

## 12. Review Checklist

Before merging, verify:

- [ ] The change solves the requested problem without unrelated scope.
- [ ] Public contracts and backward compatibility are preserved or explicitly changed.
- [ ] External integrations are isolated where the boundary adds value.
- [ ] Concurrency, retries, and transaction semantics are safe where relevant.
- [ ] Tests cover meaningful behavior and concrete expected values.
- [ ] Real infrastructure is used where mocks would hide important semantics.
- [ ] Error handling, authorization, and secrets are handled correctly.
- [ ] Logs/metrics and operational documentation are updated where needed.
- [ ] Lint, types, and relevant tests were run; any omissions are disclosed.
- [ ] The final diff is understandable and contains no accidental changes.

## Adoption

Apply these rules to new code and code being materially changed. Do not perform repo-wide refactors solely to conform to this document. If a rule conflicts with a documented repository-specific decision, follow the repository-specific decision and explain the exception.