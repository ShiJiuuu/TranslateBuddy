from __future__ import annotations

import time

from dify_plugin import Tool
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from backend.ir import Segment
from backend.jobs import JobStore
from backend.translator import BatchConfig, load_glossary, translate_segments


class TranslateShardTool(Tool):
    def _invoke(self, tool_parameters: dict):
        job_id = tool_parameters.get("job_id")
        index = int(tool_parameters.get("shard_index", -1))
        model = tool_parameters.get("model")
        force = bool(tool_parameters.get("force"))
        if not model:
            raise ValueError("需要选择一个模型")

        owner = getattr(self.runtime, "user_id", None) or "anon"
        store = JobStore()
        job = store.load(job_id, owner)
        if not 0 <= index < len(job.shards):
            raise ValueError(f"分片序号超出范围：{index}（共 {len(job.shards)} 片）")

        model_id = f"{model.get('provider')}/{model.get('model')}" if isinstance(model, dict) else str(model)
        digest = store.shard_digest(job, index, model_id)

        cached = store.read_shard(job, index)
        if cached and cached.get("digest") == digest and not force:
            stats = cached.get("stats", {})
            yield self.create_text_message(f"分片 {index} 已完成，跳过")
            yield self.create_json_message({"shard_index": index, "cached": True, **stats})
            return

        glossary = None
        glossary_path = job.dir / "glossary.csv"
        if glossary_path.exists():
            try:
                glossary = load_glossary(glossary_path.read_bytes())
            except Exception:
                glossary = None

        segments = [
            Segment(
                id=item["id"],
                kind="job_segment",
                text=item["text"],
                plain=item.get("plain") or item["text"],
                context=item.get("context") or {},
            )
            for item in job.shard_segments(index)
        ]

        started = time.time()
        translations = translate_segments(
            segments,
            self._make_invoke(model),
            target_lang=job.meta["target_lang"],
            source_lang=job.meta.get("source_lang", "auto"),
            glossary=glossary,
            config=BatchConfig(),
        )
        elapsed = round(time.time() - started, 1)
        stats = {
            "segments": len(segments),
            "translated": len(translations),
            "kept": len(segments) - len(translations),
            "elapsed_seconds": elapsed,
        }
        store.write_shard(job, index, digest, translations, stats)

        yield self.create_text_message(
            f"分片 {index}：{stats['translated']}/{stats['segments']} 段，耗时 {elapsed}s"
        )
        yield self.create_json_message({"shard_index": index, "cached": False, **stats})

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
