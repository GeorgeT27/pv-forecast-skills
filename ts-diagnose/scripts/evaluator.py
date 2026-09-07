#!/usr/bin/env python3
"""评估器契约：evaluator.json 校验 + 按契约跑适配器（单种子 / 多种子）。
适配器 CLI：python3 <adapter> --config <cfg.json> --seed <int> --out <dir> [--time-limit <秒>]
产物：<out>/metrics.json = {"status":"ok|crash|timeout","primary":float|null,"metric_id":str,
      "slices":{id:float},"t_start","t_end","config":{...},"error":str|null}
      <out>/sealed/test_metrics.json 封存——环内任何脚本不读。
子命令：validate <evaluator.json>；run --evaluator … [--config-diff …] --seed N --out DIR；
run-seeds --evaluator … [--config-diff …] [--seeds a,b,c] --out-root DIR（产 summary.json）。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import subprocess
import sys

FAMILIES = ("architecture", "training", "features", "data")
DIRECTIONS = ("lower_is_better", "higher_is_better")


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def validate(ev):
    errs = []
    if not isinstance(ev, dict):
        return ["evaluator.json 须为对象"]
    ad = ev.get("adapter")
    if not ad or not os.path.exists(ad):
        errs.append(f"adapter 不存在：{ad}")
    if not isinstance(ev.get("base_config"), dict) or not ev["base_config"]:
        errs.append("base_config 须为非空 dict")
    knobs = ev.get("knobs")
    if not isinstance(knobs, dict) or not knobs:
        errs.append("knobs 须为非空 dict")
    else:
        for k, v in knobs.items():
            if not isinstance(v, dict) or v.get("family") not in FAMILIES:
                errs.append(f"knob {k} 缺 family 或不在 {FAMILIES}")
    m = ev.get("metric") or {}
    if not m.get("id") or m.get("direction") not in DIRECTIONS:
        errs.append(f"metric 须含 id 与 direction ∈ {DIRECTIONS}")
    if not isinstance(ev.get("slices"), list) or not ev["slices"]:
        errs.append("slices 须为非空 list")
    seeds = ev.get("seeds")
    if not isinstance(seeds, list) or len(seeds) < 3 or not all(isinstance(s, int) for s in seeds):
        errs.append("seeds 须为 ≥3 个整数")
    tl = ev.get("time_limit_s")
    if not isinstance(tl, int) or tl <= 0:
        errs.append("time_limit_s 须为正整数")
    return errs


def apply_diff(ev, diff):
    unknown = [k for k in diff if k not in ev["knobs"]]
    if unknown:
        raise ValueError(f"config_diff 含未登记 knob：{unknown}（登记在 evaluator.json.knobs）")
    cfg = dict(ev["base_config"])
    cfg.update(diff)
    return cfg


def _write_metrics(out_dir, status, error, metric_id, t_start, config):
    m = {"status": status, "primary": None, "metric_id": metric_id, "slices": {},
         "t_start": t_start, "t_end": _now(), "config": config, "error": error}
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return m


def run_one(ev, config, seed, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cfg_path = os.path.join(out_dir, "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    t_start = _now()
    tl = int(ev["time_limit_s"])
    mid = ev["metric"]["id"]
    cmd = [sys.executable, ev["adapter"], "--config", cfg_path, "--seed", str(seed),
           "--out", out_dir, "--time-limit", str(tl)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tl + int(ev.get("kill_grace_s", 60)))
    except subprocess.TimeoutExpired:
        return _write_metrics(out_dir, "timeout", f"超过 time_limit_s={tl}", mid, t_start, config)
    except OSError as e:
        return _write_metrics(out_dir, "crash", f"launch failed: {e}", mid, t_start, config)
    mp = os.path.join(out_dir, "metrics.json")
    m = None
    if os.path.exists(mp):
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
        except json.JSONDecodeError:
            m = None
    if not isinstance(m, dict) or m.get("status") not in ("ok", "crash", "timeout"):
        tail = (r.stderr or r.stdout or "")[-2000:]
        return _write_metrics(out_dir, "crash", tail or f"退出码 {r.returncode}，无合法 metrics.json", mid, t_start, config)
    if m["status"] == "ok":
        missing = [s for s in ev["slices"] if s not in (m.get("slices") or {})]
        if not isinstance(m.get("primary"), (int, float)) or missing:
            return _write_metrics(out_dir, "crash", f"metrics.json 缺 primary 或切片 {missing}", mid, t_start, config)
    return m


def run_seeds(ev, diff, seeds, out_root):
    config = apply_diff(ev, diff)
    per, slices, status, dirs = [], [], [], []
    t_start = _now()
    for s in seeds:
        d = os.path.join(out_root, f"seed_{s}")
        m = run_one(ev, config, s, d)
        status.append(m["status"])
        dirs.append(d)
        if m["status"] == "ok":
            per.append(float(m["primary"]))
            slices.append({k: float(v) for k, v in m["slices"].items()})
    summary = {"config_diff": diff, "config": config, "seeds": list(seeds), "per_seed": per,
               "slices_per_seed": slices, "run_status": status, "metrics_dirs": dirs,
               "mean": statistics.fmean(per) if per else None,
               "std": statistics.stdev(per) if len(per) > 1 else None,
               "metric_id": ev["metric"]["id"], "adapter": ev["adapter"],
               "t_start": t_start, "t_end": _now()}
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser(description="评估器契约：校验 evaluator.json / 跑适配器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("evaluator")
    r = sub.add_parser("run")
    r.add_argument("--evaluator", required=True)
    r.add_argument("--config-diff", dest="config_diff", default="{}")
    r.add_argument("--seed", type=int, required=True)
    r.add_argument("--out", required=True)
    rs = sub.add_parser("run-seeds")
    rs.add_argument("--evaluator", required=True)
    rs.add_argument("--config-diff", dest="config_diff", default="{}")
    rs.add_argument("--seeds", default=None, help="逗号分隔；缺省用 evaluator.json.seeds")
    rs.add_argument("--out-root", dest="out_root", required=True)
    a = ap.parse_args()
    ev = json.load(open(a.evaluator, encoding="utf-8"))
    errs = validate(ev)
    if errs:
        print("\n".join("✗ " + e for e in errs))
        sys.exit(1)
    if a.cmd == "validate":
        print("✓ evaluator.json 合法")
        return
    diff = json.loads(a.config_diff)
    try:
        config = apply_diff(ev, diff)
    except ValueError as e:
        print(f"✗ {e}")
        sys.exit(1)
    if a.cmd == "run":
        m = run_one(ev, config, a.seed, a.out)
        print(json.dumps({"status": m["status"], "primary": m.get("primary"), "out": a.out}, ensure_ascii=False))
        sys.exit(0 if m["status"] == "ok" else 2)
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else list(ev["seeds"])
    s = run_seeds(ev, diff, seeds, a.out_root)
    print(json.dumps({"run_status": s["run_status"], "mean": s["mean"], "std": s["std"],
                      "summary": os.path.join(a.out_root, "summary.json")}, ensure_ascii=False))
    sys.exit(0 if all(x == "ok" for x in s["run_status"]) else 2)


if __name__ == "__main__":
    main()
