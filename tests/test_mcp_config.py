"""
Unit tests for mcp_config.py: the MCP catalogue and the normalised server model.
"""

import pytest

from infrakit_cli.mcp_config import (
    HTTP,
    MCP_RECIPES,
    SSE,
    STDIO,
    EnvVar,
    McpServer,
    custom_server,
    server_from_recipe,
)


class TestMcpRecipes:
    """The bundled MCP_RECIPES catalogue."""

    def test_all_recipes_have_required_fields(self):
        required = ["display_name", "description", "type", "tools", "usage"]
        for key, recipe in MCP_RECIPES.items():
            for field in required:
                assert field in recipe, f"recipe '{key}' missing '{field}'"

    def test_recipe_transport_is_known(self):
        for key, recipe in MCP_RECIPES.items():
            assert recipe["type"] in (STDIO, HTTP, SSE), f"recipe '{key}' bad transport"

    def test_stdio_recipes_have_command_and_args(self):
        for key, recipe in MCP_RECIPES.items():
            if recipe["type"] == STDIO:
                assert recipe.get("command"), f"stdio recipe '{key}' missing command"
                assert isinstance(recipe.get("args"), list) and recipe["args"]

    def test_remote_recipes_have_url(self):
        for key, recipe in MCP_RECIPES.items():
            if recipe["type"] in (HTTP, SSE):
                assert recipe.get("url", "").startswith("http"), f"remote recipe '{key}' bad url"

    def test_deepwiki_is_streamable_http(self):
        """DeepWiki's /mcp endpoint is Streamable HTTP, not legacy SSE."""
        deepwiki = MCP_RECIPES["deepwiki"]
        assert deepwiki["type"] == HTTP
        assert deepwiki["url"] == "https://mcp.deepwiki.com/mcp"

    def test_context7_recipe(self):
        c = MCP_RECIPES["context7"]
        assert c["type"] == STDIO
        assert c["command"] == "npx"
        assert c["args"] == ["-y", "@upstash/context7-mcp@latest"]

    def test_unique_display_names(self):
        names = [r["display_name"] for r in MCP_RECIPES.values()]
        assert len(names) == len(set(names))

    @pytest.mark.parametrize("key", MCP_RECIPES.keys())
    def test_tools_and_usage_non_empty(self, key):
        recipe = MCP_RECIPES[key]
        assert recipe["tools"] and all(isinstance(t, str) and t for t in recipe["tools"])
        assert isinstance(recipe["usage"], str) and recipe["usage"]


class TestServerModel:
    """server_from_recipe / custom_server / McpServer."""

    @pytest.mark.parametrize("key", MCP_RECIPES.keys())
    def test_server_from_recipe(self, key):
        server = server_from_recipe(key)
        assert server.key == key
        assert server.transport in (STDIO, HTTP, SSE)
        if server.is_remote:
            assert server.url
        else:
            assert server.command

    def test_is_remote(self):
        assert server_from_recipe("deepwiki").is_remote is True
        assert server_from_recipe("context7").is_remote is False

    def test_custom_url_defaults_to_http(self):
        s = custom_server("x", url="https://example.com/mcp")
        assert s.transport == HTTP
        assert s.is_remote

    def test_custom_command_defaults_to_stdio(self):
        s = custom_server("x", command="my-server", args=["--flag"])
        assert s.transport == STDIO
        assert s.command == "my-server"
        assert s.args == ["--flag"]

    def test_required_secrets(self):
        s = McpServer(
            key="x",
            display_name="x",
            command="srv",
            env=[
                EnvVar(name="API_KEY", is_secret=True, is_required=True),
                EnvVar(name="REGION", default="us-east-1"),
            ],
        )
        secrets = s.required_secrets
        assert [e.name for e in secrets] == ["API_KEY"]
