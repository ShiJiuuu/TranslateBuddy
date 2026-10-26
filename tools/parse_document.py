from __future__ import annotations

import tempfile
from pathlib import Path

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from backend.files import download_to
from backend.jobs import JobStore


class ParseDocumentTool(Tool):
    def _invoke(self, tool_parameters: dict):
        file = tool_parameters.get("file")
        if file is None:
            raise ValueError("缺少 file 参数")

        original_name = Path(getattr(file, "filename", None) or "document.docx").name
        target_lang = tool_parameters.get("target_lang") or "zh-Hans"
        source_lang = tool_parameters.get("source_lang") or "auto"
        shard_items = int(tool_parameters.get("shard_items") or 60)
        shard_items = max(5, min(shard_items, 200))
        owner = getattr(self.runtime, "user_id", None) or "anon"

        with tempfile.TemporaryDirectory(prefix="translatebuddy_") as workdir:
            source = Path(workdir) / f"source{Path(original_name).suffix.lower()}"
            download_to(file.url, source)

            store = JobStore()
            job = store.create(
                source=source,
                source_name=original_name,
                target_lang=target_lang,
                source_lang=source_lang,
                owner=owner,
                shard_items=shard_items,
            )

            glossary_file = tool_parameters.get("glossary")
            if glossary_file is not None:
                try:
                    (job.dir / "glossary.csv").write_bytes(glossary_file.blob)
                except Exception:
                    pass

        shards = []
        by_id = {s["id"]: s for s in job.segments}
        for index, ids in enumerate(job.shards):
            chars = sum(len(by_id[i]["text"]) for i in ids if i in by_id)
            shards.append({"index": index, "segments": len(ids), "chars": chars})

        yield self.create_text_message(
            f"解析完成：{len(job.segments)} 段，切成 {len(job.shards)} 片，作业 {job.job_id}"
        )
        yield self.create_json_message(
            {
                "job_id": job.job_id,
                "source_name": original_name,
                "suffix": job.meta["suffix"],
                "target_lang": target_lang,
                "segments": len(job.segments),
                "shard_count": len(job.shards),
                "total_chars": sum(s["chars"] for s in shards),
                "shards": shards,
            }
        )
