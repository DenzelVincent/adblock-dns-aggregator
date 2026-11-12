import pytest

from aggregator.config import ConfigError, load_config, load_sources, load_whitelist

VALID_CONFIG = """
fold: true
concurrency: 4
timeout: 30
retries: 3
sentinel:
  min_retain_ratio: 0.8
"""

VALID_SOURCES = """
- name: demo
  url: https://example.com/list.txt
  format: adguard
  tiers: [lite, full]
  license: MIT
  enabled: true
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_valid_config(tmp_path):
    config = load_config(write(tmp_path, "config.yaml", VALID_CONFIG))
    assert config.fold is True
    assert config.concurrency == 4
    assert config.timeout == 30
    assert config.retries == 3
    assert config.min_retain_ratio == 0.8


def test_missing_fold_key_is_rejected(tmp_path):
    path = write(tmp_path, "config.yaml", "concurrency: 4\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_valid_sources(tmp_path):
    sources = load_sources(write(tmp_path, "sources.yaml", VALID_SOURCES))
    assert len(sources) == 1
    assert sources[0].name == "demo"
    assert sources[0].format == "adguard"
    assert list(sources[0].tiers) == ["lite", "full"]
    assert sources[0].license == "MIT"
    assert sources[0].enabled is True


def test_missing_license_is_rejected(tmp_path):
    text = VALID_SOURCES.replace("  license: MIT\n", "")
    with pytest.raises(ConfigError, match="license"):
        load_sources(write(tmp_path, "sources.yaml", text))


def test_unknown_format_is_rejected(tmp_path):
    text = VALID_SOURCES.replace("format: adguard", "format: easylist")
    with pytest.raises(ConfigError, match="format"):
        load_sources(write(tmp_path, "sources.yaml", text))


def test_unknown_tier_is_rejected(tmp_path):
    text = VALID_SOURCES.replace("[lite, full]", "[lite, extra]")
    with pytest.raises(ConfigError, match="tier"):
        load_sources(write(tmp_path, "sources.yaml", text))


def test_optional_tiers_are_accepted(tmp_path):
    text = VALID_SOURCES.replace("[lite, full]", "[lite, full, cn, mini]")
    sources = load_sources(write(tmp_path, "sources.yaml", text))
    assert "cn" in sources[0].tiers
    assert "mini" in sources[0].tiers


def test_duplicate_source_names_rejected(tmp_path):
    path = write(tmp_path, "sources.yaml", VALID_SOURCES + VALID_SOURCES)
    with pytest.raises(ConfigError, match="重复"):
        load_sources(path)


def test_load_whitelist_normalizes(tmp_path):
    text = "# comment\nGood.Example.COM.\n\nnot a domain\n"
    domains = load_whitelist(write(tmp_path, "whitelist.txt", text))
    assert domains == {"good.example.com"}
