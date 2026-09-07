#!/usr/bin/env python3
"""ts-diagnose 回合开工软提醒（Claude Code UserPromptSubmit hook）。

作用：用户每提交一条消息时触发。若当前 cwd 下有诊断在跑，就往上下文注入一句
"本回合先跑 batch.py/orient.py 确认 phase/stage，别凭记忆推进"。不拦截、零误拦。
纯提醒，硬保证仍靠出口的 conclusion_gate Stop 钩子（gate_guard.py）。

边界：只在用户回合边界触发；agent 内部多轮不触发（CC 无"每 stage"事件）。
"""
from __future__ import annotations
import sys, os, json, glob


def find_active(cwd):
    """返回 ('batch', wd) / ('single', wd) / (None, None)。batch 优先。"""
    batch = glob.glob(os.path.join(cwd, "**", "batch_config.json"), recursive=True)
    if batch:
        return "batch", os.path.dirname(max(batch, key=os.path.getmtime))
    single = glob.glob(os.path.join(cwd, "**", "diagnose_config.json"), recursive=True)
    if single:
        return "single", os.path.dirname(max(single, key=os.path.getmtime))
    return None, None


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    cwd = inp.get("cwd") or os.getcwd()
    mode, wd = find_active(cwd)
    if not mode:
        sys.exit(0)  # 没有诊断在跑，不注入，静默

    if mode == "batch":
        msg = (f"[ts-diagnose 批量进行中] 本回合开工前先跑 "
               f"`python3 <ENGINE>/scripts/batch.py --workdir {wd}` 确认当前 Phase，"
               f"照它报的下一步办；状态以磁盘为准，不要凭记忆推进。")
    else:
        msg = (f"[ts-diagnose 诊断进行中] 本回合开工前先在 `{wd}` 跑 "
               f"`python3 <ENGINE>/scripts/orient.py` 确认当前 stage 与未答问题，"
               f"照它的行动清单办；状态以磁盘为准，不要凭记忆推进。")

    # UserPromptSubmit：把 additionalContext 注入本回合上下文（字段名以你的 hooks 版本为准）
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": msg}}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
