#!/usr/bin/env python3
"""ts-diagnose 结论闸的 harness 级守卫（Claude Code Stop hook）。

作用：agent 想结束作答时被 Claude CLI 调用一次。若当前有诊断在跑、且该 playbook
本该产出结论，就检查 gate_reports/conclusion_gate.json 这张 receipt：
  - 不存在 / passed 非真 / 与 CONCLUSION.md 的 sha256 对不上 → 打回(block)，逼它回流水线；
  - 合法 → 放行。
纯文件系统校验，与底层模型无关（Claude / DeepSeek 都一样）。

用法：
  作为 hook：Claude CLI 通过 stdin 喂一段 JSON，自动调用，无需手动跑。
  自检：    python3 gate_guard.py --selftest
"""
from __future__ import annotations
import sys, os, json, glob, hashlib, tempfile

PRODUCERS = {"data-setup", "metric-eval", "model-audit"}  # 不产 CONCLUSION.md，跳过
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


def find_workdir(cwd):
    """cwd 下最新的 diagnose_config.json 所在目录；没有则 None。"""
    cfgs = glob.glob(os.path.join(cwd, "**", "diagnose_config.json"), recursive=True)
    if not cfgs:
        return None
    return os.path.dirname(max(cfgs, key=os.path.getmtime))


def run_hook():
    inp = json.load(sys.stdin)
    cwd = inp.get("cwd") or os.getcwd()
    workdir = find_workdir(cwd)
    if not workdir:
        sys.exit(0)  # 没有诊断在跑，不干预
    try:
        cfg = json.load(open(os.path.join(workdir, "diagnose_config.json"), encoding="utf-8"))
    except Exception:
        sys.exit(0)
    pb = cfg.get("playbook")
    if not pb or pb in PRODUCERS:
        sys.exit(0)  # 未绑定 / 生产者：不产结论，放行

    ok, why = gate_passes(workdir)
    if ok:
        sys.exit(0)

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
        f"[HARNESS-BLOCKED] 未过结论闸：{why}。任何诊断结论必须走完 playbook 流水线，"
        f"由 scripts/conclusion_gate.py 生成 gate_reports/conclusion_gate.json 才能作答。"
        f"现在回到 `python3 <ENGINE>/scripts/orient.py` 继续，不要直接作答。"}))
    sys.exit(0)


def selftest():
    """构造三种 workdir，验证 缺receipt→block、tamper→block、合法→pass。"""
    def make(concl_text, receipt_obj):
        d = tempfile.mkdtemp()
        json.dump({"playbook": "result-eval"}, open(os.path.join(d, "diagnose_config.json"), "w"))
        if concl_text is not None:
            open(os.path.join(d, "CONCLUSION.md"), "w", encoding="utf-8").write(concl_text)
        if receipt_obj is not None:
            os.makedirs(os.path.join(d, "gate_reports"), exist_ok=True)
            json.dump(receipt_obj, open(os.path.join(d, "gate_reports", "conclusion_gate.json"), "w"))
        return d

    txt = "# 结论\n## 模型结构依据\nH-3 ...\n"
    good_sha = hashlib.sha256(txt.encode()).hexdigest()

    cases = [
        ("缺 receipt", make(txt, None), False),
        ("tamper(sha 不符)", make(txt, {"passed": True, "conclusion_sha256": "deadbeef"}), False),
        ("passed 非真", make(txt, {"passed": False, "conclusion_sha256": good_sha}), False),
        ("合法", make(txt, {"passed": True, "conclusion_sha256": good_sha}), True),
    ]
    all_ok = True
    for name, d, expect in cases:
        got, why = gate_passes(d)
        mark = "✓" if got == expect else "✗"
        if got != expect:
            all_ok = False
        print(f"  {mark} {name}: gate_passes={got} (期望 {expect})  {'' if got == expect else '<-- 不符!'}  [{why}]")
    print("SELFTEST", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_hook()
