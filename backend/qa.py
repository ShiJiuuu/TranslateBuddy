from __future__ import annotations

import re

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
PLACEHOLDER_RE = re.compile(r"\{[^{}]{1,40}\}|%[sd]|\[\[[^\]]{1,40}\]\]")


def check(source_plain: str, translated_plain: str) -> list[str]:
    issues: list[str] = []
    if not translated_plain.strip():
        return ["empty"]
    if translated_plain.strip() == source_plain.strip():
        issues.append("identical")

    src_nums = set(NUMBER_RE.findall(source_plain))
    dst_nums = set(NUMBER_RE.findall(translated_plain))
    if src_nums - dst_nums:
        issues.append("numbers_missing:" + ",".join(sorted(src_nums - dst_nums))[:40])

    src_ph = set(PLACEHOLDER_RE.findall(source_plain))
    dst_ph = set(PLACEHOLDER_RE.findall(translated_plain))
    if src_ph != dst_ph:
        issues.append("placeholder_mismatch")

    if len(source_plain) > 20 and len(translated_plain) > 3 * len(source_plain):
        issues.append("too_long")
    return issues
