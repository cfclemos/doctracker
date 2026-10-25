"""Embedding backend, used only when something needs it.

Backend order: the vLLM server at `embeddings.vllm_url` when it is set (external, never
managed), otherwise a `llama-server` managed here. The managed server is downloaded and
started on first use, and stopped after `embeddings.idle_timeout` seconds without use.
"""

import asyncio
import os
import platform
import time
from collections.abc import Callable
from pathlib import Path

import httpx2
import numpy as np

from doctracker.config import DATABASE_PATH, Config, models_dir
from doctracker.embeddings import llama_cpp
from doctracker.embeddings.downloads import download
from doctracker.storage.index import SearchIndex
from doctracker.server.state import DocState

HUGGING_FACE = "https://huggingface.co"
"""Where `owner/repo/file.gguf` models are downloaded from."""

BATCH_SIZE = 16
"""Texts sent to the embedding server per request."""

HEALTH_TIMEOUT = 180.0
"""Seconds to wait for a starting llama-server before trying the next build."""

IDLE_CHECK_SECONDS = 15.0
"""Seconds between checks of how long the managed llama-server has been idle."""

CONTEXT_TOKENS = "8192"
"""Context size (and batch size) of the managed llama-server, in tokens."""


class EmbeddingService:
    """Prepares the embedding backend on demand, embeds texts and keeps the entity index up to date.

    Args:
        project_root: Root of the documented project.
        config: Project settings, shared with the rest of the server.
        state: Extracted entities, shared with the rest of the server.

    Attributes:
        project_root: Root of the documented project.
        config: Project settings; `config.embeddings` is read on every use, so changes apply right away.
        state: Extracted entities, the source of the index.
        index: BM25 and vector indexes of the entities, in `doc/sqlite/doctracker.db`.
        process: The managed llama-server, while it runs.
        build: The llama.cpp build in use, once one has started.
        ready: Whether texts can be embedded right now.
        step: What the service is doing (e.g. `downloading model 45%`), shown by `status()`.
        error: Last preparation error; the next request tries again.
        last_used: Monotonic time of the last use, for the idle timeout.
        _preparing: Background task preparing the backend and building the index, if any.
        _lock: Keeps index updates from running at the same time.
    """

    def __init__(self, project_root: Path, config: Config, state: DocState) -> None:
        self.project_root = project_root
        self.config = config
        self.state = state
        self.index = SearchIndex(project_root / DATABASE_PATH)
        self.process: asyncio.subprocess.Process | None = None
        self.build: llama_cpp.Build | None = None
        self.ready = False
        self.step = "idle"
        self.error = ""
        self.last_used = time.monotonic()
        self._preparing: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # Settings --------------------------------------------------------------

    @property
    def uses_vllm(self) -> bool:
        """Whether embeddings come from the vLLM server in `embeddings.vllm_url` (takes precedence over llama.cpp)."""
        return bool(self.config.embeddings.vllm_url)

    @property
    def model_id(self) -> str:
        """Identifies the vectors: changing the backend model invalidates the index."""
        settings = self.config.embeddings
        return f"vllm:{settings.vllm_model}" if self.uses_vllm else f"llama.cpp:{settings.model}"

    @property
    def models_dir(self) -> Path:
        """Folder for models and llama.cpp binaries (`embeddings.models_dir`, or `doc/models`)."""
        return models_dir(self.project_root, self.config)

    def status(self) -> dict:
        """Describe the backend for the `embedding_status` tool.

        Returns:
            State (`idle`, a progress step, `ready` or `error`), error, backend, model, device,
            llama.cpp build, models folder, whether the server runs, and index size.
        """
        settings = self.config.embeddings
        return {
            "state": "ready" if self.ready else ("error" if self.error else self.step),
            "error": self.error,
            "backend": "vllm" if self.uses_vllm else "llama.cpp",
            "model": settings.vllm_model if self.uses_vllm else settings.model,
            "device": settings.device,
            "build": self.build.variant if self.build else None,
            "models_dir": str(self.models_dir),
            "server_running": self.process is not None and self.process.returncode is None,
            "indexed": self.index.count(),
            "entities": len(self.state.entities),
        }

    # Lifecycle -------------------------------------------------------------

    def start_preparing(self) -> None:
        """Prepare the backend and build the index in the background, if not already doing so."""
        if self.ready or (self._preparing and not self._preparing.done()):
            return
        self.error = ""
        self._preparing = asyncio.create_task(self._prepare_and_index())

    async def ensure_ready(self, wait: float) -> bool:
        """Start preparing if needed and wait a limited time for it to finish.

        Downloads can take minutes, so callers get an answer quickly and can ask again later.

        Args:
            wait: Maximum seconds to wait for the preparation (download, start, indexing).

        Returns:
            True when the backend is ready and the index is built.
        """
        self.start_preparing()
        if self._preparing and not self._preparing.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._preparing), wait)
            except TimeoutError:
                pass
        return self.ready and not (self._preparing and not self._preparing.done())

    async def _prepare_and_index(self) -> None:
        """Prepare the backend and build the index; errors are kept in `error` for `status()`."""
        try:
            await self._prepare()
            await self.update_index()
            self.step = "ready"
        except Exception as error:  # reported through status(); the next request retries
            self.ready = False
            self.error = f"{type(error).__name__}: {error}"

    async def _prepare(self) -> None:
        """Make the backend ready: nothing to do for vLLM; for llama.cpp, download and start a build.

        Builds are tried in order (CUDA, Vulkan, CPU with `device = "auto"`) until one starts.

        Raises:
            RuntimeError: When no build fits this machine or none of them starts.
            ValueError: When the configured model is neither a local file nor a Hugging Face file.
        """
        if self.uses_vllm:
            self.ready = True
            return
        model = await self._ensure_model()
        self.step = "choosing llama.cpp build"
        builds = await llama_cpp.candidate_builds(self.config.embeddings.device, self.config.embeddings.llama_cpp_release)
        if not builds:
            raise RuntimeError(f"No llama.cpp build for device '{self.config.embeddings.device}' on this machine")
        failures = []
        for build in builds:
            executable = await llama_cpp.install(build, self.models_dir, self._progress(f"downloading llama.cpp {build.variant}"))
            self.step = f"starting llama-server ({build.variant})"
            if await self._start_server(executable, model, build):
                self.build = build
                self.ready = True
                return
            failures.append(build.variant)
        raise RuntimeError(f"llama-server did not start with: {', '.join(failures)} (see llama.cpp/llama-server.log in the models folder)")

    async def _ensure_model(self) -> Path:
        """Get the local path of the GGUF model, downloading it from Hugging Face the first time.

        Returns:
            The model file: the configured local file, or the copy in the models folder.

        Raises:
            ValueError: When the model is neither a local `.gguf` file nor `owner/repo/file.gguf`.
            httpx2.HTTPError: When the download fails.
        """
        spec = self.config.embeddings.model
        local = Path(spec) if Path(spec).is_absolute() else self.project_root / spec
        if local.is_file():
            return local
        parts = spec.split("/")
        if len(parts) < 3 or not spec.endswith(".gguf"):
            raise ValueError(f"Model must be a local .gguf file or 'owner/repo/file.gguf' on Hugging Face: {spec}")
        destination = self.models_dir / parts[-1]
        if not destination.is_file():
            _ignore_in_git(self.models_dir, self.project_root)
            url = f"{HUGGING_FACE}/{parts[0]}/{parts[1]}/resolve/main/{'/'.join(parts[2:])}"
            await download(url, destination, self._progress(f"downloading model {parts[-1]}"))
        return destination

    async def _start_server(self, executable: Path, model: Path, build: llama_cpp.Build) -> bool:
        """Start llama-server and wait until it answers `/health`.

        Its output goes to `llama.cpp/llama-server.log` in the models folder.

        Args:
            executable: The `llama-server` program.
            model: The GGUF model file.
            build: Build being started; GPU builds load the whole model on the GPU.

        Returns:
            True when the server is up; False when it exited or did not answer in `HEALTH_TIMEOUT` seconds.
        """
        settings = self.config.embeddings
        args = [
            str(executable), "-m", str(model), "--embedding", "--pooling", "last",
            "--host", "127.0.0.1", "--port", str(settings.port),
            "-c", CONTEXT_TOKENS, "-b", CONTEXT_TOKENS, "-ub", CONTEXT_TOKENS, "-np", "1",
            "-ngl", "99" if build.uses_gpu else "0",
        ]
        log_folder = self.models_dir / "llama.cpp"
        log_folder.mkdir(parents=True, exist_ok=True)
        _ignore_in_git(self.models_dir, self.project_root)
        log = (log_folder / "llama-server.log").open("ab")
        self.process = await asyncio.create_subprocess_exec(*args, stdout=log, stderr=log, env=_server_env(executable.parent))
        log.close()
        deadline = time.monotonic() + HEALTH_TIMEOUT
        async with httpx2.AsyncClient(timeout=5.0) as client:
            while time.monotonic() < deadline:
                if self.process.returncode is not None:
                    break
                try:
                    if (await client.get(f"http://127.0.0.1:{settings.port}/health")).status_code == 200:
                        self.last_used = time.monotonic()
                        return True
                except httpx2.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        await self.stop()
        return False

    async def stop(self) -> None:
        """Stop the managed llama-server, if running."""
        process, self.process = self.process, None
        self.ready = self.uses_vllm
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except TimeoutError:
                process.kill()

    async def reset(self) -> None:
        """Apply new settings: stop the server; the next request prepares everything again."""
        if self._preparing and not self._preparing.done():
            self._preparing.cancel()
        await self.stop()
        self.ready = False
        self.build = None
        self.step = "idle"
        self.error = ""

    async def stop_when_idle(self) -> None:
        """Background loop: stop the managed server after `idle_timeout` seconds without use."""
        while True:
            await asyncio.sleep(IDLE_CHECK_SECONDS)
            idle = time.monotonic() - self.last_used
            if self.process is not None and idle > self.config.embeddings.idle_timeout:
                await self.stop()
                self.step = "stopped after idle timeout"

    def _progress(self, label: str) -> Callable[[int, int], None]:
        """Make a download progress callback that shows `label` and the percentage in `step`.

        Args:
            label: What is being downloaded, e.g. `downloading model x.gguf`.

        Returns:
            Callback taking the bytes done and the total size.
        """

        def report(done: int, total: int) -> None:
            percent = f" {100 * done / total:.0f}%" if total else f" {done / 1e6:.0f} MB"
            self.step = label + percent
        return report

    # Embeddings and search -------------------------------------------------

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Turn texts into vectors with the backend (vLLM or llama-server).

        Args:
            texts: Texts to embed; they are sent in batches of `BATCH_SIZE`.

        Returns:
            One row per text, normalized to length 1.

        Raises:
            httpx2.HTTPError: When the backend cannot be reached or answers with an error.
        """
        settings = self.config.embeddings
        base = settings.vllm_url.rstrip("/") if self.uses_vllm else f"http://127.0.0.1:{settings.port}"
        name = settings.vllm_model if self.uses_vllm else Path(settings.model).name
        rows = []
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(30.0, read=600.0)) as client:
            for start in range(0, len(texts), BATCH_SIZE):
                response = await client.post(f"{base}/v1/embeddings", json={"input": texts[start : start + BATCH_SIZE], "model": name})
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                rows.extend(item["embedding"] for item in data)
                self.last_used = time.monotonic()
        vectors = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    async def update_index(self) -> None:
        """Embed the entities that are new or changed since the last update."""
        async with self._lock:
            self.index.update_texts(self.state.entities)
            await self.index.update_vectors(self.model_id, self.embed, self._index_progress)

    def _index_progress(self, done: int, total: int) -> None:
        """Show the indexing progress in `step`.

        Args:
            done: Entities indexed so far.
            total: Entities to index.
        """
        self.step = f"indexing {done}/{total}"

    async def embed_query(self, query: str) -> np.ndarray:
        """Turn a search query into a vector, with `embeddings.query_instruction` before it.

        Args:
            query: Question or description.

        Returns:
            The normalized vector of the query.
        """
        return (await self.embed([self.config.embeddings.query_instruction + query]))[0]


def _server_env(binary_dir: Path) -> dict[str, str]:
    """Build the environment for llama-server: its own folder (and CUDA's, on Windows) on the library path.

    Args:
        binary_dir: Folder of the `llama-server` executable and its libraries.

    Returns:
        A copy of the current environment with the library path extended.
    """
    env = os.environ.copy()
    if platform.system() == "Windows":
        extra = [str(binary_dir)] + [os.path.join(v, "bin") for k, v in os.environ.items() if k.startswith("CUDA_PATH")]
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    else:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, [str(binary_dir), env.get("LD_LIBRARY_PATH")]))
    return env


def _ignore_in_git(folder: Path, project_root: Path) -> None:
    """Keep a data folder inside the project out of git with its own `.gitignore`.

    Folders outside the project are left untouched.

    Args:
        folder: Data folder (models, index...); created if needed.
        project_root: Root of the documented project.
    """
    try:
        folder.resolve().relative_to(project_root.resolve())
    except ValueError:
        return
    folder.mkdir(parents=True, exist_ok=True)
    gitignore = folder / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
