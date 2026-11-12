import json
from pathlib import Path

import pytest

from aggregator.main import SentinelError, run

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = FIXTURES / "config.yaml"
WHITELIST = FIXTURES / "whitelist.txt"
GENERATED_AT = "2026-11-12T20:00:00Z"

OUTPUT_FILES = {
    "mosdns-lite.txt",
    "mosdns-full.txt",
    "mosdns-cn.txt",
    "adguard-lite.txt",
    "adguard-full.txt",
    "adguard-cn.txt",
    "dnsmasq-lite.conf",
    "dnsmasq-full.conf",
    "dnsmasq-cn.conf",
    "smartdns-lite.conf",
    "smartdns-full.conf",
    "smartdns-cn.conf",
    "manifest.json",
}


def write_sources(tmp_path, include_broken=False):
    text = f"""
- name: lite-source
  url: {(FIXTURES / "lite.txt").as_uri()}
  format: adguard
  tiers: [lite, full, cn]
  license: MIT
  enabled: true
- name: full-source
  url: {(FIXTURES / "full.txt").as_uri()}
  format: plain
  tiers: [full]
  license: MIT
  enabled: true
- name: mosdns-source
  url: {(FIXTURES / "mosdns.txt").as_uri()}
  format: mosdns
  tiers: [full]
  license: 0BSD
  enabled: true
- name: cn-source
  url: {(FIXTURES / "cn.txt").as_uri()}
  format: plain
  tiers: [cn]
  license: MIT
  enabled: true
"""
    if include_broken:
        text += f"""
- name: broken-source
  url: {(FIXTURES / "missing.txt").as_uri()}
  format: adguard
  tiers: [lite, full]
  license: MIT
  enabled: true
"""
    path = tmp_path / "sources.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def run_once(tmp_path, out_name="out", fold=None, previous=None):
    out_dir = tmp_path / out_name
    manifest = run(
        CONFIG,
        write_sources(tmp_path),
        WHITELIST,
        out_dir,
        fold=fold,
        previous_manifest=previous,
        generated_at=GENERATED_AT,
    )
    return out_dir, manifest


def body(path):
    return [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith(("#", "!")) and line]


def test_pipeline_outputs_and_manifest(tmp_path):
    out_dir, manifest = run_once(tmp_path)

    assert {p.name for p in out_dir.iterdir()} == OUTPUT_FILES
    assert body(out_dir / "mosdns-lite.txt") == ["ads.example.com"]
    assert body(out_dir / "adguard-full.txt") == [
        "||ads.example.com^",
        "||fullonly.example.com^",
        "||cn.example.net^",
        "||mosdns.example.net^",
        "||tracker.example.org^",
    ]
    assert body(out_dir / "dnsmasq-lite.conf") == ["address=/ads.example.com/0.0.0.0"]
    assert body(out_dir / "smartdns-full.conf")[0] == "address /ads.example.com/#"

    assert manifest["generated_at"] == GENERATED_AT
    assert manifest["fold"] is True
    assert [s["name"] for s in manifest["sources"]] == [
        "lite-source",
        "full-source",
        "mosdns-source",
        "cn-source",
    ]
    assert {s["name"]: s["entries"] for s in manifest["sources"]} == {
        "lite-source": 3,
        "full-source": 3,
        "mosdns-source": 2,
        "cn-source": 1,
    }
    assert all(s["status"] == "ok" for s in manifest["sources"])
    assert all(len(s["sha256"]) == 64 for s in manifest["sources"])
    counts = {o["file"]: o["count"] for o in manifest["outputs"]}
    assert counts["mosdns-lite.txt"] == 1
    assert counts["mosdns-full.txt"] == 5
    assert counts["mosdns-cn.txt"] == 2
    assert all(o["previous"] is None for o in manifest["outputs"])


def test_tier_header_lists_only_sources_of_that_tier(tmp_path):
    out_dir, _ = run_once(tmp_path)
    lite_header = (out_dir / "mosdns-lite.txt").read_text(encoding="utf-8").splitlines()[2]
    full_header = (out_dir / "mosdns-full.txt").read_text(encoding="utf-8").splitlines()[2]
    cn_header = (out_dir / "mosdns-cn.txt").read_text(encoding="utf-8").splitlines()[2]
    assert "lite-source" in lite_header
    assert "full-source" not in lite_header
    assert "mosdns-source" not in lite_header
    assert "cn-source" not in lite_header
    assert "full-source" in full_header
    assert "mosdns-source" in full_header
    assert "lite-source" in cn_header
    assert "cn-source" in cn_header
    assert "full-source" not in cn_header
    assert "mosdns-source" not in cn_header


def test_pipeline_with_fold_off(tmp_path):
    out_dir, manifest = run_once(tmp_path, fold=False)
    counts = {o["file"]: o["count"] for o in manifest["outputs"]}
    assert counts["mosdns-lite.txt"] == 2
    assert counts["mosdns-full.txt"] == 8
    assert counts["mosdns-cn.txt"] == 3
    assert manifest["fold"] is False
    assert "deep.ads.example.com" in body(out_dir / "mosdns-lite.txt")
    assert "track.example.com" not in body(out_dir / "mosdns-lite.txt")


def test_outputs_are_byte_identical_across_runs(tmp_path):
    first, _ = run_once(tmp_path, "first")
    second, _ = run_once(tmp_path, "second", previous=first / "manifest.json")
    for name in OUTPUT_FILES - {"manifest.json"}:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_manifest_records_previous_counts(tmp_path):
    first, first_manifest = run_once(tmp_path, "first")
    _, second_manifest = run_once(tmp_path, "second", previous=first / "manifest.json")
    before = {o["file"]: o["count"] for o in first_manifest["outputs"]}
    assert {o["file"]: o["previous"] for o in second_manifest["outputs"]} == before


def test_sentinel_rejects_implausible_shrink(tmp_path):
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps({"outputs": [{"file": "mosdns-lite.txt", "count": 100}]}),
        encoding="utf-8",
    )
    with pytest.raises(SentinelError):
        run_once(tmp_path, previous=previous)


def test_failed_source_does_not_abort_build(tmp_path):
    out_dir = tmp_path / "out"
    manifest = run(
        CONFIG,
        write_sources(tmp_path, include_broken=True),
        WHITELIST,
        out_dir,
        generated_at=GENERATED_AT,
    )
    statuses = {s["name"]: s["status"] for s in manifest["sources"]}
    assert statuses["broken-source"] == "failed"
    assert body(out_dir / "mosdns-lite.txt") == ["ads.example.com"]
