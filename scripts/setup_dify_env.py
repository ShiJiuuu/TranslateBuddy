#!/usr/bin/env python3
"""把 Dify 的 .env 调到 TranslateBuddy 需要的量级。

用法:
    python scripts/setup_dify_env.py /path/to/dify/docker          # 写入（自动备份）
    python scripts/setup_dify_env.py /path/to/dify/docker --check   # 只检查
    python scripts/setup_dify_env.py /path/to/dify/docker --dry-run # 只预览
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

VALUES = {
    "UPLOAD_FILE_SIZE_LIMIT": "500",              # MB
    "NGINX_CLIENT_MAX_BODY_SIZE": "500M",
    "PLUGIN_MAX_FILE_SIZE": "629145600",          # 600 MB：插件产出文件
    "PLUGIN_MAX_EXECUTION_TIMEOUT": "1800",       # 秒
    "WORKFLOW_MAX_EXECUTION_TIME": "7200",        # 秒
    "APP_MAX_EXECUTION_TIME": "7200",             # 秒
    "NGINX_PROXY_READ_TIMEOUT": "7200s",
}


def read_env(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def current(lines: list[str], key: str) -> str | None:
    prefix = key + "="
    value = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(prefix):
            value = stripped[len(prefix):]
    return value


def apply(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + "="
    out, done = [], False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and stripped.startswith(prefix):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        if out and out[-1].strip():
            out.append("")
        out.append("# TranslateBuddy")
        out.append(f"{key}={value}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dify_docker_dir", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env_path = args.dify_docker_dir / ".env"
    if not env_path.exists():
        print(f"找不到 {env_path}，请确认指向 dify/docker 目录", file=sys.stderr)
        return 2

    lines = read_env(env_path)
    changed = []

    for key, value in VALUES.items():
        now = current(lines, key)
        if now == value:
            continue
        changed.append((key, now, value))
        lines = apply(lines, key, value)

    if args.check:
        for key, now, want in changed:
            print(f"  {key}: {now or '(未设置)'} -> {want}")
        print("全部达标" if not changed else f"{len(changed)} 项未达标")
        return 0 if not changed else 1

    if not changed:
        print("已经是目标值，无需修改")
        return 0

    for key, now, want in changed:
        print(f"  {key}: {now or '(未设置)'} -> {want}")

    if args.dry_run:
        print("dry-run，未写入")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = env_path.parent / (env_path.name + f".bak-{stamp}")
    shutil.copy2(env_path, backup)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {env_path}（备份 {backup.name}）")
    print("下一步：cd dify/docker && docker compose up -d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
