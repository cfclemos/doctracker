"""Command line interface: `doctracker init`, `doctracker start` and `doctracker hook` (called by Claude Code)."""

import json
import sys
from pathlib import Path

import click

from doctracker import __version__
from doctracker.config import CONFIG_PATH, Config, detect_packages, load_config, write_config
from doctracker.integrations import claude_code, opencode


@click.group()
@click.version_option(__version__, prog_name="doctracker")
def main() -> None:
    """Centralized documentation for Python projects developed with LLM agents."""


@main.command()
@click.option("--force", is_flag=True, help="Overwrite an existing configuration.")
def init(force: bool) -> None:
    """Create doc/config/config.json in the current project.

    \f
    Args:
        force: Overwrite the configuration if it already exists.

    Raises:
        click.ClickException: When the configuration exists and `force` is not set.
    """
    project_root = Path.cwd()
    if (project_root / CONFIG_PATH).exists() and not force:
        raise click.ClickException(f"{CONFIG_PATH.as_posix()} already exists (use --force to overwrite).")
    _initialize(project_root)


@main.command()
@click.option("--host", help="Override the host from the configuration.")
@click.option("--port", type=int, help="Override the port from the configuration.")
def start(host: str | None, port: int | None) -> None:
    """Start the server (MCP endpoint, wiki and watcher) for the current project.

    \f
    Runs `init` first when the project has no configuration yet.

    Args:
        host: Address to listen on instead of the configured one.
        port: Port to listen on instead of the configured one.

    Raises:
        click.ClickException: When the configuration lists no packages.
    """
    from doctracker.server.app import run

    project_root = Path.cwd()
    if not (project_root / CONFIG_PATH).exists():
        _initialize(project_root)
    config = load_config(project_root)
    if host:
        config.host = host
    if port:
        config.port = port
    if not config.packages:
        raise click.ClickException(f"No packages to document. Add them to {CONFIG_PATH.as_posix()}.")
    _write_integrations(project_root, config)
    click.echo(f"Wiki: {_base_url(config)}/")
    click.echo(f"MCP:  {_base_url(config)}/mcp")
    run(project_root, config)


@main.command(hidden=True)
@click.argument("event")
@click.option("--url", help="Address of the server, as `start` wrote it; by default the one in the configuration.")
def hook(event: str, url: str | None) -> None:
    """Answer a Claude Code hook: read its event on stdin, print the context of that moment.

    \f
    Never fails: a hook that cannot answer prints nothing, so the agent goes on.

    Args:
        event: The Claude Code event the hook was set for (the event's own name is read from stdin).
        url: The server, e.g. `http://127.0.0.1:8765`; None reads it from the configuration.
    """
    try:
        received = json.loads(sys.stdin.read() or "{}")
        received.setdefault("hook_event_name", event)
        project_root = Path(received.get("cwd") or Path.cwd())
        if not (project_root / CONFIG_PATH).exists():
            return
        reply = claude_code.answer(received, url or _base_url(load_config(project_root)))
    except (OSError, ValueError):
        return
    if reply:
        click.echo(json.dumps(reply))


def _base_url(config: Config) -> str:
    """The address of the server, e.g. `http://127.0.0.1:8765`."""
    return f"{'https' if config.ssl_certfile else 'http'}://{config.host}:{config.port}"


def _initialize(project_root: Path) -> None:
    """Write a default configuration with the packages found in the project, and the agents' integrations.

    Args:
        project_root: Root of the project to configure.
    """
    config = Config()
    config.packages = detect_packages(project_root, config.search_paths)
    write_config(project_root, config)
    found = ", ".join(config.packages) or "none (edit the file to add them)"
    click.echo(f"Created {CONFIG_PATH.as_posix()}. Packages: {found}")
    _write_integrations(project_root, config)


def _write_integrations(project_root: Path, config: Config) -> None:
    """Write the Claude Code hooks and, when OpenCode is used, its plugin; print where they went.

    Args:
        project_root: Root of the project.
        config: The configuration, for the server's address.
    """
    settings = claude_code.write_settings(project_root, _base_url(config))
    click.echo(f"Claude Code hooks: {settings.relative_to(project_root).as_posix()}")
    if opencode.uses_opencode(project_root):
        plugin = opencode.write_plugin(project_root, _base_url(config))
        click.echo(f"OpenCode plugin: {plugin.relative_to(project_root).as_posix()}")
