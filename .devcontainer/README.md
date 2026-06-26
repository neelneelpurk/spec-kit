# Dev Container for InfraKit

This dev container gives you a ready-to-hack environment for
[InfraKit](https://github.com/neelneelpurk/infrakit) with the Python toolchain,
the supported AI coding-agent CLIs, and the project's dependencies and git hooks
already set up.

## Use it

- **VS Code:** open the repo, then *Dev Containers: Reopen in Container* (needs
  Docker + the Dev Containers extension).
- **GitHub Codespaces:** *Code → Codespaces → Create codespace* — the container
  is built automatically.

When it finishes you can go straight to:

```bash
make test     # run the suite
make check    # ruff + markdownlint + pytest
infrakit --help
```

## What it provides

| Tool | Source |
|------|--------|
| Python 3.13 | base image `mcr.microsoft.com/devcontainers/python` |
| `uv` | installed in `post-create.sh` |
| `git`, `gh`, Node.js, .NET (for DocFX) | dev container features |
| AI agent CLIs — Claude Code, Codex, Gemini, Copilot, Amazon Q, and more | `post-create.sh` |
| InfraKit dependencies (`uv sync --extra test`) | `post-create.sh` |
| Git hooks enabled (`core.hooksPath .githooks`) | `post-create.sh` |

## Lifecycle

| Hook | Runs | Does |
|------|------|------|
| `postCreateCommand` | Once, after the container is created | Runs [`post-create.sh`](./post-create.sh): installs the agent CLIs + uv, syncs dependencies, and enables the git hooks |
| `postStartCommand` | Every time the container starts | Marks the workspace a safe git directory |

To change what gets installed, edit
[`post-create.sh`](./post-create.sh); to change the base image, features, or VS
Code extensions, edit [`devcontainer.json`](./devcontainer.json).
