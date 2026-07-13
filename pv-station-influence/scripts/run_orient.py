#!/usr/bin/env python3
"""Step 0：Orient —— 每次进入本技能先跑：识别模式(A/B) + 定位阶段 + 报前置。

真相以产物为准（同 pv-result-analysis 的 orient 哲学）：每次重扫工作目录产物，
不信任可能过期的 state。模式由 config.checkpoint_dir 有无自动判定，不需用户预选。

用法：
  python <skill>/scripts/run_orient.py            # 报模式 + 当前阶段 + 前置 ✓/✗
  python <skill>/scripts/run_orient.py --goto 2   # 想直达某阶段：校验前置
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic

STATE_PATH = "influence_state.json"
PROGRESS_PATH = "PROGRESS.md"

STAGE_NAMES = {
    0: "回放分组（种子/指纹 → assignments.csv）",
    1: "影响力回归（Mode A 主证据 → influence_coefs.json）",
    2: "梯度佐证 TracIn（Mode B → tracin_scores.json）",
    3: "漂移解释（复用 run_drift.py，气候距离 → 现象/假设）",
    4: "确认（Mode B：微调探针 + 剔除重训 → 已证实/CONCLUSION）",
}


def _exists(p):
    return bool(p) and os.path.exists(p)


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def scan():
    findings = _read("FINDINGS.md")
    return {
        "assignments": _exists("assignments.csv"),
        "rmse_series": _exists("rmse_series.csv"),
        "influence": _exists("influence_coefs.json"),
        "tracin": _exists("tracin_scores.json"),
        "drift_done": ("漂移" in findings) or ("现象" in findings)
                      or bool([d for d in os.listdir(".") if d.startswith("drift")]),
        "confirmed": ("已证实" in findings) or _exists("CONCLUSION.md"),
    }


def stage_done(stage, ev, mode):
    if stage == 0:
        return ev["assignments"]
    if stage == 1:
        return ev["influence"]
    if stage == 2:
        return ev["tracin"] if mode == "B" else True   # Mode A 无此阶段，视为不阻塞
    if stage == 3:
        return ev["drift_done"]
    if stage == 4:
        return ev["confirmed"] if mode == "B" else True
    return False


def prereqs(stage, cfg, ev, mode):
    if stage == 0:
        smp = cfg.get("sampler") or {}
        return [("config.sampler.n_iters 已填", bool(smp.get("n_iters"))),
                ("Mode B 才需 adapter.py（回放采样）", True)]
    if stage == 1:
        return [("assignments.csv 在（Stage 0）", ev["assignments"]),
                ("rmse_series.csv 在（日志解析或 ckpt_eval）", ev["rmse_series"])]
    if stage == 2:
        return [("Mode B（有 checkpoint_dir）", mode == "B"),
                ("adapter.loss_gradient 可用", mode == "B")]
    if stage == 3:
        return [("influence_coefs.json 或 tracin_scores.json 有嫌疑站", ev["influence"] or ev["tracin"]),
                ("训练集逐站 parquet 可读（run_drift 需要）", bool(cfg.get("stations")))]
    if stage == 4:
        return [("Mode B", mode == "B"),
                ("Stage 1/2 已给出 top 嫌疑（且最好两法一致）", ev["influence"] or ev["tracin"])]
    return []


def current(ev, mode):
    for s in (0, 1, 2, 3, 4):
        if not stage_done(s, ev, mode):
            return s
    return 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goto", type=int, choices=[0, 1, 2, 3, 4], default=None)
    args = ap.parse_args()

    if not sic.has_config():
        print("=" * 60)
        print("未找到 influence_config.json —— 此前没跑过。")
        print("→ 回 Step 1：向用户收集 训练仓库/采样代码+种子、checkpoint 目录、白马湖 true_label、")
        print("  训练日志目录、17 站表 与 迭代数，写 influence_config.json（缺字段先留空）。")
        print("  然后先跑 probe_logs.py 判断白马湖 RMSE 是否已入日志（决定 Mode A 是否零权重）。")
        print("=" * 60)
        return

    cfg = sic.load_config()
    mode = sic.mode_from_config(cfg)
    ev = scan()
    cur = current(ev, mode)

    print("=" * 60)
    print(f"模式: {mode}（{'有 checkpoint，Stage 2/4 解锁' if mode=='B' else '仅预测/日志，观测归因'}）"
          f"    工作目录: {os.getcwd()}")
    print("-" * 60)
    for s in (0, 1, 2, 3, 4):
        if mode == "A" and s in (2, 4):
            tag = "Mode B 专属（当前 Mode A，跳过）"
        else:
            tag = "已完成" if stage_done(s, ev, mode) else ("← 当前" if s == cur else "待做")
        print(f"  Stage {s} {STAGE_NAMES[s]}  [{tag}]")
    print("-" * 60)
    target = args.goto if args.goto is not None else (cur if cur <= 4 else None)
    if target is not None:
        print(f"进入 Stage {target} 的前置：")
        pr = prereqs(target, cfg, ev, mode)
        for desc, ok in pr:
            print(f"  [{'✓' if ok else '✗'}] {desc}")
        if all(ok for _, ok in pr):
            print(f"→ 前置齐，可开工 Stage {target}。")
        else:
            print("→ 有 ✗ 先补：缺路径回 Step 1 问用户；缺产物回上一阶段；缺 RMSE 先 probe_logs / ckpt_eval。")
    else:
        print("  五阶段完成——可写/刷新 CONCLUSION.md，或按 --goto 复核。")
    print("=" * 60)

    # 写 state + PROGRESS
    state = {"mode": mode, "updated": dt.datetime.now().isoformat(timespec="seconds"),
             "current_stage": cur, "artifacts": ev}
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    new = not _exists(PROGRESS_PATH)
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        if new:
            f.write("# PROGRESS —— 站点影响力归因进度日志\n\n每行：时间 | 动作。\n\n")
        f.write(f"- {stamp} | orient：模式 {mode}，当前 Stage {cur if cur<=4 else '收尾'}\n")


if __name__ == "__main__":
    main()
