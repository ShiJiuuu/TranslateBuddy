"""术语表：翻译前把术语换成占位符锁死，翻完再还原。

比"在 prompt 里叮嘱模型"可靠：模型看不到术语原文，就不会自由发挥。
"""
from __future__ import annotations

import re

PLACEHOLDER_RE = re.compile(r"⟦T\d+⟧")


class Glossary:
    def __init__(self, pairs: dict[str, str], case_sensitive: bool = True):
        self.pairs = {k: v for k, v in pairs.items() if k and v}
        self.case_sensitive = case_sensitive
        self._terms = sorted(self.pairs, key=len, reverse=True)

    def __bool__(self) -> bool:
        return bool(self.pairs)

    def lock(self, text: str) -> tuple[str, dict[str, str]]:
        mapping: dict[str, str] = {}
        if not text:
            return text, mapping
        for src in self._terms:
            if not src or src not in text:
                continue
            placeholder = f"⟦T{len(mapping)}⟧"
            text = text.replace(src, placeholder)
            mapping[placeholder] = self.pairs[src]
        return text, mapping

    def unlock(self, text: str, mapping: dict[str, str]) -> tuple[str, list[str]]:
        missing = []
        for placeholder, target in mapping.items():
            if placeholder in text:
                text = text.replace(placeholder, target)
            else:
                missing.append(target)
        return text, missing


def missing_placeholders(text: str, mapping: dict[str, str]) -> list[str]:
    return [v for k, v in mapping.items() if k not in text]
