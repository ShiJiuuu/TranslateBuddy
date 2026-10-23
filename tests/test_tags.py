from backend.tags import build_tagged, split_tagged, strip_tags


def test_single_span_has_no_markers():
    assert build_tagged(["hello"]) == "hello"


def test_multi_span_roundtrip():
    tagged = build_tagged(["a", "b", "c"])
    assert tagged == "[[0]]a[[/0]][[1]]b[[/1]][[2]]c[[/2]]"
    assert strip_tags(tagged) == "abc"
    assert split_tagged(tagged, 3) == ["a", "b", "c"]


def test_missing_marker_fails():
    assert split_tagged("[[0]]a[[/0]][[1]]b[[/1]]", 3) is None


def test_reordered_marker_fails():
    assert split_tagged("[[1]]b[[/1]][[0]]a[[/0]]", 2) is None


def test_text_outside_markers_fails():
    assert split_tagged("废话[[0]]a[[/0]][[1]]b[[/1]]", 2) is None


def test_single_span_accepts_plain_text():
    assert split_tagged("纯文本", 1) == ["纯文本"]
