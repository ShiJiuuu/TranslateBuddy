from __future__ import annotations

import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


def download_to(url: str, dst: Path, timeout: float = 600.0, chunk_size: int = 1 << 20) -> Path:
    """流式下载到本地文件。500 MB 的文件不能整块读进内存。"""
    dst = Path(dst)
    with httpx.stream(
        "GET",
        url,
        timeout=httpx.Timeout(timeout, connect=30.0),
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        with dst.open("wb") as handle:
            for chunk in response.iter_bytes(chunk_size):
                handle.write(chunk)
    log.info("downloaded %s (%d bytes)", dst.name, dst.stat().st_size)
    return dst
