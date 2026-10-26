import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf

from backend.pdf_io import PdfDocument
from backend.tags import strip_tags

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
SRC = OUT / "m2_sample.pdf"

doc = pymupdf.open()
page = doc.new_page(width=595, height=842)
page.insert_text((72, 80), "Quarterly Report 2024", fontname="hebo", fontsize=18)
page.draw_line((72, 92), (523, 92), color=(0.8, 0.8, 0.8))

body1 = ("Revenue grew by 18 percent compared with the same period last year, driven by "
         "strong demand in the enterprise segment. Operating expenses remained flat as the "
         "team continued to invest in automation and customer support.")
page.insert_textbox(pymupdf.Rect(72, 110, 523, 220), body1, fontname="helv", fontsize=11, align=3)

rows = [("Metric", "Value"), ("Revenue", "1,240"), ("Cost", "880")]
y = 260
for i, (a, b) in enumerate(rows):
    page.draw_line((72, y + 20), (523, y + 20), color=(0.85, 0.85, 0.85))
    page.insert_text((80, y + 13), a, fontname="hebo" if i == 0 else "helv", fontsize=10.5)
    page.insert_text((300, y + 13), b, fontname="hebo" if i == 0 else "helv", fontsize=10.5)
    y += 24

body2 = ("We expect growth to continue in the next two quarters, supported by the pipeline "
         "and the expansion of the partner program in Europe and Asia.")
page.insert_textbox(pymupdf.Rect(72, 360, 523, 430), body2, fontname="helv", fontsize=11)

page.insert_text((72, 800), "Confidential - page 1", fontname="helv", fontsize=8, color=(0.5, 0.5, 0.5))
doc.save(SRC)

DICT = {
    "Quarterly Report 2024": "2024 年季度报告",
    "Revenue grew by 18 percent compared with the same period last year, driven by strong demand in the enterprise segment. Operating expenses remained flat as the team continued to invest in automation and customer support.":
        "受企业客户需求强劲推动，营收较去年同期增长 18%。团队持续投入自动化与客户支持，运营费用基本持平。",
    "We expect growth to continue in the next two quarters, supported by the pipeline and the expansion of the partner program in Europe and Asia.":
        "我们预计未来两个季度将继续增长，这得益于销售管道以及在欧洲和亚洲合作伙伴计划的扩张。",
    "Metric": "指标", "Value": "数值", "Revenue": "营收", "Cost": "成本",
    "Confidential - page 1": "机密 - 第 1 页",
}


def translate(text: str, expand: int = 0) -> str:
    plain = strip_tags(text)
    out = DICT.get(plain)
    if out is None:
        out = "译：" + plain
    if expand and len(plain) > 80:
        out = out + " " + ("This paragraph was expanded to simulate a longer target language. " * expand)
    return out


for expand in (0, 2):
    pdf = PdfDocument(SRC)
    for seg in pdf.segments:
        pdf.apply(seg.id, translate(seg.text, expand))
    dst = OUT / f"m2_out_{'plain' if not expand else 'expand'}.pdf"
    pdf.save(dst)
    d = pymupdf.open(dst)
    print(f"expand={expand} pages={len(d)} report={pdf.report} stats={pdf.stats}")
    print("  text:", repr(d[0].get_text()[:120]))
    for i, p in enumerate(d):
        p.get_pixmap(dpi=100).save(str(OUT / f"m2_{'plain' if not expand else 'expand'}_p{i+1}.png"))
