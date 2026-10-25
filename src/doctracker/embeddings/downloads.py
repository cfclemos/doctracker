"""Download files with progress reporting and extract archives."""

import asyncio
import os
import stat
import tarfile
import zipfile
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import httpx2

CHUNK_SIZE = 1 << 20
"""Bytes read per step while downloading (1 MiB)."""


async def download(url: str, destination: Path, on_progress: Callable[[int, int], None]) -> None:
    """Download `url` to `destination`, calling `on_progress(done, total)` as bytes arrive.

    The file is written to `<destination>.part` and renamed at the end, so an
    interrupted download never leaves a truncated file behind.

    Args:
        url: Address of the file; redirects are followed.
        destination: Final path of the file; its folder is created if needed.
        on_progress: Called with the bytes received so far and the total size (0 when unknown).

    Raises:
        httpx2.HTTPError: When the request fails or the server answers with an error.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    async with httpx2.AsyncClient(follow_redirects=True, timeout=httpx2.Timeout(30.0, read=120.0)) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            done = 0
            with partial.open("wb") as file:
                async for chunk in response.aiter_bytes(CHUNK_SIZE):
                    file.write(chunk)
                    done += len(chunk)
                    on_progress(done, total)
    os.replace(partial, destination)


async def get_json(url: str) -> object:
    """Fetch a JSON document.

    Args:
        url: Address of the document.

    Returns:
        The decoded JSON (a dict or a list).

    Raises:
        httpx2.HTTPError: When the request fails or the server answers with an error.
    """
    async with httpx2.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()


async def extract(archive: Path, destination: Path) -> None:
    """Extract a `.zip` or `.tar.gz` archive in a separate process, so the server stays responsive.

    Args:
        archive: The archive file.
        destination: Folder to extract into; created if needed.
    """
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=1) as executor:
        await loop.run_in_executor(executor, extract_archive, str(archive), str(destination))


def extract_archive(archive: str, destination: str) -> None:
    """Extract an archive and make the extracted files executable on POSIX systems.

    Runs in a worker process, so it takes strings instead of paths.

    Args:
        archive: Path of a `.zip` or `.tar.gz` file.
        destination: Folder to extract into; created if needed.
    """
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(target)
    else:
        with tarfile.open(archive) as tarred:
            try:
                tarred.extractall(target, filter="data")
            except TypeError:  # Python < 3.11.4 has no extraction filters
                tarred.extractall(target)
    if os.name == "posix":
        for path in target.rglob("*"):
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
