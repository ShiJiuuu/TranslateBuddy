"""PDF 的可读优先重排。

思路：
  1. 按 block/line/span 提取文字与样式，识别页眉页脚、表格单元格、正文段落；
  2. 正文按列重排：保持原字号，向下排；排到页底就插入续页，不缩成蚂蚁字；
  3. 表格单元格不参与重排，只在原格内缩放换行（保持表格结构）；
  4. 图片/矢量图原样保留，作为障碍物避让。

这是"可读优先"的取舍：版式骨架（表格、图、页眉页脚）保住，正文允许页数变多。
"""
from __future__ import annotations

import html as H
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .ir import Segment
from .tags import build_tagged, split_tagged, strip_tags

LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?。！？；;])\s+")

TOP_MARGIN = 36.0
BOTTOM_MARGIN = 36.0
HEADER_ZONE = 0.08
FOOTER_ZONE = 0.92
COLUMN_GAP = 24.0
CELL_GAP = 24.0


@dataclass
class _Span:
    text: str
    font: str
    size: float
    color: int
    flags: int

    @property
    def bold(self) -> bool:
        return bool(self.flags & 16)

    @property
    def italic(self) -> bool:
        return bool(self.flags & 2)


@dataclass
class _Block:
    page: int
    rect: pymupdf.Rect
    spans: list[_Span]
    kind: str = "text"          # text | cell | header | footer
    column: int = 0
    seg_id: str = ""
    rects: list = field(default_factory=list)


class PdfDocument:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.doc = pymupdf.open(self.path)
        self._segments: list[Segment] = []
        self._blocks: dict[str, _Block] = {}
        self._translations: dict[str, str] = {}
        self._obstacles: dict[int, list[pymupdf.Rect]] = {}
        self.stats = {"pages": len(self.doc), "blocks": 0, "cells": 0, "headers": 0}
        self.report: dict = {"inserted_pages": 0, "oversized_blocks": 0, "format_fallback": 0}
        self._parse()

    # ----------------------------------------------------------------- parse
    @property
    def segments(self) -> list[Segment]:
        return self._segments

    def _parse(self) -> None:
        for pno, page in enumerate(self.doc):
            height = page.rect.height
            obstacles = []
            for block in page.get_text("dict")["blocks"]:
                if block["type"] == 1:  # 图片
                    obstacles.append(pymupdf.Rect(block["bbox"]))
                    continue
                if block["type"] != 0:
                    continue
                spans = [s for line in block["lines"] for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                rect = pymupdf.Rect(block["bbox"])
                zone = "header" if rect.y1 < height * HEADER_ZONE else (
                    "footer" if rect.y0 > height * FOOTER_ZONE else "text"
                )
                if zone != "text":
                    self._add_block(pno, rect, spans, zone, f"pdf/p{pno}/{'h' if zone == 'header' else 'f'}{len(self._blocks)}")
                    self.stats["headers"] += 1
                    continue

                if self._is_table(block):
                    for i, cell_spans in enumerate(self._cells(block)):
                        crect = pymupdf.Rect(cell_spans[0][0])
                        for bbox, _ in cell_spans[1:]:
                            crect |= pymupdf.Rect(bbox)
                        seg_id = f"pdf/p{pno}/t{len(self._blocks)}c{i}"
                        b = self._add_block(pno, crect, [s for _, s in cell_spans], "cell", seg_id)
                        self.stats["cells"] += 1
                else:
                    seg_id = f"pdf/p{pno}/b{len(self._blocks)}"
                    self._add_block(pno, rect, spans, "text", seg_id)
            self._obstacles[pno] = obstacles

    def _is_table(self, block) -> bool:
        """块内文本在水平方向分成两簇以上，按表格处理（PyMuPDF 常把一行拆成两行）。"""
        lines = [l for l in block["lines"] if any(s["text"].strip() for s in l["spans"])]
        if len(lines) < 2:
            return False
        ranges = sorted((l["bbox"][0], l["bbox"][2]) for l in lines)
        clusters = [list(ranges[0])]
        for x0, x1 in ranges[1:]:
            if x0 < clusters[-1][1] - 5:
                clusters[-1][1] = max(clusters[-1][1], x1)
            else:
                clusters.append([x0, x1])
        return len(clusters) >= 2

    def _cells(self, block):
        """先按纵向重叠聚成"行"，再在行内按水平间距切成单元格。"""
        rows: list[dict] = []
        for line in block["lines"]:
            spans = [(s["bbox"], _span(s)) for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            y0, y1 = line["bbox"][1], line["bbox"][3]
            for row in rows:
                if not (y1 < row["y0"] or y0 > row["y1"]):
                    row["lines"].extend(spans)
                    row["y0"], row["y1"] = min(row["y0"], y0), max(row["y1"], y1)
                    break
            else:
                rows.append({"y0": y0, "y1": y1, "lines": list(spans)})

        cells: list[list] = []
        for row in rows:
            spans = sorted(row["lines"], key=lambda item: item[0][0])
            current: list = []
            for bbox, span in spans:
                if current and bbox[0] - current[-1][0][2] < CELL_GAP:
                    current.append((bbox, span))
                else:
                    if current:
                        cells.append(current)
                    current = [(bbox, span)]
            if current:
                cells.append(current)
        return cells

    def _add_block(self, pno: int, rect, spans, kind: str, seg_id: str) -> _Block:
        merged = _merge_spans([s if isinstance(s, _Span) else _span_from_dict(s) for s in spans])
        text = _join(merged).strip()
        b = _Block(pno, rect, merged, kind, seg_id=seg_id)
        self._blocks[seg_id] = b
        self.stats["blocks"] += 1

        if not LETTER_RE.search(text):
            return b
        tagged = build_tagged([s.text for s in merged])
        self._segments.append(
            Segment(
                id=seg_id,
                kind=kind,
                text=tagged,
                plain=strip_tags(tagged),
                span_count=len(merged),
                context={"page": pno + 1, "kind": kind},
            )
        )
        return b

    # ----------------------------------------------------------------- apply
    def apply(self, segment_id: str, translated: str) -> bool:
        if segment_id not in self._blocks or not translated:
            return False
        block = self._blocks[segment_id]
        parts = split_tagged(translated, len(block.spans))
        ok = parts is not None
        self._translations[segment_id] = translated if ok else strip_tags(translated)
        self._translations.setdefault(f"{segment_id}#fallback", "0" if ok else "1")
        return ok

    # ------------------------------------------------------------------ save
    def save(self, dst: Path) -> Path:
        for pno in reversed(range(len(self.doc))):
            page = self.doc[pno]
            blocks = [b for b in self._blocks.values() if b.page == pno and b.seg_id in self._translations]
            if not blocks:
                continue
            self._render_page(page, blocks)
        self.doc.subset_fonts()
        self.doc.save(dst, garbage=4, deflate=True)
        return Path(dst)

    def _render_page(self, page, blocks: list[_Block]) -> None:
        for b in blocks:
            page.add_redact_annot(b.rect + (-1, -2, 1, 2), fill=False, cross_out=False)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )

        footer_top = min(
            [b.rect.y0 for b in self._blocks.values() if b.page == page.number and b.kind == "footer"],
            default=page.rect.height - BOTTOM_MARGIN,
        )
        obstacles = self._obstacles.get(page.number, [])

        cells = [b for b in blocks if b.kind == "cell"]
        flow = [b for b in blocks if b.kind == "text"]
        anchored = [b for b in blocks if b.kind in ("header", "footer")]

        # 表格也是障碍物：正文不许压在表格上
        obstacles = list(obstacles) + [b.rect for b in cells]

        for b in cells:
            self._place(page, b.rect, self._html(b), b, scale_low=0.55, fittable=False)
        for b in anchored:
            self._place(page, b.rect, self._html(b), b, scale_low=0.7, fittable=False)

        for column in self._columns(flow, page):
            self._flow_column(page, column, footer_top, obstacles)

    def _flow_column(self, page, column: list[_Block], footer_top: float, obstacles) -> None:
        if not column:
            return
        x0 = min(b.rect.x0 for b in column)
        x1 = max(b.rect.x1 for b in column)
        width = max(40.0, x1 - x0)
        cursor = min(b.rect.y0 for b in column)
        current = page

        for block in column:
            css = self._css(block)
            html = self._html(block)
            need = self._measure(html, css, width)
            limit = footer_top - 6

            if cursor + need > limit:
                if need <= limit - TOP_MARGIN:
                    current, cursor = self._new_page(current)
                else:
                    self.report["oversized_blocks"] += 1
                    for chunk, chunk_h in self._split_to_fit(block, css, width, limit - TOP_MARGIN):
                        if cursor + chunk_h > limit:
                            current, cursor = self._new_page(current)
                        cursor = self._avoid(obstacles if current is page else [], x0, width, cursor, chunk_h)
                        self._place_raw(current, pymupdf.Rect(x0, cursor, x0 + width, cursor + chunk_h + 2), chunk, css)
                        cursor += chunk_h + 4
                    continue

            cursor = self._avoid(obstacles if current is page else [], x0, width, cursor, need)
            if cursor + need > limit:
                current, cursor = self._new_page(current)
            self._place_raw(current, pymupdf.Rect(x0, cursor, x0 + width, cursor + need + 2), html, css)
            cursor += need + 6

    def _new_page(self, current):
        new = self.doc.new_page(
            pno=current.number + 1, width=current.rect.width, height=current.rect.height
        )
        self.report["inserted_pages"] += 1
        return new, TOP_MARGIN

    @staticmethod
    def _avoid(obstacles, x0: float, width: float, cursor: float, height: float) -> float:
        band = pymupdf.Rect(x0, cursor, x0 + width, cursor + height)
        for rect in obstacles:
            if band.intersects(rect) and rect.y1 > cursor:
                cursor = rect.y1 + 6
                band = pymupdf.Rect(x0, cursor, x0 + width, cursor + height)
        return cursor

    def _columns(self, blocks: list[_Block], page) -> list[list[_Block]]:
        ordered = sorted(blocks, key=lambda b: b.rect.x0)
        columns: list[list[_Block]] = []
        for block in ordered:
            if columns and block.rect.x0 < max(b.rect.x1 for b in columns[-1]) - 10:
                columns[-1].append(block)
            else:
                columns.append([block])
        for column in columns:
            column.sort(key=lambda b: b.rect.y0)
        return columns

    # ------------------------------------------------------------------ html
    def _html(self, block: _Block) -> str:
        raw = self._translations.get(block.seg_id, "")
        parts = split_tagged(raw, len(block.spans))
        if parts is None:
            return f"<p>{H.escape(strip_tags(raw))}</p>"
        out = []
        for span, text in zip(block.spans, parts):
            color = f"#{span.color & 0xFFFFFF:06x}"
            style = f"color:{color};"
            if span.bold:
                style += "font-weight:bold;"
            if span.italic:
                style += "font-style:italic;"
            out.append(f'<span style="{style}">{H.escape(text)}</span>')
        return "<p>" + "".join(out) + "</p>"

    def _css(self, block: _Block) -> str:
        size = max((s.size for s in block.spans), default=11)
        align = ""
        if block.kind == "cell" and len(strip_tags(self._translations.get(block.seg_id, ""))) <= 12:
            align += "white-space:nowrap;"
        if block.kind == "text" and block.rect.width < self.doc[0].rect.width * 0.6:
            center = (block.rect.x0 + block.rect.x1) / 2
            if abs(center - self.doc[0].rect.width / 2) < 8:
                align = "text-align:center;"
        return (
            f"* {{font-family: sans-serif; font-size: {size:.2f}px; line-height: 1.25;"
            f" margin: 0; {align}}}"
        )

    @staticmethod
    def _measure(html: str, css: str, width: float) -> float:
        story = pymupdf.Story(html, user_css=css)
        return story.fit_height(width, 1, 10000).rect.height

    def _place(self, page, rect, html: str, block: _Block, scale_low: float, fittable: bool) -> None:
        """锚定块（单元格/页眉页脚）：按需要的高度向下扩一点，避免 htmlbox 判定放不下而不画。"""
        css = self._css(block)
        need = self._measure(html, css, max(20.0, rect.width + 4))
        box = pymupdf.Rect(rect.x0, rect.y0, rect.x1 + 4, max(rect.y1, rect.y0 + need + 1))
        self._place_raw(page, box, html, css, scale_low=scale_low)

    @staticmethod
    def _place_raw(page, rect, html: str, css: str, scale_low: float = 0.0) -> None:
        page.insert_htmlbox(rect, html, css=css, scale_low=scale_low)

    def _split_to_fit(self, block: _Block, css: str, width: float, max_h: float):
        text = strip_tags(self._translations.get(block.seg_id, ""))
        sentences = [s for s in SENTENCE_RE.split(text) if s.strip()]
        chunks, buf = [], ""
        for sentence in sentences:
            candidate = (buf + " " + sentence).strip()
            html = f"<p>{H.escape(candidate)}</p>"
            height = self._measure(html, css, width)
            if height <= max_h:
                buf = candidate
            else:
                if buf:
                    chunks.append((f"<p>{H.escape(buf)}</p>", self._measure(f"<p>{H.escape(buf)}</p>", css, width)))
                buf = sentence
        if buf:
            chunks.append((f"<p>{H.escape(buf)}</p>", self._measure(f"<p>{H.escape(buf)}</p>", css, width)))
        return chunks or [(f"<p>{H.escape(text)}</p>", max_h)]


def _span(d) -> _Span:
    return _span_from_dict(d)


def _span_from_dict(s) -> _Span:
    return _Span(
        text=s["text"].strip(),
        font=s.get("font", ""),
        size=float(s.get("size", 11)),
        color=int(s.get("color", 0)),
        flags=int(s.get("flags", 0)),
    )


def _join(spans: list[_Span]) -> str:
    out = ""
    for span in spans:
        if not out:
            out = span.text
            continue
        if _cjk(out[-1]) or _cjk(span.text[:1]):
            out += span.text
        else:
            out += " " + span.text
    return out


def _cjk(ch: str) -> bool:
    return bool(ch) and ("\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff")


def _merge_spans(spans: list[_Span]) -> list[_Span]:
    merged: list[_Span] = []
    for span in spans:
        if merged and (merged[-1].font, merged[-1].size, merged[-1].color, merged[-1].flags) == (
            span.font, span.size, span.color, span.flags
        ):
            merged[-1].text += " " + span.text
        else:
            merged.append(span)
    return merged
