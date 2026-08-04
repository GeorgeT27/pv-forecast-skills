#!/usr/bin/env python3
"""生成闸（硬不变量二：进入决策的数字必须可复现）。

运行时生成的分析脚本在碰真实数据之前必须过本闸：
  1. 静态检查——语法（ast）、无危险副作用（禁 subprocess/网络/绝对路径写/删除类调用）；
  2. 金标准运行——在 playbooks/<id>/golden/ 的固定合成输入上按 manifest.json 声明的
     CLI 跑一遍（沙箱临时目录），产物过 expect 断言（结果已知）。
金标准算错 → 退出码非零，**不许拿该脚本去跑真实数据**；改脚本，不改期望。

用法（在工作目录下）：
  python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/dynamics.py \
      --playbook training-sufficiency --stage 2
闸结果落工作目录 gate_reports/<script>.json（含脚本 sha256，供 provenance 汇总）。

manifest.json 的 stage 条目：
  {"inputs": [...拷入沙箱的 golden 文件], "args": [...脚本 CLI], "expect": [check...]}
check 断言 DSL（path = 产物 JSON 内的点分路径）：
  {"file","path","op","value"[,"tol"][,"field"]}
  op ∈ eq / ge / le / between / contains / first_is / argmax / argmin / exists
  argmax/argmin：path 指向 dict——值为数时直接比键；值为 dict 时用 field 取数；期望 value=键名。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

GATE_DIR = "gate_reports"

BANNED_IMPORTS = {"subprocess", "socket", "requests", "urllib", "http", "shutil", "ctypes"}
BANNED_CALLS = {("os", "system"), ("os", "remove"), ("os", "unlink"), ("os", "rmdir"),
                ("os", "removedirs"), ("os", "rename")}
WRITE_MODES = ("w", "a", "x")


# ---------------------------------------------------------------- 静态检查
def static_check(script_path):
    """→ (passed, issues)。分析脚本的白名单世界：读输入、算、写相对路径产物。"""
    issues = []
    src = open(script_path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, [f"语法错误：{e}"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) \
                else [node.module or ""]
            for n in names:
                if n.split(".")[0] in BANNED_IMPORTS:
                    issues.append(f"L{node.lineno} 禁用导入：{n}")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if (f.value.id, f.attr) in BANNED_CALLS:
                    issues.append(f"L{node.lineno} 禁用调用：{f.value.id}.{f.attr}")
            if isinstance(f, ast.Name) and f.id in ("eval", "exec"):
                issues.append(f"L{node.lineno} 禁用调用：{f.id}")
            if isinstance(f, ast.Name) and f.id == "open":
                issues += _abs_write_issue(node)
            if isinstance(f, ast.Attribute) and f.attr in ("to_csv", "to_json", "savefig"):
                issues += _abs_write_issue(node, arg0_only=True)
    return not issues, issues


def _abs_write_issue(call, arg0_only=False):
    """open()/to_csv() 等第一个参数是绝对路径字面量（且 open 为写模式）→ 违规。
    相对路径写没问题——金标准运行在沙箱里，真实运行在工作目录里。"""
    args = call.args
    if not args or not (isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)):
        return []
    if not os.path.isabs(args[0].value):
        return []
    if arg0_only:
        return [f"L{call.lineno} 绝对路径写：{args[0].value}"]
    mode = ""
    if len(args) > 1 and isinstance(args[1], ast.Constant):
        mode = str(args[1].value)
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = str(kw.value.value)
    if any(m in mode for m in WRITE_MODES):
        return [f"L{call.lineno} 绝对路径写：{args[0].value}"]
    return []


# ---------------------------------------------------------------- 断言求值
def _resolve(obj, dotted):
    if not dotted:
        return obj
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(f"产物里没有路径 '{dotted}'（断在 '{part}'）")
    return cur


def eval_check(chk, sandbox):
    """→ (ok, actual)。"""
    fpath = os.path.join(sandbox, chk["file"])
    if chk["op"] == "exists":
        return os.path.exists(fpath), os.path.exists(fpath)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    val = _resolve(data, chk.get("path", ""))
    op, exp, tol = chk["op"], chk.get("value"), chk.get("tol", 0)
    if op == "eq":
        ok = abs(val - exp) <= tol if isinstance(exp, (int, float)) \
            and not isinstance(exp, bool) and tol else val == exp
        return ok, val
    if op == "ge":
        return val >= exp, val
    if op == "le":
        return val <= exp, val
    if op == "between":
        return exp[0] <= val <= exp[1], val
    if op == "contains":
        return exp in val, val
    if op == "first_is":
        return bool(val) and val[0] == exp, val[:3] if isinstance(val, list) else val
    if op in ("argmax", "argmin"):
        field = chk.get("field")
        num = {k: (v[field] if field else v) for k, v in val.items()}
        pick = (max if op == "argmax" else min)(num, key=num.get)
        return pick == exp, pick
    raise ValueError(f"未知断言 op：{chk['op']}")


# ---------------------------------------------------------------- 金标准运行
def golden_run(script_path, playbook, stage):
    """→ (passed, results, err)。沙箱里拷 golden 输入，按 manifest CLI 跑，过 expect。"""
    gdir = os.path.join(ec.playbook_dir(playbook), "golden")
    manifest = ec.read_json(os.path.join(gdir, "manifest.json"))
    if not manifest:
        return False, [], f"playbook '{playbook}' 缺 golden/manifest.json"
    ent = (manifest.get("stages") or {}).get(str(stage))
    if not ent:
        return False, [], f"manifest 未声明 stage {stage}（有：{sorted(manifest['stages'])}）"
    with tempfile.TemporaryDirectory(prefix="gen_gate_") as sandbox:
        for rel in ent.get("inputs") or []:
            src = os.path.join(gdir, rel)
            if not os.path.exists(src):
                return False, [], f"golden 缺输入文件 {rel}"
            shutil.copy(src, os.path.join(sandbox, os.path.basename(rel)))
        proc = subprocess.run(
            [sys.executable, os.path.abspath(script_path)] + list(ent["args"]),
            cwd=sandbox, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return False, [], f"金标准运行退出码 {proc.returncode}：{proc.stderr[-800:]}"
        results = []
        for chk in ent["expect"]:
            try:
                ok, actual = eval_check(chk, sandbox)
            except Exception as e:  # 产物 schema 不符合契约同样算 FAIL
                ok, actual = False, f"求值失败：{e}"
            results.append({**chk, "ok": ok, "actual": actual})
        return all(r["ok"] for r in results), results, None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose 生成闸")
    ap.add_argument("--script", required=True, help="待闸的生成脚本路径")
    ap.add_argument("--playbook", required=True)
    ap.add_argument("--stage", required=True)
    args = ap.parse_args()

    st_ok, issues = static_check(args.script)
    g_ok, checks, err = (False, [], "静态检查未过，未运行金标准")
    if st_ok:
        g_ok, checks, err = golden_run(args.script, args.playbook, args.stage)

    report = {
        "script": args.script,
        "script_sha256": sha256_of(args.script),
        "playbook": args.playbook,
        "stage": args.stage,
        "static": {"passed": st_ok, "issues": issues},
        "golden": {"passed": g_ok, "error": err, "checks": checks},
        "passed": st_ok and g_ok,
    }
    os.makedirs(GATE_DIR, exist_ok=True)
    out = os.path.join(GATE_DIR, os.path.basename(args.script).rsplit(".", 1)[0] + ".json")
    ec.dump_json(report, out)

    print(f"[gen_gate] {args.script}  playbook={args.playbook} stage={args.stage}")
    print(f"  静态检查：{'PASS' if st_ok else 'FAIL ' + '; '.join(issues)}")
    if not st_ok:
        print("  金标准：跳过（静态检查未过）")
    else:
        tag = "PASS" if g_ok else f"FAIL（{err or '断言未过'}）"
        print(f"  金标准：{tag}")
        for r in checks:
            print(f"    [{'✓' if r['ok'] else '✗'}] {r['file']}:{r.get('path','')} "
                  f"{r['op']} {r.get('value','')} → 实际 {r['actual']}")
    print(f"  报告：{out}")
    if not report["passed"]:
        print("  ⛔ 未过闸：不许拿本脚本跑真实数据。改脚本，不改期望。")
        sys.exit(1)
    print("  ✅ 过闸：可以跑真实数据。")


if __name__ == "__main__":
    main()
