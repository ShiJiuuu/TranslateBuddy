"""格式片段的标记协议。

同一段里如果有多段不同格式的文字，会序列化成：

    [[0]]Revenue grew[[/0]][[1]] by 18 percent[[/1]]

模型必须原样保留标记（顺序、编号），我们按标记把译文写回对应的 run。
标记守不住时调用方可以降级为「整段用第一个片段的格式」。
"""
from __future__ import annotations

import re

TAG_RE = re.compile(r"\[\[(\d+)\]\](.*?)\[\[/\1\]\]", re.S)


def build_tagged(texts: list[str]) -> str:
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    return "".join(f"[[{i}]]{t}[[/{i}]]" for i, t in enumerate(texts))


def strip_tags(text: str) -> str:
    return TAG_RE.sub(lambda m: m.group(2), text or "")


def split_tagged(text: str, n: int) -> list[str] | None:
    """把带标记的译文拆回 n 个片段；校验失败返回 None。"""
    if n <= 1:
        return [strip_tags(text)]

    found = TAG_RE.findall(text or "")
    outside = TAG_RE.sub("", text or "").strip()
    if outside or len(found) != n:
        return None

    order = [int(idx) for idx, _ in found]
    if order != list(range(n)):
        return None
    return [content for _, content in found]
