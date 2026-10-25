"""Pick and install the llama.cpp build that fits this machine.

With `device = "auto"` the order is: CUDA (NVIDIA GPU with the CUDA runtime installed
on the system), Vulkan (any other compatible GPU), CPU. doctracker never downloads
NVIDIA's CUDA libraries; it only uses the ones already installed.
"""

import glob
import os
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from doctracker.embeddings.downloads import download, extract, get_json

RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"
"""GitHub API endpoint listing the llama.cpp releases and their binaries."""

ASSET_PATTERN = re.compile(r"^llama-[^-]+-bin-(ubuntu|win)-(?:(.+)-)?(x64|arm64)\.(?:tar\.gz|zip)$")
"""Name of a llama.cpp binary archive; groups: operating system, variant (none for Linux CPU), architecture."""


@dataclass
class Build:
    """One downloadable llama.cpp build.

    Attributes:
        release: Release tag, e.g. `b11887`.
        backend: `cuda`, `vulkan` or `cpu`.
        variant: Variant in the asset name, e.g. `cuda-13.4`, `vulkan` or `cpu`.
        name: Asset file name.
        url: Download URL.
    """

    release: str
    backend: str
    variant: str
    name: str
    url: str

    @property
    def uses_gpu(self) -> bool:
        """Whether the model should be loaded on the GPU (every backend except `cpu`)."""
        return self.backend != "cpu"


def platform_tokens() -> tuple[str, str]:
    """Operating system and architecture as they appear in llama.cpp asset names."""
    system = "win" if platform.system() == "Windows" else "ubuntu"
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    return system, arch


async def release_assets(release: str) -> tuple[str, list[dict]]:
    """Look up the downloadable files of a llama.cpp release on GitHub.

    Args:
        release: Release tag (e.g. `b11887`), or `latest` for the newest release that has binaries.

    Returns:
        The release tag and its assets, as returned by the GitHub API.

    Raises:
        RuntimeError: When `latest` is asked and no recent release has binaries.
        httpx2.HTTPError: When GitHub cannot be reached or the tag does not exist.
    """
    if release != "latest":
        data = await get_json(f"{RELEASES_API}/tags/{release}")
        return data["tag_name"], data["assets"]
    for data in await get_json(f"{RELEASES_API}?per_page=10"):
        if len(data["assets"]) > 3:
            return data["tag_name"], data["assets"]
    raise RuntimeError("No llama.cpp release with binaries found")


async def candidate_builds(device: str, release: str) -> list[Build]:
    """List the builds to try on this machine, best first.

    Args:
        device: `auto` (CUDA, then Vulkan, then CPU), `cuda`, `vulkan` or `cpu`.
        release: Release tag, or `latest`.

    Returns:
        Builds for this operating system and architecture that the machine can run; may be empty.
    """
    tag, assets = await release_assets(release)
    system, arch = platform_tokens()
    builds: dict[str, list[Build]] = {"cuda": [], "vulkan": [], "cpu": []}
    for asset in assets:
        match = ASSET_PATTERN.match(asset["name"])
        if not match or match.group(1) != system or match.group(3) != arch:
            continue
        variant = match.group(2) or "cpu"
        backend = "cuda" if variant.startswith("cuda-") else variant
        if backend in builds:
            builds[backend].append(Build(tag, backend, variant, asset["name"], asset["browser_download_url"]))

    order = {"auto": ["cuda", "vulkan", "cpu"]}.get(device, [device])
    candidates = []
    for backend in order:
        if backend == "cuda":
            build = _best_cuda_build(builds["cuda"])
            if build:
                candidates.append(build)
        elif backend == "vulkan" and vulkan_available() and builds["vulkan"]:
            candidates.append(builds["vulkan"][0])
        elif backend == "cpu" and builds["cpu"]:
            candidates.append(builds["cpu"][0])
    return candidates


def _best_cuda_build(builds: list[Build]) -> Build | None:
    """Pick the newest CUDA build that the driver supports and whose runtime is installed.

    Args:
        builds: CUDA builds of the release, for this platform.

    Returns:
        The build, or `None` without an NVIDIA GPU, without the CUDA runtime, or when none fits.
    """
    driver = nvidia_cuda_version()
    runtimes = cuda_runtime_majors()
    if driver is None or not runtimes:
        return None
    usable = []
    for build in builds:
        version = _version(build.variant.removeprefix("cuda-"))
        if version[0] in runtimes and version <= driver:
            usable.append((version, build))
    return max(usable, key=lambda pair: pair[0])[1] if usable else None


def nvidia_cuda_version() -> tuple[int, ...] | None:
    """Highest CUDA version supported by the NVIDIA driver, or `None` without an NVIDIA GPU."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        output = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"CUDA (?:UMD )?Version:\s*([\d.]+)", output)
    return _version(match.group(1)) if match else None


def cuda_runtime_majors() -> set[int]:
    """Major versions of the CUDA runtime (`cudart`) installed on the system."""
    majors = set()
    if platform.system() == "Windows":
        roots = [value for key, value in os.environ.items() if key.startswith("CUDA_PATH")]
        for root in roots:
            for dll in glob.glob(os.path.join(root, "**", "cudart64_*.dll"), recursive=True):
                digits = re.search(r"cudart64_(\d+)", dll).group(1)
                majors.add(int(digits[:2]) if len(digits) > 2 else int(digits))
        return majors
    for line in _ldconfig():
        match = re.search(r"libcudart\.so\.(\d+)", line)
        if match:
            majors.add(int(match.group(1)))
    for pattern in ("/usr/local/cuda*/lib64/libcudart.so.*", "/opt/cuda/lib64/libcudart.so.*"):
        for path in glob.glob(pattern):
            match = re.search(r"libcudart\.so\.(\d+)", path)
            if match:
                majors.add(int(match.group(1)))
    return majors


def vulkan_available() -> bool:
    """Whether the Vulkan loader is installed (needed by the Vulkan build)."""
    if platform.system() == "Windows":
        return (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "vulkan-1.dll").exists()
    return any("libvulkan.so.1" in line for line in _ldconfig()) or bool(glob.glob("/usr/lib*/libvulkan.so.1"))


def _ldconfig() -> list[str]:
    """List the shared libraries known to the system linker (Linux); empty if `ldconfig` is unavailable."""
    try:
        return subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, timeout=15).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def _version(text: str) -> tuple[int, ...]:
    """Turn a version such as `13.4` into a tuple that compares numerically, e.g. `(13, 4)`.

    Args:
        text: Dotted version number.

    Returns:
        The numeric parts of the version.
    """
    return tuple(int(part) for part in text.split(".") if part.isdigit())


def server_executable(folder: Path) -> Path | None:
    """Find the `llama-server` executable inside an extracted build.

    Args:
        folder: Folder the build was extracted into.

    Returns:
        Path of the executable, or `None` when the folder does not exist or has no executable.
    """
    name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    found = sorted(folder.rglob(name)) if folder.is_dir() else []
    return found[0] if found else None


async def install(build: Build, models_dir: Path, on_progress: Callable[[int, int], None]) -> Path:
    """Download and extract a build into `<models_dir>/llama.cpp/<release>-<variant>/`, once.

    Args:
        build: Build to install.
        models_dir: Folder for models and llama.cpp binaries.
        on_progress: Called with the bytes downloaded so far and the total size.

    Returns:
        Path of the `llama-server` executable.

    Raises:
        RuntimeError: When the archive has no `llama-server`.
        httpx2.HTTPError: When the download fails.
    """
    folder = models_dir / "llama.cpp" / f"{build.release}-{build.variant}"
    executable = server_executable(folder)
    if executable:
        return executable
    archive = models_dir / "llama.cpp" / build.name
    await download(build.url, archive, on_progress)
    await extract(archive, folder)
    archive.unlink(missing_ok=True)
    executable = server_executable(folder)
    if executable is None:
        raise RuntimeError(f"llama-server not found in {build.name}")
    return executable
