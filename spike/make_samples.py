"""Generate minimal EN sample files used to validate format-preserving edit strategies."""
from pathlib import Path

import pymupdf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

OUT = Path(__file__).parent / "samples"
OUT.mkdir(parents=True, exist_ok=True)

DOCX_SENTENCES = {
    "Quarterly Report 2024": "2024 年季度报告",
    "Revenue grew by 18 percent compared with the same period last year, driven by strong demand in the enterprise segment.": "受企业客户需求强劲推动，营收较去年同期增长 18%。",
    "Operating expenses remained flat as the team continued to invest in automation and customer support.": "团队持续投入自动化与客户支持，运营费用基本持平。",
    "Outlook": "展望",
    "We expect growth to continue in the next two quarters.": "我们预计未来两个季度将继续增长。",
    "Metric": "指标",
    "Value": "数值",
    "Revenue": "营收",
    "Cost": "成本",
    "Margin": "利润率",
    "Confidential": "机密",
}


def make_docx(path: Path) -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    h = doc.add_heading("Quarterly Report 2024", level=1)

    p = doc.add_paragraph()
    r1 = p.add_run("Revenue grew by 18 percent")
    r1.bold = True
    r1.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
    p.add_run(" compared with the same period last year, driven by strong demand in the ")
    r2 = p.add_run("enterprise segment")
    r2.italic = True
    p.add_run(".")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    doc.add_paragraph("Operating expenses remained flat as the team continued to invest in automation and customer support.")

    doc.add_paragraph("Outlook", style="Heading 2")
    doc.add_paragraph("We expect growth to continue in the next two quarters.", style="List Bullet")

    table = doc.add_table(rows=3, cols=2)
    table.style = "Light Grid Accent 1"
    rows = [("Metric", "Value"), ("Revenue", "1,240"), ("Cost", "880")]
    for i, (a, b) in enumerate(rows):
        table.cell(i, 0).text = a
        table.cell(i, 1).text = b

    section = doc.sections[0]
    section.header.paragraphs[0].text = "Confidential"
    section.footer.paragraphs[0].text = "Page 1"

    doc.save(path)


def make_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    thin = Side(style="thin", color="B7B7B7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:C1")
    ws["A1"] = "Quarterly Report 2024"
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color="1F3864")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    for col, text in enumerate(["Metric", "Value", "Note"], start=1):
        c = ws.cell(row=3, column=col, value=text)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F5597")
        c.border = border
        c.alignment = Alignment(horizontal="center")

    ws["A4"], ws["B4"], ws["C4"] = "Revenue", 1240, "Enterprise segment strong"
    ws["A5"], ws["B5"], ws["C5"] = "Cost", 880, "Automation investment continued"
    ws["A6"], ws["B6"] = "Margin", "=B4-B5"
    ws["B4"].number_format = '#,##0 "USD"'
    ws["B5"].number_format = '#,##0 "USD"'
    ws["B6"].number_format = "0.0%"
    ws["C4"].alignment = Alignment(wrap_text=True, vertical="top")
    ws["C5"].alignment = Alignment(wrap_text=True, vertical="top")
    for row in ws.iter_rows(min_row=4, max_row=6, min_col=1, max_col=3):
        for c in row:
            c.border = border
    ws.column_dimensions["C"].width = 34

    wb.save(path)


def make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 90), "Quarterly Report 2024", fontname="hebo", fontsize=22)
    page.draw_line((72, 104), (523, 104), color=(0.75, 0.75, 0.75), width=0.8)

    body = "Revenue grew by 18 percent compared with the same period last year, driven by strong demand in the enterprise segment."
    page.insert_textbox(pymupdf.Rect(72, 130, 523, 200), body,
                        fontname="helv", fontsize=12, color=(0.1, 0.1, 0.1))
    body2 = "Operating expenses remained flat as the team continued to invest in automation and customer support."
    page.insert_textbox(pymupdf.Rect(72, 210, 523, 280), body2,
                        fontname="helv", fontsize=12, color=(0.1, 0.1, 0.1))

    rows = [("Metric", "Value"), ("Revenue", "1,240"), ("Cost", "880")]
    y = 320
    for i, (a, b) in enumerate(rows):
        page.draw_line((72, y + 22), (523, y + 22), color=(0.8, 0.8, 0.8), width=0.5)
        page.insert_text((80, y + 14), a, fontname="hebo" if i == 0 else "helv", fontsize=11)
        page.insert_text((300, y + 14), b, fontname="hebo" if i == 0 else "helv", fontsize=11)
        y += 26

    page.insert_text((72, 800), "Confidential", fontname="heit", fontsize=8, color=(0.5, 0.5, 0.5))
    doc.save(path)


if __name__ == "__main__":
    make_docx(OUT / "sample.docx")
    make_xlsx(OUT / "sample.xlsx")
    make_pdf(OUT / "sample.pdf")
    print("samples written to", OUT)
