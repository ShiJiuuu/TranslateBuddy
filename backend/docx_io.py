"""DOCX 的 L2 就地改写：只动承载文字的 XML 节点，其余 zip 条目原样拷贝。"""
from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .ir import Segment
from .tags import build_tagged, split_tagged, strip_tags

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

TEXT_PART = re.compile(
    r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$"
)
# 这些是 Word 插的排版标记，不影响文字，遇到时不应中断格式分组
IGNORABLE_RUN_CHILDREN = {"lastRenderedPageBreak"}
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


@dataclass
class _Span:
    text: str
    runs: list
    rpr: bytes | None


@dataclass
class _Entry:
    part: str
    spans: list[_Span]


class DocxDocument:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._entries: list[zipfile.ZipInfo] = []
        self._roots: dict[str, etree._Element] = {}
        self._segments: list[Segment] = []
        self._refs: dict[str, _Entry] = {}
        self._changed: set[str] = set()
        self.stats = {"paragraphs": 0, "skipped_runs": 0}
        self._load()
        self._parse()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        with zipfile.ZipFile(self.path) as zf:
            self._entries = zf.infolist()
            for info in self._entries:
                if TEXT_PART.match(info.filename):
                    self._roots[info.filename] = etree.fromstring(zf.read(info))

    # ----------------------------------------------------------------- parse
    @property
    def segments(self) -> list[Segment]:
        return self._segments

    def _parse(self) -> None:
        for part, root in self._roots.items():
            heading = ""
            prev = ""
            for idx, p in enumerate(root.iter(W + "p")):
                self.stats["paragraphs"] += 1
                style = self._style(p)
                if style.lower().startswith("heading") or style.startswith("标题"):
                    heading = self._plain_of(p)[:80]

                spans = self._spans(p)
                joined = "".join(s.text for s in spans)
                if not spans or not LETTER_RE.search(joined):
                    prev = joined or prev
                    continue

                tagged = build_tagged([s.text for s in spans])
                plain = strip_tags(tagged)
                seg = Segment(
                    id=f"{part}#{idx}",
                    kind="paragraph",
                    text=tagged,
                    plain=plain,
                    span_count=len(spans),
                    context={"part": part, "heading": heading, "prev": prev[:80]},
                )
                self._segments.append(seg)
                self._refs[seg.id] = _Entry(part, spans)
                prev = plain[:80]

    def _spans(self, p) -> list[_Span]:
        spans: list[_Span] = []
        cur: _Span | None = None
        for r in self._runs(p):
            if self._run_kind(r) != "text":
                self.stats["skipped_runs"] += 1
                cur = None  # 制表符/换行/域代码等：打断格式分组，本身不动
                continue
            txt = self._run_text(r)
            if not txt:
                continue
            sig = self._rpr(r)
            if cur is not None and cur.rpr == sig:
                cur.text += txt
                cur.runs.append(r)
            else:
                cur = _Span(txt, [r], sig)
                spans.append(cur)
        return spans

    def _runs(self, p) -> list:
        """只取属于本段落的 run，不进入嵌套段落（文本框里的 w:p 会单独处理）。"""
        out: list = []

        def walk(el) -> None:
            for child in el:
                tag = child.tag
                if tag == W + "p":          # 嵌套段落
                    continue
                if tag == W + "del":        # 修订删除：不碰
                    continue
                if tag == W + "r":
                    out.append(child)
                    continue
                walk(child)

        walk(p)
        return out

    @staticmethod
    def _run_kind(r) -> str:
        for child in r:
            local = etree.QName(child).localname
            if local in ("rPr", "t") or local in IGNORABLE_RUN_CHILDREN:
                continue
            return "other"
        return "text"

    @staticmethod
    def _run_text(r) -> str:
        return "".join(t.text or "" for t in r.findall(W + "t"))

    @staticmethod
    def _rpr(r) -> bytes | None:
        rpr = r.find(W + "rPr")
        return None if rpr is None else etree.tostring(rpr)

    @staticmethod
    def _style(p) -> str:
        el = p.find(f"{W}pPr/{W}pStyle")
        return "" if el is None else (el.get(W + "val") or "")

    def _plain_of(self, p) -> str:
        return "".join(self._run_text(r) for r in self._runs(p) if self._run_kind(r) == "text")

    # ----------------------------------------------------------------- apply
    def apply(self, segment_id: str, translated: str) -> bool:
        """写回译文；返回 False 表示标记没守住、已降级为整段单格式。"""
        entry = self._refs.get(segment_id)
        if entry is None or not translated:
            return False

        parts = split_tagged(translated, len(entry.spans))
        ok = parts is not None
        if parts is None:
            parts = [strip_tags(translated)] + [""] * (len(entry.spans) - 1)

        for span, text in zip(entry.spans, parts):
            self._write_span(span, text)
        self._changed.add(entry.part)
        return ok

    def _write_span(self, span: _Span, text: str) -> None:
        first = span.runs[0]
        ts = first.findall(W + "t")
        if not ts:
            ts = [etree.SubElement(first, W + "t")]
        ts[0].text = text
        if text != text.strip():
            ts[0].set(XML_SPACE, "preserve")
        elif XML_SPACE in ts[0].attrib:
            del ts[0].attrib[XML_SPACE]
        for extra in ts[1:]:
            first.remove(extra)
        for r in span.runs[1:]:
            for t in r.findall(W + "t"):
                r.remove(t)

    # ------------------------------------------------------------------ save
    def save(self, dst: Path) -> Path:
        dst = Path(dst)
        with zipfile.ZipFile(self.path) as zin, zipfile.ZipFile(dst, "w") as zout:
            for info in self._entries:
                if info.filename in self._changed:
                    root = self._roots[info.filename]
                    data = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                    zout.writestr(info, data)
                else:
                    # 大文件不整块读：按块流式拷贝
                    with zin.open(info) as src, zout.open(info, "w") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
        return dst
