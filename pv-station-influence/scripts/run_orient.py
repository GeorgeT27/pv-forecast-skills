#!/usr/bin/env python3
"""Step 0：Orient —— 每次进入本技能先跑：识别模式(A/B) + 预测侧上下文 + 定位阶段 + 报前置。

真相以产物为准（同 pv-result-analysis 的 orient 哲学）：每次重扫工作目录产物，
不信任可能过期的 state。模式由 config.checkpoint_dir 有无自动判定，不需用户预选。
预测侧上下文（留出站线 pv-result-analysis 产物）由 config.result_analysis_workdir/
result_analysis_status 判定——orient 只打印指引，问用户与写 config 是主 agent 的活。

用法：
  python <skill>/scripts/run_orient.py            # 报模式 + 上下文 + 当前阶段 + 前置 ✓/✗
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
    1: "训练动力学（loss 水平/收敛 ~ 站成员 → chunk_loss_dynamics.json）",
    2: "影响力回归（Mode A 主证据 → influence_coefs.json）",
    3: "梯度佐证 TracIn（Mode B → tracin_scores.json）",
    4: "漂移解释（复用 run_drift.py，气候距离 → 现象/假设）",
    5: "确认（Mode B：微调探针 + 剔除重训 → 已证实/CONCLUSION）",
}
ALL_STAGES = (0, 1, 2, 3, 4, 5)


def _exists(p):
    return bool(p) and os.path.exists(p)


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def scan():
    findings = _read("FINDINGS.md")
    return {
        "assignments": _exists("assignments.csv"),
        "rmse_series": _exists("rmse_series.csv"),
        "loss_records": _exists("loss_records.csv"),
        "loss_dynamics": _exists("chunk_loss_dynamics.json"),
        "probe": _read_json("probe_summary.json"),  # None = 还没探过日志
        "influence": _exists("influence_coefs.json"),
        "tracin": _exists("tracin_scores.json"),
        "drift_done": ("漂移" in findings) or ("现象" in findings)
                      or bool([d for d in os.listdir(".") if d.startswith("drift")]),
        "confirmed": ("已证实" in findings) or _exists("CONCLUSION.md"),
    }


def loss_unavailable(ev, mode):
    """Stage 1 的'无料可跑'判定：探过日志且没 loss，且 Mode A（拿不到 checkpoint 内 loss）。
    Mode B 下不能据此跳过——adapter.load_loss_history 可能可用（--from-ckpt）。"""
    probe = ev["probe"]
    return (probe is not None and not probe.get("loss_found")
            and not ev["loss_records"] and mode == "A")


def stage_done(stage, ev, mode):
    if stage == 0:
        return ev["assignments"]
    if stage == 1:
        # 无 loss 记录源 → 跳过不阻塞（同 Mode A 下 Stage 3/5 的处理）
        return ev["loss_dynamics"] or loss_unavailable(ev, mode)
    if stage == 2:
        return ev["influence"]
    if stage == 3:
        return ev["tracin"] if mode == "B" else True   # Mode A 无此阶段，视为不阻塞
    if stage == 4:
        return ev["drift_done"]
    if stage == 5:
        return ev["confirmed"] if mode == "B" else True
    return False


def prereqs(stage, cfg, ev, mode):
    if stage == 0:
        smp = cfg.get("sampler") or {}
        return [("config.sampler.n_iters 已填", bool(smp.get("n_iters"))),
                ("Mode B 才需 adapter.py（回放采样）", True)]
    if stage == 1:
        probe = ev["probe"]
        has_source = (ev["loss_records"]
                      or (probe is not None and probe.get("loss_found"))
                      or mode == "B")  # Mode B 可 --from-ckpt（需 adapter.load_loss_history）
        return [("assignments.csv 在（Stage 0）", ev["assignments"]),
                ("loss 记录源：loss_records.csv / probe 报 loss_found / Mode B 可 --from-ckpt",
                 has_source),
                ("（可选）rmse_series.csv 在——有则做 loss×ΔRMSE 关联", ev["rmse_series"])]
    if stage == 2:
        return [("assignments.csv 在（Stage 0）", ev["assignments"]),
                ("rmse_series.csv 在（日志解析或 ckpt_eval）", ev["rmse_series"])]
    if stage == 3:
        return [("Mode B（有 checkpoint_dir）", mode == "B"),
                ("adapter.loss_gradient 可用", mode == "B")]
    if stage == 4:
        return [("influence_coefs.json 或 tracin_scores.json 有嫌疑站", ev["influence"] or ev["tracin"]),
                ("训练集逐站 parquet 可读（run_drift 需要）", bool(cfg.get("stations")))]
    if stage == 5:
        return [("Mode B", mode == "B"),
                ("Stage 2/3 已给出 top 嫌疑（且最好两法一致）", ev["influence"] or ev["tracin"])]
    return []


OPTIONAL_PREFIX = "（可选）"


def _prereqs_ok(pr):
    """可选项（描述以（可选）开头）不计入 all-ok 判定。"""
    return all(ok for desc, ok in pr if not desc.startswith(OPTIONAL_PREFIX))


def current(ev, mode):
    for s in ALL_STAGES:
        if not stage_done(s, ev, mode):
            return s
    return len(ALL_STAGES)


def print_prediction_context(cfg):
    """预测侧上下文块：检测留出站线 pv-result-analysis 产物，打印三分支指引。"""
    ra = sic.detect_result_analysis(cfg)
    print("-" * 60)
    if ra["status"] == "linked":
        if ra.get("station_mismatch"):
            print(f"  ⚠⚠ 预测侧上下文：链接目录 station='{ra['station']}' ≠ 本技能测试站"
                  f"'{cfg.get('test_station', '<test_station>')}' —— 这是另一条实验线！")
            print("     拒绝消费其产物。回 Step 1 改 result_analysis_workdir 指向留出站线目录。")
        else:
            s1 = "✓" if ra.get("stage1_done") else "✗"
            s3 = "✓" if ra.get("stage3_done") else "✗"
            print(f"  预测侧上下文 [linked]: {ra['workdir']}")
            print(f"    主技能完成度：Stage1 质检+指标 {s1}   Stage3 现象提取 {s3}")
            print(f"    可消费：指标Excel×{ra['metric_excels']}"
                  f"  suspect_days {'✓' if ra['suspect_days'] else '✗'}"
                  f"  weather_class {'✓' if ra['weather_class'] else '✗'}"
                  f"  ANALYSIS.md×{ra['analysis_mds']}"
                  f"  FINDINGS {'✓' if ra['findings'] else '✗'}"
                  f"  drift/ {'✓' if ra['drift_dir'] else '✗'}")
            print("    用法：指标=留出站基线；weather_class=天气分型条件；suspect_days=反驳门#3"
                  "数据质量证据；FINDINGS 现象=归因素材；drift/=Stage 4 直接复用。")
    elif ra["status"] == "declined":
        print("  预测侧上下文 [declined]：用户已选择不先跑 pv-result-analysis —— "
              "报告与 FINDINGS 须注明缺预测侧上下文。")
    else:
        print("  ⚠ 预测侧上下文 [absent]：尚未对留出站预测跑过 pv-result-analysis（或未链接）。")
        print("    主 agent 必须先问用户：是否先跑主技能 Stage 1–3（质检+指标+现象提取）作归因上下文？")
        print(f"    同意 → 建 <cwd>/result_analysis_{cfg.get('test_station', '<test_station>')}/，"
              "按本技能 references/subagent-briefs.md")
        print("           「嵌入式主技能运行」节执行；完成后回填 config.result_analysis_workdir")
        print("           + result_analysis_status=\"linked\"。")
        print("    拒绝 → 回填 result_analysis_status=\"declined\"，继续 influence-only 分析。")
    return ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goto", type=int, choices=list(ALL_STAGES), default=None)
    args = ap.parse_args()

    if not sic.has_config():
        print("=" * 60)
        print("未找到 influence_config.json —— 此前没跑过。")
        print("→ 回 Step 1：向用户收集 训练仓库/采样代码+种子、checkpoint 目录、留出站 true_label、")
        print("  训练日志目录、17 站表 与 迭代数，写 influence_config.json（缺字段先留空）。")
        print("  同时确认：是否已有/是否要先跑留出站的 pv-result-analysis（预测侧上下文，")
        print("  见 SKILL.md「预测侧上下文」节）——已跑就填 result_analysis_workdir。")
        print("  然后先跑 probe_logs.py 探日志（同时探留出站 RMSE 与 training loss，")
        print("  决定 Mode A 是否零权重、Stage 1 动力学是否可跑）。")
        print("=" * 60)
        return

    cfg = sic.load_config()
    mode = sic.mode_from_config(cfg)
    ev = scan()
    cur = current(ev, mode)

    print("=" * 60)
    print(f"模式: {mode}（{'有 checkpoint，Stage 3/5 解锁' if mode=='B' else '仅预测/日志，观测归因'}）"
          f"    工作目录: {os.getcwd()}")
    ra = print_prediction_context(cfg)
    print("-" * 60)
    for s in ALL_STAGES:
        if mode == "A" and s in (3, 5):
            tag = "Mode B 专属（当前 Mode A，跳过）"
        elif s == 1 and loss_unavailable(ev, mode):
            tag = "无 loss 记录（跳过，不阻塞）"
        else:
            tag = "已完成" if stage_done(s, ev, mode) else ("← 当前" if s == cur else "待做")
        print(f"  Stage {s} {STAGE_NAMES[s]}  [{tag}]")
    print("-" * 60)
    target = args.goto if args.goto is not None else (cur if cur < len(ALL_STAGES) else None)
    if target is not None:
        print(f"进入 Stage {target} 的前置：")
        pr = prereqs(target, cfg, ev, mode)
        for desc, ok in pr:
            print(f"  [{'✓' if ok else '✗'}] {desc}")
        if _prereqs_ok(pr):
            print(f"→ 前置齐，可开工 Stage {target}。")
        else:
            print("→ 有 ✗ 先补：缺路径回 Step 1 问用户；缺产物回上一阶段；"
                  "缺 RMSE/loss 先 probe_logs / ckpt_eval / loss_dynamics --from-ckpt。")
    else:
        print("  六阶段完成——可写/刷新 CONCLUSION.md，或按 --goto 复核。")
    print("=" * 60)

    # 写 state + PROGRESS（单写者：只有主 agent 调 orient，subagent 不碰这两个文件）
    state = {"mode": mode, "updated": dt.datetime.now().isoformat(timespec="seconds"),
             "current_stage": cur, "artifacts": {k: v for k, v in ev.items() if k != "probe"},
             "prediction_context": {"status": ra["status"],
                                    "workdir": ra.get("workdir"),
                                    "station_mismatch": ra.get("station_mismatch", False)}}
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    new = not _exists(PROGRESS_PATH)
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        if new:
            f.write("# PROGRESS —— 站点影响力归因进度日志\n\n每行：时间 | 动作。\n\n")
        f.write(f"- {stamp} | orient：模式 {mode}，预测侧上下文 {ra['status']}，"
                f"当前 Stage {cur if cur < len(ALL_STAGES) else '收尾'}\n")


if __name__ == "__main__":
    main()
