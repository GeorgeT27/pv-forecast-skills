#!/usr/bin/env python3
"""Step 0：Orient —— 每次进入本技能先跑：定位阶段 + 报前置 + 执行 feature_true 硬规则。

真相以产物为准（同 pv-result-analysis / pv-station-influence 的 orient 哲学）：每次重扫
工作目录产物，不信任可能过期的 state。**硬规则**：feature_true.parquet 未提供且用户未明确
确认"没有"（config.feature_true_status != "user_confirmed_missing"）时，Stage 0 前置报 ✗，
主 agent 必须先 AskUserQuestion 向用户索要——绝不静默降级到窗口重叠重建。

用法：
  python <skill>/scripts/run_orient.py            # 报当前阶段 + 前置 ✓/✗
  python <skill>/scripts/run_orient.py --goto 2   # 想直达某阶段：校验前置
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb

STATE_PATH = "blame_state.json"
PROGRESS_PATH = "PROGRESS.md"

STAGE_NAMES = {
    0: "schema 探查与对齐守卫（probe_schema.py → probe_schema.json + feature_pairs.json）",
    1: "坏行定位·每口径×每模型（find_bad_rows.py → bad_rows_summary.json + CSV）",
    2: "特征归因·先剥系统偏差（feature_decompose.py=Stage 1.5）再 ε_res 两关点名（feature_blame.py）+ 翻新跳变两关（feature_revision.py，免 API）",
    3: "现象清单（**停顿**：主 agent 汇报现象，问用户是否做反事实 → FINDINGS.md）",
    4: "反事实确认·可选（counterfactual_api.py + adapter.py + FastAPI → counterfactual_summary.json）",
    5: "结论（反驳门 + CONCLUSION.md）",
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


def feature_true_ok(cfg):
    """硬规则台账：给了路径且文件在 → ok；用户明确确认没有 → 降级模式（ok 但要在报告注明）。"""
    ft = cfg.get("feature_true")
    if ft and os.path.exists(ft):
        return True, "provided"
    if cfg.get("feature_true_status") == "user_confirmed_missing":
        return True, "degraded"
    return False, "missing"


def api_declined(cfg):
    return (cfg.get("api") or {}).get("declined") is True


def scan():
    findings = _read("FINDINGS.md")
    return {
        "probe": fb.read_json("probe_schema.json"),
        "pairs": fb.read_json("feature_pairs.json"),
        "bad_rows": _exists("bad_rows_summary.json"),
        "blame": _exists("blame_report.csv") and _exists("blame_summary.json"),
        "revision": _exists("revision_summary.json"),
        "decomp": _exists("feature_decomp.json"),
        "findings_done": "现象" in findings,
        "counterfactual": _exists("counterfactual_summary.json"),
        "concluded": _exists("CONCLUSION.md"),
    }


def revision_enabled(cfg):
    return (cfg.get("revision") or {}).get("enabled", True) is not False


def decompose_enabled(cfg):
    return (cfg.get("decompose") or {}).get("enabled", True) is not False


def stage_done(stage, ev, cfg):
    if stage == 0:
        pairs = ev["pairs"] or {}
        return bool(ev["probe"]) and bool(pairs.get("pairs")) and not pairs.get("unmapped")
    if stage == 1:
        return ev["bad_rows"]
    if stage == 2:
        return (ev["blame"] and (ev["revision"] or not revision_enabled(cfg))
                and (ev["decomp"] or not decompose_enabled(cfg)))
    if stage == 3:
        return ev["findings_done"]
    if stage == 4:
        return ev["counterfactual"] or api_declined(cfg)   # 用户拒绝反事实 → 跳过不阻塞
    if stage == 5:
        return ev["concluded"]
    return False


def prereqs(stage, cfg, ev):
    ft_ok, ft_mode = feature_true_ok(cfg)
    if stage == 0:
        return [("test_label / predict 路径已填", bool(cfg.get("test_label")) and bool(cfg.get("predict"))),
                ("feature_true 已提供或用户已确认缺失（硬规则：缺了先 AskUserQuestion 要，绝不静默降级）", ft_ok)]
    if stage == 1:
        probe = ev["probe"] or {}
        pairs = ev["pairs"] or {}
        cross = probe.get("label_crosscheck") or {}
        cross_ok = (not cross.get("n_checked")) or (cross.get("agree_rate") or 0) >= 0.99
        wc_ok = not probe.get("window_consistency_bad_rate")
        return [("probe_schema.json 在（Stage 0）", bool(probe)),
                ("特征对已配齐：unmapped 为空（配不上的先问用户，答案写回 feature_pairs.json）",
                 bool(pairs.get("pairs")) and not pairs.get("unmapped")),
                ("真值列滚动窗一致性通过（>0 = 窗口构造 bug；predict/预报特征行间差是预期物理，不进闸）", wc_ok),
                ("label 交叉核验 ≥0.99 或无可核材料（核不上 = 对齐错位/label 有假，先排除）", cross_ok)]
    if stage == 2:
        return [("feature_decomp.json 在（Stage 1.5 feature_decompose.py；不想剥系统偏差可"
                 "在 config 设 decompose.enabled=false）",
                 ev["decomp"] or not decompose_enabled(cfg)),
                ("bad_rows_summary.json 在（Stage 1）", ev["bad_rows"]),
                ("feature_pairs.json 在（Stage 0）", bool((ev["pairs"] or {}).get("pairs")))]
    if stage == 3:
        return [("blame_summary.json 在（Stage 2）", ev["blame"])]
    if stage == 4:
        api = cfg.get("api") or {}
        return [("用户已确认 FastAPI 配置（config.api.confirmed=true；细节先跟用户对）",
                 api.get("confirmed") is True),
                ("工作目录有 adapter.py（复制 scripts/api_adapter_template.py 填 TODO）",
                 _exists("adapter.py")),
                ("blame_report.csv 在（Stage 2；oracle/minimal-set 用全部坏行，不限被点名的）", ev["blame"]),
                ("（可选）revision_summary.json 在——neighbor-swap 模式（翻新致不稳反事实）才需要", ev["revision"]),
                ("（可选）metric_py 已填——要复算月度口径 (--monthly) 才需要", bool(cfg.get("metric_py")))]
    if stage == 5:
        return [("FINDINGS.md 已有现象（Stage 3）", ev["findings_done"]),
                ("（可选）反事实产物在——没跑反事实不得把归因标「已证实」", ev["counterfactual"])]
    return []


OPTIONAL_PREFIX = "（可选）"


def _prereqs_ok(pr):
    return all(ok for desc, ok in pr if not desc.startswith(OPTIONAL_PREFIX))


def current(ev, cfg):
    for s in ALL_STAGES:
        if not stage_done(s, ev, cfg):
            return s
    return len(ALL_STAGES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goto", type=int, choices=list(ALL_STAGES), default=None)
    args = ap.parse_args()

    if not fb.has_config():
        print("=" * 60)
        print("未找到 blame_config.json —— 此前没跑过。")
        print("→ 回 Step 1：向用户收集 test.parquet（真值）、predict.parquet（模型预测）、")
        print("  **feature_true.parquet（特征预测/真值对照——没有就必须先问用户要，绝不静默降级）**，")
        print("  写 blame_config.json（字段说明见 scripts/fb_common.py 头部；缺字段先留空）。")
        print("  同时按 SKILL.md Step 0.5 载入 project-context 实验线（data_paths.feature_true")
        print("  缺【待补】→ 追问一次并补写回实验线 json）。")
        print("=" * 60)
        return

    cfg = fb.load_config()
    ev = scan()
    cur = current(ev, cfg)
    ft_ok, ft_mode = feature_true_ok(cfg)

    print("=" * 60)
    print(f"工作目录: {os.getcwd()}")
    if ft_mode == "degraded":
        print("  ⚠ feature_true 缺失但用户已确认没有 → 降级模式（窗口重叠重建，见 references/"
              "blame-methods.md；FINDINGS/CONCLUSION 须注明证据弱一级）")
    elif ft_mode == "missing":
        print("  ⛔ feature_true 未提供且用户未确认缺失 —— 先 AskUserQuestion 向用户要，")
        print("     确实没有则写 config.feature_true_status=\"user_confirmed_missing\" 再继续。")
    if ev["blame"] and not ev["decomp"] and decompose_enabled(cfg):
        print("  ℹ 旧版产物：blame 在但缺 feature_decomp.json（v3 起点名基于 ε_res）。")
        print("    补跑 feature_decompose.py + 重跑 feature_blame.py 即升级；不需要可设"
              " decompose.enabled=false。")
    if ev["blame"] and not ev["revision"] and revision_enabled(cfg):
        print("  ℹ 检测到旧版产物：blame 归因在但缺 revision_summary.json（v2 起 Stage 2 含翻新")
        print("    跳变分析）。补跑 feature_revision.py（免 API，本地即可）即恢复；不需要可在")
        print("    config 里设 revision.enabled=false。")
    print("-" * 60)
    for s in ALL_STAGES:
        if s == 4 and api_declined(cfg):
            tag = "用户拒绝反事实（跳过，不阻塞；结论最高只能到「假设」）"
        else:
            tag = "已完成" if stage_done(s, ev, cfg) else ("← 当前" if s == cur else "待做")
        print(f"  Stage {s} {STAGE_NAMES[s]}  [{tag}]")
    print("-" * 60)
    target = args.goto if args.goto is not None else (cur if cur < len(ALL_STAGES) else None)
    if target is not None:
        print(f"进入 Stage {target} 的前置：")
        pr = prereqs(target, cfg, ev)
        for desc, ok in pr:
            print(f"  [{'✓' if ok else '✗'}] {desc}")
        if _prereqs_ok(pr):
            print(f"→ 前置齐，可开工 Stage {target}。")
            if target == 3:
                print("  （Stage 3 是停顿点：现象报给用户点名，问要不要做反事实，别自作主张往下冲。）")
        else:
            print("→ 有 ✗ 先补：缺路径/缺 feature_true 回 Step 1 问用户；缺产物回上一阶段；"
                  "unmapped 非空先 AskUserQuestion 配对；API 未确认先跟用户对细节。")
    else:
        print("  六阶段完成——可写/刷新 CONCLUSION.md，或按 --goto 复核。")
    print("=" * 60)

    # 写 state + PROGRESS（单写者：只有主 agent 调 orient，subagent 不碰这两个文件）
    state = {"updated": dt.datetime.now().isoformat(timespec="seconds"),
             "current_stage": cur, "feature_true_mode": ft_mode,
             "artifacts": {k: bool(v) for k, v in ev.items()}}
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    new = not _exists(PROGRESS_PATH)
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        if new:
            f.write("# PROGRESS —— 特征归因进度日志\n\n每行：时间 | 动作。\n\n")
        f.write(f"- {stamp} | orient：feature_true={ft_mode}，"
                f"当前 Stage {cur if cur < len(ALL_STAGES) else '收尾'}\n")


if __name__ == "__main__":
    main()
