"""MCP provisioning — render and install MCP servers into each agent's config.

InfraKit provisions MCP for the four agents whose config format it knows; each
is a small **adapter** behind one interface:

* :func:`add_server` / :func:`list_servers` / :func:`remove_server` are pure
  text transforms (text in, text out) — unit-tested without the filesystem.
* :func:`provision` / :func:`installed` / :func:`uninstall` wrap them with IO.

Per-agent targets (project scope):

============  ============================  =====  ====================  =========================
Agent         File                          Fmt    Top-level key         Remote field
============  ============================  =====  ====================  =========================
claude        ``.mcp.json``                 JSON   ``mcpServers``         ``type:"http"`` + ``url``
gemini        ``.gemini/settings.json``     JSON   ``mcpServers``         ``httpUrl``
codex         ``.codex/config.toml``        TOML   ``[mcp_servers.*]``    ``url``
copilot       ``.vscode/mcp.json``          JSON   ``servers`` + inputs   ``type:"http"`` + ``url``
============  ============================  =====  ====================  =========================

The ``generic`` (bring-your-own) agent has no known config format, so MCP
provisioning is not available for it — :func:`supports_mcp` returns False and the
CLI reports it. Transports follow the current MCP spec (stdio + Streamable HTTP);
``sse`` is accepted as legacy. Secrets are referenced (``${NAME}`` /
``${input:...}``), never written to disk.
"""

from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

import tomlkit
import typer
import yaml
from rich.panel import Panel

from .agent_config import AGENT_CONFIG
from .banner import show_banner
from .console import console
from .interactive import select_with_arrows
from .mcp_config import (
    HTTP,
    MCP_RECIPES,
    SSE,
    EnvVar,
    McpServer,
    custom_server,
    server_from_recipe,
)
from .tools import find_project_root

# Per-agent MCP config target: (project-relative path, format family).
_TARGETS: dict[str, tuple[str, str]] = {
    "claude": (".mcp.json", "json-mcpservers"),
    "gemini": (".gemini/settings.json", "json-gemini"),
    "codex": (".codex/config.toml", "toml-codex"),
    "copilot": (".vscode/mcp.json", "json-vscode"),
}


def supports_mcp(agent: str) -> bool:
    """True when InfraKit can write ``agent``'s MCP config directly."""
    return agent in _TARGETS


def target_for(agent: str) -> tuple[str, str]:
    """Return ``(project-relative path, format family)`` for an agent.

    Raises ``ValueError`` for agents InfraKit can't provision (e.g. ``generic`` —
    bring-your-own, so its config format is unknown).
    """
    if agent not in _TARGETS:
        raise ValueError(f"MCP provisioning is not supported for agent '{agent}'")
    return _TARGETS[agent]


# ---------------------------------------------------------------------------
# Per-agent entry builders (server model -> that agent's entry shape).
# ---------------------------------------------------------------------------


def _env_value(ev: EnvVar, *, vscode: bool = False) -> str:
    """Render an env value as a reference, never a literal secret."""
    if vscode:
        return f"${{input:{ev.name.lower()}}}" if ev.is_secret else f"${{env:{ev.name}}}"
    if ev.default is not None and not ev.is_secret:
        return ev.default
    return f"${{{ev.name}}}"


def _claude_entry(server: McpServer) -> dict:
    """Claude Code / Cursor ``mcpServers`` entry."""
    if server.is_remote:
        entry: dict = {"type": server.transport, "url": server.url}
        if server.headers:
            entry["headers"] = dict(server.headers)
        return entry
    entry = {"type": "stdio", "command": server.command, "args": list(server.args)}
    if server.env:
        entry["env"] = {e.name: _env_value(e) for e in server.env}
    return entry


def _gemini_entry(server: McpServer) -> dict:
    """Gemini CLI ``mcpServers`` entry — uses ``httpUrl`` for Streamable HTTP."""
    if server.transport == HTTP:
        entry: dict = {"httpUrl": server.url}
    elif server.transport == SSE:
        entry = {"url": server.url}
    else:
        entry = {"command": server.command, "args": list(server.args)}
        if server.env:
            entry["env"] = {e.name: _env_value(e) for e in server.env}
        return entry
    if server.headers:
        entry["headers"] = dict(server.headers)
    return entry


def _vscode_entry(server: McpServer) -> tuple[dict, list[dict]]:
    """VS Code / Copilot ``servers`` entry plus any ``inputs`` for secrets."""
    inputs: list[dict] = []
    if server.is_remote:
        entry: dict = {"type": server.transport, "url": server.url}
        if server.headers:
            entry["headers"] = dict(server.headers)
        return entry, inputs
    entry = {"type": "stdio", "command": server.command, "args": list(server.args)}
    if server.env:
        env_map: dict[str, str] = {}
        for e in server.env:
            env_map[e.name] = _env_value(e, vscode=True)
            if e.is_secret:
                inputs.append(
                    {
                        "id": e.name.lower(),
                        "type": "promptString",
                        "description": e.description or e.name,
                        "password": True,
                    }
                )
        entry["env"] = env_map
    return entry, inputs


def _codex_table(server: McpServer) -> dict:
    """Codex ``[mcp_servers.<name>]`` table contents."""
    if server.is_remote:
        tbl: dict = {"url": server.url}
        if server.headers:
            tbl["headers"] = dict(server.headers)
        return tbl
    tbl = {"command": server.command, "args": list(server.args)}
    if server.env:
        tbl["env"] = {e.name: _env_value(e) for e in server.env}
    return tbl


# ---------------------------------------------------------------------------
# Format-family transforms (pure: text in, text out).
# ---------------------------------------------------------------------------


def _json_load(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_dump(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def _mcpservers_add(text: str | None, name: str, entry: dict) -> str:
    data = _json_load(text)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers[name] = entry
    return _json_dump(data)


def _vscode_add(text: str | None, name: str, entry: dict, inputs: list[dict]) -> str:
    data = _json_load(text)
    servers = data.get("servers")
    if not isinstance(servers, dict):
        servers = {}
        data["servers"] = servers
    servers[name] = entry
    if inputs:
        existing = data.get("inputs")
        if not isinstance(existing, list):
            existing = []
        ids = {i.get("id") for i in existing if isinstance(i, dict)}
        for inp in inputs:
            if inp["id"] not in ids:
                existing.append(inp)
        data["inputs"] = existing
    return _json_dump(data)


def _toml_doc(text: str | None):
    return tomlkit.parse(text) if text else tomlkit.document()


def _codex_add(text: str | None, name: str, table: dict) -> str:
    doc = _toml_doc(text)
    if "mcp_servers" not in doc:
        doc["mcp_servers"] = tomlkit.table()
    tbl = tomlkit.table()
    for key, value in table.items():
        tbl[key] = value
    doc["mcp_servers"][name] = tbl
    return tomlkit.dumps(doc)


# ---------------------------------------------------------------------------
# Public adapter interface (dispatch on agent's format family).
# ---------------------------------------------------------------------------


def add_server(agent: str, text: str | None, server: McpServer) -> str:
    """Return the new config-file content with ``server`` added for ``agent``."""
    fam = target_for(agent)[1]
    if fam == "json-mcpservers":
        return _mcpservers_add(text, server.key, _claude_entry(server))
    if fam == "json-gemini":
        return _mcpservers_add(text, server.key, _gemini_entry(server))
    if fam == "toml-codex":
        return _codex_add(text, server.key, _codex_table(server))
    if fam == "json-vscode":
        entry, inputs = _vscode_entry(server)
        return _vscode_add(text, server.key, entry, inputs)
    raise ValueError(f"unknown MCP format family: {fam}")


def list_servers(agent: str, text: str | None) -> list[str]:
    """Return the names of MCP servers already configured in ``text``."""
    fam = target_for(agent)[1]
    if fam in ("json-mcpservers", "json-gemini"):
        return sorted((_json_load(text).get("mcpServers") or {}).keys())
    if fam == "json-vscode":
        return sorted((_json_load(text).get("servers") or {}).keys())
    if fam == "toml-codex":
        return sorted((_toml_doc(text).get("mcp_servers") or {}).keys())
    raise ValueError(f"unknown MCP format family: {fam}")


def remove_server(agent: str, text: str | None, name: str) -> str:
    """Return the new config-file content with ``name`` removed."""
    fam = target_for(agent)[1]
    if fam in ("json-mcpservers", "json-gemini"):
        data = _json_load(text)
        if isinstance(data.get("mcpServers"), dict):
            data["mcpServers"].pop(name, None)
        return _json_dump(data)
    if fam == "json-vscode":
        data = _json_load(text)
        if isinstance(data.get("servers"), dict):
            data["servers"].pop(name, None)
        return _json_dump(data)
    if fam == "toml-codex":
        doc = _toml_doc(text)
        servers = doc.get("mcp_servers")
        if servers is not None and name in servers:
            del servers[name]
        return tomlkit.dumps(doc)
    raise ValueError(f"unknown MCP format family: {fam}")


# ---------------------------------------------------------------------------
# Provisioning (file IO around the pure transforms).
# ---------------------------------------------------------------------------


def provision(project_root: Path, agent: str, server: McpServer) -> tuple[Path, bool]:
    """Install ``server`` into ``agent``'s config under ``project_root``.

    Returns ``(path, changed)``; ``changed`` is False when the server was already
    configured (idempotent).
    """
    relpath, _ = target_for(agent)
    path = project_root / relpath
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if server.key in list_servers(agent, existing):
        return path, False
    new_text = add_server(agent, existing, server)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    _update_index(project_root, server)
    return path, True


def installed(project_root: Path, agent: str) -> list[str]:
    """List MCP server names configured for ``agent`` under ``project_root``."""
    relpath, _ = target_for(agent)
    path = project_root / relpath
    text = path.read_text(encoding="utf-8") if path.exists() else None
    return list_servers(agent, text)


def uninstall(project_root: Path, agent: str, name: str) -> bool:
    """Remove ``name`` from ``agent``'s config. Returns True when something changed."""
    relpath, _ = target_for(agent)
    path = project_root / relpath
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if name not in list_servers(agent, text):
        return False
    path.write_text(remove_server(agent, text, name), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Installed-server index (.infrakit/mcp-use.md) and legacy helpers.
# ---------------------------------------------------------------------------


def _update_index(project_root: Path, server: McpServer) -> None:
    """Append ``server`` to ``.infrakit/mcp-use.md`` if not already listed."""
    md_path = project_root / ".infrakit" / "mcp-use.md"
    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    if f"| {server.key} |" in existing:
        return
    tools_str = ", ".join(f"`{t}`" for t in server.tools)
    new_row = f"| {server.key} | {server.description} | {tools_str} | {server.usage} |\n"
    if existing:
        updated = existing.replace("| — | — | — | — |\n", new_row)
        if updated == existing:
            updated = existing + new_row
        md_path.write_text(updated, encoding="utf-8")
    else:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(
            "# Installed MCP Servers\n\n"
            "| MCP | Description | Tools | Usage |\n"
            "|-----|-------------|-------|-------|\n" + new_row,
            encoding="utf-8",
        )


def _update_mcp_use_table(project_root: Path, recipe_key: str) -> None:
    """Backward-compatible shim: index a catalogue recipe by key."""
    _update_index(project_root, server_from_recipe(recipe_key))


def _build_mcp_server_entry(recipe_key: str) -> dict:
    """Backward-compatible shim: the Claude ``mcpServers`` entry for a recipe."""
    return _claude_entry(server_from_recipe(recipe_key))


def _read_mcp_json(path: Path) -> dict:
    """Backward-compatible shim: read an ``mcp.json``, tolerating bad input."""
    text = path.read_text(encoding="utf-8") if path.exists() else None
    data = _json_load(text)
    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    return data


# ---------------------------------------------------------------------------
# CLI — `infrakit mcp [add|list|remove|doctor]`.
# ---------------------------------------------------------------------------

mcp_app = typer.Typer(
    name="mcp",
    help="Add and manage MCP servers for your project's agent.",
    no_args_is_help=False,
)


def _fail(message: str, title: str = "MCP") -> None:
    console.print(Panel(message, title=f"[red]{title}[/red]", border_style="red", padding=(1, 2)))
    raise typer.Exit(1)


def _resolve_project_agent(agent_override: str | None) -> tuple[Path, str]:
    """Find the project root and the active agent (config or override)."""
    project_root = find_project_root()
    if project_root is None:
        _fail(
            "No InfraKit project found.\n\n"
            "Run [cyan]infrakit init[/cyan] first, or cd into an existing project.",
            "Not in an InfraKit Project",
        )
    agent = agent_override
    if not agent:
        config_path = project_root / ".infrakit" / "config.yaml"
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except OSError as e:
            _fail(f"Error reading .infrakit/config.yaml: {e}")
            return project_root, ""  # unreachable; satisfies type checkers
        agent = data.get("ai_assistant")
    if not agent:
        _fail("No agent found. Pass [cyan]--agent[/cyan] or set ai_assistant in config.yaml.")
    if agent not in AGENT_CONFIG:
        _fail(f"Unknown agent '{agent}'. Choose one of: {', '.join(AGENT_CONFIG)}.")
    if not supports_mcp(agent):
        _fail(
            f"MCP provisioning isn't available for the '{agent}' agent.\n\n"
            "InfraKit writes native MCP configs for claude, codex, gemini, and copilot. "
            "For a bring-your-own agent, configure MCP servers in your agent's own settings.",
            "Unsupported agent",
        )
    return project_root, agent


def _report(project_root: Path, agent: str, server: McpServer) -> None:
    path, changed = provision(project_root, agent, server)
    rel = path.relative_to(project_root)
    if changed:
        console.print(f"[green]✓[/green] {server.key} → [cyan]{rel}[/cyan]")
        for secret in server.required_secrets:
            console.print(
                f"  [yellow]![/yellow] set [bold]${secret.name}[/bold] in your environment — "
                "the config references it; no secret was written."
            )
    else:
        console.print(f"[dim]• {server.key} already configured in {rel} — unchanged.[/dim]")


@mcp_app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Run the interactive picker when invoked as bare ``infrakit mcp``."""
    if ctx.invoked_subcommand is not None:
        return
    show_banner()
    project_root, agent = _resolve_project_agent(None)
    agent_name = AGENT_CONFIG.get(agent, {}).get("name", agent)
    console.print(f"[cyan]Agent:[/cyan] {agent_name} [dim]({agent})[/dim]")
    console.print(f"[cyan]Project:[/cyan] [dim]{project_root}[/dim]\n")
    choices = {k: v["display_name"] for k, v in MCP_RECIPES.items()}
    selected = select_with_arrows(choices, "Choose an MCP recipe to install:")
    _report(project_root, agent, server_from_recipe(selected))


@mcp_app.command("add")
def mcp_add(
    recipe: str = typer.Argument(
        None, help="Catalogue recipe key (omit for --all or a custom server)"
    ),
    agent: str = typer.Option(
        None, "--agent", help="Target agent (default: project's ai_assistant)"
    ),
    all_recipes: bool = typer.Option(False, "--all", help="Install every catalogue recipe"),
    name: str = typer.Option(None, "--name", help="Name for a custom server"),
    command: str = typer.Option(None, "--command", help="Command for a custom stdio server"),
    args: str = typer.Option(None, "--args", help="Args for a custom stdio server (shell-quoted)"),
    url: str = typer.Option(None, "--url", help="URL for a custom remote server"),
    transport: str = typer.Option(None, "--transport", help="stdio | http | sse (custom server)"),
) -> None:
    """Add one or more MCP servers to the agent's config (non-interactive)."""
    show_banner()
    project_root, agent = _resolve_project_agent(agent)

    if command or url:
        key = name or (Path(command).name if command else "custom")
        server = custom_server(
            key,
            command=command,
            args=shlex.split(args) if args else None,
            url=url,
            transport=transport,
        )
        _report(project_root, agent, server)
        return

    if all_recipes:
        for key in MCP_RECIPES:
            _report(project_root, agent, server_from_recipe(key))
        return

    if not recipe:
        _fail("Pass a recipe key, [cyan]--all[/cyan], or a custom server (--command/--url).")
    if recipe not in MCP_RECIPES:
        _fail(f"Unknown recipe '{recipe}'. Available: {', '.join(MCP_RECIPES)}.")
    _report(project_root, agent, server_from_recipe(recipe))


@mcp_app.command("list")
def mcp_list(
    agent: str = typer.Option(
        None, "--agent", help="Target agent (default: project's ai_assistant)"
    ),
) -> None:
    """List MCP servers configured for the agent."""
    project_root, agent = _resolve_project_agent(agent)
    relpath, _ = target_for(agent)
    names = installed(project_root, agent)
    if not names:
        console.print(f"[dim]No MCP servers configured in {relpath}.[/dim]")
        return
    console.print(f"[cyan]MCP servers in[/cyan] {relpath}:")
    for n in names:
        console.print(f"  • {n}")


@mcp_app.command("remove")
def mcp_remove(
    name: str = typer.Argument(..., help="Server name to remove"),
    agent: str = typer.Option(
        None, "--agent", help="Target agent (default: project's ai_assistant)"
    ),
) -> None:
    """Remove an MCP server from the agent's config."""
    project_root, agent = _resolve_project_agent(agent)
    if uninstall(project_root, agent, name):
        console.print(f"[green]✓[/green] removed {name}")
    else:
        console.print(f"[dim]{name} was not configured — nothing to remove.[/dim]")


@mcp_app.command("doctor")
def mcp_doctor(
    agent: str = typer.Option(
        None, "--agent", help="Target agent (default: project's ai_assistant)"
    ),
) -> None:
    """Report configured servers and whether their stdio command is on PATH."""
    project_root, agent = _resolve_project_agent(agent)
    names = installed(project_root, agent)
    if not names:
        console.print("[dim]No MCP servers configured.[/dim]")
        return
    for n in names:
        if n in MCP_RECIPES:
            server = server_from_recipe(n)
            if server.is_remote:
                console.print(f"  [green]✓[/green] {n} — remote ({server.url})")
            elif shutil.which(server.command):
                console.print(f"  [green]✓[/green] {n} — '{server.command}' on PATH")
            else:
                console.print(f"  [yellow]![/yellow] {n} — '{server.command}' not found on PATH")
        else:
            console.print(f"  [dim]•[/dim] {n} — configured (custom)")
