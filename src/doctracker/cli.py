"""Command line interface: `doctracker init` and `doctracker start`."""

from pathlib import Path

import click

from doctracker import __version__
from doctracker.config import CONFIG_PATH, Config, detect_packages, load_config, write_config


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
    scheme = "https" if config.ssl_certfile else "http"
    click.echo(f"Wiki: {scheme}://{config.host}:{config.port}/")
    click.echo(f"MCP:  {scheme}://{config.host}:{config.port}/mcp")
    run(project_root, config)


def _initialize(project_root: Path) -> None:
    """Write a default configuration with the packages found in the project.

    Args:
        project_root: Root of the project to configure.
    """
    config = Config()
    config.packages = detect_packages(project_root, config.search_paths)
    write_config(project_root, config)
    found = ", ".join(config.packages) or "none (edit the file to add them)"
    click.echo(f"Created {CONFIG_PATH.as_posix()}. Packages: {found}")
