"""Load and write the doctracker configuration (`doc/config/config.json`)."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DOC_DIR = "doc"
CONFIG_PATH = Path(DOC_DIR) / "config" / "config.json"
GITIGNORE_PATH = Path(DOC_DIR) / ".gitignore"
GITIGNORE_CONTENT = "sqlite/\nmodels/\n"


@dataclass
class Config:
    """Settings read from `doc/config/config.json`."""

    packages: list[str] = field(default_factory=list)
    search_paths: list[str] = field(default_factory=lambda: ["src", "."])
    host: str = "127.0.0.1"
    port: int = 8765
    docstring_style: str = "google"
    show_private: bool = True
    code_theme: str = "default"
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    watch_interval: float = 1.0


def load_config(project_root: Path) -> Config:
    """Read the config file of a project, filling missing keys with defaults."""
    path = project_root / CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    known = Config.__dataclass_fields__
    return Config(**{key: value for key, value in data.items() if key in known})


def write_config(project_root: Path, config: Config) -> None:
    """Write the config file and the `doc/.gitignore`."""
    path = project_root / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    (project_root / GITIGNORE_PATH).write_text(GITIGNORE_CONTENT, encoding="utf-8")


def update_config_value(project_root: Path, key: str, value) -> None:
    """Change one key in the config file, keeping everything else as it is on disk."""
    path = project_root / CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def detect_packages(project_root: Path, search_paths: list[str]) -> list[str]:
    """Find top-level Python packages (folders with `__init__.py`) in the search paths."""
    packages = []
    for search_path in search_paths:
        base = project_root / search_path
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.name.startswith(".") or child.name == DOC_DIR:
                continue
            if (child / "__init__.py").is_file() and child.name not in packages:
                packages.append(child.name)
    return packages
