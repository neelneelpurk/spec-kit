# Testing

InfraKit's test suite is **fast and fully offline** — no network, no API keys,
no live AI agent. It exercises the CLI, the template renderer, the per-IaC
configuration, and an eval harness that grades the example deliverables against
the secure-defaults the personas promise.

## Running the tests

```bash
make test            # uv run pytest — the full suite
# or, without uv:
python -m pytest tests/
```

```bash
make check           # everything CI runs: ruff + markdownlint + pytest
make lint            # ruff over src/
make lint-md         # markdownlint-cli2 over **/*.md (the CI lint gate)
```

Run a single file or test while iterating:

```bash
uv run pytest tests/test_template_renderer.py
uv run pytest -k "terraform and init"
```

## What the suite covers

The suite lives in [`tests/`](./tests/) and is grouped by responsibility:

| Area | Files | What it asserts |
|------|-------|-----------------|
| CLI behavior | `test_cli_commands.py`, `test_check_command.py`, `test_check_tool.py` | `init` / `check` / `mcp` / `version` argument parsing and orchestration |
| Rendering | `test_template_renderer.py` | The per-agent layout `materialize_project()` produces (TOML wrap, Copilot pairs, Claude subagents, path rewrites) |
| Config invariants | `test_iac_config.py`, `test_agent_config.py`, `test_mcp_config.py` | `IAC_CONFIG` / `AGENT_CONFIG` shape; `generic_commands` identical across IaC tools, `iac_commands` distinct |
| Per-IaC command sets | `test_terraform_*.py`, `test_cloudformation_*.py` | Each tool's command count and template files exist and stay in sync |
| Secure-default evals | `test_evals.py` (+ [`evals/`](./evals/)) | The committed example deliverables score 100%; deliberately-insecure fixtures score ≤40% |
| UI primitives | `test_banner_group.py`, `test_step_tracker.py`, `test_select_with_arrows.py` | Banner, tracker, and interactive selection rendering |

Several tests assert **hardcoded counts or command sets** on purpose — they are
the tripwire for the cross-file invariants in
[CLAUDE.md](./CLAUDE.md#cross-file-invariants-break-one-and-things-silently-drift).
When you add, rename, or remove a command or IaC tool, expect to update them.

## The eval harness

[`evals/`](./evals/) is a deterministic, headless scorer that grades generated
IaC against the guarantees the personas make — encryption at rest, public access
blocked, required tags, no hardcoded secrets, TLS, versioning, deletion safety,
and a passing validator. `tests/test_evals.py` wires it into pytest so CI runs
the checks offline. The scorer is proven to be able to fail: it scores the three
committed examples (which must hit 100%) **and** two deliberately-insecure
fixtures (which must score ≤40%). See [`evals/README.md`](./evals/README.md).

## Offline end-to-end smoke test

`make e2e` mirrors the check in [RELEASING.md](./RELEASING.md): it builds the
wheel, runs a real `infrakit init`, and asserts the rendered command files
landed — with no network access.

```bash
make e2e
```

## Adding a test

- Put new tests in `tests/`, named `test_*.py` with `test_*` functions
  (configured in `pyproject.toml`).
- Keep them offline. The suite must never reach the network; `infrakit init`
  itself makes no network calls, and the tests rely on that.
- If your change touches a cross-file invariant (a command set, an IaC tool, an
  agent layout), add or update the assertion that guards it so the next change
  can't silently drift.
