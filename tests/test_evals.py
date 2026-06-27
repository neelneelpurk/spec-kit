"""Run the InfraKit eval suite under pytest (deterministic, offline, CI-safe).

These tests are the always-on floor of the eval harness:

- every **golden** example deliverable scores 100% of its applicable
  security checks (the examples are InfraKit's own claim of "good output");
- every **negative** fixture scores below its bar (proving the scorer actually
  discriminates — an eval that can't fail is worthless);
- the suite scores at least 20 individual checks ("20 evals").

The deeper LLM eval (drive the real pipeline, then score) is a documented hook
in ``evals/run.py`` and intentionally not run here — it needs an agent/API key.
"""

import sys
from pathlib import Path

import pytest

_EVALS = Path(__file__).resolve().parent.parent / "evals"
sys.path.insert(0, str(_EVALS))

import cases as cases_mod  # noqa: E402
import scorer  # noqa: E402


@pytest.mark.parametrize("case", cases_mod.GOLDEN, ids=[c.id for c in cases_mod.GOLDEN])
def test_golden_examples_meet_the_bar(case):
    """Committed example deliverables must pass every applicable security check."""
    assert case.path.exists(), f"example not found: {case.path}"
    results = scorer.score(case.iac, case.path, case.checks)
    failed = [f"{r.check} ({r.detail})" for r in results if r.status == scorer.FAIL]
    assert not failed, f"{case.id} failed security checks: {failed}"


@pytest.mark.parametrize("case", cases_mod.NEGATIVE, ids=[c.id for c in cases_mod.NEGATIVE])
def test_negative_fixtures_are_caught(case):
    """Deliberately-insecure fixtures must score below their bar."""
    assert case.path.exists(), f"fixture not found: {case.path}"
    results = scorer.score(case.iac, case.path, case.checks)
    summary = scorer.summarize(results)
    assert summary["pct"] <= case.max_pct_if_negative, (
        f"{case.id} scored {summary['pct']:.0f}% — scorer failed to catch insecure output; "
        f"results={[(r.check, r.status) for r in results]}"
    )
    # And it must specifically catch the core violations.
    by_check = {r.check: r.status for r in results}
    for must_fail in ("encryption_at_rest", "public_access_blocked", "required_tags_present"):
        assert by_check.get(must_fail) == scorer.FAIL, (
            f"{case.id}: expected {must_fail} to FAIL, got {by_check.get(must_fail)}"
        )


def test_negative_fixture_catches_hardcoded_secret():
    """The hardcoded-password fixtures must trip no_hardcoded_secrets."""
    for case in cases_mod.NEGATIVE:
        results = {r.check: r.status for r in scorer.score(case.iac, case.path, case.checks)}
        assert results.get("no_hardcoded_secrets") == scorer.FAIL, (
            f"{case.id}: hardcoded secret not detected"
        )


def test_hardcoded_secret_heuristic_does_not_false_positive():
    """Reference-based / generated credentials must NOT be flagged as hardcoded."""
    safe = [
        "password = var.db_password",
        "MasterUserPassword: !Ref DBPassword",
        "MasterUserPassword: '{{resolve:secretsmanager:prod/db:SecretString:password}}'",
        "autoGeneratePassword: true",
        "passwordSecretRef:\n  key: password",
        "key: password",
    ]
    for snippet in safe:
        assert scorer._find_hardcoded_secret(snippet) is None, f"false positive on: {snippet!r}"
    # And a genuine literal IS caught.
    assert scorer._find_hardcoded_secret('password = "hunter2"') is not None
    assert scorer._find_hardcoded_secret("MasterUserPassword: hunter2") is not None


def test_check_registry_covers_all_declared_checks():
    for check in cases_mod.ALL_CHECKS:
        assert check in scorer.CHECKS, f"declared check '{check}' has no implementation"


def test_suite_scores_at_least_20_checks():
    """'Build 20 evals' — count individual scored (non-NA-excluded) check executions."""
    total_applicable = 0
    for case in cases_mod.ALL_CASES:
        results = scorer.score(case.iac, case.path, case.checks)
        total_applicable += scorer.summarize(results)["applicable"]
    assert total_applicable >= 20, f"only {total_applicable} scored checks; expected >= 20"
