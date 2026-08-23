#!/usr/bin/env python3
"""Print (or install) the MCP config for Claude Code and Claude Desktop.

    python setup_mcp.py            # show the config for both clients
    python setup_mcp.py --write    # merge it into both, backing up first

Paths are resolved from this file's location, so the output is ready to paste.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ADVISOR_SRC = REPO / "stock-advisor" / "src"


def block(mode: str = "auto") -> dict:
    return {
        "command": "python",
        "args": ["-m", "advisor_mcp.server"],
        "cwd": str(HERE),
        "env": {
            "PYTHONPATH": f"{HERE}{__import__('os').pathsep}{ADVISOR_SRC}",
            "ADVISOR_MODE": mode,          # auto | local | remote
            "ADVISOR_API_BASE": "https://advisor-360-live.netlify.app",
        },
    }


def targets() -> dict[str, Path]:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    elif system == "Windows":
        desktop = Path(__import__("os").environ.get("APPDATA", home)) / "Claude/claude_desktop_config.json"
    else:
        desktop = home / ".config/Claude/claude_desktop_config.json"
    return {"Claude Code": home / ".claude.json", "Claude Desktop": desktop}


def merge(path: Path, cfg: dict) -> str:
    existing = {}
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
        shutil.copy2(path, backup)
        try:
            existing = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError:
            return f"SKIPPED {path} — existing file is not valid JSON; merge by hand"
    servers = existing.setdefault("mcpServers", {})
    replaced = "advisor" in servers
    servers["advisor"] = cfg
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n")
    return f"{'updated' if replaced else 'added'} 'advisor' in {path}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="merge into the real config files")
    ap.add_argument("--mode", default="auto", choices=["auto", "local", "remote"])
    args = ap.parse_args()
    cfg = block(args.mode)

    if not args.write:
        print("Add this under \"mcpServers\" in each client's config:\n")
        print(json.dumps({"mcpServers": {"advisor": cfg}}, indent=2))
        print("\nConfig locations on this machine:")
        for client, path in targets().items():
            print(f"  {client:<15} {path}{'' if path.exists() else '   (will be created)'}")
        print("\nRe-run with --write to merge it in automatically (originals are backed up).")
        return

    for client, path in targets().items():
        print(f"{client}: {merge(path, cfg)}")
    print("\nRestart both clients, then ask: \"What does the advisor say about RELIANCE?\"")


if __name__ == "__main__":
    main()
