from pathlib import Path

import pymupdf

from backend.pdf_io import PdfDocument


def build_pdf(path: Path, pages: int = 1) -> None:
    doc = pymupdf.open()
    for p in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 80), f"Quarterly Report 2024 - Part {p + 1}", fontname="hebo", fontsize=16)
        body = (
            "Revenue grew by 18 percent compared with the same period last year, driven by "
            "strong demand in the enterprise segment. Operating expenses remained flat as the "
            "team continued to invest in automation and customer support."
        )
        page.insert_textbox(pymupdf.Rect(72, 110, 523, 220), body, fontname="helv", fontsize=11)
        rows = [("Metric", "Value"), ("Revenue", "1,240"), ("Cost", "880")]
        y = 260
        for i, (a, b) in enumerate(rows):
            page.draw_line((72, y + 20), (523, y + 20), color=(0.85, 0.85, 0.85))
            page.insert_text((80, y + 13), a, fontname="hebo" if i == 0 else "helv", fontsize=10.5)
            page.insert_text((300, y + 13), b, fontname="hebo" if i == 0 else "helv", fontsize=10.5)
            y += 24
        page.insert_text((72, 800), "Confidential - page 1", fontname="helv", fontsize=8)
    doc.save(path)


ZH = {
    "Quarterly Report 2024 - Part 1": "2024 年季度报告（一）",
    "Quarterly Report 2024 - Part 2": "2024 年季度报告（二）",
    "Revenue grew by 18 percent compared with the same period last year, driven by strong demand in the enterprise segment. Operating expenses remained flat as the team continued to invest in automation and customer support.":
        "受企业客户需求强劲推动，营收较去年同期增长 18%。团队持续投入自动化与客户支持，运营费用基本持平。",
    "Metric": "指标",
    "Value": "数值",
    "Revenue": "营收",
    "Cost": "成本",
    "Confidential - page 1": "机密 - 第 1 页",
}


def translate(pdf: PdfDocument, overrides: dict[str, str] | None = None) -> None:
    overrides = overrides or {}
    for seg in pdf.segments:
        text = overrides.get(seg.id) or ZH.get(seg.plain) or ("译：" + seg.plain)
        pdf.apply(seg.id, text)


def test_table_and_footer_are_kept(tmp_path):
    src = tmp_path / "in.pdf"
    build_pdf(src)
    pdf = PdfDocument(src)
    assert pdf.stats["cells"] == 6
    assert pdf.stats["headers"] == 1

    translate(pdf)
    out = pdf.save(tmp_path / "out.pdf")
    text = pymupdf.open(out)[0].get_text()

    assert "指标" in text and "数值" in text
    assert "营收" in text and "成本" in text
    assert "机密 - 第 1 页" in text
    assert "2024 年季度报告（一）" in text
    assert "成\n本" not in text  # 单元格不该被拆成两行


def test_overflow_inserts_a_page(tmp_path):
    src = tmp_path / "in.pdf"
    build_pdf(src)
    pdf = PdfDocument(src)
    body = next(s for s in pdf.segments if s.plain.startswith("Revenue grew"))
    long_text = "这是一段被刻意拉长的译文，用来验证溢出时会插入续页而不是把文字画到页面外。" * 40
    for seg in pdf.segments:
        pdf.apply(seg.id, long_text if seg.id == body.id else "标题")
    out = pdf.save(tmp_path / "out.pdf")
    assert pdf.report["inserted_pages"] >= 1
    assert len(pymupdf.open(out)) >= 2


def test_second_page_stays_intact_when_first_flows(tmp_path):
    src = tmp_path / "in.pdf"
    build_pdf(src, pages=2)
    before = pymupdf.open(src)[1].get_text()

    pdf = PdfDocument(src)
    body = next(s for s in pdf.segments if s.plain.startswith("Revenue grew"))
    for seg in pdf.segments:
        if seg.id == body.id:
            pdf.apply(seg.id, "很长的译文。" * 60)
    pdf.save(tmp_path / "out.pdf")

    # 第二页可能被挤到后面，但内容不能丢
    texts = "".join(page.get_text() for page in pymupdf.open(tmp_path / "out.pdf"))
    first_line = before.strip().splitlines()[0]
    assert first_line in texts


def test_untagged_translation_falls_back(tmp_path):
    src = tmp_path / "in.pdf"
    build_pdf(src)
    pdf = PdfDocument(src)
    seg = next(s for s in pdf.segments if s.plain.startswith("Revenue grew"))
    # 该块只有一个 span，普通文本应视为合法
    assert pdf.apply(seg.id, "单片段译文") is True
