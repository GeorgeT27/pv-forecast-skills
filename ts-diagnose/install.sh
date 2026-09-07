#!/usr/bin/env bash
# ts-diagnose 安装：把包内文件链接进 Claude Code 目录并合并钩子。
#   bash install.sh              安装/刷新（幂等）
#   bash install.sh --check      只校验
#   bash install.sh --uninstall  卸载
#   bash install.sh --copy       agents/workflows 用复制而非 symlink
# 环境变量 CLAUDE_HOME 覆盖 ~/.claude（测试用）。
set -euo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_HOME:-$HOME/.claude}"
MODE="install"; COPY=0
for a in "$@"; do
  case "$a" in
    --check) MODE=check ;;
    --uninstall) MODE=uninstall ;;
    --copy) COPY=1 ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

# macOS 自带 bash 3.2：空数组展开在 set -u 下会报错，统一用 ${arr[@]+"${arr[@]}"} 写法。
cards=()
for f in "$PKG"/agents/*-compute.md "$PKG"/agents/*-worker.md "$PKG"/agents/*-baseline.md; do
  [ -e "$f" ] && cards+=("$f")
done
flows=()
for f in "$PKG"/workflows/*.js; do [ -e "$f" ] && flows+=("$f"); done

place() {  # place <src> <dst>
  if [ "$COPY" = 1 ]; then rm -f "$2"; cp "$1" "$2"; else ln -sfn "$1" "$2"; fi
}

case "$MODE" in
  install)
    mkdir -p "$CLAUDE/skills" "$CLAUDE/agents" "$CLAUDE/workflows"
    ln -sfn "$PKG" "$CLAUDE/skills/ts-diagnose"
    rm -f "$CLAUDE/skills/ts-diagnose-v2"
    for f in ${cards[@]+"${cards[@]}"}; do place "$f" "$CLAUDE/agents/$(basename "$f")"; done
    for f in ${flows[@]+"${flows[@]}"}; do place "$f" "$CLAUDE/workflows/$(basename "$f")"; done
    python3 "$PKG/hooks/install_hooks.py" --settings "$CLAUDE/settings.json"
    echo "installed → $CLAUDE   (verify: bash \"$PKG/install.sh\" --check)"
    ;;
  uninstall)
    rm -f "$CLAUDE/skills/ts-diagnose"
    for f in ${cards[@]+"${cards[@]}"}; do rm -f "$CLAUDE/agents/$(basename "$f")"; done
    for f in ${flows[@]+"${flows[@]}"}; do rm -f "$CLAUDE/workflows/$(basename "$f")"; done
    python3 "$PKG/hooks/install_hooks.py" --settings "$CLAUDE/settings.json" --uninstall
    echo "uninstalled from $CLAUDE"
    ;;
  check)
    ok=1
    chk() { if [ -e "$1" ]; then echo "  ✓ $1"; else echo "  ✗ $1"; ok=0; fi; }
    echo "skill:";     chk "$CLAUDE/skills/ts-diagnose/SKILL.md"
    echo "agents:";    for f in ${cards[@]+"${cards[@]}"}; do chk "$CLAUDE/agents/$(basename "$f")"; done
    echo "workflows:"; for f in ${flows[@]+"${flows[@]}"}; do chk "$CLAUDE/workflows/$(basename "$f")"; done
    echo "hooks in $CLAUDE/settings.json:"
    for h in stage_probe.py gate_guard.py orient_reminder.py; do
      if grep -q "$h" "$CLAUDE/settings.json" 2>/dev/null; then echo "  ✓ $h"; else echo "  ✗ $h"; ok=0; fi
    done
    echo "selftests:"
    python3 "$PKG/hooks/gate_guard.py" --selftest >/dev/null 2>&1 && echo "  ✓ gate_guard" || { echo "  ✗ gate_guard"; ok=0; }
    python3 "$PKG/hooks/stage_probe.py" --selftest >/dev/null 2>&1 && echo "  ✓ stage_probe" || { echo "  ✗ stage_probe"; ok=0; }
    if [ "$ok" = 1 ]; then echo "ALL OK"; else echo "CHECK FAILED"; exit 1; fi
    ;;
esac
