"""白名单扣除与父域折叠。

两条硬约束（见设计 5.5/5.6）：
1. 白名单必须先于折叠；否则被父域覆盖的子域条目提前消失，父域再被顶掉时无法恢复。
2. 折叠只对后缀匹配语义成立，输出顺序按反转标签排序，保证同输入字节一致。
"""

from __future__ import annotations

from collections.abc import Iterable


def _reverse_labels(domain: str) -> str:
    return ".".join(reversed(domain.split(".")))


def _suffixes(domain: str) -> list[str]:
    """从 TLD 向上枚举：a.b.c -> c, b.c, a.b.c。"""
    labels = domain.split(".")
    suffixes = [labels[-1]]
    for index in range(len(labels) - 2, -1, -1):
        suffixes.append(f"{labels[index]}.{suffixes[-1]}")
    return suffixes


def subtract_excludes(include: set[str], exclude: set[str]) -> set[str]:
    """删除所有会连带拦到白名单项的条目。

    两个方向都要处理：
    - 祖先（含自身）：白名单 w 会被父域拦截项连带命中，必须顶掉；
    - 子孙：白名单在后缀匹配下对子域同样生效，父域被放行时子域条目也要移除。
    """
    result = set(include)
    for domain in exclude:
        # 祖先方向：w 的全部后缀就是会连带拦到它的条目
        for suffix in _suffixes(domain):
            result.discard(suffix)
    # 子孙方向：d 的后缀里出现白名单项，说明 d 落在白名单子树内
    return {
        domain
        for domain in result
        if not any(suffix in exclude for suffix in _suffixes(domain))
    }


def _ordered(domains: Iterable[str]) -> list[str]:
    return sorted(domains, key=_reverse_labels)


def fold_domains(domains: Iterable[str]) -> list[str]:
    """父域折叠：按反转标签升序单遍扫描，祖先一定紧邻在子孙之前。"""
    ordered = sorted({_reverse_labels(domain) for domain in domains})
    kept: list[str] = []
    last: str | None = None
    for reversed_domain in ordered:
        if last is not None and reversed_domain.startswith(f"{last}."):
            continue
        kept.append(reversed_domain)
        last = reversed_domain
    return [".".join(reversed(item.split("."))) for item in kept]


def resolve(include: set[str], exclude: set[str], fold: bool = True) -> list[str]:
    domains = subtract_excludes(include, exclude)
    if fold:
        return fold_domains(domains)
    return _ordered(domains)
