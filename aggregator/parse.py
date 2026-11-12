"""规则行解析：把各源的行文本折叠成 (拦截集, 例外集)。

四种目标格式在后缀匹配语义下等价（见设计 2），所以这里只做"能否用后缀表达"的
判断：不能精确表达的一律丢弃，绝不降级——降级会把"仅第三方"放大成全量拦截。
"""

from __future__ import annotations

import ipaddress
import re

LABEL_RE = re.compile(r"^[a-z0-9_-]+$")

# adguard 形态：||domain^ 或 ||domain，$ 之后是修饰符。
# 域名部分不允许出现 | ^ $ / 空白，避免把路径、正则混进来。
ADGUARD_RE = re.compile(r"^\|\|([^|^$/\s]+)\^?(?:\$(.+))?$")

HOSTS_IPS = {"0.0.0.0", "127.0.0.1", "::", "::1"}

RESERVED_NAMES = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
}

FORMATS = ("adguard", "hosts", "plain", "mosdns")


def normalize_domain(value: str) -> str | None:
    """归一化域名；无法用后缀精确表达时返回 None。"""
    value = value.strip().lower().rstrip(".")
    if not value or any(ch.isspace() for ch in value):
        return None
    # 这些字符属于 AdGuard/EasyList 语法，落到域名位置说明规则无法直接表达
    if any(ch in value for ch in "/*|^$@:?=,"):
        return None
    if any(ord(ch) > 127 for ch in value):
        try:
            value = value.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    labels = value.split(".")
    if len(labels) < 2 or len(value) > 253:
        return None
    for label in labels:
        if not label or len(label) > 63 or not LABEL_RE.match(label):
            return None
        # 下划线允许（_dmarc 等），连字符不能在标签首尾
        if label.startswith("-") or label.endswith("-"):
            return None
    if value in RESERVED_NAMES or value.startswith("ip6-"):
        return None
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    return None


def _parse_adguard(line: str, include: set[str], exclude: set[str]) -> None:
    exception = line.startswith("@@")
    pattern = line[2:] if exception else line
    if pattern.startswith("||"):
        match = ADGUARD_RE.match(pattern)
        if not match:
            return
        domain = normalize_domain(match.group(1))
        if not domain:
            return
        if exception:
            # 例外方向宁可放宽：带 $ 修饰符的例外也放行
            exclude.add(domain)
        elif match.group(2):
            # 带 $ 修饰符的拦截规则无法用后缀表达，丢弃
            return
        else:
            include.add(domain)
        return
    if exception:
        return
    # adguard 源里混入的纯域名行按普通域名兜底
    domain = normalize_domain(line)
    if domain:
        include.add(domain)


def _parse_mosdns(line: str, include: set[str]) -> None:
    if line.startswith("domain:"):
        domain = normalize_domain(line[len("domain:"):])
        if domain:
            include.add(domain)
        return
    if line.startswith(("full:", "keyword:", "regexp:")):
        # full:/regexp: 与后缀匹配不等价，keyword: 没有域名可提
        return
    domain = normalize_domain(line)
    if domain:
        include.add(domain)


def parse_source(text: str, fmt: str) -> tuple[set[str], set[str]]:
    if fmt not in FORMATS:
        raise ValueError(f"未知源格式: {fmt}")
    include: set[str] = set()
    exclude: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "!#[":
            continue

        # hosts 行在任何声明格式里都按形态兜底识别
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in HOSTS_IPS:
            domain = normalize_domain(parts[1].split()[0])
            if domain:
                include.add(domain)
            continue
        if fmt == "hosts":
            continue

        if fmt == "adguard":
            _parse_adguard(line, include, exclude)
        elif fmt == "mosdns":
            _parse_mosdns(line, include)
        else:
            domain = normalize_domain(line)
            if domain:
                include.add(domain)

    return include, exclude
