# Changelog

<!-- markdownlint-disable MD024 -->

Recent changes to the InfraKit CLI and templates are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Repository packaging and presentation are brought up to open-source community
standard (no CLI behaviour change, so no release is cut by these).

### Added

- **Community-health files.** `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 —
  also fixes the previously-broken link from `CONTRIBUTING.md`), `SECURITY.md`
  (private vulnerability reporting, supported versions, scope, release
  integrity), `GEMINI.md` (Gemini CLI agent guidance pointing at `AGENTS.md` /
  `CLAUDE.md`), and `TESTING.md` (how to run the offline suite, what it covers,
  the eval harness, and how to add a test).
- **`Makefile`** — a self-documenting task runner (`make` lists targets):
  `setup`, `hooks`, `test`, `lint`, `lint-md`, `check`, `build`, `e2e`, `clean`,
  wrapping the commands already documented in `CLAUDE.md`.
- **Git hooks** (`.githooks/pre-commit`, `.githooks/pre-push`) — lint staged
  Python/Markdown on commit, run the test suite on push. Opt-in via `make hooks`;
  both degrade gracefully when tooling is absent.
- **Developer-experience tooling.** `.editorconfig`; an explicit ruff config in
  `pyproject.toml` (`[tool.ruff]` — deterministic linting with import sorting and
  pyupgrade, replacing CI's reliance on ruff defaults); **`ruff format` adopted
  as the formatter** (the whole tree reformatted once), enforced by a
  `ruff format --check` gate in CI and auto-applied by the pre-commit hook; a
  reusable `setup-python-uv` composite GitHub Action; a `.devcontainer/README.md`;
  and `make cov` / `make lint` / `make fix` / `make format` targets.

### Changed

- **README** restructured for scannability — a hero with badges and a nav bar, a
  mermaid pipeline diagram, an embedded demo, a "What you get" summary, a
  compact quickstart, a repository-layout map, and the deep step-by-step
  walkthrough moved into a collapsible. Content is unchanged in substance.
- **`SUPPORT.md`** expanded to the structured "before / where / what / expect"
  form, and `CONTRIBUTING.md` now lists the `make` targets and links `TESTING.md`.
- **Dev container** now syncs dependencies and enables the git hooks on create
  (ready-to-hack), and the `test.yml` CI workflow uses the new composite setup
  action instead of repeating the uv/Python setup per job.

### Fixed

- **Issue-template contact links** (`.github/ISSUE_TEMPLATE/config.yml`) pointed
  at `github/spec-kit` (including a "Security Issues" link to spec-kit's policy);
  they now point at InfraKit's own README, `CONTRIBUTING.md`, `SUPPORT.md`, and
  `SECURITY.md`.
- **Dev container spec-kit leftovers** — it was named `SpecKitDevContainer` and
  carried spec-kit-only VS Code settings (`speckit.*` prompt recommendations and
  `.specify/scripts/` auto-approve paths that don't exist in InfraKit). Renamed
  and trimmed to InfraKit-relevant settings.
- **Test-suite lint** — removed unused assignments and a `lambda` assignment so
  `tests/` passes the new ruff config.

## [1.0.0] - 2026-05-31

First stable release. CloudFormation joins Terraform and Crossplane as a
first-class IaC tool, validation is enforced rather than promised, the eval
harness gives the multi-persona pipeline a measuring stick, and the
CLI/commands/docs are mutually consistent.

### Added

- **AWS CloudFormation support** — CloudFormation is now a first-class IaC tool alongside Crossplane and Terraform. `infrakit init --iac cloudformation` renders the full command set (`create_cloudformation_code`, `update_cloudformation_code`, `plan`, `implement`, `review`, `setup-coding-style`, `quick_fix`) plus a new `cloudformation-engineer` persona (registered as a Claude subagent) and a CloudFormation coding-style template. The engineer verifies every resource `Type` and property against the AWS resource-type reference before writing, enforces `NoEcho` + dynamic-reference secret handling, per-resource `Tags`, `DeletionPolicy`/`UpdateReplacePolicy` on stateful resources, and validates with `cfn-lint`. `resource_term` is `template`; required tool is the `aws` CLI with optional `cfn-lint`. A full `examples/cloudformation/` walkthrough is included.

- **`/infrakit:quick_fix` — the lighter path.** A new per-IaC command (Terraform, Crossplane, CloudFormation) that takes a natural-language requirement and runs the IaC Engineer through **plan → tasks → your review → implement**, skipping the multi-persona spec/architect/security ceremony. It creates a `quick` track for the audit trail, verifies provider schemas, presents `plan.md` + `tasks.md` for approval before writing any code, then implements behind a mandatory validation gate. It recommends the full pipeline for compliance-sensitive or new-design changes.

- **`infrakit check` now reports IaC tool CLIs.** In addition to git and agent CLIs, `check` now reports each IaC tool's required and optional binaries (`kubectl`, `terraform`, `aws`, `cfn-lint`, …) — required tools error when missing, optional ones are skipped — driven by `IAC_CONFIG`. This makes the documented behaviour ("checks kubectl/terraform") actually true.

- **Eval harness (`evals/`).** A deterministic, headless scorer that grades generated IaC against the secure-defaults the personas promise (encryption at rest, public access blocked, required tags, no hardcoded secrets, TLS, versioning, deletion safety, validator passes). It scores the three committed example deliverables (which must hit 100%) and two deliberately-insecure fixtures (which must score ≤40%, proving the scorer can actually fail). Wired into pytest (`tests/test_evals.py`) so CI runs ~38 checks offline; a documented `--generator llm` hook in `evals/run.py` is the seam for driving the real pipeline against golden requirements and measuring whether the multi-persona flow beats a single prompt.

### Changed

- **`infrakit init` "Next Steps" panel is now IaC-aware and accurate.** It derives the create/update command names and resource term from `IAC_CONFIG` (so it prints `create_terraform_code` / `new_composition` / `create_cloudformation_code` correctly), walks the real `setup → setup-coding-style → spec → plan → implement → review` flow, surfaces the `quick_fix` fast path, and uses a clean running counter. The `--iac` help text now lists all supported tools dynamically.

- **Validation is now a hard gate.** `/infrakit:implement` and `/infrakit:quick_fix` no longer treat validation as a suggested next step — they must run the tool's validator (`tofu validate` / `cfn-lint` / `crossplane render` + YAML parse) and may **not** mark a track ✅ done until it passes. If the validator can't run, the track is set to ❌ blocked (or flagged unvalidated), never silently "done". The three engineer personas carry the same constraint. This makes the "provider-verified" claim enforced rather than promised.

- **Release pipeline is now `pyproject.toml`-driven.** `release.yml` previously auto-patch-bumped the latest git tag on every merge and committed the bump back to `main`; it now reads the version straight from `pyproject.toml` and releases it only if no GitHub Release exists for it yet. Bumping `version` in a PR is what cuts a release — patch, minor, or major (this `1.0.0` is the first cut this way) — and merges that don't touch the version are no-ops. CI no longer edits `pyproject.toml`; the redundant version-stamp and commit-back steps (and the `update-version.sh` script) were removed.

### Fixed

- **Removed references to commands that don't exist.** The init panels, `skills.py` `SKILL_DESCRIPTIONS`, and several docs referenced `/infrakit:project_context`, `/infrakit:review_composition`, `/infrakit:validate_composition`, `/infrakit:clarify`, `/infrakit:checklist`, `/infrakit:specify_composition`, `/infrakit:plan_composition`, and `/infrakit:implement_composition` — none of which are real commands. All now reference the actual command set.

- **`SKILL_DESCRIPTIONS` rekeyed to real command stems.** The `--ai-skills` enhanced descriptions were keyed to stale names (`specify_composition`, `coding_style`, `tagging`, …) so they were silently dropped on install. Keys now match every real stem across all three IaC tools.

- **Stale `*_contract.md` references removed from docs.** `README.md`, `docs/quickstart.md`, and `docs/installation.md` still described a per-resource `infrakit_composition_contract.md` / `.infrakit_terraform_contract.md` that is no longer generated; they now correctly describe the code + `README.md` as the contract. Also corrected `docs/installation.md`'s `tagging.md` → `tagging-standard.md`.

- **Markdown linting now actually runs in CI.** The `globs` in `.github/workflows/lint.yml` were quoted (`'**/*.md'`), so markdownlint-cli2 matched a literal filename and linted **0 files** — the lint job was a silent no-op. Removed the quotes so it lints the repo. To keep the suite green without fighting InfraKit's deliberate dense-prompt template style, `.markdownlint-cli2.jsonc` now also disables MD031/MD032 (blanks around fences/lists in the `> - …` Q&A prompt blocks) and MD055/MD056 (the `[PROJECT_SPECIFIC_TAGS]` placeholder-in-table in the coding-style assets), and ignores `.venv`/`node_modules`/`.pytest_cache`/`dist`/`build`. Remaining real issues were fixed: a language was added to every bare code fence (MD040) and a stray double blank line removed (MD012). The repo now lints clean.

### Removed

- **Dead `github_api.py` module and four unused dependencies.** `infrakit version` never actually checked for upgrades — it only prints local metadata — so the 104-line `github_api.py` (token/rate-limit/SSL helpers left over from the retired template-download flow) had no callers. Deleted it, its 22-test suite, and the dependencies it pulled in: `httpx[socks]`, `truststore`, plus `packaging` and `platformdirs` which were also unused. The CLI now declares 5 runtime deps (was 9) and makes **zero network calls**. Docs that described `infrakit version` as "check for upgrades" / a network call were corrected.

## [0.1.14] - 2026-05-12

### Changed

- **Personas rewritten — first 50 lines load-bearing, all files ≤265 lines.** The five persona files (`cloud_solutions_engineer.md`, `cloud_architect.md`, `cloud_security_engineer.md`, `terraform_engineer.md`, `crossplane_engineer.md`) totalled 2,147 lines before — now 1,063 (cut in half). The first ~50 lines of each now packs everything the model conditions on hardest: identity, scope, what they DON'T own (with explicit hand-off targets), what files they must read, and the hard rules. Everything else is reference material. Removed: long table-of-contents lists, ASCII flow diagrams, duplicate examples, multi-paragraph rationale for every rule, and the `MUST` / `CRITICAL` / `WAIT` all-caps shouting that frontier models don't respond to better than calm prose.

- **Claude Code subagents are now real subagents, not role-play.** On Claude Code, the persona files are registered as **custom subagent types** at `.claude/agents/<persona-name>.md`. The multi-persona commands invoke them via `Task(subagent_type=cloud-architect, …)` with a one-paragraph delegation prompt; the persona file is the subagent's system prompt, the report contract is in the persona, and the orchestrator never sees the architect's reasoning steps — only the final report. New `claude_subagents` extras hook in `AGENT_CONFIG` drives the rendering; new tests cover the layout. Codex / Gemini / Copilot / generic agents keep the inline fallback as before (no custom-subagent primitive available there).

- **Scoped supported AI agents from 19 down to 5**. The supported set is now: **Claude Code**, **Codex CLI**, **Gemini CLI**, **GitHub Copilot**, and a **generic** fallback for bring-your-own-agent setups. Dropped: cursor-agent, qwen, opencode, windsurf, kilocode, auggie, codebuddy, qodercli, roo, q (Amazon Q), amp, shai, agy, bob. The wider agent matrix accumulated faster than it could be tested end-to-end; per-agent prompt quality drifted because no one was running the workflow against 19 harnesses. The cap is now five agents that are tested on every release. If you need first-class support for another agent, open an issue. Existing user projects on dropped agents continue to work — the prompts they already have don't move; only fresh `infrakit init` is constrained.

- **Multi-persona commands now invoke real subagents on agents that support them.** The four multi-persona commands (`/infrakit:create_terraform_code`, `/infrakit:new_composition`, `/infrakit:update_terraform_code`, `/infrakit:update_composition`) previously asked the parent agent to "adopt the X persona" inline — which produced role-play rather than real context isolation. On Claude Code, each read-only review phase (Cloud Architect, Cloud Security Engineer) now delegates to a fresh subagent via the `Task` tool, with the persona file as the subagent's system prompt and a structured-report return contract. The interactive Cloud Solutions Engineer phase still runs inline because subagents can't pause for user input. For Codex / Gemini / Copilot / generic agents (no `Task` primitive), the prompts include an explicit inline fallback that marks the persona-switch boundary in the agent's output. New `supports_subagents` field in `AGENT_CONFIG` is the source of truth.

- **Split `src/infrakit_cli/__init__.py` into focused modules**. The 1,837-line megafile is now 11 modules of 100–600 lines each (`cli.py`, `bootstrap.py`, `skills.py`, `mcp.py`, `git_utils.py`, `tools.py`, `tracker.py`, `interactive.py`, `banner.py`, `console.py`, `github_api.py`). `__init__.py` is now an explicit re-export shim with `__all__` so existing imports (`from infrakit_cli import app`, etc.) continue to work. No behaviour change.

- **Dropped the "Constraint-Driven Development" branding**. InfraKit is now described as "spec-kit for IaC, with a multi-persona pipeline" — a more honest framing that credits [spec-kit](https://github.com/github/spec-kit) for the workflow shape and reserves InfraKit's claims for its actual contribution (the four-persona Cloud Solutions Engineer → Architect → Security → IaC Engineer pipeline). The CDD name appeared only in marketing and docs; prompts and runtime code were already neutral. The methodology document at `constraint-driven.md` keeps its filename (URL stability) but reads as Spec-Driven Development with InfraKit-specific additions.

- **Single-artifact release**. Templates and prompts now ship inside the `infrakit-cli` PyPI wheel instead of as 76 per-agent GitHub release ZIPs (19 agents × 2 IaC × 2 scripts). `infrakit init` performs all per-agent layout transformations (folder placement, TOML wrapping, Copilot prompt pairs, VS Code settings) at install time from the bundled prompts. **Effects**:
  - `infrakit init` now runs entirely offline; no network calls.
  - `--github-token` and `--skip-tls` flags are removed (templates no longer download).
  - Existing user projects continue to work — the prompts they already have in `.claude/commands/` (or equivalent) are unchanged. Re-running `infrakit init --here` will re-materialize the latest in-package prompts.

- **Full walkthrough examples**. `examples/terraform/` and `examples/crossplane/` now contain complete end-to-end runs (config, spec, plan, tasks, reviews, generated code) for an AWS S3 secure-bucket module and an `XPostgreSQLInstance` composition respectively.

- **Prompts: compliance is now context-driven**. The security persona's hard-coded framework list has been removed; compliance scope is read from `.infrakit/context.md` (populated via `/infrakit:setup`). Also drops the explicit composition-contract step and re-syncs `update_composition` with the current prompt shape.

- **README: dropped the `logo.svg` image** from the header for a tighter first-fold.

- **CI: `release.yml` hardened**. The publish step now pins `pypa/gh-action-pypi-publish` to commit SHA `cef221092ed1bacb1cc03d23a2d87d1d172e277b` (v1.14.0) instead of the moving `release/v1` branch, and sets `repository-url: https://upload.pypi.org/legacy/` explicitly. Trusted-publishing config on PyPI was also recreated after the project was deleted and restored — first publish of v0.1.14 promoted a pending publisher into a regular one.

### Removed

- Per-agent GitHub release ZIPs (`infrakit-template-<agent>-<iac>-<script>-vX.Y.Z.zip`). Install the CLI from PyPI (`pip install infrakit-cli` or `uv pip install infrakit-cli`) and run `infrakit init`.
- The `--github-token` and `--skip-tls` flags on `infrakit init` (templates are now bundled in the wheel).
- Six unused root template files (`plan-template.md`, `spec-template.md`, `tasks-template.md`, `agent-file-template.md`, `checklist-template.md`, `tagging-constraint-template.md`) and ten helper scripts (`setup-plan.sh/.ps1`, `create-new-feature.sh/.ps1`, `update-agent-context.sh/.ps1`, `check-prerequisites.sh/.ps1`, `common.sh/.ps1`) that fed them. None were referenced by any current InfraKit prompt.
- **GitHub Pages docs deployment workflow** (`.github/workflows/docs.yml`). DocFX → Pages deploys are retired; `docs/` is left in place for local builds. The `github-pages` GitHub environment is now orphaned and can be deleted from repo Settings → Environments.
- **`.infrakit_terraform_contract.md`** as a maintained artifact. The per-resource Terraform contract file is no longer written alongside generated code; resource context lives in `.infrakit/context.md` and the code itself.

### Added

- **Auto-generated Task Lists**: `/infrakit:plan` now automatically generates `tasks.md` after the user accepts the plan. Tasks are checkbox items (`- [ ]`) that `/infrakit:implement` marks off as it executes. No separate `/infrakit:tasks` command needed.

- **Post-Implementation Artifacts**: `/infrakit:implement` now writes three artifacts after all tasks complete:
  - `.infrakit_context.md` — records the resource interface (variables, outputs, resources provisioned)
  - `.infrakit_changelog.md` — appends a structured entry (change type, summary, ADD/MODIFY/REMOVE breakdown, state impact)
  - `infrakit_composition_contract.md` / `.infrakit_terraform_contract.md` — regenerated from the freshly-written code and presented for review

- **Contract File Bootstrapping**: `/infrakit:update_composition` and `/infrakit:update_terraform_code` now check for `.infrakit_context.md`, `.infrakit_changelog.md`, and the resource contract file at the start. If any are missing but the implementation code exists, they are generated from the code and presented for user review before the spec update begins.

- **Iterative Requirements Clarification**: The Cloud Solutions Engineer in update commands now asks clarifying questions iteratively until requirements are fully understood before writing `spec.md`. A completion gate ("Are these requirements fully clear?") must pass before handing off to the Cloud Architect.

- **Multi-Option Architecture Review**: The Cloud Architect now presents 2–3 named design options with trade-off tables (complexity, cost, flexibility, risk) for the user to choose from, rather than a single recommendation.

- **Track Path Migration**: All track directories now live under `.infrakit_tracks/tracks/<track-name>/` and the registry is at `.infrakit_tracks/tracks.md`. Previously these were under `.infrakit/tracks/`. Projects initialized with an older version should move these directories manually.

### Removed

- **`/infrakit:tasks` command**: Removed as a standalone command. Task generation is now integrated into `/infrakit:plan` — after the user accepts the plan, `tasks.md` is auto-generated with no extra step required. The workflow is now `plan → implement` instead of `plan → tasks → implement`.

### Changed

- **Changelog timing**: The changelog (`infrakit_changelog.md`) is now written by `/infrakit:implement` after successful implementation, not by the update commands during spec registration. This ensures the changelog only records what was actually built.

- **Implement prereq checks**: `/infrakit:implement` now requires all three track artifacts — `spec.md`, `plan.md`, and `tasks.md`. If any are missing, it halts with a clear error directing to the right command to generate the missing file.

- **`/infrakit:security-review` verdict messages**: Updated to direct users to `/infrakit:plan` instead of the removed `/infrakit:tasks` command.

- **`/infrakit:status` output**: Planned tracks now show `→ Run /infrakit:implement <track-name>` (tasks.md note added inline).

### Fixed

- **Terraform Release Artifacts**: Fixed Terraform zip packages not being uploaded to GitHub Releases
  - `create-github-release.sh` was hard-coded with 38 Crossplane-only file paths; Terraform packages
    built by `create-release-packages.sh` were silently omitted from every release since v0.1.7
  - Replaced hard-coded list with dynamic discovery: uploads all `infrakit-template-*-$VERSION.zip`
    files from `.genreleases/`, covering all agents × IaC tools × script types automatically
  - Added guard that exits with a clear error if no packages are found in `.genreleases/`

- **Test Coverage**: Added `implement.md` to all parametrized test lists in `TestTerraformCommandFilesExist`
  and `TestTerraformCommandFileFrontmatter` — the file existed and was registered in `iac_config.py`
  but was absent from the test suite

## [0.1.9] - 2026-04-07

### Added

- **Roo Code Support**: Added `roo` (Roo Code) to the supported AI assistants list
- **Documentation Updates**: Synchronized all documentation (README, AGENTS.md, and docs/) with the latest code features
  - Updated `README.md` and `AGENTS.md` with latest agent directories and formats
  - Updated `docs/index.md` and others to reflect full Terraform support
  - Updated `infrakit init` help text with all supported agents

## [0.1.8] - 2026-04-07

### Changed

- **Release Script Cleanup**: Removed dead `technical-reference` copy blocks from release scripts
  (PR #11) — technical reference docs no longer exist in the repository

## [0.1.7] - 2026-04-07

### Added

- **Terraform IaC Support**: Added full Terraform support as a second IaC tool alongside Crossplane
  - New `--iac terraform` option in `infrakit init` bootstraps projects with Terraform-specific workflows
  - New commands: `create_terraform_code`, `update_terraform_code`, `plan`, `review`
  - `create_terraform_code`: Multi-phase Cloud Solutions Engineer → Architect Review → Security Review → spec confirmation workflow for new Terraform modules
  - `update_terraform_code`: Scans existing `.tf` files to reconstruct context, classifies changes (Additive/Behavioral/Breaking), generates `spec.md` and `migration.md` for breaking changes
  - `plan`: Looks up resource arguments on `registry.terraform.io`, designs variable→resource and output→attribute mappings, writes `plan.md`
  - `review`: Reviews HCL for hardcoded secrets, encryption, tagging completeness, version pinning, variable/output descriptions, and file structure
  - New `terraform_engineer.md` agent persona for the `/implement` command
  - New `coding-style-template.md` with Terraform conventions (naming, tagging, backend, security defaults)
  - New `terraform.md` technical reference documentation
  - Updated `create-release-packages.sh` to include terraform in release packages

## [0.1.6] - 2026-02-23

### Fixed

- **Parameter Ordering Issues (#1641)**: Fixed CLI parameter parsing issue where option flags were incorrectly consumed as values for preceding options
  - Added validation to detect when `--ai` or `--ai-commands-dir` incorrectly consume following flags like `--here` or `--ai-skills`
  - Now provides clear error messages: "Invalid value for --ai: '--here'"
  - Includes helpful hints suggesting proper usage and listing available agents
  - Commands like `infrakit init --ai-skills --ai --here` now fail with actionable feedback instead of confusing "Must specify project name" errors
  - Added comprehensive test suite (5 new tests) to prevent regressions

  ## [0.1.5] - 2026-02-21

  ### Fixed

  - **AI Skills Installation Bug (#1658)**: Fixed `--ai-skills` flag not generating skill files for GitHub Copilot and other agents with non-standard command directory structures
  - Added `commands_subdir` field to `AGENT_CONFIG` to explicitly specify the subdirectory name for each agent
  - Affected agents now work correctly: copilot (`.github/agents/`), opencode (`.opencode/command/`), windsurf (`.windsurf/workflows/`), codex (`.codex/prompts/`), kilocode (`.kilocode/workflows/`), q (`.amazonq/prompts/`), and agy (`.agent/workflows/`)
  - The `install_ai_skills()` function now uses the correct path for all agents instead of assuming `commands/` for everyone

  ## [0.1.4] - 2026-02-20

  ### Fixed

  - **Qoder CLI detection**: Renamed `AGENT_CONFIG` key from `"qoder"` to `"qodercli"` to match the actual executable name, fixing `infrakit check` and `infrakit init --ai` detection failures

  ## [0.1.3] - 2026-02-20

  ### Added

  - **Generic Agent Support**: Added `--ai generic` option for unsupported AI agents ("bring your own agent")
  - Requires `--ai-commands-dir <path>` to specify where the agent reads commands from
  - Generates Markdown commands with `$ARGUMENTS` format (compatible with most agents)
  - Example: `infrakit init my-project --ai generic --ai-commands-dir .myagent/commands/`
  - Enables users to start with InfraKit immediately while their agent awaits formal support

## [0.0.102] - 2026-02-20

- fix: include 'src/**' path in release workflow triggers (#1646)

## [0.0.101] - 2026-02-19

- chore(deps): bump github/codeql-action from 3 to 4 (#1635)

## [0.0.100] - 2026-02-19

- Add pytest and Python linting (ruff) to CI (#1637)
- feat: add pull request template for better contribution guidelines (#1634)

## [0.0.99] - 2026-02-19

- Feat/ai skills (#1632)

## [0.0.98] - 2026-02-19

- chore(deps): bump actions/stale from 9 to 10 (#1623)
- feat: add dependabot configuration for pip and GitHub Actions updates (#1622)

## [0.0.97] - 2026-02-18

- Remove Maintainers section from README.md (#1618)

## [0.0.96] - 2026-02-17

- fix: typo in plan-template.md (#1446)

## [0.0.95] - 2026-02-12

- Feat: add a new agent: Google Anti Gravity (#1220)

## [0.0.94] - 2026-02-11

- Add stale workflow for 180-day inactive issues and PRs (#1594)
