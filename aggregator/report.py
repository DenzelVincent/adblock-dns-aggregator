"""把 manifest 渲染成 GitHub Step Summary 的 Markdown。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def render_summary(manifest: dict) -> str:
    lines = [
        "## 广告过滤规则聚合结果",
        "",
        f"- 生成时间：{manifest['generated_at']}",
        f"- 父域折叠：{'开' if manifest['fold'] else '关'}",
        "",
        "### 源",
        "",
        "| 源 | 状态 | 条目 | 例外 | 字节 | 耗时(ms) |",
        "|---|---|---|---|---|---|",
    ]
    for source in manifest["sources"]:
        lines.append(
            f"| {source['name']} | {source['status']} | {source['entries']} "
            f"| {source['excluded']} | {source['bytes']} | {source['duration_ms']} |"
        )

    lines += [
        "",
        "### 产物",
        "",
        "| 文件 | 条数 | 上一版 |",
        "|---|---|---|",
    ]
    for output in manifest["outputs"]:
        previous = output.get("previous")
        lines.append(
            f"| {output['file']} | {output['count']} | "
            f"{'—' if previous is None else previous} |"
        )

    failed = [source["name"] for source in manifest["sources"] if source["status"] != "ok"]
    if failed:
        lines += ["", f"失败源：{', '.join(failed)}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("用法: python -m aggregator.report dist/manifest.json", file=sys.stderr)
        return 1
    manifest = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    print(render_summary(manifest), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
