#!/usr/bin/env python3
"""实验日志与冠军状态（改进环的记忆）。只由主 agent 执行（单写者）。
文件：experiment_log.jsonl（一行一条候选）、champion.json（当前冠军 + 预算 + 收敛）、
rounds/round_<n>/{candidates.json, batch_result.json, summary.json}、final_test.json（封存终评）。
子命令：init / candidates / confirm-round / append / decide / new-round / stop / finalize / status。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402

LOG = "experiment_log.jsonl"
CHAMP = "champion.json"
FINAL = "final_test.json"
SEALED_KEYS = ("test", "sealed")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _state():
    return ec.read_json(ec.STATE_PATH) or {}


def _round():
    return int(_state().get("round") or 1)


def _set_round(n):
    st = _state()
    st["round"] = int(n)
    ec.dump_json(st, ec.STATE_PATH)


def _round_dir(n=None):
    d = os.path.join("rounds", f"round_{_round() if n is None else n}")
    os.makedirs(d, exist_ok=True)
    return d


def _need(path, msg):
    doc = ec.read_json(path)
    if doc is None:
        sys.exit(f"✗ {msg}：{path}")
    return doc


def _champ():
    return _need(CHAMP, "无 champion.json——先 experiment_log.py init")


def _save_champ(c):
    c["updated"] = _now()
    ec.dump_json(c, CHAMP)


def read_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_rows(rows):
    with open(LOG, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _nf(per):
    return (statistics.stdev(per) if len(per) > 1 else 0.0) * 3


def _slice_keys(sps):
    keys = set()
    for s in sps:
        keys |= set(s)
    return sorted(keys)


def _slices_mean(sps):
    return {k: statistics.fmean([s[k] for s in sps if k in s]) for k in _slice_keys(sps)}


def _slices_nf(sps):
    return {k: _nf([s[k] for s in sps if k in s]) for k in _slice_keys(sps)}


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def _last_entry(path):
    doc = ec.read_json(path)
    if isinstance(doc, list):
        return doc[-1] if doc else None
    return doc if isinstance(doc, dict) else None


def _switch_to_diff(switch):
    s = str(switch).lstrip("-")
    if "=" in s:
        k, v = s.split("=", 1)
        for cast in (int, float):
            try:
                return {k: cast(v)}
            except ValueError:
                pass
        return {k: v}
    return {s: True}


# ---------------------------------------------------------------- init
def cmd_init(a):
    if os.path.exists(CHAMP):
        sys.exit("✗ champion.json 已存在——改进环只 init 一次；要重来先删 champion.json / experiment_log.jsonl / rounds/")
    ev = _need(a.evaluator, "读不到 evaluator")
    base = _need(a.baseline, "读不到基线 summary")
    per = [float(x) for x in base.get("per_seed") or []]
    if len(per) < 3:
        sys.exit(f"✗ 基线有效种子 {len(per)} 个（<3）——补种子再 init")
    sps = base.get("slices_per_seed") or []
    mean, std = statistics.fmean(per), statistics.stdev(per)
    champ = {"exp_id": "E000", "round": 1, "base_config": ev["base_config"], "config": dict(ev["base_config"]),
             "metric": ev["metric"], "mean": mean, "std": std, "per_seed": per,
             "seeds": base.get("seeds") or ev["seeds"], "noise_floor_3sigma": _nf(per),
             "slices_mean": _slices_mean(sps), "slices_noise_floor": _slices_nf(sps),
             "metrics_dirs": base.get("metrics_dirs") or [], "since_round": 0,
             "history": [{"round": 0, "exp_id": "E000", "mean": mean, "delta": 0.0}],
             "budget": {"max_trainings": a.max_trainings, "max_rounds": a.max_rounds,
                        "max_per_round": a.max_per_round, "stagnation_rounds": a.stagnation_rounds,
                        "used_trainings": len(per)},
             "converged": False, "converged_reason": None}
    _save_champ(champ)
    append_rows([{"exp_id": "E000", "round": 0, "hypothesis_id": None, "source": "baseline",
                  "config_diff": {}, "seeds": champ["seeds"], "per_seed": per, "mean": mean, "std": std,
                  "delta": 0.0, "noise_floor_3sigma": champ["noise_floor_3sigma"], "guard": {},
                  "verdict": "baseline", "receipt_file": None, "receipt_line": None,
                  "slices_per_seed": sps, "metrics_dirs": champ["metrics_dirs"], "t": _now()}])
    _set_round(1)
    print(f"✓ 冠军 E000：mean={mean:.6f} std={std:.6f} 噪声底3σ={champ['noise_floor_3sigma']:.6f}；"
          f"预算 {a.max_trainings} 次训练 / {a.max_rounds} 轮 / 每轮 ≤{a.max_per_round} 候选；已用 {len(per)}")


# ---------------------------------------------------------------- candidates
def cmd_candidates(a):
    champ = _champ()
    rows = read_log()
    rnd = _round()
    if champ.get("converged"):
        sys.exit(f"✗ 已收敛（{champ['converged_reason']}）——进结论阶段，不再排候选")
    next_id = 1 + max(int(r["exp_id"][1:]) for r in rows)
    cands = []
    if a.ledger:
        led = _need(a.ledger, "读不到账本")
        by_id = {h.get("id"): h for h in led.get("hypotheses") or []}
        hyps = [h for h in led.get("hypotheses") or []
                if h.get("kind") == "improvement" and h.get("status") == "pending"
                and (h.get("fix") or {}).get("target_model") == a.target]

        def key(h):
            parent = by_id.get(h.get("derived_from")) or {}
            return (-(parent.get("discriminating_power") or 0), h["id"])
        for h in sorted(hyps, key=key):
            cands.append({"hypothesis_id": h["id"], "source": "ledger", "config_diff": h["fix"]["config_diff"],
                          "predicted_gain": h["fix"]["predicted_gain"], "guard_slices": h["fix"]["guard_slices"]})
    if a.switches:
        sw = _need(a.switches, "读不到 switches")
        items = sw.get("ablation_switches", sw) if isinstance(sw, dict) else sw
        order = {"config-flag": 0, "code-stub": 1}
        picked = [i for i in items if i.get("kind") in order and i.get("switch")]
        for it in sorted(picked, key=lambda i: (order[i["kind"]], i.get("component", ""))):
            cands.append({"hypothesis_id": None, "source": "switches", "config_diff": _switch_to_diff(it["switch"]),
                          "predicted_gain": "未预登记（素版）", "guard_slices": [s for s in a.guard.split(",") if s]})
    seen = {json.dumps(r["config_diff"], sort_keys=True) for r in rows}
    fresh = []
    for c in cands:
        k = json.dumps(c["config_diff"], sort_keys=True)
        if k in seen:
            continue
        seen.add(k)
        fresh.append(c)
    b = champ["budget"]
    left = int(b["max_trainings"]) - int(b["used_trainings"])
    cap = min(int(b["max_per_round"]), max(0, left // max(1, len(champ["seeds"]))))
    for i, c in enumerate(fresh[:cap]):
        c["exp_id"] = f"E{next_id + i:03d}"
    doc = {"round": rnd, "confirmed": False, "target_model": a.target, "champion_exp_id": champ["exp_id"],
           "champion_mean": champ["mean"], "noise_floor_3sigma": champ["noise_floor_3sigma"],
           "seeds": champ["seeds"], "candidates": fresh[:cap], "deferred": fresh[cap:], "t": _now()}
    out = a.out or os.path.join(_round_dir(), "candidates.json")
    ec.dump_json(doc, out)
    n = len(doc["candidates"])
    print(f"✓ 第 {rnd} 轮候选 {n} 条（× {len(champ['seeds'])} 种子 = {n * len(champ['seeds'])} 次训练），"
          f"顺延 {len(doc['deferred'])} 条 → {out}")
    if n == 0:
        print("  ⚠ 本轮没有新候选——用 stop --reason no_candidates 收敛，或换候选来源")


def cmd_confirm_round(a):
    p = os.path.join(_round_dir(), "candidates.json")
    doc = _need(p, "无本轮 candidates.json——先 candidates")
    if not doc.get("candidates"):
        sys.exit("✗ 候选为空，不能确认")
    doc["confirmed"], doc["confirmed_at"] = True, _now()
    ec.dump_json(doc, p)
    print(f"✓ 第 {doc['round']} 轮已确认开跑：{[c['exp_id'] for c in doc['candidates']]}")


# ---------------------------------------------------------------- append
def cmd_append(a):
    _champ()
    rnd = _round()
    cands = _need(os.path.join(_round_dir(), "candidates.json"), "本轮无 candidates.json")
    if not cands.get("confirmed"):
        sys.exit("✗ 本轮候选未确认（先 confirm-round）")
    batch = _need(a.batch, "读不到批结果")
    results = batch.get("results", batch) if isinstance(batch, dict) else batch
    for k in _keys(results):
        if any(s in str(k).lower() for s in SEALED_KEYS):
            sys.exit(f"✗ 结果里出现封存字段 {k!r}——环内不许读测试集")
    by_exp = {c["exp_id"]: c for c in cands["candidates"]}
    existing = {r["exp_id"] for r in read_log()}
    rows = []
    for res in results:
        if not isinstance(res, dict):
            continue
        eid = res.get("exp_id")
        c = by_exp.get(eid)
        if c is None:
            sys.exit(f"✗ {eid} 不在第 {rnd} 轮候选里")
        if eid in existing:
            sys.exit(f"✗ {eid} 已在日志里，不许重复追加")
        row = {"exp_id": eid, "round": rnd, "hypothesis_id": c.get("hypothesis_id"), "source": c["source"],
               "config_diff": c["config_diff"], "seeds": cands["seeds"], "t": _now(),
               "metrics_dirs": res.get("metrics_dirs") or [], "slices_per_seed": res.get("slices_per_seed") or []}
        bad = [s for s in (res.get("run_status") or []) if s != "ok"]
        if res.get("status") != "COMPUTE_DONE" or bad or not res.get("receipt_file"):
            row.update({"verdict": "untested", "per_seed": res.get("per_seed") or [], "delta": None,
                        "untested_reason": res.get("blocked_reason") or ",".join(res.get("run_status") or [])
                        or res.get("status") or "无结果", "receipt_file": None, "receipt_line": None})
        else:
            rec = _last_entry(res["receipt_file"])
            if rec is None:
                sys.exit(f"✗ {eid} 的 receipt 缺失或为空：{res['receipt_file']}")
            if rec.get("exp_id") != eid:
                sys.exit(f"✗ {res['receipt_file']} 的 exp_id={rec.get('exp_id')} ≠ {eid}")
            if rec.get("verdict") not in ("keep", "discard", "undecided"):
                sys.exit(f"✗ {eid} receipt 判定非法：{rec.get('verdict')}")
            row.update({"per_seed": rec["per_seed"], "mean": rec["mean"], "std": rec["std"], "delta": rec["delta"],
                        "noise_floor_3sigma": rec["noise_floor_3sigma"], "guard": rec.get("guard") or {},
                        "verdict": rec["verdict"], "receipt_file": res["receipt_file"], "receipt_line": rec["line"]})
        rows.append(row)
    if not rows:
        sys.exit("✗ 批结果里没有任何候选")
    append_rows(rows)
    print(f"✓ 追加 {len(rows)} 行：" + ", ".join(f"{r['exp_id']}={r['verdict']}" for r in rows))


# ---------------------------------------------------------------- Task 6 填充
def cmd_decide(a):
    sys.exit("✗ decide 未实现（Task 6）")


def cmd_new_round(a):
    sys.exit("✗ new-round 未实现（Task 6）")


def cmd_stop(a):
    sys.exit("✗ stop 未实现（Task 6）")


def cmd_finalize(a):
    sys.exit("✗ finalize 未实现（Task 6）")


def cmd_status(a):
    sys.exit("✗ status 未实现（Task 6）")


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="实验日志与冠军状态（改进环）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--evaluator", required=True)
    p.add_argument("--baseline", required=True, help="evaluator.py run-seeds 产的基线 summary.json")
    p.add_argument("--max-trainings", dest="max_trainings", type=int, default=30)
    p.add_argument("--max-rounds", dest="max_rounds", type=int, default=3)
    p.add_argument("--max-per-round", dest="max_per_round", type=int, default=10)
    p.add_argument("--stagnation-rounds", dest="stagnation_rounds", type=int, default=2)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("candidates")
    p.add_argument("--ledger", default=None, help="hypothesis_ledger.json（取 kind=improvement 且 pending 的条目）")
    p.add_argument("--switches", default=None, help="model_profile 的 ablation_switches JSON（素版候选）")
    p.add_argument("--target", required=True, help="改进目标模型名（匹配 fix.target_model）")
    p.add_argument("--guard", default="", help="素版候选的守护切片，逗号分隔")
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_candidates)
    sub.add_parser("confirm-round").set_defaults(fn=cmd_confirm_round)
    p = sub.add_parser("append")
    p.add_argument("--batch", required=True, help="{\"results\": [<worker 输出 JSON>...]}")
    p.set_defaults(fn=cmd_append)
    sub.add_parser("decide").set_defaults(fn=cmd_decide)
    sub.add_parser("new-round").set_defaults(fn=cmd_new_round)
    p = sub.add_parser("stop")
    p.add_argument("--reason", required=True)
    p.set_defaults(fn=cmd_stop)
    sub.add_parser("finalize").set_defaults(fn=cmd_finalize)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
