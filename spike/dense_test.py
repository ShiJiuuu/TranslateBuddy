import pymupdf
from pathlib import Path
from reflow import reflow

HERE = Path(__file__).parent
dense = HERE / "samples" / "dense.pdf"

doc = pymupdf.open()
page = doc.new_page(width=595, height=842)
y = 72
for i in range(26):
    text = (f"Paragraph {i + 1}. The team continued to invest in automation and customer support, "
            "while revenue growth stayed strong across the enterprise segment.")
    page.insert_textbox(pymupdf.Rect(72, y, 523, y + 60), text, fontname="helv", fontsize=10.5)
    y += 27
doc.save(dense)
print("dense page blocks:", len([b for b in pymupdf.open(dense)[0].get_text("dict")["blocks"] if b["type"] == 0]))

print("expand x2:", reflow(dense, HERE / "out" / "dense_expand.pdf", expand=2))
d = pymupdf.open(HERE / "out" / "dense_expand.pdf")
print("pages:", len(d))
for i, p in enumerate(d):
    p.get_pixmap(dpi=90).save(str(HERE / "out" / f"dense_expand_p{i+1}.png"))
    blocks = [b for b in p.get_text("dict")["blocks"] if b["type"] == 0]
    if blocks:
        print(f"  p{i+1}: {len(blocks)} blocks, y max {max(b['bbox'][3] for b in blocks):.0f}")
