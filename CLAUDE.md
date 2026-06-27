# CLAUDE.md

Guidance for working in the **InfraKit** repository. Read this first; it is the
architecture map and the list of cross-file invariants that are easy to break.

> See also: [AGENTS.md](./AGENTS.md) for how to add a new AI agent, and
> [RELEASING.md](./RELEASING.md) for the release pipeline.

## What this project is

InfraKit is **spec-kit for Infrastructure-as-Code**, plus a four-persona review
pipeline. It is a Python CLI (`infrakit-cli`, published to PyPI) that bootstraps
a project with slash commands + agent personas for a chosen AI coding agent and a
chosen IaC tool. The CLI ships prompt/persona/asset **templates** inside the
wheel and renders the per-agent layout on the user's machine at `infrakit init`
time — there are **no network calls** during init.

The end-user workflow the templates drive:
`setup` → spec (`new_composition` / `create_terraform_code` / `create_cloudformation_code`)
→ `plan` (auto-generates `tasks.md`) → `implement` → `review`, with optional
`analyze` / `architect-review` / `security-review`. A lighter path is `quick_fix`:
the IaC Engineer plans from a requirement, generates `tasks.md`, gets the user's
review, then implements — skipping the multi-persona spec/architect/security ceremony.

The four personas: **Cloud Solutions Engineer** (spec) → **Cloud Architect**
(architecture review) → **Cloud Security Engineer** (compliance review) → **IaC
Engineer** (code; one of `terraform-engineer` / `crossplane-engineer` /
`cloudformation-engineer`).

## Repository layout

```text
src/infrakit_cli/        # The Python CLI package (published wheel)
templates/               # Prompt/persona/asset templates, force-included into the wheel
  commands/              # Generic (IaC-agnostic) slash commands
  agent_personas/        # The 3 generic personas (solutions/architect/security)
  iac/<tool>/            # Per-IaC-tool: commands/, agent_personas/, assets/
  *.md / vscode-settings.json   # Shared templates (project-context, tagging-standard)
tests/                   # pytest suite (no network)
examples/<tool>/         # Full worked walkthroughs (.infrakit/ + final deliverable)
docs/                    # DocFX sources (local build only; Pages deploy retired)
```

### CLI module map (`src/infrakit_cli/`)

`__init__.py` is a re-export shim (`__all__`) so `from infrakit_cli import X` is
stable — **keep it in sync** when adding public symbols. Per AGENTS.md, any
behavioural change to the CLI requires a version note in CHANGELOG.md.

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Typer app + the commands `init`, `check`, `version`, and the `mcp` sub-app (wired via `app.add_typer`). Arg parsing + orchestration only. |
| `agent_config.py` | `AGENT_CONFIG` — per-agent layout data (folder, command format, extension, args token, `supports_subagents`, `extras`). |
| `iac_config.py` | `IAC_CONFIG` — per-IaC-tool data (name, tools, output_format, resource_term, `generic_commands`, `iac_commands`). |
| `template_renderer.py` | `materialize_project()` — copies templates into the project, renders per-agent variants (TOML wrap, Copilot pairs, Claude subagents, path rewrites). Runtime counterpart to the old release-time bash. |
| `bootstrap.py` | `initialize_iac_config()` — writes `.infrakit/` + `.infrakit_tracks/` (config.yaml, context/coding-style/tagging, tracks registry, memory dir) then calls the renderer. |
| `skills.py` | `--ai-skills` install (commands → agent skills) + `SKILL_DESCRIPTIONS` + project-context seeding. |
| `mcp.py` / `mcp_config.py` | `infrakit mcp [add\|list\|remove\|doctor]` provisioning. `mcp_config.py` = the `McpServer`/`EnvVar` model + bundled `MCP_RECIPES` catalogue. `mcp.py` = per-agent config **writers** behind one interface (Claude `.mcp.json` · Codex `.codex/config.toml` · Gemini `.gemini/settings.json` `httpUrl` · Copilot `.vscode/mcp.json` `servers`+`inputs`). The `generic` bring-your-own agent is **not** provisionable (`supports_mcp` is False; the CLI reports it). Pure text transforms (`add_server`/`list_servers`/`remove_server`) wrapped by `provision`/`installed`/`uninstall`. Transports: stdio + Streamable HTTP (`http`); `sse` legacy. Secrets are referenced, never written. |
| `tracker.py`, `interactive.py`, `banner.py`, `console.py`, `tools.py`, `git_utils.py`, `github_api.py` | UI primitives, tool detection, git, optional version check. |

## How rendering works (the key flow)

`infrakit init` → `bootstrap.initialize_iac_config()` → `template_renderer.materialize_project()`:

1. Render `IAC_CONFIG[tool]["generic_commands"]` from `templates/commands/` and
   `IAC_CONFIG[tool]["iac_commands"]` from `templates/iac/<tool>/commands/` into
   the agent's commands dir, named `infrakit:<stem><ext>`.
2. Copy generic personas + `templates/iac/<tool>/agent_personas/` into
   `.infrakit/agent_personas/`.
3. Per-agent extras: Copilot prompt pairs, VS Code settings, and — for Claude —
   register each persona as a custom subagent at `.claude/agents/<name>.md`
   (filename from the persona's frontmatter `name:`).

The renderer is **data-driven**: a new IaC tool that follows the directory
convention needs no renderer code change. Command bodies use `{ARGS}` (→ agent
args token) and `__AGENT__` tokens; bare `memory/` `scripts/` `templates/` paths
are rewritten under `.infrakit/`.

## Cross-file invariants (break one and things silently drift)

When you add/rename/remove a command or IaC tool, update **all** of these:

1. **`iac_config.py`** — `generic_commands` / `iac_commands` lists. A command
   only renders if its stem is listed here. `generic_commands` must be identical
   across all IaC tools (a test enforces this); `iac_commands` must differ.
2. **The template file** must exist at `templates/commands/<stem>.md` (generic)
   or `templates/iac/<tool>/commands/<stem>.md` (IaC-native), with YAML
   frontmatter: `description:`, `argument-hint:`, optional `handoffs:`. Body must
   contain the `$ARGUMENTS` placeholder.
3. **Command `handoffs:` and prose cross-references** must point to commands that
   actually exist for that tool (e.g. don't reference `new_composition` from a
   terraform command).
4. **`cli.py` "Next Steps" / "Enhancement" panels** — these are hand-maintained
   strings printed after init. They must list real commands for the selected
   tool. (Historically drifted — see Gotchas.)
5. **`skills.py` `SKILL_DESCRIPTIONS`** — keys must match real command stems
   (after stripping the `infrakit:` prefix), or the enhanced description is
   silently dropped on `--ai-skills`.
6. **README.md / AGENTS.md / docs/** — supported-tool tables, command tables,
   examples. The repo's stated goal is spec-kit-grade doc/command sync.
7. **Tests** — several assert hardcoded counts or command sets
   (e.g. `test_terraform_init_command.py` asserts terraform has exactly N
   `iac_commands`; `test_terraform_templates.py` parametrizes the file list).
   Update them when the command set changes.
8. **Personas** are referenced by the engineer name in commands and, on Claude,
   by `subagent_type`. The frontmatter `name:` is the contract (e.g.
   `terraform-engineer`).

## Conventions

- **Per-IaC duplication is expected.** `plan`, `implement`, `review`,
  `setup-coding-style`, `quick_fix`, and the create/update commands are
  duplicated per IaC tool because the persona, file types, schema-lookup source,
  artifact shapes, and validation commands genuinely differ. Each lives at
  `templates/iac/<tool>/commands/<stem>.md`. Generic commands (`setup`, `status`,
  `analyze`, `architect-review`, `security-review`) are shared in
  `templates/commands/`.
- **Validation is a hard gate.** `implement` and `quick_fix` must not mark a track
  done until the tool's validator (`tofu validate` / `cfn-lint` / `crossplane
  render` / YAML parse) passes; if it can't run, the track is blocked, not done.
  The engineer personas carry the same constraint. Don't soften this to "suggested".
- **`quick_fix` is the lighter path**, per IaC tool: requirement → `plan.md` +
  `tasks.md` → user review → implement (+ the validation gate). It skips the
  multi-persona spec/architect/security ceremony but still creates a `quick` track
  for the audit trail.
- **The IaC Engineer verifies every field against authoritative docs before
  writing.** Terraform → `registry.terraform.io`; Crossplane → `doc.crds.dev`;
  CloudFormation → AWS resource-type reference / `aws-documentation` MCP. "Never
  guess argument names" is the project's core trust claim — preserve it in any
  engineer persona.
- **No separate contract file.** The code itself (`.tf` / XRD / template) is the
  machine-readable contract; `README.md` is the human-readable one. Per-resource
  artifacts written by `implement`: `.infrakit_context.md`,
  `.infrakit_changelog.md` (the old `*_contract.md` files were removed).
- **Markdown** must pass markdownlint-cli2 — it is enforced in CI
  (`.github/workflows/lint.yml`). Config in `.markdownlint-cli2.jsonc`: ATX
  headings, 2-space list indent, `*` for emphasis/bold (not `_`), and a
  language on every code fence (MD040 is on — bare ```` ``` ```` fails). Disabled
  on purpose: MD013 (line length), MD024 siblings-only, MD031/MD032 (the dense
  `> - …` Q&A prompt blocks deliberately omit blank lines around lists/fences),
  MD055/MD056 (the `[PROJECT_SPECIFIC_TAGS]` placeholder-in-table in coding-style
  assets). Mirror the existing command files' style exactly.

## Build, test, lint

```bash
uv run pytest                 # full suite (preferred)
python -m pytest tests/       # if uv unavailable
uvx ruff check src/           # style (local only; CI lint is markdownlint)
npx markdownlint-cli2 "**/*.md"   # what CI runs
uv build                      # wheel + sdist (templates force-included)
```

Offline e2e (mirrors RELEASING.md):

```bash
infrakit init demo --ai claude --iac terraform --script sh --no-git --ignore-agent-tools
test -f demo/.claude/commands/infrakit:setup.md
```

## Release

`pyproject.toml` is the source of truth for the version. Every merge to `main`
runs `.github/workflows/release.yml`, which ships the version declared in
`pyproject.toml` (PyPI + GitHub Release + tag) — but **only if no GitHub Release
exists for it yet**. So bumping `version` in your PR is what cuts a release of
that version (patch, minor, or major alike); a merge that leaves it untouched is
a no-op (the run stops at the "release already exists" guard). CI never edits
`pyproject.toml`. Add a CHANGELOG entry for user-visible changes.
