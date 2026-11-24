"""并发下载。单源失败只记录，不中断整轮；发布前的哨兵负责拦住整体异常。"""

from __future__ import annotations

import gzip
import hashlib
import logging
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .config import Config, ExtraWhitelistSource, Source
from .parse import normalize_domain

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


def _download(url: str, config: Config, label: str) -> tuple[bytes, str]:
    """带重试的单次下载，返回 (内容, 错误串)；成功时错误串为空。"""
    last_error = ""
    for attempt in range(config.retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
            )
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                data = response.read()
                encoding = response.headers.get("Content-Encoding", "")
            if encoding == "gzip" or data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return data, ""
        except Exception as exc:  # 网络边界：任何异常都只算该源失败
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "下载失败 name=%s attempt=%d/%d error=%s",
                label,
                attempt + 1,
                config.retries + 1,
                last_error,
            )
            if attempt < config.retries:
                time.sleep(min(2**attempt, 5))
    return b"", last_error


def fetch_source(source: Source, config: Config) -> FetchResult:
    started = time.monotonic()
    data, error = _download(source.url, config, source.name)
    duration_ms = int((time.monotonic() - started) * 1000)
    if error:
        return FetchResult(
            name=source.name,
            status="failed",
            text="",
            nbytes=0,
            sha256=hashlib.sha256(b"").hexdigest(),
            duration_ms=duration_ms,
            error=error,
        )
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


def fetch_all(sources: list[Source], config: Config) -> list[FetchResult]:
    if not sources:
        return []
    workers = max(1, min(config.concurrency, len(sources)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # map 保序，manifest 与源清单顺序一致
        return list(pool.map(lambda source: fetch_source(source, config), sources))


# tracker 清单一行一条 URL（http://host:port/announce），主机名在 :// 之后、下一个 : 或 / 之前
_HOST_IN_URL = re.compile(r"^[a-z][a-z0-9+.-]*://(\[[0-9a-fA-F:]+\]|[^/:\[\]]+)")


def _host_of_line(line: str) -> str | None:
    """取出 URL 主机名并归一化；IPv6 字面量、单标签等不可拦形态返回 None。"""
    match = _HOST_IN_URL.match(line)
    if not match:
        return None
    host = match.group(1)
    if host.startswith("["):
        return None  # [2001:db8::1] 是 IPv6 字面量
    return normalize_domain(host)


def fetch_whitelist_extra(
    sources: list[ExtraWhitelistSource], config: Config
) -> tuple[set[str], list[dict]]:
    """拉取白名单补充源并抽出主机名，返回 (域名集合, manifest 记录)。

    单源失败只记 warning 并跳过：白名单少一条只会让该域名继续被拦，
    不该让整轮构建失败；但记录会进 manifest，红了能查到。
    """
    domains: set[str] = set()
    records: list[dict] = []
    for source in sources:
        started = time.monotonic()
        data, error = _download(source.url, config, source.name)
        if error:
            logger.warning("白名单源下载失败 name=%s error=%s", source.name, error)
            records.append(
                {"name": source.name, "status": "failed", "domains": 0, "error": error}
            )
            continue

        text = data.decode("utf-8", errors="replace")
        found = 0
        for line in text.splitlines():
            host = _host_of_line(line.strip())
            if not host:
                continue
            if host not in domains:
                domains.add(host)
                found += 1
        logger.info("白名单源解析完成 name=%s domains=%d", source.name, found)
        records.append(
            {
                "name": source.name,
                "status": "ok",
                "domains": found,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
    return domains, records