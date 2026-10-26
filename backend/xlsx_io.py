"""XLSX 的 L2 就地改写：只动 sharedStrings / inlineStr 里的文字节点。

不用 openpyxl 保存——它会把整个工作簿重写，切片器、部分图表、条件格式扩展、
外部链接都有丢失风险，而且所有 XML 的命名空间顺序都会变。
"""
from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .ir import Segment

S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
S = "{%s}" % S_NS
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

SHARED = "xl/sharedStrings.xml"
SHEET_RE = re.compile(r"^xl/worksheets/sheet\d+\.xml$")


@dataclass
class _Target:
    part: str
    ts: list  # <t> 元素，按文档顺序


class XlsxDocument:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._entries: list[zipfile.ZipInfo] = []
        self._roots: dict[str, etree._Element] = {}
        self._segments: list[Segment] = []
        self._targets: dict[str, _Target] = {}
        self._changed: set[str] = set()
        self.stats = {"shared_strings": 0, "inline_strings": 0, "skipped": 0}
        self._load()
        self._parse()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        with zipfile.ZipFile(self.path) as zf:
            self._entries = zf.infolist()
            for info in self._entries:
                name = info.filename
                if name == SHARED or SHEET_RE.match(name):
                    self._roots[name] = etree.fromstring(zf.read(info))

    # ----------------------------------------------------------------- parse
    @property
    def segments(self) -> list[Segment]:
        return self._segments

    def _parse(self) -> None:
        shared = self._roots.get(SHARED)
        if shared is not None:
            for index, si in enumerate(shared.findall(S + "si")):
                ts = _text_nodes(si)
                text = "".join(t.text or "" for t in ts)
                if not ts or not LETTER_RE.search(text):
                    self.stats["skipped"] += 1
                    continue
                seg = Segment(
                    id=f"{SHARED}#si{index}",
                    kind="shared_string",
                    text=text,
                    plain=text,
                    context={"part": SHARED},
                )
                self._segments.append(seg)
                self._targets[seg.id] = _Target(SHARED, ts)
            self.stats["shared_strings"] = len(self._segments)

        for part, root in self._roots.items():
            if not part.startswith("xl/worksheets/"):
                continue
            for cell in root.iter(S + "c"):
                if cell.get("t") != "inlineStr":
                    continue
                if cell.find(S + "f") is not None:  # 公式单元格不碰
                    continue
                inline = cell.find(S + "is")
                if inline is None:
                    continue
                ts = _text_nodes(inline)
                text = "".join(t.text or "" for t in ts)
                if not ts or not LETTER_RE.search(text):
                    continue
                ref = cell.get("r") or "?"
                seg = Segment(
                    id=f"{part}!{ref}",
                    kind="inline_string",
                    text=text,
                    plain=text,
                    context={"part": part, "cell": ref},
                )
                self._segments.append(seg)
                self._targets[seg.id] = _Target(part, ts)
                self.stats["inline_strings"] += 1

    # ----------------------------------------------------------------- apply
    def apply(self, segment_id: str, translated: str) -> bool:
        target = self._targets.get(segment_id)
        if target is None or not translated:
            return False

        first = target.ts[0]
        first.text = translated
        if translated != translated.strip():
            first.set(XML_SPACE, "preserve")
        elif XML_SPACE in first.attrib:
            del first.attrib[XML_SPACE]
        for extra in target.ts[1:]:
            extra.text = ""
        self._changed.add(target.part)
        return True

    # ------------------------------------------------------------------ save
    def save(self, dst: Path) -> Path:
        dst = Path(dst)
        with zipfile.ZipFile(self.path) as zin, zipfile.ZipFile(dst, "w") as zout:
            for info in self._entries:
                if info.filename in self._changed:
                    data = etree.tostring(
                        self._roots[info.filename],
                        xml_declaration=True,
                        encoding="UTF-8",
                        standalone=True,
                    )
                    zout.writestr(info, data)
                else:
                    with zin.open(info) as src, zout.open(info, "w") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
        return dst

    # ---------------------------------------------------------------- helper
    def sheet_names(self) -> list[str]:
        """仅用于报告：从 workbook.xml 读工作表名。"""
        wb = self._roots.get("xl/workbook.xml")
        if wb is None:
            return []
        return [s.get("name", "") for s in wb.iter(S + "sheet")]


def _text_nodes(node) -> list:
    """收集文本节点，跳过日文注音 <rPh> 里的内容。"""
    out = []

    def walk(el) -> None:
        for child in el:
            local = etree.QName(child).localname
            if local == "rPh":
                continue
            if local == "t":
                out.append(child)
                continue
            walk(child)

    walk(node)
    return out
