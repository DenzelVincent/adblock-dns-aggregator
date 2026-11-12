from aggregator.fold import fold_domains, resolve, subtract_excludes


def test_whitelist_subdomain_removes_parent():
    include = {"example.com", "other.example.com", "keep.example.org"}
    exclude = {"a.example.com"}
    # 只顶掉 a.example.com 的祖先；兄弟子域不属于白名单语义
    assert subtract_excludes(include, exclude) == {"other.example.com", "keep.example.org"}


def test_whitelist_parent_removes_all_children():
    include = {"example.com", "a.example.com", "b.example.com", "other.org"}
    exclude = {"example.com"}
    assert subtract_excludes(include, exclude) == {"other.org"}


def test_whitelist_respects_label_boundary():
    include = {"example.com", "notexample.com", "example.com.evil.org"}
    exclude = {"example.com"}
    assert subtract_excludes(include, exclude) == {"notexample.com", "example.com.evil.org"}


def test_empty_inputs():
    assert subtract_excludes(set(), {"example.com"}) == set()
    assert fold_domains([]) == []


def test_fold_removes_descendants():
    assert fold_domains(["example.com", "a.example.com", "b.a.example.com"]) == ["example.com"]


def test_fold_keeps_siblings_with_shared_prefix():
    assert fold_domains(["b.com", "bx.com"]) == ["b.com", "bx.com"]


def test_fold_respects_label_boundary():
    assert fold_domains(["b.com", "c.b.com", "b.com.evil.org"]) == [
        "b.com",
        "b.com.evil.org",
    ]


def test_fold_output_order_is_stable():
    assert fold_domains(["z.example.com", "a.example.com"]) == ["a.example.com", "z.example.com"]


def test_resolve_applies_whitelist_before_fold():
    include = {"example.com", "a.example.com", "b.example.com"}
    exclude = {"b.example.com"}
    assert resolve(include, exclude, fold=True) == ["a.example.com"]


def test_resolve_with_fold_off_still_applies_whitelist():
    include = {"example.com", "a.example.com"}
    exclude = {"a.example.com"}
    assert resolve(include, exclude, fold=False) == []


def test_resolve_with_fold_off_keeps_descendants():
    include = {"example.com", "a.example.com"}
    assert resolve(include, set(), fold=False) == ["example.com", "a.example.com"]
