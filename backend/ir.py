from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    """一段可翻译文本，以及把它写回原文档所需的上下文。"""

    id: str
    kind: str
    text: str                      # 送模型的文本，多格式段落带 [[n]] 标记
    plain: str                     # 去掉标记的纯文本
    span_count: int = 1            # 格式片段数（docx 的 run 分组）
    context: dict = field(default_factory=dict)
    translated: str | None = None
    status: str = "pending"        # pending | translated | kept | failed

    def __post_init__(self) -> None:
        if not self.plain:
            self.plain = self.text


@dataclass
class DocumentReport:
    segments: int = 0
    translated: int = 0
    kept: int = 0
    format_fallback: int = 0       # 标签没守住、降级成整段单格式的次数
    qa_issues: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "segments": self.segments,
            "translated": self.translated,
            "kept_source": self.kept,
            "format_fallback": self.format_fallback,
            "qa_issues": len(self.qa_issues),
            "qa_samples": self.qa_issues[:10],
        }
