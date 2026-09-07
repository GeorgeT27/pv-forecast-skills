#!/usr/bin/env python3
"""冒烟驱动：代替 worker 卡片，机械执行「evaluator.py run-seeds + improve_verdict.py」并写本轮 batch_result.json。
用法：python3 smoke_driver.py <ENGINE> baseline | python3 smoke_driver.py <ENGINE> round
正式运行由 model-improve-worker / workflows/ts-train-batch.js 执行同样两条命令；本脚本只服务脚本驱动的冒烟。"""
import json
import subprocess
import sys

ENGINE, MODE = sys.argv[1], sys.argv[2]
EV = json.load(open("evaluator.json", encoding="utf-8"))


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-600:], r.stderr[-300:] if r.returncode else "")
    return r


if MODE == "baseline":
    run([sys.executable, f"{ENGINE}/scripts/evaluator.py", "run-seeds", "--evaluator", "evaluator.json",
         "--config-diff", "{}", "--out-root", "runs/E000"])
    sys.exit(0)

rnd = json.load(open("diagnose_state.json", encoding="utf-8"))["round"]
cands = json.load(open(f"rounds/round_{rnd}/candidates.json", encoding="utf-8"))
results = []
for c in cands["candidates"]:
    eid = c["exp_id"]
    run([sys.executable, f"{ENGINE}/scripts/evaluator.py", "run-seeds", "--evaluator", "evaluator.json",
         "--config-diff", json.dumps(c["config_diff"]), "--out-root", f"runs/{eid}"])
    s = json.load(open(f"runs/{eid}/summary.json", encoding="utf-8"))
    res = {"status": "COMPUTE_DONE", "task": "candidate", "exp_id": eid, "hypothesis_id": c.get("hypothesis_id"),
           "config_diff": c["config_diff"], "per_seed": s["per_seed"], "mean": s["mean"], "std": s["std"],
           "run_status": s["run_status"], "metrics_dirs": s["metrics_dirs"], "slices_per_seed": s["slices_per_seed"],
           "summary_file": f"runs/{eid}/summary.json", "receipt_line": "", "receipt_file": "",
           "need_info": [], "blocked_reason": ""}
    if all(x == "ok" for x in s["run_status"]):
        r = run([sys.executable, f"{ENGINE}/scripts/improve_verdict.py", "--exp-id", eid,
                 "--hypothesis-id", c.get("hypothesis_id") or "", "--summary", f"runs/{eid}/summary.json",
                 "--champion", "champion.json", "--guard", ",".join(c.get("guard_slices") or []),
                 "--config-diff", json.dumps(c["config_diff"]), "--script", EV["adapter"],
                 "--t-start", s["t_start"], "--t-end", s["t_end"],
                 "--selftest", f"seeds={len(s['per_seed'])}=={len(EV['seeds'])}", "--out", f"receipts/{eid}.json"])
        res["receipt_file"] = f"receipts/{eid}.json"
        res["receipt_line"] = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    else:
        res["status"], res["blocked_reason"] = "BLOCKED", ",".join(s["run_status"])
    results.append(res)
json.dump({"results": results, "failed": [x["exp_id"] for x in results if x["status"] != "COMPUTE_DONE"]},
          open(f"rounds/round_{rnd}/batch_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("✓ batch_result.json:", [(x["exp_id"], x["status"]) for x in results])
