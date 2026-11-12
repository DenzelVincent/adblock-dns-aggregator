"""编排：下载 → 解析 → 白名单扣除 → 折叠 → 产物 → manifest → 哨兵。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigError, load_config, load_sources, load_whitelist
from .emit import write_all
from .fetch import fetch_all
from .fold import resolve
from .parse import parse_source

logger = logging.getLogger(__name__)


class SentinelError(Exception):
    pass


def _read_previous_counts(path: Path | None) -> dict[str, int]:
    if path is None or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        item["file"]: int(item["count"])
        for item in data.get("outputs", [])
        if "file" in item and "count" in item
    }


def run(
    config_path: Path,
    sources_path: Path,
    whitelist_path: Path,
    out_dir: Path,
    fold: bool | None = None,
    previous_manifest: Path | None = None,
    generated_at: str | None = None,
) -> dict:
    config = load_config(config_path)
    sources = [source for source in load_sources(sources_path) if source.enabled]
    whitelist = load_whitelist(whitelist_path)

    results = fetch_all(sources, config)
    if sources and not any(result.status == "ok" for result in results):
        raise RuntimeError("所有源均下载失败，拒绝产出空清单")

    exclude = set(whitelist)
    include_lite: set[str] = set()
    include_full: set[str] = set()
    source_records: list[dict] = []

    for source, result in zip(sources, results):
        status = result.status
        include: set[str] = set()
        source_exclude: set[str] = set()
        if status == "ok":
            include, source_exclude = parse_source(result.text, source.format)
            # 解析出 0 条与下载失败同权：多半是上游改了格式
            status = "empty" if not include else "ok"
        if "lite" in source.tiers:
            include_lite |= include
        include_full |= include
        exclude |= source_exclude

        record = {
            "name": source.name,
            "status": status,
            "entries": len(include),
            "excluded": len(source_exclude),
            "bytes": result.nbytes,
            "sha256": result.sha256,
            "duration_ms": result.duration_ms,
        }
        if result.error:
            record["error"] = result.error
        source_records.append(record)
        logger.info(
            "源解析完成 name=%s status=%s entries=%d excluded=%d",
            source.name,
            status,
            len(include),
            len(source_exclude),
        )

    if not include_full:
        raise RuntimeError("解析后拦截集为空，拒绝产出空清单")

    fold_enabled = config.fold if fold is None else fold
    generated = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    tier_domains = {
        "lite": resolve(include_lite, exclude, fold_enabled),
        "full": resolve(include_full, exclude, fold_enabled),
    }

    def summary(lite_only: bool) -> str:
        return ", ".join(
            f"{record['name']} ({record['status']}, {record['entries']} 条)"
            for source, record in zip(sources, source_records)
            if not lite_only or "lite" in source.tiers
        )

    out_dir = Path(out_dir)
    outputs = write_all(
        out_dir,
        tier_domains,
        generated,
        fold_enabled,
        {"lite": summary(True), "full": summary(False)},
    )

    previous_counts = _read_previous_counts(previous_manifest)
    for output in outputs:
        output["previous"] = previous_counts.get(output["file"])

    manifest = {
        "generated_at": generated,
        "fold": fold_enabled,
        "sources": source_records,
        "outputs": outputs,
    }
    (out_dir / "manifest.json").write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    logger.info(
        "构建完成 lite=%d full=%d fold=%s",
        len(tier_domains["lite"]),
        len(tier_domains["full"]),
        fold_enabled,
    )

    violations = [
        (output["file"], output["count"], output["previous"])
        for output in outputs
        if output["previous"] is not None
        and output["count"] < output["previous"] * config.min_retain_ratio
    ]
    if violations:
        detail = "; ".join(
            f"{name} {count} < {previous}×{config.min_retain_ratio}"
            for name, count, previous in violations
        )
        raise SentinelError(f"产物条数异常收缩，拒绝发布: {detail}")

    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="聚合广告过滤规则并生成多格式清单")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--sources", default="sources.yaml")
    parser.add_argument("--whitelist", default="whitelist.txt")
    parser.add_argument("--out", default="dist")
    parser.add_argument("--previous-manifest", type=Path, default=None)
    fold_group = parser.add_mutually_exclusive_group()
    fold_group.add_argument("--fold", dest="fold", action="store_true", default=None)
    fold_group.add_argument("--no-fold", dest="fold", action="store_false")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    try:
        manifest = run(
            Path(args.config),
            Path(args.sources),
            Path(args.whitelist),
            Path(args.out),
            fold=args.fold,
            previous_manifest=args.previous_manifest,
        )
    except SentinelError as exc:
        logger.error("哨兵失败 %s", exc)
        return 2
    except (ConfigError, RuntimeError, json.JSONDecodeError) as exc:
        logger.error("构建失败 %s", exc)
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
