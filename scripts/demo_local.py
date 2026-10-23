#!/usr/bin/env python3
"""不连 Dify 也能跑通的端到端演示：生成样例 docx → 解析 → 假翻译 → 就地回写。

真跑时把 stub_invoke 换成 session.model.llm.invoke 即可（见 tools/translate_document.py）。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document
from docx.shared import RGBColor

from backend.docx_io import DocxDocument
from backend.qa import check
from backend.tags import strip_tags
from backend.translator import translate_segments

DICT = {
    "Quarterly Report": "季度报告",
    "Revenue grew by 18 percent": "营收同比增长 18%",
    "Operating expenses remained flat": "运营费用基本持平",
    "enterprise segment": "企业客户",
    "Confidential": "机密",
    "Metric": "指标",
    "Value": "数值",
    "Revenue": "营收",
    "Cost": "成本",
}


def stub_invoke(system: str, user: str) -> str:
    import json

    payload = json.loads(user)
    items = []
    for item in payload["items"]:
        text = item["text"]
        for src in sorted(DICT, key=len, reverse=True):
            text = text.replace(src, DICT[src])
        items.append({"id": item["id"], "text": text})
    return json.dumps({"items": items}, ensure_ascii=False)


def build_sample(path: Path) -> None:
    doc = Document()
    doc.add_heading("Quarterly Report 2024", level=1)
    p = doc.add_paragraph()
    r1 = p.add_run("Revenue grew by 18 percent")
    r1.bold = True
    r1.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
    p.add_run(" compared with the same period last year, driven by strong demand in the ")
    r2 = p.add_run("enterprise segment")
    r2.italic = True
    p.add_run(".")
    doc.add_paragraph("Operating expenses remained flat.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Revenue"
    table.cell(1, 1).text = "1,240"
    doc.sections[0].header.paragraphs[0].text = "Confidential"
    doc.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, help="输入 docx；不填则生成样例")
    parser.add_argument("--out", type=Path, default=Path("demo_out.docx"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as td:
        src = args.src
        if src is None:
            src = Path(td) / "sample.docx"
            build_sample(src)
            print("已生成样例：", src)

        doc = DocxDocument(src)
        print(f"解析：{len(doc.segments)} 段可翻译文本")

        translations = translate_segments(doc.segments, stub_invoke, "zh-Hans")
        fallback = 0
        issues = []
        for seg in doc.segments:
            text = translations.get(seg.id)
            if not text:
                continue
            if not doc.apply(seg.id, text):
                fallback += 1
            issues.extend(check(seg.plain, strip_tags(text)))

        out = doc.save(args.out)
        print(f"回写完成：{len(translations)}/{len(doc.segments)} 段，格式降级 {fallback} 次，QA {len(issues)} 条")
        print("输出：", out.resolve())

    result = Document(args.out)
    for paragraph in result.paragraphs[:3]:
        if not paragraph.text.strip():
            continue
        print("\n段落：", paragraph.text)
        for run in paragraph.runs:
            if run.text:
                color = run.font.color.rgb if run.font.color and run.font.color.rgb else None
                print(f"   run={run.text!r} bold={run.bold} italic={run.italic} color={color}")


if __name__ == "__main__":
    main()
