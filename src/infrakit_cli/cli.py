"""Typer-based CLI definition for ``infrakit``.

This module defines the :data:`app` instance and the four user-facing
commands (``init``, ``check``, ``mcp``, ``version``). The actual work for
each command is delegated to the focused helper modules
(:mod:`bootstrap`, :mod:`mcp`, :mod:`skills`, :mod:`git_utils`, etc.) — this
file is just argument parsing and orchestration.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

import typer
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .agent_config import AGENT_CONFIG
from .banner import BannerGroup, show_banner
from .bootstrap import initialize_iac_config
from .console import console
from .git_utils import init_git_repo, is_git_repo
from .iac_config import IAC_CONFIG, get_iac_choices
from .interactive import select_with_arrows
from .mcp import mcp_app
from .skills import ensure_project_context_from_template, install_ai_skills
from .tools import SCRIPT_TYPE_CHOICES, check_tool
from .tracker import StepTracker

app = typer.Typer(
    name="infrakit",
    help="InfraKit — spec-kit for IaC, with a multi-persona pipeline.",
    add_completion=False,
    invoke_without_command=True,
    cls=BannerGroup,
)

# `infrakit mcp [add|list|remove|doctor]` lives in the mcp module (deep module:
# the MCP command surface ships with the MCP logic). Bare `infrakit mcp` still
# runs the interactive installer via the sub-app's callback.
app.add_typer(mcp_app, name="mcp")


@app.callback()
def callback(ctx: typer.Context):
    """Show the banner when no subcommand is provided."""
    from rich.align import Align

    if ctx.invoked_subcommand is None and "--help" not in sys.argv and "-h" not in sys.argv:
        show_banner()
        console.print(Align.center("[dim]Run 'infrakit --help' for usage information[/dim]"))
        console.print()


@app.command()
def init(
    project_name: str = typer.Argument(
        None,
        help="Name for your new project directory (optional if using --here, or use '.' for current directory)",
    ),
    ai_assistant: str = typer.Option(
        None,
        "--ai",
        help="AI assistant to use: claude, codex, gemini, copilot, or generic (requires --ai-commands-dir)",
    ),
    ai_commands_dir: str = typer.Option(
        None,
        "--ai-commands-dir",
        help="Directory for agent command files (required with --ai generic, e.g. .myagent/commands/)",
    ),
    iac_tool: str = typer.Option(None, "--iac", help=f"IaC tool to use: {', '.join(IAC_CONFIG)}"),
    script_type: str = typer.Option(None, "--script", help="Script type to use: sh or ps"),
    ignore_agent_tools: bool = typer.Option(
        False,
        "--ignore-agent-tools",
        help="Skip checks for AI agent tools like Claude Code",
    ),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git repository initialization"),
    here: bool = typer.Option(
        False,
        "--here",
        help="Initialize project in the current directory instead of creating a new one",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force merge/overwrite when using --here (skip confirmation)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show verbose diagnostic output for initialization failures",
    ),
    ai_skills: bool = typer.Option(
        False,
        "--ai-skills",
        help="Install Prompt.MD templates as agent skills (requires --ai)",
    ),
):
    """Initialize a new InfraKit project.

    Templates ship inside the CLI package — ``infrakit init`` runs entirely
    offline and renders the per-agent layout (Claude, Gemini, Copilot, etc.)
    from the bundled prompts.

    This command will:

    1. Check that required tools are installed (git is optional)
    2. Let you choose your AI assistant and IaC tool
    3. Render commands + personas for the selected agent into the project
    4. Initialize a fresh git repository (if not ``--no-git`` and no existing repo)

    Examples::

        infrakit init my-project --ai claude --iac crossplane
        infrakit init my-project --ai claude --iac crossplane --no-git
        infrakit init --here --ai claude --iac crossplane
        infrakit init . --ai claude --iac crossplane
        infrakit init my-project --ai claude --iac terraform
        infrakit init --here --ai claude --iac terraform
        infrakit init my-project --ai generic --ai-commands-dir .myagent/commands/
    """

    show_banner()

    # Catch the parameter-ordering mistake where the next flag's name gets
    # consumed as the previous flag's value.
    if ai_assistant and ai_assistant.startswith("--"):
        console.print(f"[red]Error:[/red] Invalid value for --ai: '{ai_assistant}'")
        console.print("[yellow]Hint:[/yellow] Did you forget to provide a value for --ai?")
        console.print("[yellow]Example:[/yellow] infrakit init --ai claude --here")
        console.print(f"[yellow]Available agents:[/yellow] {', '.join(AGENT_CONFIG.keys())}")
        raise typer.Exit(1)

    if ai_commands_dir and ai_commands_dir.startswith("--"):
        console.print(f"[red]Error:[/red] Invalid value for --ai-commands-dir: '{ai_commands_dir}'")
        console.print(
            "[yellow]Hint:[/yellow] Did you forget to provide a value for --ai-commands-dir?"
        )
        console.print(
            "[yellow]Example:[/yellow] infrakit init --ai generic --ai-commands-dir .myagent/commands/"
        )
        raise typer.Exit(1)

    if project_name == ".":
        here = True
        project_name = None  # Clear so existing --here validation logic applies

    if here and project_name:
        console.print("[red]Error:[/red] Cannot specify both project name and --here flag")
        raise typer.Exit(1)

    if not here and not project_name:
        console.print(
            "[red]Error:[/red] Must specify either a project name, use '.' for current directory, or use --here flag"
        )
        raise typer.Exit(1)

    if ai_skills and not ai_assistant:
        console.print("[red]Error:[/red] --ai-skills requires --ai to be specified")
        console.print("[yellow]Usage:[/yellow] infrakit init <project> --ai <agent> --ai-skills")
        raise typer.Exit(1)

    if here:
        project_name = Path.cwd().name
        project_path = Path.cwd()

        existing_items = list(project_path.iterdir())
        if existing_items:
            console.print(
                f"[yellow]Warning:[/yellow] Current directory is not empty ({len(existing_items)} items)"
            )
            console.print(
                "[yellow]Template files will be merged with existing content and may overwrite existing files[/yellow]"
            )
            if force:
                console.print(
                    "[cyan]--force supplied: skipping confirmation and proceeding with merge[/cyan]"
                )
            else:
                response = typer.confirm("Do you want to continue?")
                if not response:
                    console.print("[yellow]Operation cancelled[/yellow]")
                    raise typer.Exit(0)
    else:
        project_path = Path(project_name).resolve()
        if project_path.exists():
            error_panel = Panel(
                f"Directory '[cyan]{project_name}[/cyan]' already exists\n"
                "Please choose a different project name or remove the existing directory.",
                title="[red]Directory Conflict[/red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print()
            console.print(error_panel)
            raise typer.Exit(1)

    current_dir = Path.cwd()

    setup_lines = [
        "[cyan]InfraKit Project Setup[/cyan]",
        "",
        f"{'Project':<15} [green]{project_path.name}[/green]",
        f"{'Working Path':<15} [dim]{current_dir}[/dim]",
    ]

    if not here:
        setup_lines.append(f"{'Target Path':<15} [dim]{project_path}[/dim]")

    console.print(Panel("\n".join(setup_lines), border_style="cyan", padding=(1, 2)))

    should_init_git = False
    if not no_git:
        should_init_git = check_tool("git")
        if not should_init_git:
            console.print("[yellow]Git not found - will skip repository initialization[/yellow]")

    if ai_assistant:
        if ai_assistant not in AGENT_CONFIG:
            console.print(
                f"[red]Error:[/red] Invalid AI assistant '{ai_assistant}'. Choose from: {', '.join(AGENT_CONFIG.keys())}"
            )
            raise typer.Exit(1)
        selected_ai = ai_assistant
    else:
        ai_choices = {key: config["name"] for key, config in AGENT_CONFIG.items()}
        selected_ai = select_with_arrows(ai_choices, "Choose your AI assistant:", "copilot")

    # Validate --ai-commands-dir usage.
    if selected_ai == "generic":
        if not ai_commands_dir:
            console.print("[red]Error:[/red] --ai-commands-dir is required when using --ai generic")
            console.print(
                "[dim]Example: infrakit init my-project --ai generic --ai-commands-dir .myagent/commands/[/dim]"
            )
            raise typer.Exit(1)
    elif ai_commands_dir:
        console.print(
            f"[red]Error:[/red] --ai-commands-dir can only be used with --ai generic (not '{selected_ai}')"
        )
        raise typer.Exit(1)

    if not ignore_agent_tools:
        agent_config = AGENT_CONFIG.get(selected_ai)
        if agent_config and agent_config["requires_cli"]:
            install_url = agent_config["install_url"]
            if not check_tool(selected_ai):
                error_panel = Panel(
                    f"[cyan]{selected_ai}[/cyan] not found\n"
                    f"Install from: [cyan]{install_url}[/cyan]\n"
                    f"{agent_config['name']} is required to continue with this project type.\n\n"
                    "Tip: Use [cyan]--ignore-agent-tools[/cyan] to skip this check",
                    title="[red]Agent Detection Error[/red]",
                    border_style="red",
                    padding=(1, 2),
                )
                console.print()
                console.print(error_panel)
                raise typer.Exit(1)

    if script_type:
        if script_type not in SCRIPT_TYPE_CHOICES:
            console.print(
                f"[red]Error:[/red] Invalid script type '{script_type}'. Choose from: {', '.join(SCRIPT_TYPE_CHOICES.keys())}"
            )
            raise typer.Exit(1)
        selected_script = script_type
    else:
        default_script = "ps" if os.name == "nt" else "sh"

        if sys.stdin.isatty():
            selected_script = select_with_arrows(
                SCRIPT_TYPE_CHOICES,
                "Choose script type (or press Enter)",
                default_script,
            )
        else:
            selected_script = default_script

    if iac_tool:
        if iac_tool not in IAC_CONFIG:
            console.print(
                f"[red]Error:[/red] Invalid IaC tool '{iac_tool}'. Choose from: {', '.join(IAC_CONFIG.keys())}"
            )
            raise typer.Exit(1)
        selected_iac = iac_tool
    else:
        iac_choices = get_iac_choices()
        if sys.stdin.isatty():
            selected_iac = select_with_arrows(iac_choices, "Choose your IaC tool:", "crossplane")
        else:
            selected_iac = "crossplane"

    console.print(f"[cyan]Selected AI assistant:[/cyan] {selected_ai}")
    console.print(f"[cyan]Selected IaC tool:[/cyan] {selected_iac}")
    console.print(f"[cyan]Selected script type:[/cyan] {selected_script}")

    tracker = StepTracker("Initialize InfraKit Project")

    sys._infrakit_tracker_active = True

    tracker.add("precheck", "Check required tools")
    tracker.complete("precheck", "ok")
    tracker.add("ai-select", "Select AI assistant")
    tracker.complete("ai-select", f"{selected_ai}")
    tracker.add("iac-select", "Select IaC tool")
    tracker.complete("iac-select", f"{selected_iac}")
    tracker.add("script-select", "Select script type")
    tracker.complete("script-select", selected_script)
    for key, label in [
        ("project_context", "Project Context setup"),
        ("iac-config", "IaC configuration"),
        ("iac-commands", "Render commands & personas"),
    ]:
        tracker.add(key, label)
    if ai_skills:
        tracker.add("ai-skills", "Install agent skills")
    for key, label in [
        ("git", "Initialize git repository"),
        ("final", "Finalize"),
    ]:
        tracker.add(key, label)

    # Track git error message outside Live context so it survives the redraw.
    git_error_message = None

    with Live(tracker.render(), console=console, refresh_per_second=8, transient=True) as live:
        tracker.attach_refresh(lambda: live.update(tracker.render()))
        try:
            # Templates ship inside the package; no network calls.
            if not here:
                project_path.mkdir(parents=True, exist_ok=True)

            ensure_project_context_from_template(project_path, tracker=tracker)

            # Materialise .infrakit/, .infrakit_tracks/, commands, personas.
            initialize_iac_config(project_path, selected_iac, selected_ai, tracker=tracker)

            # For the generic agent, rename the rendered .infrakit/commands/
            # to the user-specified path so they can place commands wherever
            # they want.
            if selected_ai == "generic" and ai_commands_dir:
                placeholder_dir = project_path / ".infrakit" / "commands"
                target_dir = project_path / ai_commands_dir
                if placeholder_dir.is_dir() and placeholder_dir != target_dir:
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(placeholder_dir), str(target_dir))

            if ai_skills:
                skills_ok = install_ai_skills(project_path, selected_ai, tracker=tracker)

                # When --ai-skills is used on a NEW project and skills were
                # successfully installed, remove the command files that the
                # template renderer just created. Skills replace commands;
                # keeping both would be confusing. For --here on an existing
                # repo we leave pre-existing commands untouched. We only
                # delete AFTER skills succeed so the project always has at
                # least one of {commands, skills}.
                if skills_ok and not here:
                    agent_cfg = AGENT_CONFIG.get(selected_ai, {})
                    agent_folder = agent_cfg.get("folder", "")
                    if agent_folder:
                        cmds_dir = project_path / agent_folder.rstrip("/") / "commands"
                        if cmds_dir.exists():
                            try:
                                shutil.rmtree(cmds_dir)
                            except OSError:
                                # Best-effort cleanup: skills are installed,
                                # so leaving stale commands is non-fatal.
                                console.print(
                                    "[yellow]Warning: could not remove extracted commands directory[/yellow]"
                                )

            if not no_git:
                tracker.start("git")
                if is_git_repo(project_path):
                    tracker.complete("git", "existing repo detected")
                elif should_init_git:
                    success, error_msg = init_git_repo(project_path, quiet=True)
                    if success:
                        tracker.complete("git", "initialized")
                    else:
                        tracker.error("git", "init failed")
                        git_error_message = error_msg
                else:
                    tracker.skip("git", "git not available")
            else:
                tracker.skip("git", "--no-git flag")

            tracker.complete("final", "project ready")
        except Exception as e:
            tracker.error("final", str(e))
            console.print(Panel(f"Initialization failed: {e}", title="Failure", border_style="red"))
            if debug:
                _env_pairs = [
                    ("Python", sys.version.split()[0]),
                    ("Platform", sys.platform),
                    ("CWD", str(Path.cwd())),
                ]
                _label_width = max(len(k) for k, _ in _env_pairs)
                env_lines = [
                    f"{k.ljust(_label_width)} → [bright_black]{v}[/bright_black]"
                    for k, v in _env_pairs
                ]
                console.print(
                    Panel(
                        "\n".join(env_lines),
                        title="Debug Environment",
                        border_style="magenta",
                    )
                )
            if not here and project_path.exists():
                shutil.rmtree(project_path)
            raise typer.Exit(1)
        finally:
            pass

    console.print(tracker.render())
    console.print("\n[bold green]Project ready.[/bold green]")

    if git_error_message:
        console.print()
        git_error_panel = Panel(
            f"[yellow]Warning:[/yellow] Git repository initialization failed\n\n"
            f"{git_error_message}\n\n"
            f"[dim]You can initialize git manually later with:[/dim]\n"
            f"[cyan]cd {project_path if not here else '.'}[/cyan]\n"
            f"[cyan]git init[/cyan]\n"
            f"[cyan]git add .[/cyan]\n"
            f'[cyan]git commit -m "Initial commit"[/cyan]',
            title="[red]Git Initialization Failed[/red]",
            border_style="red",
            padding=(1, 2),
        )
        console.print(git_error_panel)

    # Agent folder security notice.
    agent_config = AGENT_CONFIG.get(selected_ai)
    if agent_config:
        agent_folder = ai_commands_dir if selected_ai == "generic" else agent_config["folder"]
        if agent_folder:
            security_notice = Panel(
                f"Some agents may store credentials, auth tokens, or other identifying and private artifacts in the agent folder within your project.\n"
                f"Consider adding [cyan]{agent_folder}[/cyan] (or parts of it) to [cyan].gitignore[/cyan] to prevent accidental credential leakage.",
                title="[yellow]Agent Folder Security[/yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
            console.print()
            console.print(security_notice)

    # Resolve the IaC-specific command names so the printed next-steps match the
    # commands that were actually rendered for the selected tool (these differ:
    # crossplane uses new_composition/update_composition, terraform uses
    # create_terraform_code/update_terraform_code, etc.).
    iac_cfg = IAC_CONFIG.get(selected_iac, {})
    resource_term = iac_cfg.get("resource_term", "resource")
    iac_cmds = iac_cfg.get("iac_commands", [])
    create_cmd = next((c for c in iac_cmds if c.startswith(("new_", "create_"))), None)
    update_cmd = next((c for c in iac_cmds if c.startswith("update_")), None)

    steps_lines = []
    n = 1
    if not here:
        steps_lines.append(f"{n}. Go to the project folder: [cyan]cd {project_name}[/cyan]")
    else:
        steps_lines.append(f"{n}. You're already in the project directory!")
    n += 1

    # Codex-specific setup step.
    if selected_ai == "codex":
        codex_path = project_path / ".codex"
        quoted_path = shlex.quote(str(codex_path))
        if os.name == "nt":
            cmd = f"setx CODEX_HOME {quoted_path}"
        else:
            cmd = f"export CODEX_HOME={quoted_path}"

        steps_lines.append(
            f"{n}. Set [cyan]CODEX_HOME[/cyan] environment variable before running Codex: [cyan]{cmd}[/cyan]"
        )
        n += 1

    steps_lines.append(f"{n}. Establish your project standards:")
    steps_lines.append(
        "   • [cyan]/infrakit:setup[/] - Capture project context & tagging standards"
    )
    steps_lines.append("   • [cyan]/infrakit:setup-coding-style[/] - Define IaC coding standards")
    n += 1

    steps_lines.append(f"{n}. Build a {resource_term} (full spec-driven pipeline):")
    if create_cmd:
        steps_lines.append(
            f"   • [cyan]/infrakit:{create_cmd}[/] - Spec → architect → security review"
        )
    if update_cmd:
        steps_lines.append(
            f"   • [cyan]/infrakit:{update_cmd}[/] - Update an existing {resource_term}"
        )
    steps_lines.append("   • [cyan]/infrakit:plan[/] - Plan + auto-generate tasks.md")
    steps_lines.append("   • [cyan]/infrakit:implement[/] - Execute the task list")
    steps_lines.append("   • [cyan]/infrakit:review[/] - Review generated code against standards")
    n += 1

    steps_lines.append(f"{n}. …or take the lighter path:")
    steps_lines.append(
        "   • [cyan]/infrakit:quick_fix[/] - Requirement → plan → tasks → review → implement"
    )
    n += 1

    steps_lines.append(f"{n}. Track all work anytime with [cyan]/infrakit:status[/]")

    steps_panel = Panel(
        "\n".join(steps_lines), title="Next Steps", border_style="cyan", padding=(1, 2)
    )
    console.print()
    console.print(steps_panel)

    enhancement_lines = [
        "Optional quality gates [bright_black](run before merging)[/bright_black]",
        "",
        "○ [cyan]/infrakit:analyze[/] - Cross-artifact consistency report (spec ↔ plan ↔ code)",
        "○ [cyan]/infrakit:architect-review[/] - Architecture, cost & reliability review",
        "○ [cyan]/infrakit:security-review[/] - Compliance audit (SOC 2, HIPAA, PCI-DSS, …)",
    ]
    enhancements_panel = Panel(
        "\n".join(enhancement_lines),
        title="Enhancement Commands",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print()
    console.print(enhancements_panel)


@app.command()
def check():
    """Check that all required tools are installed."""
    show_banner()
    console.print("[bold]Checking for installed tools...[/bold]\n")

    tracker = StepTracker("Check Available Tools")

    tracker.add("git", "Git version control")
    git_ok = check_tool("git", tracker=tracker)

    agent_results = {}
    for agent_key, agent_config in AGENT_CONFIG.items():
        if agent_key == "generic":
            continue  # Generic is not a real agent to check
        agent_name = agent_config["name"]
        requires_cli = agent_config["requires_cli"]

        tracker.add(agent_key, agent_name)

        if requires_cli:
            agent_results[agent_key] = check_tool(agent_key, tracker=tracker)
        else:
            # IDE-based agent — skip CLI check and mark as optional.
            tracker.skip(agent_key, "IDE-based, no CLI check")
            agent_results[agent_key] = False

    # VS Code variants are not in agent config; check them separately.
    tracker.add("code", "Visual Studio Code")
    check_tool("code", tracker=tracker)

    tracker.add("code-insiders", "Visual Studio Code Insiders")
    check_tool("code-insiders", tracker=tracker)

    # IaC tool CLIs (per IAC_CONFIG requires_tools / optional_tools). Required
    # tools report an error when missing; optional ones are skipped so the check
    # doesn't look like a failure for tools the user simply hasn't installed.
    iac_tools: dict[str, dict] = {}
    for iac_cfg in IAC_CONFIG.values():
        iac_name = iac_cfg.get("name", "")
        for tool_name in iac_cfg.get("requires_tools", []):
            entry = iac_tools.setdefault(tool_name, {"used_by": set(), "required": False})
            entry["used_by"].add(iac_name)
            entry["required"] = True
        for tool_name in iac_cfg.get("optional_tools", []):
            entry = iac_tools.setdefault(tool_name, {"used_by": set(), "required": False})
            entry["used_by"].add(iac_name)

    for tool_name in sorted(iac_tools):
        info = iac_tools[tool_name]
        used_by = ", ".join(sorted(info["used_by"]))
        suffix = "" if info["required"] else ", optional"
        key = f"iac:{tool_name}"
        tracker.add(key, f"{tool_name} ({used_by}{suffix})")
        if shutil.which(tool_name) is not None:
            tracker.complete(key, "available")
        elif info["required"]:
            tracker.error(key, "not found")
        else:
            tracker.skip(key, "optional, not installed")

    console.print(tracker.render())

    console.print("\n[bold green]InfraKit CLI is ready to use![/bold green]")

    if not git_ok:
        console.print("[dim]Tip: Install git for repository management[/dim]")

    if not any(agent_results.values()):
        console.print("[dim]Tip: Install an AI assistant for the best experience[/dim]")


@app.command()
def version():
    """Display version and system information."""
    import importlib.metadata
    import platform

    show_banner()

    cli_version = "unknown"
    try:
        cli_version = importlib.metadata.version("infrakit-cli")
    except Exception:
        # Fallback: read from pyproject.toml when running from source.
        try:
            import tomllib

            pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                    cli_version = data.get("project", {}).get("version", "unknown")
        except Exception:
            pass

    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Key", style="cyan", justify="right")
    info_table.add_column("Value", style="white")

    info_table.add_row("CLI Version", cli_version)
    info_table.add_row("", "")
    info_table.add_row("Python", platform.python_version())
    info_table.add_row("Platform", platform.system())
    info_table.add_row("Architecture", platform.machine())
    info_table.add_row("OS Version", platform.version())

    panel = Panel(
        info_table,
        title="[bold cyan]InfraKit CLI Information[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )

    console.print(panel)
    console.print()


def main():
    """Entry point exposed via ``project.scripts`` in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
