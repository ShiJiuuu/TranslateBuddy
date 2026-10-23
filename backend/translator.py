from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from .ir import Segment
from .prompts import build_system, STRICT_SUFFIX

log = logging.getLogger(__name__)

FENCE_RE = re.compile(r"^\s*\`\`\`[a-zA-Z]*\s*|\s*\`\`\`\s*$")


@dataclass
class BatchConfig:
    max_chars: int = 1800
    max_items: int = 12
    retries: int = 1


def translate_segments(
    segments: list[Segment],
    invoke,
    target_lang: str,
    source_lang: str = "auto",
    glossary: dict[str, str] | None = None,
    config: BatchConfig | None = None,
    on_progress=None,
) -> dict[str, str]:
    """把分段翻成 {segment_id: translated_text}。单批失败不影响其他批。"""
    cfg = config or BatchConfig()
    system = build_system(target_lang, source_lang, glossary)
    out: dict[str, str] = {}

    batches = list(_batch(segments, cfg))
    for index, batch in enumerate(batches, start=1):
        got = _run_batch(batch, invoke, system, strict=False)
        missing = [s for s in batch if s.id not in got]
        if missing and cfg.retries:
            got.update(_run_batch(missing, invoke, system, strict=True))

        for seg in batch:
            text = got.get(seg.id)
            if text and text.strip():
                out[seg.id] = text
                seg.status = "translated"
            else:
                seg.status = "kept"
        if on_progress:
            on_progress(index, len(batches), len(out), len(segments))
    return out


def _batch(segments: list[Segment], cfg: BatchConfig):
    batch: list[Segment] = []
    size = 0
    for seg in segments:
        cost = len(seg.text)
        if batch and (size + cost > cfg.max_chars or len(batch) >= cfg.max_items):
            yield batch
            batch, size = [], 0
        batch.append(seg)
        size += cost
    if batch:
        yield batch


def _run_batch(batch, invoke, system: str, strict: bool) -> dict[str, str]:
    payload = {"items": [{"id": s.id, "text": s.text} for s in batch]}
    prompt = json.dumps(payload, ensure_ascii=False)
    sys_prompt = system + (STRICT_SUFFIX if strict else "")
    try:
        raw = invoke(sys_prompt, prompt) or ""
    except Exception as exc:  # 上游模型报错：这一批保留原文
        log.warning("translator batch failed: %s", exc)
        return {}

    parsed = _parse(raw)
    if parsed is None:
        log.warning("translator batch returned unparsable output: %.200s", raw)
        return {}
    return parsed


def _parse(raw: str) -> dict[str, str] | None:
    cleaned = FENCE_RE.sub("", raw.strip())
    data = _json(cleaned)
    if data is None:
        left, right = cleaned.find("{"), cleaned.rfind("}")
        if left >= 0 and right > left:
            data = _json(cleaned[left : right + 1])
    if data is None:
        return None

    items = data.get("items") if isinstance(data, dict) else data
    result: dict[str, str] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("id") is not None:
                result[str(item["id"])] = str(item.get("text", ""))
    elif isinstance(items, dict):
        for key, value in items.items():
            if isinstance(value, str):
                result[str(key)] = value
    return result or None


def _json(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def load_glossary(raw: bytes) -> dict[str, str]:
    """CSV: source,target[,case_sensitive]；容忍 BOM 与空行。"""
    import csv
    import io

    if not raw:
        return {}
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    out: dict[str, str] = {}
    for row in reader:
        if len(row) < 2:
            continue
        src, dst = row[0].strip(), row[1].strip()
        if not src or not dst or src.lower() in ("source", "src"):
            continue
        out[src] = dst
    return out
