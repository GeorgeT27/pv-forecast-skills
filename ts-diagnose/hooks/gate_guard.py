#!/usr/bin/env python3
"""ts-diagnose 结论闸的 harness 级守卫（Claude Code Stop hook）。

作用：agent 想结束作答时被 Claude CLI 调用一次。若某个工作目录**已经拿出结论**、
却没有合法的 gate_reports/conclusion_gate.json，就打回(block)，逼它回流水线。

拦不拦三条判据（按顺序，命中即拦）：
  1. 盘上有 CONCLUSION.md，但 receipt 缺失/passed 非真/sha256 与 CONCLUSION.md 不符；
  2. diagnose_state.json 缺失或解析不了——阶段状态不明，等同没走流水线；
  3. diagnose_state.json 自称 current_stage=done，却没有合法 receipt。
以上都不命中且流水线正在中途（current_stage 是某个阶段号）→ **放行**：playbook 的
pause_after 停顿、等 subagent 回卡都是正常的回合结束，拦它只会空烧回合。

cwd 下的每个 diagnose_config.json 都是一个候选工作目录，逐个按上面三条判；已跑完
（receipt 合法）或正在中途的目录不拦别人。纯文件系统校验，与底层模型无关。

用法：
  作为 hook：Claude CLI 通过 stdin 喂一段 JSON，自动调用，无需手动跑。
  自检：    python3 gate_guard.py --selftest
"""
from __future__ import annotations
import sys, os, json, glob, hashlib, tempfile

# 不产 CONCLUSION.md 的剧本（生产者 + 生成器）。真相在 playbook frontmatter，
# 由 orient 写进 diagnose_state.json 的 produces_conclusion；本名单只是旧工作目录
# （state 里还没有该字段）的兜底，别再往里加新剧本——加 frontmatter 才是对的。
PRODUCERS = {"data-setup", "metric-eval", "model-audit",
             "model-comparison", "fact-scan"}
CAP = 3  # 恢复上限，防弱模型死循环


def gate_passes(workdir):
    """返回 (ok: bool, why: str)。这是核心判据，自检直接测它。"""
    receipt = os.path.join(workdir, "gate_reports", "conclusion_gate.json")
    concl = os.path.join(workdir, "CONCLUSION.md")
    if not (os.path.exists(receipt) and os.path.exists(concl)):
        return False, "缺 conclusion_gate receipt 或 CONCLUSION.md"
    try:
        r = json.load(open(receipt, encoding="utf-8"))
    except Exception:
        return False, "receipt 无法解析"
    if not r.get("passed"):
        return False, "receipt.passed 非真"
    cur = hashlib.sha256(open(concl, "rb").read()).hexdigest()
    if cur != r.get("conclusion_sha256"):
        return False, "CONCLUSION.md 与 receipt sha256 不符(结论被改过或 receipt 过期)"
    return True, "ok"


def block_reason(workdir):
    """返回 (要不要拦: bool, 原因: str)。自检直接测它。"""
    try:
        cfg = json.load(open(os.path.join(workdir, "diagnose_config.json"), encoding="utf-8"))
    except Exception:
        return False, "config 无法解析，不干预"
    pb = cfg.get("playbook")
    if not pb:
        return False, "未绑定 playbook"
    state_p = os.path.join(workdir, "diagnose_state.json")
    st = None
    if os.path.exists(state_p):
        try:
            st = json.load(open(state_p, encoding="utf-8"))
        except Exception:
            st = None
    # 该不该有结论：优先信 orient 落盘的事实，其次才是兜底名单
    if isinstance(st, dict) and "produces_conclusion" in st:
        if not st.get("produces_conclusion"):
            return False, f"{pb} 不产 CONCLUSION.md（frontmatter 无结论阶段）：不拦"
    elif os.path.basename(str(pb)).replace(".md", "") in PRODUCERS:
        return False, "生产者/生成器剧本（兜底名单）：不产结论"
    ok, why = gate_passes(workdir)
    if ok:
        return False, "已过结论闸"
    if os.path.exists(os.path.join(workdir, "CONCLUSION.md")):
        return True, f"{why}（CONCLUSION.md 已落盘）"
    if not os.path.exists(state_p):
        return True, "该工作目录没有 diagnose_state.json——还没跑过 orient.py，阶段状态不明"
    if st is None:
        return True, "diagnose_state.json 无法解析，阶段状态不明"
    cur = st.get("current_stage")
    if cur in (None, "", "done"):
        return True, "diagnose_state 自称阶段全部完成，却没有合法结论 receipt"
    return False, f"流水线进行中（current_stage={cur}），停顿/等 subagent 不拦"


def find_workdirs(cwd):
    """cwd 下所有 diagnose_config.json 所在目录，按 mtime 新 → 旧。"""
    cfgs = glob.glob(os.path.join(cwd, "**", "diagnose_config.json"), recursive=True)
    return [os.path.dirname(p) for p in sorted(cfgs, key=os.path.getmtime, reverse=True)]


def run_hook():
    inp = json.load(sys.stdin)
    cwd = inp.get("cwd") or os.getcwd()
    hit = None
    for wd in find_workdirs(cwd):
        need, why = block_reason(wd)
        if need:
            hit = (wd, why)
            break
    if hit is None:
        sys.exit(0)  # 没有诊断在跑 / 都合法 / 都在中途：不干预
    workdir, why = hit

    # 环路上限：计数文件在 workdir，换新诊断目录自动清零
    cnt_f = os.path.join(workdir, "gate_reports", ".stop_force_count")
    cnt = 0
    if os.path.exists(cnt_f):
        try:
            cnt = int(open(cnt_f).read().strip() or "0")
        except Exception:
            cnt = 0
    if cnt >= CAP:
        sys.exit(0)  # 到上限：放行并升级给人类，避免死循环
    os.makedirs(os.path.dirname(cnt_f), exist_ok=True)
    open(cnt_f, "w").write(str(cnt + 1))

    print(json.dumps({"decision": "block", "reason":
        f"[HARNESS-BLOCKED] {workdir} 未过结论闸：{why}。任何诊断结论必须走完 playbook 流水线，"
        f"由 scripts/conclusion_gate.py 生成 gate_reports/conclusion_gate.json 才能作答。"
        f"现在回到 `python3 <ENGINE>/scripts/orient.py` 继续，不要直接作答。"}))
    sys.exit(0)


def selftest():
    """构造各种 workdir，验证 gate_passes 与 block_reason 的判定。"""
    def make(concl_text, receipt_obj, state=None, playbook="result-eval"):
        d = tempfile.mkdtemp()
        json.dump({"playbook": playbook}, open(os.path.join(d, "diagnose_config.json"), "w"))
        if concl_text is not None:
            open(os.path.join(d, "CONCLUSION.md"), "w", encoding="utf-8").write(concl_text)
        if receipt_obj is not None:
            os.makedirs(os.path.join(d, "gate_reports"), exist_ok=True)
            json.dump(receipt_obj, open(os.path.join(d, "gate_reports", "conclusion_gate.json"), "w"))
        if state is not None:
            json.dump(state, open(os.path.join(d, "diagnose_state.json"), "w"))
        return d

    txt = "# 结论\n## 模型结构依据\nH-3 ...\n"
    good_sha = hashlib.sha256(txt.encode()).hexdigest()
    mid = {"current_stage": "2", "stages": {"0": "done"}}
    done = {"current_stage": "done", "stages": {"0": "done"}}

    gate_cases = [
        ("缺 receipt", make(txt, None), False),
        ("tamper(sha 不符)", make(txt, {"passed": True, "conclusion_sha256": "deadbeef"}), False),
        ("passed 非真", make(txt, {"passed": False, "conclusion_sha256": good_sha}), False),
        ("合法", make(txt, {"passed": True, "conclusion_sha256": good_sha}), True),
    ]
    block_cases = [
        ("结论已落盘但无 receipt → 拦", make(txt, None, mid), True),
        ("结论已落盘但 sha 不符 → 拦", make(txt, {"passed": True, "conclusion_sha256": "dead"}, mid), True),
        ("无结论 + 无 state → 拦", make(None, None, None), True),
        ("无结论 + state 自称 done → 拦", make(None, None, done), True),
        ("无结论 + 流水线中途 → 放行", make(None, None, mid), False),
        ("已过闸 → 放行", make(txt, {"passed": True, "conclusion_sha256": good_sha}, done), False),
        ("生产者 → 放行", make(None, None, None, playbook="data-setup"), False),
    ]
    all_ok = True
    for name, d, expect in gate_cases:
        got, why = gate_passes(d)
        all_ok &= got == expect
        print(f"  {'✓' if got == expect else '✗'} gate_passes {name}: {got} (期望 {expect})  [{why}]")
    for name, d, expect in block_cases:
        got, why = block_reason(d)
        all_ok &= got == expect
        print(f"  {'✓' if got == expect else '✗'} block_reason {name}: {got} (期望 {expect})  [{why}]")
    print("SELFTEST", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_hook()
