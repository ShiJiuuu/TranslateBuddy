#!/usr/bin/env python3
"""把插件目录打成 .difypkg（不依赖 dify CLI）。

注意：图标等资源必须放在 _assets/ 下，YAML 里写相对路径（如 icon.svg），
这是 plugin_daemon 的约定；否则安装时会报 "file not found: icon.svg"。

用法:
    python scripts/package.py                 # 输出 dist/translate_buddy-<version>.difypkg
    python scripts/package.py --out /tmp/x.difypkg
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

INCLUDE = [
    "manifest.yaml",
    "main.py",
    "_assets",
    "requirements.txt",
    "provider",
    "tools",
    "backend",
]

EXCLUDE_DIRS = {"__pycache__", ".venv", ".git", "dist", "tests", "spike", "docs", "scripts"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".difypkg"}


def iter_files(base: Path):
    for name in INCLUDE:
        path = base / name
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_dir():
                    continue
                if any(part in EXCLUDE_DIRS for part in child.parts):
                    continue
                if child.suffix in EXCLUDE_SUFFIX:
                    continue
                yield child


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    version = manifest.get("version", "0.0.0")
    out = args.out or ROOT / "dist" / f"translate_buddy-{version}.difypkg"
    out.parent.mkdir(parents=True, exist_ok=True)

    files = list(iter_files(ROOT))
    if not any(f.name == "manifest.yaml" for f in files):
        raise SystemExit("manifest.yaml 不在包里，检查 INCLUDE")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=str(path.relative_to(ROOT)))

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"打包完成: {out}  ({out.stat().st_size / 1024:.1f} KB, {len(files)} 个文件)")
    print(f"sha256: {digest}")
    print("下一步: python scripts/validate_package.py " + str(out))
    print("安装: Dify 控制台 → 插件 → 安装插件 → 本地文件")


if __name__ == "__main__":
    main()
