"""
Unit tests for AWS CloudFormation IaC tool support in iac_config.py.

Tests cover:
- CloudFormation entry present and correctly structured in IAC_CONFIG
- CloudFormation-specific field values (output_format, resource_term, requires_tools)
- CloudFormation IaC commands (create/update_cloudformation_code, quick_fix, ...)
- get_iac_choices() includes cloudformation
- get_iac_commands() returns correct commands for cloudformation
- CloudFormation coexists with Terraform and Crossplane without interference
- quick_fix is present across every IaC tool
"""

import pytest

from infrakit_cli.iac_config import IAC_CONFIG, get_iac_choices, get_iac_commands


class TestCloudFormationIacConfig:
    """Tests for the CloudFormation entry in IAC_CONFIG."""

    def test_cloudformation_present_in_iac_config(self):
        """cloudformation must be a key in IAC_CONFIG."""
        assert "cloudformation" in IAC_CONFIG, "cloudformation key missing from IAC_CONFIG"

    def test_cloudformation_has_all_required_fields(self):
        """CloudFormation config must contain every required field."""
        required_fields = [
            "name",
            "description",
            "requires_tools",
            "optional_tools",
            "output_format",
            "resource_term",
            "generic_commands",
            "iac_commands",
        ]
        cfn = IAC_CONFIG["cloudformation"]
        for field in required_fields:
            assert field in cfn, f"cloudformation config missing required field '{field}'"

    def test_cloudformation_name(self):
        """CloudFormation display name should be 'AWS CloudFormation'."""
        assert IAC_CONFIG["cloudformation"]["name"] == "AWS CloudFormation"

    def test_cloudformation_description_non_empty(self):
        """CloudFormation description must be a non-empty string."""
        desc = IAC_CONFIG["cloudformation"]["description"]
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_cloudformation_requires_aws_cli(self):
        """CloudFormation requires the aws CLI."""
        assert IAC_CONFIG["cloudformation"]["requires_tools"] == ["aws"]

    def test_cloudformation_optional_tools_include_cfn_lint(self):
        """cfn-lint should be an optional tool for CloudFormation."""
        assert "cfn-lint" in IAC_CONFIG["cloudformation"]["optional_tools"]

    def test_cloudformation_output_format_is_yaml(self):
        """CloudFormation output format must be 'yaml'."""
        assert IAC_CONFIG["cloudformation"]["output_format"] == "yaml"

    def test_cloudformation_resource_term_is_template(self):
        """CloudFormation resource term must be 'template'."""
        assert IAC_CONFIG["cloudformation"]["resource_term"] == "template"

    def test_cloudformation_generic_commands_include_core_workflow(self):
        """CloudFormation must include the core spec-driven generic commands."""
        expected = [
            "setup",
            "status",
            "analyze",
            "architect-review",
            "security-review",
        ]
        generic = IAC_CONFIG["cloudformation"]["generic_commands"]
        for cmd in expected:
            assert cmd in generic, f"cloudformation generic_commands missing '{cmd}'"
        # implement is IaC-specific, not generic
        assert "implement" not in generic
        assert "implement" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_create_command(self):
        """create_cloudformation_code must be in cloudformation iac_commands."""
        assert "create_cloudformation_code" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_update_command(self):
        """update_cloudformation_code must be in cloudformation iac_commands."""
        assert "update_cloudformation_code" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_plan_command(self):
        """plan must be in cloudformation iac_commands."""
        assert "plan" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_review_command(self):
        """review must be in cloudformation iac_commands."""
        assert "review" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_implement_command(self):
        """implement must be in cloudformation iac_commands."""
        assert "implement" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_setup_coding_style_command(self):
        """setup-coding-style must be in cloudformation iac_commands."""
        assert "setup-coding-style" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_has_quick_fix_command(self):
        """quick_fix must be in cloudformation iac_commands."""
        assert "quick_fix" in IAC_CONFIG["cloudformation"]["iac_commands"]

    def test_cloudformation_iac_commands_count(self):
        """CloudFormation must have exactly 7 IaC-native commands."""
        assert len(IAC_CONFIG["cloudformation"]["iac_commands"]) == 7

    def test_cloudformation_iac_commands_no_duplicates(self):
        """cloudformation iac_commands must have no duplicate entries."""
        iac = IAC_CONFIG["cloudformation"]["iac_commands"]
        assert len(iac) == len(set(iac)), "cloudformation iac_commands contains duplicates"

    def test_cloudformation_no_overlap_between_generic_and_iac_commands(self):
        """cloudformation generic_commands and iac_commands must not overlap."""
        generic = set(IAC_CONFIG["cloudformation"]["generic_commands"])
        iac = set(IAC_CONFIG["cloudformation"]["iac_commands"])
        assert len(generic & iac) == 0, f"cloudformation command overlap: {generic & iac}"

    def test_cloudformation_uses_shared_generic_commands(self):
        """CloudFormation generic commands should match Crossplane's and Terraform's."""
        cfn_generic = set(IAC_CONFIG["cloudformation"]["generic_commands"])
        crossplane_generic = set(IAC_CONFIG["crossplane"]["generic_commands"])
        terraform_generic = set(IAC_CONFIG["terraform"]["generic_commands"])
        assert cfn_generic == crossplane_generic == terraform_generic, (
            "all IaC tools should share the same generic workflow commands"
        )

    def test_cloudformation_iac_commands_differ_from_others(self):
        """CloudFormation IaC-native commands must differ from Terraform/Crossplane."""
        cfn_iac = set(IAC_CONFIG["cloudformation"]["iac_commands"])
        assert cfn_iac != set(IAC_CONFIG["terraform"]["iac_commands"])
        assert cfn_iac != set(IAC_CONFIG["crossplane"]["iac_commands"])

    def test_cloudformation_does_not_use_other_tools_create_commands(self):
        """CloudFormation must not reference Terraform/Crossplane create commands."""
        cfn_iac = IAC_CONFIG["cloudformation"]["iac_commands"]
        assert "new_composition" not in cfn_iac
        assert "update_composition" not in cfn_iac
        assert "create_terraform_code" not in cfn_iac
        assert "update_terraform_code" not in cfn_iac

    def test_other_tools_do_not_use_cloudformation_commands(self):
        """Terraform and Crossplane must not reference CloudFormation commands."""
        assert "create_cloudformation_code" not in IAC_CONFIG["terraform"]["iac_commands"]
        assert "create_cloudformation_code" not in IAC_CONFIG["crossplane"]["iac_commands"]


class TestGetIacChoicesWithCloudFormation:
    """Tests for get_iac_choices() after CloudFormation was added."""

    def test_get_iac_choices_includes_cloudformation(self):
        choices = get_iac_choices()
        assert "cloudformation" in choices

    def test_get_iac_choices_cloudformation_display_name(self):
        choices = get_iac_choices()
        assert choices["cloudformation"] == "AWS CloudFormation"

    def test_get_iac_choices_returns_all_three_tools(self):
        choices = get_iac_choices()
        assert {"crossplane", "terraform", "cloudformation"} <= set(choices)


class TestGetIacCommandsWithCloudFormation:
    """Tests for get_iac_commands() with cloudformation as input."""

    def test_get_iac_commands_cloudformation_non_empty(self):
        result = get_iac_commands("cloudformation")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_iac_commands_cloudformation_includes_create_command(self):
        assert "create_cloudformation_code" in get_iac_commands("cloudformation")

    def test_get_iac_commands_cloudformation_includes_quick_fix(self):
        assert "quick_fix" in get_iac_commands("cloudformation")

    def test_get_iac_commands_cloudformation_total_count(self):
        expected = len(IAC_CONFIG["cloudformation"]["generic_commands"]) + len(
            IAC_CONFIG["cloudformation"]["iac_commands"]
        )
        assert len(get_iac_commands("cloudformation")) == expected

    def test_get_iac_commands_order_generic_before_iac(self):
        commands = get_iac_commands("cloudformation")
        generic_cmds = IAC_CONFIG["cloudformation"]["generic_commands"]
        iac_cmds = IAC_CONFIG["cloudformation"]["iac_commands"]
        n = len(generic_cmds)
        assert commands[:n] == generic_cmds
        assert commands[n:] == iac_cmds


class TestQuickFixAcrossAllTools:
    """quick_fix is the fast-path command and must exist for every IaC tool."""

    @pytest.mark.parametrize("tool_key", ["crossplane", "terraform", "cloudformation"])
    def test_quick_fix_in_iac_commands(self, tool_key):
        assert "quick_fix" in IAC_CONFIG[tool_key]["iac_commands"], (
            f"{tool_key} iac_commands missing quick_fix"
        )

    @pytest.mark.parametrize("tool_key", ["crossplane", "terraform", "cloudformation"])
    def test_quick_fix_returned_by_get_iac_commands(self, tool_key):
        assert "quick_fix" in get_iac_commands(tool_key)
