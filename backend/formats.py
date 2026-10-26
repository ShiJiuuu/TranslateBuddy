from __future__ import annotations

from pathlib import Path

from .docx_io import DocxDocument
from .errors import UnsupportedFormat
from .xlsx_io import XlsxDocument

MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
}

PLANNED = {
    ".pdf": "M2",
    ".doc": "M4（需要 LibreOffice）",
    ".xls": "M4（需要 LibreOffice）",
}


def open_document(path: Path):
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return DocxDocument(path)
    if suffix == ".xlsx":
        return XlsxDocument(path)
    if suffix in PLANNED:
        raise UnsupportedFormat(f"{suffix} 计划在 {PLANNED[suffix]} 支持", {"ext": suffix})
    raise UnsupportedFormat(f"不支持的格式：{suffix or '(无扩展名)'}")
