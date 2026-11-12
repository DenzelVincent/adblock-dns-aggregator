"""并发下载。单源失败只记录，不中断整轮；发布前的哨兵负责拦住整体异常。"""

from __future__ import annotations

import gzip
import hashlib
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .config import Config, Source

logger = logging.getLogger(__name__)

USER_AGENT = (
    "adblock-dns-aggregator/1.0 "
    "(+https://github.com/DenzelVincent/adblock-dns-aggregator)"
)


@dataclass
class FetchResult:
    name: str
    status: str
    text: str
    nbytes: int
    sha256: str
    duration_ms: int
    error: str = ""


def fetch_source(source: Source, config: Config) -> FetchResult:
    started = time.monotonic()
    last_error = ""
    for attempt in range(config.retries + 1):
        try:
            request = urllib.request.Request(
                source.url,
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            )
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                data = response.read()
                encoding = response.headers.get("Content-Encoding", "")
            if encoding == "gzip" or data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "源下载完成 name=%s bytes=%d duration_ms=%d",
                source.name,
                len(data),
                duration_ms,
            )
            return FetchResult(
                name=source.name,
                status="ok",
                text=data.decode("utf-8", errors="replace"),
                nbytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                duration_ms=duration_ms,
            )
        except Exception as exc:  # 网络边界：任何异常都只算该源失败
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "源下载失败 name=%s attempt=%d/%d error=%s",
                source.name,
                attempt + 1,
                config.retries + 1,
                last_error,
            )
            if attempt < config.retries:
                time.sleep(min(2**attempt, 5))

    return FetchResult(
        name=source.name,
        status="failed",
        text="",
        nbytes=0,
        sha256=hashlib.sha256(b"").hexdigest(),
        duration_ms=int((time.monotonic() - started) * 1000),
        error=last_error,
    )


def fetch_all(sources: list[Source], config: Config) -> list[FetchResult]:
    if not sources:
        return []
    workers = max(1, min(config.concurrency, len(sources)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # map 保序，manifest 与源清单顺序一致
        return list(pool.map(lambda source: fetch_source(source, config), sources))
