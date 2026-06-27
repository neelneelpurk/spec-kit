"""MCP (Model Context Protocol) catalogue and server model for infrakit-cli.

This module owns two things:

1. :data:`MCP_RECIPES` — a bundled, **offline** catalogue of ready-to-install
   MCP servers. The shape is aligned with the official ``server.json`` registry
   schema (transport + environment variables) so a recipe stays close to a
   verbatim registry entry.
2. :class:`McpServer` / :class:`EnvVar` — the normalised, agent-agnostic server
   model that :mod:`infrakit_cli.mcp` renders into each agent's own config
   format.

Transports follow the current MCP spec (2025-11-25): ``stdio`` and ``http``
(Streamable HTTP). ``sse`` is accepted as a legacy/deprecated transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Transports -------------------------------------------------------------
STDIO = "stdio"
HTTP = "http"  # Streamable HTTP — the current remote transport
SSE = "sse"  # legacy HTTP+SSE, deprecated since MCP spec 2025-03-26
TRANSPORTS = (STDIO, HTTP, SSE)
REMOTE_TRANSPORTS = (HTTP, SSE)


@dataclass
class EnvVar:
    """An environment variable a server needs. Mirrors ``server.json``'s
    ``environmentVariables`` entry. Secrets are **never** written to disk — the
    per-agent writer emits a reference (``${NAME}`` / ``${input:...}``) instead.
    """

    name: str
    description: str = ""
    is_required: bool = False
    is_secret: bool = False
    default: str | None = None


@dataclass
class McpServer:
    """Normalised, agent-agnostic description of one MCP server.

    :mod:`infrakit_cli.mcp` renders this into each agent's own config format.
    """

    key: str
    display_name: str
    description: str = ""
    transport: str = STDIO
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    env: list[EnvVar] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    usage: str = ""

    @property
    def is_remote(self) -> bool:
        return self.transport in REMOTE_TRANSPORTS

    @property
    def required_secrets(self) -> list[EnvVar]:
        return [e for e in self.env if e.is_secret]


# Bundled catalogue. ``type`` is the transport; remote recipes carry ``url``,
# stdio recipes carry ``command`` + ``args``. Optional ``env`` is a list of
# environment-variable dicts (``name`` / ``is_required`` / ``is_secret`` / …).
MCP_RECIPES = {
    "context7": {
        "display_name": "Context7 — Up-to-date library docs",
        "description": "Provides current library documentation via Upstash Context7",
        "type": STDIO,
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp@latest"],
        "tools": ["resolve-library-id", "get-library-docs"],
        "usage": "Ask agent to 'use context7' when looking up library/framework docs",
    },
    "deepwiki": {
        "display_name": "DeepWiki — GitHub repo deep research",
        "description": "Deep research into GitHub repositories over Streamable HTTP",
        "type": HTTP,
        "url": "https://mcp.deepwiki.com/mcp",
        "tools": ["ask_question", "read_wiki_structure", "read_wiki_contents"],
        "usage": "Ask agent to 'use deepwiki' to research a GitHub repo in depth",
    },
    "aws-best-practices": {
        "display_name": "AWS Best Practices — AWS docs & best practices",
        "description": "Access AWS documentation and best practices via awslabs server",
        "type": STDIO,
        "command": "uvx",
        "args": ["awslabs.aws-documentation-mcp-server@latest"],
        "tools": ["search_documentation", "read_documentation", "recommend"],
        "usage": "Agent will use automatically when generating AWS infrastructure",
    },
    "microsoft-learn": {
        "display_name": "Microsoft Learn — Microsoft & Azure docs",
        "description": "Access Microsoft and Azure documentation via Microsoft Learn MCP",
        "type": STDIO,
        "command": "npx",
        "args": ["-y", "@microsoft/mcp-microsoft-learn@latest"],
        "tools": ["microsoft_docs_search", "microsoft_docs_fetch", "microsoft_code_sample_search"],
        "usage": "Agent will use automatically when generating Azure infrastructure",
    },
}


def server_from_recipe(key: str) -> McpServer:
    """Build a normalised :class:`McpServer` from a catalogue recipe."""
    r = MCP_RECIPES[key]
    env = [EnvVar(**e) for e in r.get("env", [])]
    return McpServer(
        key=key,
        display_name=r["display_name"],
        description=r["description"],
        transport=r["type"],
        command=r.get("command"),
        args=list(r.get("args", [])),
        url=r.get("url"),
        headers=dict(r.get("headers", {})),
        env=env,
        tools=list(r.get("tools", [])),
        usage=r.get("usage", ""),
    )


def custom_server(
    key: str,
    *,
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    transport: str | None = None,
    description: str = "",
    env: list[EnvVar] | None = None,
) -> McpServer:
    """Build a :class:`McpServer` for a server not in the catalogue.

    A ``url`` implies a remote (Streamable HTTP) server unless ``transport`` is
    given explicitly; otherwise the server is ``stdio``.
    """
    transport = transport or (HTTP if url else STDIO)
    return McpServer(
        key=key,
        display_name=key,
        description=description or f"Custom MCP server: {key}",
        transport=transport,
        command=command,
        args=list(args or []),
        url=url,
        env=list(env or []),
        usage="",
    )
