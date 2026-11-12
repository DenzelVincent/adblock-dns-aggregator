from aggregator.report import render_summary


def test_summary_lists_sources_outputs_and_failures():
    manifest = {
        "generated_at": "2026-11-12T20:00:00Z",
        "fold": True,
        "sources": [
            {"name": "ok-source", "status": "ok", "entries": 10, "excluded": 1,
             "bytes": 100, "duration_ms": 5},
            {"name": "bad-source", "status": "failed", "entries": 0, "excluded": 0,
             "bytes": 0, "duration_ms": 1},
        ],
        "outputs": [{"file": "mosdns-lite.txt", "count": 3, "previous": 4}],
    }
    summary = render_summary(manifest)
    assert "ok-source" in summary
    assert "bad-source" in summary
    assert "mosdns-lite.txt" in summary
    assert "失败源" in summary
