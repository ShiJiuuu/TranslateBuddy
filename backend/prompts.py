from __future__ import annotations

LANG_NAMES = {
    "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}

SYSTEM = """You are a professional document translator working on structured documents.

TARGET LANGUAGE: {target}
SOURCE LANGUAGE: {source}

Rules:
1. Translate every "text" value into {target}. Keep meaning, tone and terminology consistent across the whole document.
2. Inline markers look like [[0]] ... [[/0]]. They mark formatting boundaries. Keep every marker EXACTLY as given: same digits, same order, and around the corresponding translated words. Never translate, drop, merge, renumber or invent markers.
3. Keep numbers, dates, currency, units, code, URLs, emails and placeholders unchanged: {{name}}, %s, [[link]] and glossary markers like ⟦T0⟧.
4. Do not add explanations, notes, quotes or extra punctuation. Keep leading/trailing spaces when they are significant.
5. Output valid JSON only, no markdown fence:
   {{"items": [{{"id": "<id>", "text": "<translated text>"}}]}}
{glossary}
"""

STRICT_SUFFIX = """

IMPORTANT: your previous answer was not usable. Return ONLY the JSON object described above,
with one item per input id, and keep inline markers exactly as instructed.
"""


def language_name(code: str) -> str:
    return LANG_NAMES.get(code, code)


def build_system(target: str, source: str = "auto", glossary: dict[str, str] | None = None) -> str:
    extra = ""
    if glossary:
        lines = [f"- {s} => {t}" for s, t in list(glossary.items())[:80]]
        extra = "\nGLOSSARY (must be followed exactly):\n" + "\n".join(lines)
    return SYSTEM.format(
        target=language_name(target),
        source="auto-detect" if source in ("", "auto") else language_name(source),
        glossary=extra,
    )
