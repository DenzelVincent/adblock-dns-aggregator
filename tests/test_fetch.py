from pathlib import Path

from aggregator.config import Config, Source
from aggregator.fetch import fetch_all, fetch_source

FIXTURES = Path(__file__).parent / "fixtures"


def config():
    return Config(fold=True, concurrency=2, timeout=5, retries=1, min_retain_ratio=0.8)


def source(url, name="demo"):
    return Source(
        name=name,
        url=url,
        format="adguard",
        tiers=("lite", "full"),
        license="MIT",
        enabled=True,
    )


def test_fetch_file_source_ok():
    result = fetch_source(source((FIXTURES / "lite.txt").as_uri()), config())
    assert result.status == "ok"
    assert "ads.example.com" in result.text
    assert result.nbytes > 0
    assert len(result.sha256) == 64
    assert result.duration_ms >= 0


def test_fetch_missing_file_reports_failed():
    result = fetch_source(source((FIXTURES / "missing.txt").as_uri()), config())
    assert result.status == "failed"
    assert result.text == ""
    assert result.error


def test_fetch_all_keeps_going_after_failure():
    cfg = config()
    sources = [
        source((FIXTURES / "lite.txt").as_uri(), "ok-source"),
        source((FIXTURES / "missing.txt").as_uri(), "bad-source"),
    ]
    results = fetch_all(sources, cfg)
    assert [r.status for r in results] == ["ok", "failed"]
