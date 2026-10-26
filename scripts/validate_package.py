#!/usr/bin/env python3
"""校验 .difypkg 的资源布局，避免上传时才报 "file not found: icon.svg"。

规则（与 plugin_daemon 的 decoder 一致）：
  - 资源必须放在包内 _assets/ 下，YAML 里的 icon 写相对路径（icon.svg）
  - manifest / provider / tool 引用的文件都要在包里
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import yaml


def load(zf: zipfile.ZipFile, name: str) -> dict:
    try:
        return yaml.safe_load(zf.read(name)) or {}
    except KeyError:
        raise SystemExit(f"缺少 {name}") from None


def check_icon(zf: zipfile.ZipFile, icon: str | None, where: str, errors: list[str]) -> None:
    if not icon:
        return
    path = f"_assets/{icon}"
    if path not in zf.namelist():
        errors.append(f"{where}: 引用 {icon}，但包里没有 {path}")


def main(path: str) -> int:
    pkg = Path(path)
    errors: list[str] = []
    with zipfile.ZipFile(pkg) as zf:
        names = set(zf.namelist())
        manifest = load(zf, "manifest.yaml")

        check_icon(zf, manifest.get("icon"), "manifest.icon", errors)
        check_icon(zf, manifest.get("icon_dark"), "manifest.icon_dark", errors)

        for provider_path in manifest.get("plugins", {}).get("tools", []) or []:
            if provider_path not in names:
                errors.append(f"manifest 引用 provider {provider_path}，但包里没有")
                continue
            provider = load(zf, provider_path)
            identity = provider.get("identity", {}) or {}
            check_icon(zf, identity.get("icon"), f"{provider_path}:identity.icon", errors)
            source = (provider.get("extra", {}) or {}).get("python", {}).get("source")
            if source and source not in names:
                errors.append(f"{provider_path}: python source {source} 不存在")

            for tool_path in provider.get("tools", []) or []:
                if tool_path not in names:
                    errors.append(f"{provider_path} 引用 tool {tool_path}，但包里没有")
                    continue
                tool = load(zf, tool_path)
                ident = tool.get("identity", {}) or {}
                check_icon(zf, ident.get("icon"), f"{tool_path}:identity.icon", errors)
                src = (tool.get("extra", {}) or {}).get("python", {}).get("source")
                if src and src not in names:
                    errors.append(f"{tool_path}: python source {src} 不存在")

        assets = [n for n in names if n.startswith("_assets/")]
        print(f"包: {pkg}  ({pkg.stat().st_size / 1024:.1f} KB, {len(names)} 个文件)")
        print(f"资源: {', '.join(assets) or '(无)'}")

    if errors:
        print("\n校验失败:")
        for err in errors:
            print("  -", err)
        return 1
    print("校验通过")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "dist/translate_buddy-0.0.2.difypkg"
    raise SystemExit(main(target))
