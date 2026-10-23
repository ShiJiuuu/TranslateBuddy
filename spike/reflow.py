"""PDF 可读优先重排：验证「测量高度 → 游标排版 → 溢出插页」这条链是否成立。"""
import html as H
import os
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
SRC = HERE / "samples" / "sample.pdf"
OUT = HERE / "out"

FONT_CSS = "font-family: sans-serif; line-height: 1.25; margin: 0;"


def block_html(block) -> str:
    parts = []
    for line in block["lines"]:
        spans = []
        for sp in line["spans"]:
            if not sp["text"].strip():
                continue
            t = H.escape(sp["text"])
            if "Bold" in sp["font"] or "HeBo" in sp["font"]:
                t = f"<b>{t}</b>"
            elif "Italic" in sp["font"] or "It" in sp["font"]:
                t = f"<i>{t}</i>"
            color = f"#{sp['color'] & 0xFFFFFF:06x}"
            spans.append(f'<span style="color:{color}">{t}</span>')
        if spans:
            parts.append("".join(spans))
    return "<p>" + "<br/>".join(parts) + "</p>"


def reflow(src: Path, dst: Path, expand: int = 1) -> dict:
    doc = pymupdf.open(src)
    stats = {"inserted_pages": 0, "blocks": 0}

    for page in list(doc):
        blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
        if not blocks:
            continue
        items = []
        for b in blocks:
            text = " ".join(
                sp["text"] for line in b["lines"] for sp in line["spans"] if sp["text"].strip()
            )
            if not text:
                continue
            size = max(sp["size"] for line in b["lines"] for sp in line["spans"])
            items.append({"rect": pymupdf.Rect(b["bbox"]), "html": block_html(b), "size": size, "text": text})

        items.sort(key=lambda x: (round(x["rect"].y0 / 6), x["rect"].x0))
        x0 = min(i["rect"].x0 for i in items)
        x1 = max(i["rect"].x1 for i in items)
        width = x1 - x0
        top = 72
        bottom = page.rect.height - 72

        for it in items:
            page.add_redact_annot(it["rect"], fill=False, cross_out=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)

        cursor = min(i["rect"].y0 for i in items)
        cur_page = page
        for it in items:
            body = it["html"]
            if expand > 1:
                body = body.replace("<p>", "<p>" + "<b>EXPANDED</b> " * (expand - 1))
            css = "* {%s font-size: %.1fpx;}" % (FONT_CSS, it["size"])
            st = pymupdf.Story(body, user_css=css)
            need = st.fit_height(width, 1, 4000).rect.height
            if cursor + need > bottom:
                stats["inserted_pages"] += 1
                new = doc.new_page(pno=cur_page.number + 1,
                                   width=page.rect.width, height=page.rect.height)
                cur_page = new
                cursor = top
            box = pymupdf.Rect(x0, cursor, x0 + width, cursor + need)
            cur_page.insert_htmlbox(box, body, css=css, scale_low=0)
            cursor += need + 6
            stats["blocks"] += 1

    doc.subset_fonts()
    doc.save(dst, garbage=4, deflate=True)
    stats["pages"] = len(pymupdf.open(dst))
    stats["bytes"] = os.path.getsize(dst)
    return stats


if __name__ == "__main__":
    print("normal:", reflow(SRC, OUT / "reflow_normal.pdf"))
    print("expand:", reflow(SRC, OUT / "reflow_expand.pdf", expand=3))
    for name in ("reflow_normal", "reflow_expand"):
        d = pymupdf.open(OUT / f"{name}.pdf")
        for i, p in enumerate(d):
            p.get_pixmap(dpi=110).save(str(OUT / f"{name}_p{i+1}.png"))
        print(name, "pages", len(d))
