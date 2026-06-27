# PRD — MCP provisioning overhaul

* **Status:** Implemented (project-scope) — see CHANGELOG `[Unreleased]`
* **Author:** InfraKit maintainers
* **Date:** 2026-06-27
* **Area:** `infrakit mcp`, `mcp.py`, `mcp_config.py`, `agent_config.py`

> **Implementation note.** Shipped: per-agent writers for Claude/Codex/Gemini/
> Copilot + generic markdown (FR-1), stdio + Streamable HTTP with the DeepWiki
> fix (FR-2), env/secret reference handling (FR-3), `infrakit mcp add [--agent]
> [--all]` + custom `--command/--url` (FR-4, FR-5), `list`/`remove`/`doctor`
> (FR-6), and a `server.json`-aligned `McpServer` model (FR-7). Deferred: live
> `--from-registry` fetch, `--scope user`, and pinned catalogue versions (FR-8 —
> shape supports it; values still `@latest`).

## TL;DR

`infrakit mcp` writes a working MCP configuration for **one** of InfraKit's five
agents (Claude). The other four get a copy-paste Markdown block they must wire up
by hand. The transport model is stale (`stdio` + deprecated `sse` only; a
Streamable-HTTP server is mislabelled as `sse`), there is no non-interactive
mode, no environment/secret handling, no list/remove/verify, and the four-recipe
catalogue is a hardcoded Python dict pinned to `@latest`. This PRD proposes a
**per-agent MCP provisioning module** with real config writers for every
supported agent, a modern transport model, safe secret handling, a scriptable
interface, and a catalogue aligned to the official MCP `server.json` schema.

## Problem

### What exists today

`infrakit mcp` ([cli.py](../src/infrakit_cli/cli.py), [mcp.py](../src/infrakit_cli/mcp.py),
[mcp_config.py](../src/infrakit_cli/mcp_config.py)):

* Interactive arrow-key picker; installs **one** recipe per invocation.
* Catalogue is a hardcoded dict of **four** recipes (`context7`, `deepwiki`,
  `aws-best-practices`, `microsoft-learn`).
* Two install paths, branched on `agent_cfg["mcp_install_path"]`:
  * **Path A — native JSON:** only `claude` sets `mcp_install_path = ".mcp.json"`.
    Merges an entry into `mcpServers`.
  * **Path B — Markdown fallback:** `codex`, `gemini`, `copilot`, `generic` all
    fall here. InfraKit appends a JSON block to `.infrakit/mcp-servers.md` and
    tells the user to wire it up manually.
* Transports handled: `stdio` and `sse` only.

### Why it is inadequate

1. **Only one agent gets a real install.** Codex, Gemini, and Copilot each have a
   real, writable per-project MCP config — InfraKit just doesn't write them. The
   "supported on five agents" promise silently degrades to "configured on one".
2. **Stale, partly-wrong transport model.** The current MCP spec (2025-11-25)
   standardises on **stdio + Streamable HTTP**; HTTP+SSE was **deprecated** in
   2025-03-26. InfraKit knows only `stdio` + `sse`, and the `deepwiki` recipe
   points `type: "sse"` at `https://mcp.deepwiki.com/mcp` — a Streamable-HTTP
   endpoint. The taxonomy is both incomplete and mislabelled.
3. **No secrets/env story.** Real servers need API keys. There is no `env`, no
   `${env:VAR}` reference syntax, no `inputs` prompting — so any server needing a
   credential can't be expressed, and the only workaround (inlining a secret into
   a committed `.mcp.json`) is a security defect.
4. **Interactive-only.** No `--recipe` / `--all` / non-interactive flags, so MCP
   setup can't run in CI, in `init`, or in a scripted bootstrap. One server per
   run, arrow-keys required.
5. **Closed, non-reproducible catalogue.** Four servers, hardcoded in Python,
   every package pinned to `@latest`. Users can't add their own server, and
   `@latest` violates InfraKit's reproducibility ethos.
6. **No lifecycle.** Add only. No `list`, `remove`, `update`, or `doctor` to see
   what's installed, remove it, or verify the server actually starts.

## Goals

* Write a **working** MCP config for every supported agent, in that agent's own
  format and location — not a manual hand-off.
* Adopt the current transport model: **stdio + Streamable HTTP (`http`)**, with
  `sse` accepted as legacy and clearly marked deprecated.
* Handle **environment variables and secrets** safely — reference syntax, never
  committed plaintext.
* Add a **non-interactive** interface usable from scripts, CI, and `init`.
* Support **custom servers** (arbitrary command/URL), not just the bundled
  catalogue.
* Add **lifecycle**: `list`, `remove`, and a `doctor`/verify step.
* Align the catalogue's data shape to the official **`server.json`** schema.

## Non-goals

* Hosting or proxying MCP servers (no gateway, no containerisation). InfraKit
  configures clients; it does not run servers.
* Implementing an OAuth client/token store. For remote servers we emit config and
  defer the OAuth 2.1 handshake to the agent, which owns that flow.
* Fetching the live registry at `init` time. InfraKit's init is **offline by
  contract**; any registry fetch is an explicit, opt-in online action only.
* Auto-installing the underlying server packages (npm/PyPI). Those run via
  `npx`/`uvx` at agent runtime, as today.

## Background — the MCP landscape (mid-2026)

### Transports

* **stdio** — local subprocess, JSON-RPC over stdin/stdout. Inherits the host's
  trust level; credentials via environment variables are appropriate.
* **Streamable HTTP** (`type: "http"`) — single endpoint (e.g. `/mcp`) accepting
  POST and GET; the server may upgrade to SSE for streaming. Introduced in spec
  2025-03-26, retained in 2025-11-25. **This is the modern remote transport.**
* **HTTP+SSE** (`type: "sse"`) — **deprecated** since 2025-03-26; kept only for
  backward compatibility.

### Per-agent config formats (the crux)

The same logical server serialises differently per agent. A correct writer must
know each shape:

| Agent | Project-scope file | Format | Top-level key | Remote field | Secret reference |
|-------|--------------------|--------|---------------|--------------|------------------|
| Claude Code | `.mcp.json` | JSON | `mcpServers` | `type:"http"`, `url` | `${VAR}` / `${VAR:-default}` expansion |
| Codex CLI | `.codex/config.toml` (or `~/.codex/config.toml`) | TOML | `[mcp_servers.<name>]` | `url` | `env` table |
| Gemini CLI | `.gemini/settings.json` | JSON | `mcpServers` | **`httpUrl`** (streamable); `url` (sse) | `env`, `headers` |
| GitHub Copilot / VS Code | `.vscode/mcp.json` | JSON | **`servers`** + `inputs` | `type:"http"`, `url` | `${input:...}` / `${env:...}` |
| generic | `.infrakit/mcp-servers.md` | Markdown | — | — | manual (documented) |

Three traps a single shared writer would hit: **file format** (Codex is TOML),
the **remote URL field** (`url` vs Gemini's `httpUrl`), and the **top-level key**
(VS Code's `servers`, not `mcpServers`). Each is a distinct adapter.

### Secrets

* Never write a secret into a committed config. Use the agent's reference syntax
  (`${env:VAR}`, `${input:...}`) so the value resolves at runtime.
* **stdio** servers take credentials via `env`.
* **Remote** servers exposed over the internet must use **OAuth 2.1 + PKCE**
  (mandated by the 2025-11-25 spec); InfraKit emits the server config and lets the
  agent run the OAuth flow.

### Registry and `server.json`

The official MCP Registry standardises a **`server.json`** descriptor
(`name`, `description`, `version`, `packages[]`, `remotes[]`). Packages carry
`registryType` (npm/pypi/oci), `identifier`, `version`, `transport`, and
`environmentVariables[]` with `isRequired` / `isSecret` / `default`. Remotes carry
`type` (`streamable-http`/`sse`), `url`, and `headers`. Aligning InfraKit's
recipe shape to `server.json` makes each recipe a near-verbatim registry entry and
keeps one renderer that can target any agent.

## Users and use cases

* **As a platform engineer** initialising a project, I run one command and every
  agent on my team (Claude, Codex, Gemini, Copilot) gets the docs servers wired
  up correctly — no per-tool copy-paste.
* **As a CI/bootstrap script**, I install a fixed, pinned set of servers
  non-interactively and reproducibly.
* **As a security-conscious user**, I add a server that needs an API key without
  ever committing the key.
* **As a power user**, I register a custom internal MCP server by command or URL.
* **As a maintainer**, I list what's configured, remove one, and verify it starts.

## Requirements

### Functional

* **FR-1 — Per-agent writers.** Provision the selected server into the active
  agent's real config (table above). Each agent is its own adapter behind a shared
  interface. `generic` keeps the documented Markdown fallback (it has no canonical
  file by definition).
* **FR-2 — Transport model.** First-class `stdio` and `http` (Streamable HTTP).
  Accept `sse` as input but render it per-agent and mark it deprecated. Map the
  remote URL to the correct per-agent field (`url` vs `httpUrl`). Fix the
  `deepwiki` recipe to `http`.
* **FR-3 — Env and secrets.** Recipes and custom servers may declare
  `environment_variables` with `is_required` / `is_secret`. Writers emit the
  agent's reference syntax; InfraKit never writes a secret value. A secret with no
  resolvable env var produces a clear warning, not a silent inline value.
* **FR-4 — Non-interactive interface.** `infrakit mcp add <recipe> [--agent ...]`,
  `infrakit mcp add --all`, and a custom form
  (`--command/--args` or `--url --transport http`). The interactive picker remains
  the default when no recipe is named.
* **FR-5 — Custom servers.** Add an arbitrary stdio or remote server not in the
  catalogue.
* **FR-6 — Lifecycle.** `infrakit mcp list`, `infrakit mcp remove <name>`, and
  `infrakit mcp doctor` (best-effort verify the command resolves / endpoint
  reachable). `add` stays idempotent.
* **FR-7 — Catalogue shape.** Recipes adopt a `server.json`-aligned shape
  (packages/remotes, `registryType`, `environment_variables`). Optionally seed a
  recipe from a local `server.json` path. Catalogue stays **bundled** (offline);
  pulling from the live registry is a separate opt-in online flag.
* **FR-8 — Pinning.** Recipes carry explicit pinned versions; `@latest` is opt-in.

### Non-functional

* **NFR-1 — Offline by default.** `infrakit mcp` performs no network calls unless
  the user passes an explicit online flag (e.g. `--from-registry`). Preserves the
  init/offline contract.
* **NFR-2 — No secret ever committed.** Enforced by construction (reference syntax
  only) and covered by a test.
* **NFR-3 — Reproducible.** Default to pinned versions; deterministic output.
* **NFR-4 — Testable through one interface.** Per-agent writers are pure
  `(server spec) → (file content)` functions, unit-tested per agent without
  touching the filesystem or a live agent. (See Design.)
* **NFR-5 — Doc/command sync.** New subcommands and recipe set stay in sync with
  README/AGENTS/docs and the `infrakit mcp` help — InfraKit's standing doc gate.

## Proposed design

A **deep MCP provisioning module** with a small interface and per-agent adapters
behind a real seam.

```text
                 server spec (server.json-aligned)
                              │
                ┌─────────────▼──────────────┐
                │   mcp provisioning module   │   interface:
                │  provision(agent, server)   │   provision() · render(agent, server)
                │  render(agent, server)      │   list() · remove() · verify()
                └─────────────┬──────────────┘
        ┌──────────┬──────────┼───────────┬────────────┐
        ▼          ▼          ▼           ▼            ▼
   claude       codex      gemini      copilot      generic
  .mcp.json   config.toml settings.json .vscode/    mcp-servers.md
   (JSON)       (TOML)      (JSON)      mcp.json      (doc)
```

* **One interface, N adapters.** `render(agent, server) -> (path, content)` is the
  seam; each agent is an adapter that knows its file, format, key, and field
  names. This is a *real* seam — four agents genuinely vary across it — unlike a
  hypothetical one-implementation wrapper.
* **`server.json`-aligned spec** is the single internal representation; recipes and
  custom/registry servers all become one spec, rendered per agent.
* **Locality:** "how Codex serialises an MCP server" lives in exactly one place;
  today that knowledge doesn't exist at all (Codex gets Markdown).
* **The interface is the test surface:** assert `render("gemini", brave)` emits
  `httpUrl`; assert `render("copilot", brave)` emits a `servers` key and an
  `inputs` entry for the API key; assert no adapter ever inlines a secret.

This is the same deepening the architecture review flagged: per-agent config
writers are the textbook "two adapters justify the seam" case.

## Phasing

* **Phase 1 — MVP (correctness).** Per-agent writers for Claude, Codex, Gemini,
  Copilot (FR-1); modern transport model + fix `deepwiki` (FR-2);
  `server.json`-aligned recipe shape + pinning (FR-7, FR-8). Keep the interactive
  picker. Outcome: every agent gets a real, correct config.
* **Phase 2 — Safety + automation.** Env/secret handling (FR-3); non-interactive
  flags + `--all` (FR-4); idempotent `add` retained. Outcome: usable in CI and for
  servers needing credentials.
* **Phase 3 — Lifecycle + extensibility.** `list` / `remove` / `doctor` (FR-6);
  custom servers (FR-5); optional `--from-registry` (FR-7). Outcome: full
  lifecycle and an open catalogue.

## Risks and open questions

* **Per-agent format drift.** Agents change their MCP config formats. *Mitigation:*
  treat each adapter the way InfraKit treats provider fields — verify against the
  agent's own docs, and cover each adapter with a golden-output test.
* **Project vs user scope.** Some agents key MCP off a user/global file
  (`~/.codex/config.toml`), others off a project file. *Open question:* does
  InfraKit write project-scope only (safe, committable, matches its model) and
  document user-scope, or also offer `--scope user`? Recommend project-scope first.
* **`generic` agent.** No canonical file — the Markdown fallback stays, but should
  emit the modern shape and be clearly labelled as manual.
* **Secret UX divergence.** `${input:...}` (VS Code) vs `${env:VAR}` (Claude) vs
  TOML `env` (Codex) differ. *Mitigation:* the adapter owns the per-agent syntax;
  the recipe only declares intent (`is_secret`).
* **Catalogue vs registry.** Bundled catalogue keeps offline guarantees but ages.
  *Resolution:* bundle as source of truth; `--from-registry` is explicit opt-in.

## Success metrics

* All five agents produce a valid, agent-correct MCP config (4 written + 1
  documented) — up from 1 written.
* `infrakit mcp add <recipe> --agent <x>` runs non-interactively for every agent.
* Zero secrets written to disk in any path (asserted by test).
* Adding a new server to the catalogue touches one recipe entry and zero adapters.
* Golden-output test per agent for at least one stdio and one remote server.

## References

* [MCP transports spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
* [Why MCP deprecated SSE for Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
* [Official MCP Registry](https://registry.modelcontextprotocol.io/) · [`server.json` reference](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md)
* [Add an MCP server to any AI coding CLI (Claude/Codex/Gemini/Cursor)](https://inventivehq.com/blog/add-mcp-server-to-ai-coding-cli)
* [One MCP config for Codex, Claude, Cursor, Copilot](https://dev.to/dotwee/one-mcp-configuration-for-codex-claude-cursor-and-copilot-with-chezmoi-925)
* [MCP authorization spec](https://modelcontextprotocol.io/docs/tutorials/security/authorization) · [MCP credential/secret best practices (Doppler)](https://www.doppler.com/blog/mcp-server-credential-security-best-practices)
