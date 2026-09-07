#!/usr/bin/env python3
"""改进判定：候选 vs 冠军。delta = mean(候选) − mean(冠军)，lower_is_better 时负=变好；
|delta| < 噪声底 3σ → undecided；变好且守护切片无退化 → keep；否则 discard。
守护退化 = 该切片 delta > 0 且 ≥ 该切片噪声底。
CLI summary 模式写 receipts/E<id>.json（追加数组；字段与 ablation_verdict 同族：判定 + 溯源块），
receipt 行格式匹配 conclusion_gate.IMPROVE_RECEIPT_RE。`--round` 模式批量判定（golden 闸用）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys


def guard_check(guards):
    """guards: {slice: {"per_seed": [...], "champion_mean": float, "noise_floor": float}}
    → {slice: {"delta", "noise_floor", "regress"}}。"""
    out = {}
    for s, g in (guards or {}).items():
        m = statistics.fmean([float(x) for x in g["per_seed"]])
        d = m - float(g["champion_mean"])
        nf = float(g["noise_floor"])
        out[s] = {"delta": d, "noise_floor": nf, "regress": bool(d > 0 and d >= nf)}
    return out


def verdict(delta, noise_floor_3sigma, guard_regress):
    if abs(delta) < noise_floor_3sigma:
        return "undecided"
    if delta < 0:
        return "discard" if guard_regress else "keep"
    return "discard"


def judge(exp_id, hypothesis_id, per_seed, champion_mean, noise_floor_3sigma,
          guards=None, higher_is_better=False):
    sign = -1.0 if higher_is_better else 1.0
    per = [sign * float(x) for x in per_seed]
    champ = sign * float(champion_mean)
    g_in = {}
    for s, g in (guards or {}).items():
        g_in[s] = {"per_seed": [sign * float(x) for x in g["per_seed"]],
                   "champion_mean": sign * float(g["champion_mean"]),
                   "noise_floor": float(g["noise_floor"])}
    mean = statistics.fmean(per)
    std = statistics.stdev(per) if len(per) > 1 else 0.0
    delta = mean - champ
    g = guard_check(g_in)
    regress = sorted(s for s, r in g.items() if r["regress"])
    v = verdict(delta, float(noise_floor_3sigma), bool(regress))
    line = (f"- {exp_id} {v}: hyp={hypothesis_id} delta={delta:+.4f} "
            f"noise_floor={float(noise_floor_3sigma):.4f} seeds={len(per)} "
            f"guard={('regress:' + ','.join(regress)) if regress else 'ok'}")
    return {"exp_id": exp_id, "hypothesis_id": hypothesis_id,
            "per_seed": [float(x) for x in per_seed], "mean": sign * mean, "std": std,
            "champion_mean": float(champion_mean), "delta": delta,
            "noise_floor_3sigma": float(noise_floor_3sigma), "seeds": len(per),
            "guard": g, "verdict": v, "line": line}


def judge_round(obj):
    """obj: {"champion_mean", "noise_floor_3sigma", "higher_is_better"?, "candidates": [{exp_id, hypothesis_id, per_seed, guards?}]}"""
    out = {}
    for c in obj["candidates"]:
        out[c["exp_id"]] = judge(c["exp_id"], c.get("hypothesis_id"), c["per_seed"],
                                 obj["champion_mean"], obj["noise_floor_3sigma"],
                                 guards=c.get("guards"), higher_is_better=bool(obj.get("higher_is_better")))
    return {"verdicts": out}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:  # 路径写错必须当场炸，不许静默记空指纹
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()


def _guards_from(summary, champ, guard_ids):
    guards = {}
    for s in guard_ids:
        per = [float(sp[s]) for sp in summary.get("slices_per_seed") or [] if s in sp]
        if not per or s not in (champ.get("slices_mean") or {}):
            sys.exit(f"✗ 守护切片 {s} 在 summary.slices_per_seed 或 champion.slices_mean 里缺失")
        guards[s] = {"per_seed": per, "champion_mean": champ["slices_mean"][s],
                     "noise_floor": (champ.get("slices_noise_floor") or {}).get(s, 0.0)}
    return guards


def main():
    ap = argparse.ArgumentParser(description="改进判定：候选 vs 冠军 → keep/discard/undecided + receipt")
    ap.add_argument("--round", default=None, help="批量模式：{champion_mean, noise_floor_3sigma, candidates[]} 的 JSON")
    ap.add_argument("--exp-id", dest="exp_id")
    ap.add_argument("--hypothesis-id", dest="hypothesis_id", default=None)
    ap.add_argument("--summary", help="evaluator.py run-seeds 产的 summary.json")
    ap.add_argument("--champion", help="champion.json")
    ap.add_argument("--guard", default="", help="守护切片 id，逗号分隔")
    ap.add_argument("--config-diff", dest="config_diff", default="{}")
    ap.add_argument("--higher-is-better", dest="higher_is_better", action="store_true")
    ap.add_argument("--script", default=None, help="产出指标的适配器/eval 脚本（receipt 记 produced_by + sha256）")
    ap.add_argument("--t-start", dest="t_start", default=None)
    ap.add_argument("--t-end", dest="t_end", default=None)
    ap.add_argument("--selftest", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.round:
        obj = json.load(open(a.round, encoding="utf-8"))
        res = judge_round(obj)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        for v in res["verdicts"].values():
            print(v["line"])
        return

    if not (a.exp_id and a.summary and a.champion):
        sys.exit("✗ summary 模式须给 --exp-id --summary --champion")
    summary = json.load(open(a.summary, encoding="utf-8"))
    champ = json.load(open(a.champion, encoding="utf-8"))
    per = [float(x) for x in summary.get("per_seed") or []]
    if len(per) < 3:
        sys.exit(f"✗ 有效种子只有 {len(per)} 个（<3）——本候选记 untested，不判定")
    guard_ids = [s for s in a.guard.split(",") if s]
    r = judge(a.exp_id, a.hypothesis_id, per, champ["mean"], champ["noise_floor_3sigma"],
              guards=_guards_from(summary, champ, guard_ids), higher_is_better=a.higher_is_better)
    print(r["line"])
    r.update({"config_diff": json.loads(a.config_diff),
              "produced_by": a.script, "script_sha256": _sha256(a.script) if a.script else None,
              "t_start": a.t_start or summary.get("t_start"), "t_end": a.t_end or summary.get("t_end"),
              "script_selftest": a.selftest})
    import os
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    try:
        with open(a.out, encoding="utf-8") as f:
            receipts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        receipts = []
    receipts.append(r)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(receipts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
