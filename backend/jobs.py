"""作业化：解析一次 → 分片翻译 → 统一回写。

大文档不能塞进一次插件调用（默认 600s，最长 1800s），所以把"解析结果"和
"分片译文"落到插件工作目录，让工作流按分片驱动、失败可续跑。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

TTL_SECONDS = 24 * 3600
DEFAULT_ITEMS = 60
DEFAULT_CHARS = 8000


def jobs_root() -> Path:
    override = os.environ.get("TRANSLATE_BUDDY_HOME")
    if override:
        return Path(override) / "jobs"
    base = os.environ.get("PLUGIN_STORAGE_LOCAL_ROOT") or "/tmp/translate_buddy"
    return Path(base) / "translate_buddy" / "jobs"


@dataclass
class Job:
    job_id: str
    dir: Path
    meta: dict
    segments: list[dict]
    shards: list[list[str]]

    def segment_by_id(self, segment_id: str) -> dict | None:
        for seg in self.segments:
            if seg["id"] == segment_id:
                return seg
        return None

    def shard_segments(self, index: int) -> list[dict]:
        ids = self.shards[index]
        by_id = {s["id"]: s for s in self.segments}
        return [by_id[i] for i in ids if i in by_id]


class JobStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else jobs_root()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            # 插件容器里 /app/storage 不可写时退回临时目录，作业会随容器重启丢失
            fallback = Path(tempfile.gettempdir()) / "translate_buddy" / "jobs"
            fallback.mkdir(parents=True, exist_ok=True)
            log.warning("job root %s not writable, falling back to %s", self.root, fallback)
            self.root = fallback

    # ------------------------------------------------------------------ create
    def create(
        self,
        source: Path,
        source_name: str,
        target_lang: str,
        source_lang: str,
        owner: str,
        shard_items: int = DEFAULT_ITEMS,
        shard_chars: int = DEFAULT_CHARS,
    ) -> Job:
        self.cleanup()
        job_id = uuid.uuid4().hex
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)

        suffix = Path(source_name).suffix.lower()
        shutil.copy2(source, job_dir / f"source{suffix}")

        from .formats import open_document

        doc = open_document(job_dir / f"source{suffix}")
        segments = [
            {
                "id": s.id,
                "text": s.text,
                "plain": s.plain,
                "context": s.context,
            }
            for s in doc.segments
        ]
        shards = _plan(segments, shard_items, shard_chars)

        meta = {
            "job_id": job_id,
            "owner": owner,
            "source_name": source_name,
            "suffix": suffix,
            "target_lang": target_lang,
            "source_lang": source_lang,
            "created_at": time.time(),
            "segments": len(segments),
            "shards": len(shards),
        }
        _write_json(job_dir / "meta.json", meta)
        _write_json(job_dir / "segments.json", segments)
        _write_json(job_dir / "shards.json", shards)
        return Job(job_id, job_dir, meta, segments, shards)

    # -------------------------------------------------------------------- load
    def load(self, job_id: str, owner: str | None = None) -> Job:
        if not job_id or len(job_id) != 32 or not all(c in "0123456789abcdef" for c in job_id):
            raise ValueError("job_id 不合法")
        job_dir = self.root / job_id
        if not job_dir.exists():
            raise ValueError("作业不存在或已过期（默认保留 24 小时）")
        meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
        if owner and meta.get("owner") and meta["owner"] != owner:
            raise ValueError("无权访问该作业")
        segments = json.loads((job_dir / "segments.json").read_text(encoding="utf-8"))
        shards = json.loads((job_dir / "shards.json").read_text(encoding="utf-8"))
        return Job(job_id, job_dir, meta, segments, shards)

    # ------------------------------------------------------------------ shards
    def shard_digest(self, job: Job, index: int, model_id: str) -> str:
        payload = json.dumps(
            {
                "target": job.meta["target_lang"],
                "model": model_id,
                "items": [s["text"] for s in job.shard_segments(index)],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def read_shard(self, job: Job, index: int) -> dict | None:
        path = job.dir / f"shard_{index:03d}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_shard(self, job: Job, index: int, digest: str, translations: dict[str, str], stats: dict) -> None:
        path = job.dir / f"shard_{index:03d}.json"
        tmp = path.with_suffix(".tmp")
        _write_json(tmp, {"digest": digest, "translations": translations, "stats": stats})
        tmp.replace(path)

    def collect(self, job: Job) -> tuple[dict[str, str], list[int]]:
        merged: dict[str, str] = {}
        missing = []
        for index in range(len(job.shards)):
            data = self.read_shard(job, index)
            if not data:
                missing.append(index)
                continue
            merged.update(data.get("translations", {}))
        return merged, missing

    # ----------------------------------------------------------------- cleanup
    def cleanup(self) -> None:
        cutoff = time.time() - TTL_SECONDS
        try:
            for child in self.root.iterdir():
                if child.is_dir() and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def _plan(segments: list[dict], max_items: int, max_chars: int) -> list[list[str]]:
    shards: list[list[str]] = []
    current: list[str] = []
    size = 0
    for seg in segments:
        length = len(seg["text"])
        if current and (len(current) >= max_items or size + length > max_chars):
            shards.append(current)
            current, size = [], 0
        current.append(seg["id"])
        size += length
    if current:
        shards.append(current)
    return shards


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
