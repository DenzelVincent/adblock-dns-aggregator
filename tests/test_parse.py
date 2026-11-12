import pytest

from aggregator.parse import parse_source


def parse(text, fmt="adguard"):
    include, exclude = parse_source(text, fmt)
    return include, exclude


def test_adguard_suffix_forms():
    include, exclude = parse("||ads.example.com^\n||track.example.com\n")
    assert include == {"ads.example.com", "track.example.com"}
    assert exclude == set()


def test_adguard_modifier_rule_is_dropped():
    include, exclude = parse("||ads.example.com^$third-party\n||x.example.com$important\n")
    assert include == set()
    assert exclude == set()


def test_adguard_exception_forms():
    include, exclude = parse("@@||good.example.com^\n@@||ok.example.com\n")
    assert include == set()
    assert exclude == {"good.example.com", "ok.example.com"}


def test_adguard_exception_with_modifier_still_excluded():
    include, exclude = parse("@@||good.example.com^$third-party\n")
    assert include == set()
    assert exclude == {"good.example.com"}


def test_mosdns_domain_prefix():
    include, exclude = parse("domain:ads.example.com\ndomain:sub.ads.example.com\n", "mosdns")
    assert include == {"ads.example.com", "sub.ads.example.com"}


@pytest.mark.parametrize("line", ["full:ads.example.com", "keyword:ads", "regexp:^ads"])
def test_mosdns_unsupported_prefix_dropped(line):
    include, exclude = parse(line, "mosdns")
    assert include == set()
    assert exclude == set()


@pytest.mark.parametrize(
    "line",
    [
        "0.0.0.0 ads.example.com",
        "127.0.0.1 track.example.com",
        ":: ipv6.example.com",
        "::1 ipv6b.example.com",
        "0.0.0.0\tbare.example.com\t# trailing",
    ],
)
def test_hosts_lines_recognized_in_any_format(line):
    include, exclude = parse(line)
    assert len(include) == 1
    assert exclude == set()


def test_plain_domain_in_plain_format():
    include, exclude = parse("ads.example.com\nTRACK.Example.COM.\n", "plain")
    assert include == {"ads.example.com", "track.example.com"}


def test_plain_domain_accepted_in_adguard_format():
    include, _ = parse("ads.example.com\n")
    assert include == {"ads.example.com"}


@pytest.mark.parametrize(
    "line",
    [
        "*.ads.example.com",
        "||*.example.com^",
        "/ad[0-9]+/",
        "||example.com/path",
        "https://example.com",
        "ads.*.example.com",
    ],
)
def test_unexpressible_rules_dropped(line):
    include, exclude = parse(line)
    assert include == set()
    assert exclude == set()


@pytest.mark.parametrize(
    "line",
    [
        "! comment",
        "#TITLE=anti-AD",
        "# plain comment",
        "[Adblock Plus]",
        "",
        "   ",
    ],
)
def test_header_and_comment_lines_skipped(line):
    include, exclude = parse(line)
    assert include == set()
    assert exclude == set()


@pytest.mark.parametrize(
    "line",
    [
        "localhost",
        "localhost.localdomain",
        "broadcasthost",
        "ip6-localhost",
        "ip6-loopback",
        "0.0.0.0 localhost",
    ],
)
def test_reserved_names_dropped(line):
    include, exclude = parse(line)
    assert include == set()
    assert exclude == set()


@pytest.mark.parametrize(
    "line",
    ["1.2.3.4", "||1.2.3.4^", "0.0.0.0 1.2.3.4", "::1"],
)
def test_ip_literal_dropped(line):
    include, exclude = parse(line)
    assert include == set()
    assert exclude == set()


@pytest.mark.parametrize(
    "line",
    ["com", "-bad.example", "a..example", "bad-.example", "under_score..example"],
)
def test_invalid_labels_dropped(line):
    include, exclude = parse(line)
    assert include == set()
    assert exclude == set()


def test_underscore_label_is_allowed():
    include, _ = parse("||_dmarc.example.com^\n")
    assert include == {"_dmarc.example.com"}


def test_punycode_conversion():
    include, _ = parse("||bücher.example^\n")
    assert include == {"xn--bcher-kva.example"}


def test_overlong_domain_dropped():
    label = "a" * 64
    include, _ = parse(f"||{label}.example.com^\n")
    assert include == set()
