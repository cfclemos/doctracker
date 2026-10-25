"""Load and write the doctracker configuration (`doc/config/config.json`)."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DOC_DIR = "doc"
"""Folder, inside the documented project, where doctracker keeps everything it creates."""

CONFIG_PATH = Path(DOC_DIR) / "config" / "config.json"
"""Configuration file, relative to the project root. Meant to be committed."""

GITIGNORE_PATH = Path(DOC_DIR) / ".gitignore"
"""`.gitignore` written by `init` to keep local data out of git."""

GITIGNORE_CONTENT = "sqlite/\nmodels/\n"
"""Local data folders ignored by `doc/.gitignore`."""

DATABASE_PATH = Path(DOC_DIR) / "sqlite" / "doctracker.db"
"""Local database with the search indexes (BM25 and embedding vectors), relative to the project root."""

DEFAULT_MODELS_DIR = Path(DOC_DIR) / "models"
"""Where models and the llama.cpp binaries go when `embeddings.models_dir` is not set."""

QWEN3_QUERY_INSTRUCTION = (
    "Instruct: Given a question about a Python codebase, retrieve the module, class, function "
    "or attribute whose documentation answers it\nQuery: "
)
"""Prefix added to search queries; Qwen3-Embedding is trained to use an instruction like this."""


@dataclass
class EmbeddingsConfig:
    """Settings of the embedding model used by semantic search.

    The backend is chosen in this order: the vLLM server at `vllm_url` when it is set,
    otherwise a `llama-server` (llama.cpp) managed by doctracker.

    Attributes:
        vllm_url: Base URL of a running vLLM server (e.g. `http://127.0.0.1:8000`). Takes precedence over llama.cpp.
        vllm_model: Name of the model served by vLLM.
        model: GGUF model for llama.cpp: `owner/repo/file.gguf` on Hugging Face, or a local file path.
        models_dir: Folder for models and llama.cpp binaries; `null` means `doc/models`.
        device: `auto` (CUDA, then another GPU through Vulkan, then CPU), `cuda`, `vulkan` or `cpu`.
        llama_cpp_release: llama.cpp release to download (e.g. `b11887`), or `latest`.
        port: Port of the managed `llama-server`.
        idle_timeout: Seconds without use before the managed `llama-server` is stopped.
        query_instruction: Text added before every search query.
    """

    vllm_url: str | None = None
    vllm_model: str = "Qwen/Qwen3-Embedding-0.6B"
    model: str = "Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf"
    models_dir: str | None = None
    device: str = "auto"
    llama_cpp_release: str = "b11887"
    port: int = 8790
    idle_timeout: float = 600.0
    query_instruction: str = QWEN3_QUERY_INSTRUCTION


@dataclass
class Config:
    """Settings read from `doc/config/config.json`.

    Attributes:
        packages: Top-level packages to document.
        search_paths: Folders where the packages are found, relative to the project root.
        host: Address the server listens on.
        port: Port of the server (wiki and MCP endpoint).
        docstring_style: Docstring style of the project: `google`, `numpy` or `sphinx`.
        show_private: Whether `_private` members appear in the wiki.
        code_theme: Pygments theme of the source code in the wiki.
        ssl_certfile: Certificate file; with `ssl_keyfile`, the server uses HTTPS.
        ssl_keyfile: Private key file of the certificate.
        watch_interval: Seconds between checks for changed files.
        embeddings: Settings of the embedding model used by semantic search.
    """

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
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)


def load_config(project_root: Path) -> Config:
    """Read the config file of a project, filling missing keys with defaults.

    Unknown keys are ignored, so older and newer config files both load.

    Args:
        project_root: Root of the documented project.

    Returns:
        The settings, with `embeddings` as an `EmbeddingsConfig`.

    Raises:
        FileNotFoundError: When the project has no `doc/config/config.json`.
    """
    path = project_root / CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    known = Config.__dataclass_fields__
    values = {key: value for key, value in data.items() if key in known}
    embeddings = values.pop("embeddings", None) or {}
    known_embeddings = EmbeddingsConfig.__dataclass_fields__
    values["embeddings"] = EmbeddingsConfig(**{k: v for k, v in embeddings.items() if k in known_embeddings})
    return Config(**values)


def write_config(project_root: Path, config: Config) -> None:
    """Write the config file and the `doc/.gitignore`.

    Args:
        project_root: Root of the documented project.
        config: Settings to write; every key is written, with its current value.
    """
    path = project_root / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    (project_root / GITIGNORE_PATH).write_text(GITIGNORE_CONTENT, encoding="utf-8")


def update_config_value(project_root: Path, key: str, value: object, section: str | None = None) -> None:
    """Change one key in the config file (optionally inside `section`), keeping the rest as it is on disk.

    Args:
        project_root: Root of the documented project.
        key: Key to change, e.g. `code_theme`.
        value: New value; it must be JSON serializable.
        section: Object holding the key, e.g. `embeddings`; created if missing. `None` means the top level.
    """
    path = project_root / CONFIG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    target = data.setdefault(section, {}) if section else data
    target[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def set_config_value(project_root: Path, config: Config, key: str, value: object, section: str | None = None) -> None:
    """Change a setting in memory and save it in the config file.

    Args:
        project_root: Root of the documented project.
        config: Settings in use by the server; changed in place.
        key: Setting to change, e.g. `code_theme` or, with `section="embeddings"`, `model`.
        value: New value; it must be JSON serializable.
        section: Group of the setting, e.g. `embeddings`; `None` means the top level.
    """
    setattr(getattr(config, section) if section else config, key, value)
    update_config_value(project_root, key, value, section)


def models_dir(project_root: Path, config: Config) -> Path:
    """Resolve the folder for models and llama.cpp binaries.

    Args:
        project_root: Root of the documented project; relative folders are taken from here.
        config: Settings; `embeddings.models_dir` is used when set, `doc/models` otherwise.

    Returns:
        The folder as an absolute path (it may not exist yet).
    """
    folder = Path(config.embeddings.models_dir) if config.embeddings.models_dir else DEFAULT_MODELS_DIR
    return folder if folder.is_absolute() else project_root / folder


def detect_packages(project_root: Path, search_paths: list[str]) -> list[str]:
    """Find top-level Python packages (folders with `__init__.py`) in the search paths.

    Args:
        project_root: Root of the project.
        search_paths: Folders to look in, relative to `project_root` (e.g. `src`, `.`).

    Returns:
        Package names, in the order found, without duplicates.
    """
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
