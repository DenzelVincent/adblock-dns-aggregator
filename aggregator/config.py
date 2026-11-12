"""配置加载与校验。配置是唯一事实来源，缺字段直接报错而不是猜默认值。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .parse import FORMATS, normalize_domain

TIERS = ("lite", "full", "cn")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    fold: bool
    concurrency: int
    timeout: float
    retries: int
    min_retain_ratio: float


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    format: str
    tiers: tuple[str, ...]
    license: str
    enabled: bool


def _load_yaml(path: Path, label: str):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"{label} 读取失败: {exc}") from exc
    if data is None:
        raise ConfigError(f"{label} 内容为空")
    return data


def load_config(path: Path) -> Config:
    data = _load_yaml(path, "config.yaml")
    if not isinstance(data, dict):
        raise ConfigError("config.yaml 顶层必须是映射")

    for key in ("fold", "concurrency", "timeout", "retries", "sentinel"):
        if key not in data:
            raise ConfigError(f"config.yaml 缺少字段 {key}")

    fold = data["fold"]
    concurrency = data["concurrency"]
    timeout = data["timeout"]
    retries = data["retries"]
    sentinel = data["sentinel"]

    if not isinstance(fold, bool):
        raise ConfigError("fold 必须是布尔值")
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency < 1:
        raise ConfigError("concurrency 必须是正整数")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ConfigError("timeout 必须是正数")
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise ConfigError("retries 必须是非负整数")
    if not isinstance(sentinel, dict) or "min_retain_ratio" not in sentinel:
        raise ConfigError("config.yaml 缺少 sentinel.min_retain_ratio")
    ratio = sentinel["min_retain_ratio"]
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not 0 < ratio <= 1:
        raise ConfigError("sentinel.min_retain_ratio 必须在 (0, 1] 区间")

    return Config(
        fold=fold,
        concurrency=concurrency,
        timeout=timeout,
        retries=retries,
        min_retain_ratio=float(ratio),
    )


def load_sources(path: Path) -> list[Source]:
    data = _load_yaml(path, "sources.yaml")
    if not isinstance(data, list) or not data:
        raise ConfigError("sources.yaml 必须是非空列表")

    sources: list[Source] = []
    seen: set[str] = set()
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"sources.yaml 第 {index} 项必须是映射")
        for key in ("name", "url", "format", "tiers"):
            if not item.get(key):
                raise ConfigError(f"sources.yaml 第 {index} 项缺少 {key}")
        name = str(item["name"]).strip()
        if name in seen:
            raise ConfigError(f"sources.yaml 源名重复: {name}")
        seen.add(name)

        fmt = str(item["format"]).strip().lower()
        if fmt not in FORMATS:
            raise ConfigError(f"源 {name} 的 format 未知: {fmt}")

        tiers_value = item["tiers"]
        if not isinstance(tiers_value, list) or not tiers_value:
            raise ConfigError(f"源 {name} 的 tiers 必须是非空列表")
        tiers = tuple(dict.fromkeys(str(tier).strip() for tier in tiers_value))
        for tier in tiers:
            if tier not in TIERS:
                raise ConfigError(f"源 {name} 的 tier 未知: {tier}")

        license_name = str(item.get("license") or "").strip()
        if not license_name:
            raise ConfigError(f"源 {name} 缺少 license 字段")

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"源 {name} 的 enabled 必须是布尔值")

        url = str(item["url"]).strip()
        if not url:
            raise ConfigError(f"源 {name} 的 url 为空")

        sources.append(
            Source(
                name=name,
                url=url,
                format=fmt,
                tiers=tiers,
                license=license_name,
                enabled=enabled,
            )
        )
    return sources


def load_whitelist(path: Path) -> set[str]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"whitelist.txt 读取失败: {exc}") from exc

    domains: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#!":
            continue
        domain = normalize_domain(line)
        if domain:
            domains.add(domain)
    return domains
