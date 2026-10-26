import json

from backend.ir import Segment
from backend.translator import BatchConfig, load_glossary, translate_segments


def make_segments(n: int) -> list[Segment]:
    return [Segment(id=f"s{i}", kind="p", text=f"text {i}", plain=f"text {i}") for i in range(n)]


def test_batches_respect_item_limit():
    calls = []

    def invoke(system, user):
        payload = json.loads(user)
        calls.append(len(payload["items"]))
        return json.dumps(
            {"items": [{"id": i["id"], "text": "译 " + i["text"]} for i in payload["items"]]},
            ensure_ascii=False,
        )

    out = translate_segments(make_segments(30), invoke, "zh-Hans", config=BatchConfig(max_items=10))
    assert len(out) == 30
    assert calls == [10, 10, 10]


def test_bad_json_keeps_source():
    segments = make_segments(3)
    out = translate_segments(segments, lambda s, u: "not json", "zh-Hans")
    assert out == {}
    assert all(s.status == "kept" for s in segments)


def test_json_inside_fence_is_accepted():
    fence = chr(96) * 3

    def invoke(system, user):
        return fence + 'json\n{"items": [{"id": "s0", "text": "译文"}]}\n' + fence

    out = translate_segments(make_segments(1), invoke, "zh-Hans")
    assert out == {"s0": "译文"}


def test_glossary_csv():
    raw = "source,target\nRevenue,营收\n\n".encode()
    glossary = load_glossary(raw)
    assert glossary.pairs == {"Revenue": "营收"}


def test_duplicate_texts_are_translated_once():
    segments = [
        Segment(id="a", kind="p", text="Confidential", plain="Confidential"),
        Segment(id="b", kind="p", text="Confidential", plain="Confidential"),
        Segment(id="c", kind="p", text="Other", plain="Other"),
    ]
    calls = []

    def invoke(system, user):
        payload = json.loads(user)
        calls.append(len(payload["items"]))
        return json.dumps(
            {"items": [{"id": i["id"], "text": "译" + i["text"]} for i in payload["items"]]},
            ensure_ascii=False,
        )

    out = translate_segments(segments, invoke, "zh-Hans")
    assert calls == [2]
    assert out["a"] == out["b"] == "译Confidential"
    assert out["c"] == "译Other"


def test_glossary_locks_terms_during_translation():
    raw = "source,target\nRevenue,营收\n".encode()
    glossary = load_glossary(raw)
    seen = []

    def invoke(system, user):
        payload = json.loads(user)
        seen.extend(item["text"] for item in payload["items"])
        return json.dumps(
            {"items": [{"id": i["id"], "text": i["text"]} for i in payload["items"]]},
            ensure_ascii=False,
        )

    segments = [Segment(id="s0", kind="p", text="Revenue grew 18%", plain="Revenue grew 18%")]
    out = translate_segments(segments, invoke, "zh-Hans", glossary=glossary)

    assert "Revenue" not in seen[0]          # 模型看不到术语原文
    assert out["s0"] == "营收 grew 18%"      # 翻完还原成目标词
