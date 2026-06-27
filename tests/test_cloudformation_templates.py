"""
Unit tests for AWS CloudFormation template files.

Tests cover:
- All expected template files exist under templates/iac/cloudformation/
- Command files have valid YAML frontmatter with required fields
- Command files contain the $ARGUMENTS placeholder
- coding-style-template.md contains expected CloudFormation placeholders
- cloudformation_engineer.md persona has correct frontmatter and content
- quick_fix.md is present and adopts the engineer persona directly
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CFN_TEMPLATES_DIR = REPO_ROOT / "templates" / "iac" / "cloudformation"

# Every IaC-native command template CloudFormation ships.
COMMAND_FILES = [
    "create_cloudformation_code.md",
    "update_cloudformation_code.md",
    "plan.md",
    "review.md",
    "implement.md",
    "setup-coding-style.md",
    "quick_fix.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    fm_text = content[3:end].strip()
    result = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                result[key] = value
    return result


class TestCloudFormationTemplateDirectoryStructure:
    def test_cfn_template_root_exists(self):
        assert CFN_TEMPLATES_DIR.is_dir(), f"Expected directory not found: {CFN_TEMPLATES_DIR}"

    def test_commands_directory_exists(self):
        assert (CFN_TEMPLATES_DIR / "commands").is_dir()

    def test_assets_directory_exists(self):
        assert (CFN_TEMPLATES_DIR / "assets").is_dir()

    def test_agent_personas_directory_exists(self):
        assert (CFN_TEMPLATES_DIR / "agent_personas").is_dir()


class TestCloudFormationCommandFiles:
    @pytest.mark.parametrize("filename", COMMAND_FILES)
    def test_command_file_exists(self, filename):
        path = CFN_TEMPLATES_DIR / "commands" / filename
        assert path.is_file(), f"Missing command template: {path}"

    @pytest.mark.parametrize("filename", COMMAND_FILES)
    def test_command_file_non_empty(self, filename):
        content = _read(CFN_TEMPLATES_DIR / "commands" / filename)
        assert len(content.strip()) > 0, f"Command template is empty: {filename}"

    @pytest.mark.parametrize("filename", COMMAND_FILES)
    def test_frontmatter_present(self, filename):
        content = _read(CFN_TEMPLATES_DIR / "commands" / filename)
        assert content.startswith("---"), f"{filename} must start with YAML frontmatter"

    @pytest.mark.parametrize("filename", COMMAND_FILES)
    def test_frontmatter_has_description(self, filename):
        content = _read(CFN_TEMPLATES_DIR / "commands" / filename)
        fm = _parse_frontmatter(content)
        assert "description" in fm and len(fm["description"]) > 0, (
            f"{filename} frontmatter missing a non-empty description"
        )

    @pytest.mark.parametrize("filename", COMMAND_FILES)
    def test_frontmatter_has_argument_hint(self, filename):
        content = _read(CFN_TEMPLATES_DIR / "commands" / filename)
        assert "argument-hint:" in content, f"{filename} frontmatter missing argument-hint"

    @pytest.mark.parametrize("filename", COMMAND_FILES)
    def test_command_body_contains_arguments_placeholder(self, filename):
        content = _read(CFN_TEMPLATES_DIR / "commands" / filename)
        assert "$ARGUMENTS" in content, f"{filename} missing $ARGUMENTS placeholder"


class TestCreateCloudFormationCodeCommand:
    @pytest.fixture
    def content(self):
        return _read(CFN_TEMPLATES_DIR / "commands" / "create_cloudformation_code.md")

    def test_references_cloudformation(self, content):
        assert "cloudformation" in content.lower() or "template" in content.lower()

    def test_references_setup_command_on_missing_files(self, content):
        assert "infrakit:setup" in content

    def test_references_spec_md_output(self, content):
        assert "spec.md" in content

    def test_references_tracks_md(self, content):
        assert "tracks.md" in content

    def test_references_architect_review_phase(self, content):
        assert "architect" in content.lower()

    def test_references_security_review_phase(self, content):
        assert "security" in content.lower()

    def test_references_update_command_for_existing_dirs(self, content):
        assert "update_cloudformation_code" in content

    def test_references_infrakit_plan_next_step(self, content):
        assert "infrakit:plan" in content

    def test_has_error_handling_section(self, content):
        assert "Error Handling" in content or "error handling" in content.lower()


class TestUpdateCloudFormationCodeCommand:
    @pytest.fixture
    def content(self):
        return _read(CFN_TEMPLATES_DIR / "commands" / "update_cloudformation_code.md")

    def test_references_template_yaml(self, content):
        assert "template.yaml" in content

    def test_references_change_classification(self, content):
        assert "Additive" in content
        assert "Breaking" in content

    def test_references_migration_md_for_breaking_changes(self, content):
        assert "migration.md" in content

    def test_references_create_command_for_new_dirs(self, content):
        assert "create_cloudformation_code" in content

    def test_references_replacement_impact(self, content):
        """Breaking CFN changes hinge on resource replacement — must be addressed."""
        assert "eplacement" in content or "replace" in content.lower()


class TestCloudFormationPlanCommand:
    @pytest.fixture
    def content(self):
        return _read(CFN_TEMPLATES_DIR / "commands" / "plan.md")

    def test_references_aws_docs(self, content):
        """Must look up resources against the AWS CloudFormation docs."""
        assert "docs.aws.amazon.com" in content

    def test_references_parameters_design(self, content):
        assert "parameter" in content.lower()

    def test_references_outputs_design(self, content):
        assert "output" in content.lower()

    def test_references_create_command_for_missing_spec(self, content):
        assert "create_cloudformation_code" in content

    def test_references_plan_md_output_file(self, content):
        assert "plan.md" in content

    def test_references_tagging(self, content):
        assert "tag" in content.lower()


class TestCloudFormationReviewCommand:
    @pytest.fixture
    def content(self):
        return _read(CFN_TEMPLATES_DIR / "commands" / "review.md")

    def test_references_template(self, content):
        assert "template.yaml" in content or "template" in content.lower()

    def test_references_no_hardcoded_secrets(self, content):
        assert "secret" in content.lower() or "hardcode" in content.lower()

    def test_references_tagging_check(self, content):
        assert "tag" in content.lower()

    def test_references_encryption(self, content):
        assert "encrypt" in content.lower()

    def test_references_cfn_lint(self, content):
        assert "cfn-lint" in content.lower()

    def test_verdict_options_present(self, content):
        assert "APPROVED" in content
        assert "NEEDS FIXES" in content

    def test_references_severity_levels(self, content):
        assert "CRITICAL" in content
        assert "HIGH" in content


class TestCloudFormationQuickFixCommand:
    @pytest.fixture
    def content(self):
        return _read(CFN_TEMPLATES_DIR / "commands" / "quick_fix.md")

    def test_adopts_engineer_persona(self, content):
        assert "CloudFormation Engineer" in content
        assert "cloudformation_engineer.md" in content

    def test_flow_is_plan_tasks_review_implement(self, content):
        lowered = content.lower()
        assert "plan.md" in content
        assert "tasks.md" in content
        assert "review" in lowered
        assert "implement" in lowered

    def test_creates_a_track(self, content):
        assert "tracks.md" in content
        assert "quickfix" in content.lower()

    def test_recommends_full_pipeline(self, content):
        assert "create_cloudformation_code" in content

    def test_validation_is_a_gate(self, content):
        assert "cfn-lint" in content.lower()
        assert "MANDATORY" in content or "blocks completion" in content

    def test_verifies_schemas(self, content):
        assert "never guess" in content.lower() or "verify" in content.lower()


class TestCloudFormationAssets:
    def test_coding_style_template_exists(self):
        path = CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md"
        assert path.is_file(), f"Missing: {path}"

    def test_coding_style_non_empty(self):
        content = _read(CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md")
        assert len(content.strip()) > 0

    def test_coding_style_references_format(self):
        content = _read(CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md")
        assert "TEMPLATE_FORMAT" in content or "AWSTemplateFormatVersion" in content

    def test_coding_style_references_tagging(self):
        content = _read(CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md")
        assert "tag" in content.lower()

    def test_coding_style_references_security(self):
        content = _read(CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md")
        assert "security" in content.lower()

    def test_coding_style_references_managed_by_tag(self):
        content = _read(CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md")
        assert "managed-by" in content

    def test_coding_style_references_noecho_secrets(self):
        content = _read(CFN_TEMPLATES_DIR / "assets" / "coding-style-template.md")
        assert "NoEcho" in content or "resolve:secretsmanager" in content


class TestCloudFormationAgentPersona:
    @pytest.fixture
    def content(self):
        return _read(CFN_TEMPLATES_DIR / "agent_personas" / "cloudformation_engineer.md")

    def test_persona_exists(self):
        path = CFN_TEMPLATES_DIR / "agent_personas" / "cloudformation_engineer.md"
        assert path.is_file(), f"Missing: {path}"

    def test_persona_has_frontmatter(self, content):
        assert content.startswith("---")

    def test_persona_frontmatter_has_name(self, content):
        assert "name: cloudformation-engineer" in content

    def test_persona_references_aws_resource_reference(self, content):
        assert "docs.aws.amazon.com" in content

    def test_persona_references_never_guess(self, content):
        lowered = content.lower()
        assert "never" in lowered
        assert "guess" in lowered

    def test_persona_references_compliance_check(self, content):
        assert "compliance" in content.lower()

    def test_persona_references_template_files(self, content):
        assert "template.yaml" in content
        assert "Parameters" in content
        assert "Resources" in content
        assert "Outputs" in content

    def test_persona_references_tagging(self, content):
        assert "tag" in content.lower()

    def test_persona_references_noecho_secrets(self, content):
        assert "NoEcho" in content or "resolve:secretsmanager" in content

    def test_persona_references_cfn_lint(self, content):
        assert "cfn-lint" in content

    def test_persona_treats_spec_as_immutable_contract(self, content):
        assert "spec.md" in content
        assert "immutable" in content.lower() or "contract" in content.lower()
