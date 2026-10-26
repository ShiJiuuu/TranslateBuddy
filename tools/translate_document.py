from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

from dify_plugin import Tool
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from backend.errors import TranslationFailed, UnsupportedFormat
from backend.files import download_to
from backend.formats import MIME, PLANNED, open_document
from backend.ir import DocumentReport
from backend.qa import check
from backend.tags import strip_tags
from backend.translator import BatchConfig, load_glossary, translate_segments

log = logging.getLogger(__name__)

SUPPORTED = {".docx", ".xlsx", ".pdf"}


class TranslateDocumentTool(Tool):
    def _invoke(self, tool_parameters: dict):
        file = tool_parameters.get("file")
        if file is None:
            raise ValueError("缺少 file 参数")

        original_name = Path(getattr(file, "filename", None) or "document.docx").name
        suffix = Path(original_name).suffix.lower()
        if suffix not in SUPPORTED:
            planned = PLANNED.get(suffix)
            hint = f"，计划在 {planned} 支持" if planned else ""
            raise UnsupportedFormat(
                f"不支持的格式：{suffix or '(无扩展名)'}{hint}", {"ext": suffix}
            )

        target_lang = tool_parameters.get("target_lang") or "zh-Hans"
        source_lang = tool_parameters.get("source_lang") or "auto"
        model_config = tool_parameters.get("model")
        if not model_config:
            raise ValueError("需要选择一个模型")

        glossary = None
        glossary_file = tool_parameters.get("glossary")
        if glossary_file is not None:
            try:
                glossary = load_glossary(glossary_file.blob)
            except Exception as exc:  # 术语表坏了不应该阻断翻译
                log.warning("glossary parse failed: %s", exc)

        started = time.time()
        with tempfile.TemporaryDirectory(prefix="translatebuddy_") as workdir:
            work = Path(workdir)
            source = work / f"source{suffix}"
            yield self.create_text_message(f"下载 {original_name} …")
            download_to(file.url, source)

            yield self.create_text_message("解析文档结构 …")
            doc = open_document(source)
            segments = doc.segments
            if not segments:
                raise TranslationFailed("没有找到可翻译的文本（文档可能是空的或全是图片）")

            yield self.create_text_message(
                f"共 {len(segments)} 段，开始翻译为 {target_lang} …"
            )
            invoke = self._make_invoke(model_config)
            translations = translate_segments(
                segments,
                invoke,
                target_lang=target_lang,
                source_lang=source_lang,
                glossary=glossary,
                config=BatchConfig(),
            )

            report = DocumentReport(segments=len(segments))
            for seg in segments:
                translated = translations.get(seg.id)
                if not translated:
                    report.kept += 1
                    continue
                if not doc.apply(seg.id, translated):
                    report.format_fallback += 1
                report.translated += 1
                issues = check(seg.plain, strip_tags(translated))
                if issues:
                    report.qa_issues.append({"id": seg.id, "issues": issues})

            out_name = tool_parameters.get("output_name") or f"{Path(original_name).stem}.{target_lang}{suffix}"
            out_name = Path(out_name).name
            if not Path(out_name).suffix:
                out_name += suffix
            output = doc.save(work / out_name)
            blob = output.read_bytes()

        elapsed = round(time.time() - started, 1)
        summary = (
            f"完成：{report.translated}/{report.segments} 段已翻译"
            + (f"，{report.kept} 段保留原文" if report.kept else "")
            + (f"，{report.format_fallback} 段格式降级" if report.format_fallback else "")
            + (f"，{len(report.qa_issues)} 条 QA 提示" if report.qa_issues else "")
            + f"，耗时 {elapsed}s"
        )

        yield self.create_blob_message(
            blob=blob,
            meta={"mime_type": MIME[suffix], "filename": out_name},
        )
        yield self.create_text_message(summary)
        payload = {
            "output_filename": out_name,
            "elapsed_seconds": elapsed,
            "source_lang": source_lang,
            "target_lang": target_lang,
            **report.as_dict(),
        }
        layout_report = getattr(doc, "report", None)
        if layout_report:
            payload["layout"] = layout_report
        yield self.create_json_message(payload)

    def _make_invoke(self, model_config):
        def invoke(system_prompt: str, user_prompt: str) -> str:
            response = self.session.model.llm.invoke(
                model_config=model_config,
                prompt_messages=[
                    SystemPromptMessage(content=system_prompt),
                    UserPromptMessage(content=user_prompt),
                ],
                stream=False,
            )
            message = getattr(response, "message", None)
            content = getattr(message, "content", "") if message is not None else ""
            if isinstance(content, list):
                content = "".join(
                    getattr(part, "text", "") for part in content if getattr(part, "text", None)
                )
            return content or ""

        return invoke
