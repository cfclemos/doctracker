"""Command line interface: `doctracker init`, `start`, `restart` and `hook` (called by Claude Code and Codex)."""

import json
import sys
from pathlib import Path

import click

from doctracker import __version__
from doctracker.config import (CONFIG_PATH, Config, ensure_gitignore, free_ports, load_config, port_free,
                               project_files, write_config)
from doctracker.extraction.languages import LANGUAGES, NO_SOURCES, language_of
from doctracker.integrations import autostart, claude_code, codex, opencode


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

    The code is found in the source folders (`src/`, `packages/*/src/`, `package/*/src/`); without
    any, the server still starts and says there is nothing to document.

    Raises:
        click.ClickException: When the port is in use.
    """
    from doctracker.server.app import run

    project_root = Path.cwd()
    if not (project_root / CONFIG_PATH).exists():
        _initialize(project_root)
    config = load_config(project_root)
    ensure_gitignore(project_root)
    if host:
        config.host = host
    if port:
        config.port = port
    if not port_free(config.host, config.port):
        raise click.ClickException(
            f"Port {config.port} is in use, by this project's server already running or by another program. "
            f"Choose another `port` in {CONFIG_PATH.as_posix()} (or use --port).")
    _echo_sources(project_root)
    _write_integrations(project_root, config)
    click.echo(f"Wiki: {_base_url(config)}/")
    click.echo(f"MCP:  {_base_url(config)}/mcp")
    autostart.record_server(project_root, _base_url(config))
    run(project_root, config)


@main.command()
def restart() -> None:
    """Stop the server of the current project and start it again in the background.

    \f
    The new server listens on the address of the one stopped (or the configured one when none was
    running) and writes its output to `doc/logs/server.log`.

    Raises:
        click.ClickException: When the project has no configuration, or the server does not stop or start.
    """
    project_root = Path.cwd()
    if not (project_root / CONFIG_PATH).exists():
        raise click.ClickException(f"No {CONFIG_PATH.as_posix()} here: run `doctracker start` first.")
    base_url = autostart.stop_server(project_root) or _base_url(load_config(project_root))
    if autostart.answers(base_url):
        raise click.ClickException(f"A server still answers at {base_url}; stop it by hand.")
    if not autostart.ensure_server(project_root, base_url):
        raise click.ClickException(f"The server did not start; see {autostart.LOG_PATH.as_posix()}.")
    click.echo(f"Wiki: {base_url}/")
    click.echo(f"MCP:  {base_url}/mcp")
    click.echo(f"Log:  {autostart.LOG_PATH.as_posix()}")


@main.command(hidden=True)
@click.argument("event")
@click.option("--url", help="Address of the server, as `start` wrote it; by default the one in the configuration.")
def hook(event: str, url: str | None) -> None:
    """Answer a Claude Code or Codex hook: read its event on stdin, print the context of that moment.

    \f
    Never fails: a hook that cannot answer prints nothing, so the agent goes on.

    Args:
        event: The event the hook was set for (the event's own name is read from stdin).
        url: The server, e.g. `http://127.0.0.1:8765`; None reads it from the configuration.
    """
    try:
        received = json.loads(sys.stdin.read() or "{}")
        received.setdefault("hook_event_name", event)
        project_root = Path(received.get("cwd") or Path.cwd())
        if not (project_root / CONFIG_PATH).exists():
            return
        reply = claude_code.answer(received, url or _base_url(load_config(project_root)), project_root)
    except (OSError, ValueError):
        return
    if reply:
        click.echo(json.dumps(reply))


def _base_url(config: Config) -> str:
    """The address of the server, e.g. `http://127.0.0.1:8765`."""
    return f"{'https' if config.ssl_certfile else 'http'}://{config.host}:{config.port}"


def _initialize(project_root: Path) -> None:
    """Write a default configuration, on free ports, and the agents' integrations; tell what code will be read.

    Args:
        project_root: Root of the project to configure.
    """
    config = Config()
    free_ports(config)
    write_config(project_root, config)
    click.echo(f"Created {CONFIG_PATH.as_posix()}.")
    _echo_sources(project_root)
    _write_integrations(project_root, config)


def _echo_sources(project_root: Path) -> None:
    """Print how many files of each language will be read, or `NO_SOURCES` when there are none."""
    counts: dict[str, int] = {}
    for file in project_files(project_root):
        if language := language_of(file):
            counts[language] = counts.get(language, 0) + 1
    if not counts:
        before, title, after, advice = NO_SOURCES
        click.echo(f"Nothing to document. {before}\n{title}")
        for language in LANGUAGES.values():
            click.echo(f"  - {language['label']}: {', '.join(language['suffixes'])}")
        click.echo(after)
        click.echo(click.style(advice, bold=True))
        return
    click.echo("Files read: " + ", ".join(f"{LANGUAGES[name]['label']} {counts[name]}"
                                          for name in LANGUAGES if name in counts))


def _write_integrations(project_root: Path, config: Config) -> None:
    """Write the Claude Code and Codex hooks and MCP servers, and the OpenCode plugin when used; print where they went.

    Args:
        project_root: Root of the project.
        config: The configuration, for the server's address.
    """
    settings = claude_code.write_settings(project_root, _base_url(config))
    click.echo(f"Claude Code hooks: {settings.relative_to(project_root).as_posix()}")
    mcp_config = claude_code.write_mcp_config(project_root, _base_url(config))
    click.echo(f"Claude Code MCP server: {mcp_config.relative_to(project_root).as_posix()}")
    codex_hooks = codex.write_hooks(project_root, _base_url(config))
    click.echo(f"Codex hooks: {codex_hooks.relative_to(project_root).as_posix()}")
    codex_config = codex.write_mcp_config(project_root, _base_url(config))
    click.echo(f"Codex MCP server: {codex_config.relative_to(project_root).as_posix()}")
    if opencode.uses_opencode(project_root):
        plugin = opencode.write_plugin(project_root, _base_url(config))
        click.echo(f"OpenCode plugin: {plugin.relative_to(project_root).as_posix()}")
