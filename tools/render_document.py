from __future__ import annotations

import tempfile
from pathlib import Path

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from backend.formats import MIME, open_document
from backend.jobs import JobStore


class RenderDocumentTool(Tool):
    def _invoke(self, tool_parameters: dict):
        job_id = tool_parameters.get("job_id")
        owner = getattr(self.runtime, "user_id", None) or "anon"
        store = JobStore()
        job = store.load(job_id, owner)

        suffix = job.meta["suffix"]
        source = job.dir / f"source{suffix}"
        doc = open_document(source)
        translations, missing = store.collect(job)

        applied = 0
        fallback = 0
        for seg in doc.segments:
            text = translations.get(seg.id)
            if not text:
                continue
            if not doc.apply(seg.id, text):
                fallback += 1
            applied += 1

        out_name = tool_parameters.get("output_name") or (
            f"{Path(job.meta['source_name']).stem}.{job.meta['target_lang']}{suffix}"
        )
        out_name = Path(out_name).name
        if not Path(out_name).suffix:
            out_name += suffix

        with tempfile.TemporaryDirectory(prefix="translatebuddy_") as workdir:
            output = doc.save(Path(workdir) / out_name)
            blob = output.read_bytes()

        yield self.create_blob_message(
            blob=blob,
            meta={"mime_type": MIME.get(suffix, "application/octet-stream"), "filename": out_name},
        )
        yield self.create_text_message(
            f"回写完成：{applied}/{len(doc.segments)} 段"
            + (f"，缺 {len(missing)} 个分片" if missing else "")
            + (f"，{fallback} 段格式降级" if fallback else "")
        )
        payload = {
            "output_filename": out_name,
            "segments": len(doc.segments),
            "applied": applied,
            "missing_shards": missing,
            "format_fallback": fallback,
        }
        layout_report = getattr(doc, "report", None)
        if layout_report:
            payload["layout"] = layout_report
        yield self.create_json_message(payload)
