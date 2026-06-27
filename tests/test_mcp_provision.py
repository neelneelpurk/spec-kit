"""
Unit tests for the MCP provisioning adapters (infrakit_cli.mcp).

The per-agent writers are pure text transforms, so most of these tests assert
on rendered content without touching the filesystem. A few exercise
provision/installed/uninstall against tmp_path.
"""

import json
import tomllib

import pytest

from infrakit_cli.mcp import (
    add_server,
    installed,
    list_servers,
    provision,
    remove_server,
    supports_mcp,
    target_for,
    uninstall,
)
from infrakit_cli.mcp_config import EnvVar, McpServer, custom_server, server_from_recipe

CONTEXT7 = server_from_recipe("context7")  # stdio
DEEPWIKI = server_from_recipe("deepwiki")  # http (remote)


class TestTargets:
    def test_each_agent_has_a_distinct_target(self):
        paths = {a: target_for(a)[0] for a in ("claude", "gemini", "codex", "copilot")}
        assert paths == {
            "claude": ".mcp.json",
            "gemini": ".gemini/settings.json",
            "codex": ".codex/config.toml",
            "copilot": ".vscode/mcp.json",
        }

    def test_generic_is_unsupported(self):
        assert supports_mcp("generic") is False
        for agent in ("claude", "gemini", "codex", "copilot"):
            assert supports_mcp(agent) is True
        with pytest.raises(ValueError):
            target_for("generic")


class TestStdioRendering:
    def test_claude(self):
        entry = json.loads(add_server("claude", None, CONTEXT7))["mcpServers"]["context7"]
        assert entry == {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp@latest"],
        }

    def test_gemini_omits_type(self):
        entry = json.loads(add_server("gemini", None, CONTEXT7))["mcpServers"]["context7"]
        assert entry == {"command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"]}

    def test_codex_is_valid_toml(self):
        doc = tomllib.loads(add_server("codex", None, CONTEXT7))
        assert doc["mcp_servers"]["context7"]["command"] == "npx"
        assert doc["mcp_servers"]["context7"]["args"] == ["-y", "@upstash/context7-mcp@latest"]

    def test_copilot_uses_servers_key(self):
        data = json.loads(add_server("copilot", None, CONTEXT7))
        assert "servers" in data and "mcpServers" not in data
        assert data["servers"]["context7"]["type"] == "stdio"


class TestRemoteRendering:
    """deepwiki is Streamable HTTP — each agent serialises it differently."""

    def test_claude_uses_type_http_and_url(self):
        entry = json.loads(add_server("claude", None, DEEPWIKI))["mcpServers"]["deepwiki"]
        assert entry == {"type": "http", "url": "https://mcp.deepwiki.com/mcp"}

    def test_gemini_uses_httpurl(self):
        entry = json.loads(add_server("gemini", None, DEEPWIKI))["mcpServers"]["deepwiki"]
        assert entry == {"httpUrl": "https://mcp.deepwiki.com/mcp"}
        assert "url" not in entry

    def test_codex_uses_url(self):
        doc = tomllib.loads(add_server("codex", None, DEEPWIKI))
        assert doc["mcp_servers"]["deepwiki"]["url"] == "https://mcp.deepwiki.com/mcp"

    def test_copilot_uses_type_http(self):
        entry = json.loads(add_server("copilot", None, DEEPWIKI))["servers"]["deepwiki"]
        assert entry == {"type": "http", "url": "https://mcp.deepwiki.com/mcp"}


class TestSecrets:
    SECRET = McpServer(
        key="secret-srv",
        display_name="secret-srv",
        command="my-server",
        env=[EnvVar(name="API_KEY", description="API key", is_secret=True, is_required=True)],
    )

    def test_no_agent_ever_writes_a_secret_literal(self):
        # The env var carries no value in the model; assert the rendered text
        # references it rather than inlining anything, across every writer.
        for agent in ("claude", "gemini", "codex", "copilot"):
            text = add_server(agent, None, self.SECRET)
            assert "API_KEY" in text  # referenced
            # the reference syntax, never a bare assignment of a literal secret
            assert "${API_KEY}" in text or "${input:api_key}" in text

    def test_claude_env_reference(self):
        entry = json.loads(add_server("claude", None, self.SECRET))["mcpServers"]["secret-srv"]
        assert entry["env"] == {"API_KEY": "${API_KEY}"}

    def test_copilot_prompts_for_secret_via_inputs(self):
        data = json.loads(add_server("copilot", None, self.SECRET))
        assert data["servers"]["secret-srv"]["env"] == {"API_KEY": "${input:api_key}"}
        assert data["inputs"] == [
            {"id": "api_key", "type": "promptString", "description": "API key", "password": True}
        ]

    def test_non_secret_env_with_default_is_inlined(self):
        srv = McpServer(
            key="s", display_name="s", command="x", env=[EnvVar(name="REGION", default="us-east-1")]
        )
        entry = json.loads(add_server("claude", None, srv))["mcpServers"]["s"]
        assert entry["env"] == {"REGION": "us-east-1"}


class TestMergeAndRoundTrip:
    @pytest.mark.parametrize("agent", ["claude", "gemini", "codex", "copilot"])
    def test_add_preserves_existing(self, agent):
        text = add_server(agent, None, CONTEXT7)
        text = add_server(agent, text, DEEPWIKI)
        assert set(list_servers(agent, text)) == {"context7", "deepwiki"}

    @pytest.mark.parametrize("agent", ["claude", "gemini", "codex", "copilot"])
    def test_remove_round_trip(self, agent):
        text = add_server(agent, None, CONTEXT7)
        text = add_server(agent, text, DEEPWIKI)
        text = remove_server(agent, text, "context7")
        assert list_servers(agent, text) == ["deepwiki"]

    def test_malformed_json_is_tolerated(self):
        text = add_server("claude", "{ not valid json", CONTEXT7)
        assert list_servers("claude", text) == ["context7"]


class TestProvisionIO:
    def test_provision_writes_and_is_idempotent(self, tmp_path):
        path, changed = provision(tmp_path, "claude", CONTEXT7)
        assert changed is True
        assert path == tmp_path / ".mcp.json"
        assert installed(tmp_path, "claude") == ["context7"]
        # second time: no change
        _, changed2 = provision(tmp_path, "claude", CONTEXT7)
        assert changed2 is False

    def test_provision_updates_index(self, tmp_path):
        provision(tmp_path, "claude", CONTEXT7)
        index = (tmp_path / ".infrakit" / "mcp-use.md").read_text(encoding="utf-8")
        assert "| context7 |" in index

    def test_uninstall(self, tmp_path):
        provision(tmp_path, "gemini", CONTEXT7)
        assert uninstall(tmp_path, "gemini", "context7") is True
        assert installed(tmp_path, "gemini") == []
        # removing again is a no-op
        assert uninstall(tmp_path, "gemini", "context7") is False

    def test_codex_provision_path(self, tmp_path):
        path, _ = provision(tmp_path, "codex", DEEPWIKI)
        assert path == tmp_path / ".codex" / "config.toml"
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        assert doc["mcp_servers"]["deepwiki"]["url"] == "https://mcp.deepwiki.com/mcp"

    def test_custom_server_provision(self, tmp_path):
        srv = custom_server("internal", url="https://mcp.internal.example/mcp")
        provision(tmp_path, "claude", srv)
        entry = json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["internal"]
        assert entry == {"type": "http", "url": "https://mcp.internal.example/mcp"}
