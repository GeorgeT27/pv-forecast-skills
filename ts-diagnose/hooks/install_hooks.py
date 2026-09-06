#!/usr/bin/env python3
"""把 hooks.json 声明的三条 ts-diagnose 钩子幂等合并进 Claude Code settings.json。

用法：
  python3 install_hooks.py                       # 合并进 ~/.claude/settings.json
  python3 install_hooks.py --settings <path>     # 指定文件（本仓库 .claude/settings.json 也用它）
  python3 install_hooks.py --uninstall           # 只删自家条目
  python3 install_hooks.py --dry-run             # 打印将写入的 JSON，不落盘
识别自家条目：命令串里出现三个脚本文件名之一。
"""
from __future__ import annotations
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SCRIPTS = ("stage_probe.py", "gate_guard.py", "orient_reminder.py")


def load_hooks_json():
    with open(os.path.join(HERE, "hooks.json"), encoding="utf-8") as f:
        return json.loads(f.read().replace("<PKG>", PKG))["hooks"]


def is_ours(entry):
    return any(any(s in (h.get("command") or "") for s in SCRIPTS)
               for h in (entry.get("hooks") or []))


def merge(settings, ours):
    hooks = settings.setdefault("hooks", {})
    for event, entries in ours.items():
        hooks[event] = [e for e in (hooks.get(event) or []) if not is_ours(e)] + entries
    return settings


def remove(settings):
    hooks = settings.get("hooks") or {}
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if not is_ours(e)]
        if not hooks[event]:
            del hooks[event]
    return settings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default=os.path.expanduser("~/.claude/settings.json"))
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    settings = {}
    if os.path.exists(a.settings):
        with open(a.settings, encoding="utf-8") as f:
            settings = json.load(f)
    settings = remove(settings) if a.uninstall else merge(settings, load_hooks_json())
    out = json.dumps(settings, ensure_ascii=False, indent=2)
    if a.dry_run:
        print(out)
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(a.settings)), exist_ok=True)
    with open(a.settings, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"{'removed' if a.uninstall else 'merged'} ts-diagnose hooks → {a.settings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
