#!/usr/bin/env python3
"""Step 0：Orient —— 每次进入技能先跑，告诉你"现在在哪个阶段、下一步前置齐不齐"。

用法（在有 analysis_config.json 的工作目录）：
    python <skill>/scripts/run_orient.py            # 报当前阶段 + 各阶段前置 ✓/✗
    python <skill>/scripts/run_orient.py --goto 4   # 想直达 Stage 4：校验前置，缺则告诉你正确入口

设计要点（见技能计划 & SKILL.md Step 0）：
- **真相以产物为准，state 只是快速索引**。每次跑都重新扫 figures/ 等真实文件，
  再和 analysis_state.json 里的记录"和解"：state 说 done 但产物缺了 → 该阶段降级为未完成。
  这样既满足"要显式日志/能续跑"，又不被会说谎的状态文件带偏。
- 判定"当前阶段 = 第一个未完成阶段"；每阶段的前置条件编码在下面 STAGE_PREREQS。
- 收尾把和解后的状态写回 analysis_state.json，并向 PROGRESS.md 追加一行叙事日志。

本脚本只做"扫产物 + 核验 + 报阶段"，不重复任何数据处理逻辑。
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_utils as du  # 复用 CONFIG 常量与 load_table，不新写数据逻辑

CONFIG_PATH = "analysis_config.json"
STATE_PATH = "analysis_state.json"
PROGRESS_PATH = "PROGRESS.md"

STAGE_NAMES = {
    1: "数据与指标（质检 + metric.py → 5 Excel）",
    2: "相关性（误差矩阵 + 图#2）",
    3: "事实提取（图#1/#4/#7/#8… → 现象清单）",
    4: "深归因（Playbook + 反驳门 + CONCLUSION.md）",
}


# ---------------------------------------------------------------- 产物扫描
def _exists(path):
    return bool(path) and os.path.exists(path)


def _readable_parquet(path):
    """只判存在 + 能被 load_table 打开（不做完整质检，那是 Stage 1 的事）。"""
    if not _exists(path):
        return False
    try:
        du.load_table(path)
        return True
    except Exception:
        return False


def scan_artifacts(cfg):
    """扫工作目录 + figures/<station> 下的真实产物，返回一个 evidence 字典。"""
    station = cfg.get("station", "")
    figdir = os.path.join("figures", station) if station else "figures"

    metric_excels = sorted(
        set(glob.glob("*.xlsx"))
        | set(glob.glob(os.path.join(figdir, "**", "*.xlsx"), recursive=True))
    )
    corr_pngs = glob.glob(os.path.join(figdir, "**", "02_error_corr.png"), recursive=True)
    corr_stats = glob.glob(os.path.join(figdir, "**", "02_error_corr.stats.json"), recursive=True)
    analysis_mds = glob.glob(os.path.join(figdir, "**", "ANALYSIS.md"), recursive=True)
    stats_jsons = glob.glob(os.path.join(figdir, "**", "*.stats.json"), recursive=True)

    findings = _read_text("FINDINGS.md")
    # "现象" 条目 = Stage 3 产出；"已证实/假设" = Stage 4 升级后
    has_phenomena = ("现象" in findings) or bool(analysis_mds)
    has_attributed = ("已证实" in findings) or ("假设" in findings) or _exists("CONCLUSION.md")

    refs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")
    refs_present = os.path.isdir(refs_dir) and bool(os.listdir(refs_dir))

    return {
        "station": station,
        "metric_excels": metric_excels,
        "suspect_days": _exists("suspect_days.csv"),
        "weather_class": _exists("weather_class.csv"),
        "corr_png": corr_pngs[0] if corr_pngs else None,
        "corr_stats": corr_stats[0] if corr_stats else None,
        "analysis_mds": analysis_mds,
        "stats_jsons": stats_jsons,
        "has_phenomena": has_phenomena,
        "has_attributed": has_attributed,
        "conclusion": _exists("CONCLUSION.md"),
        "refs_present": refs_present,
    }


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# ---------------------------------------------------------------- 阶段判定 & 前置
def stage_done(stage, cfg, ev):
    """某阶段是否"已完成"——纯看真实产物（真相以产物为准）。"""
    if stage == 1:
        return ev["suspect_days"] and bool(ev["metric_excels"])
    if stage == 2:
        return _exists(ev["corr_png"]) and _exists(ev["corr_stats"])
    if stage == 3:
        return ev["has_phenomena"]
    if stage == 4:
        return ev["has_attributed"]
    return False


def stage_prereqs(stage, cfg, ev):
    """进入某阶段前应满足的前置，返回 [(说明, 通过?)]。"""
    if stage == 1:
        pred = cfg.get("predicted") or {}
        return [
            ("config 有 metric_py 且文件存在", _exists(cfg.get("metric_py"))),
            ("config 有 true_label 且 parquet 可读", _readable_parquet(cfg.get("true_label"))),
            ("config 有至少一个 predicted 且可读",
             bool(pred) and all(_readable_parquet(p) for p in pred.values())),
        ]
    if stage == 2:
        pred = cfg.get("predicted") or {}
        return [
            ("质检已过（suspect_days.csv 在）", ev["suspect_days"]),
            ("true_label parquet 可读", _readable_parquet(cfg.get("true_label"))),
            ("predicted parquet 可读", bool(pred) and all(_readable_parquet(p) for p in pred.values())),
        ]
    if stage == 3:
        return [
            ("Stage 2 已完成（02_error_corr.png + stats 在）", stage_done(2, cfg, ev)),
        ]
    if stage == 4:
        return [
            ("现象清单可得（FINDINGS.md 现象条目 或 ANALYSIS.md+stats.json）", ev["has_phenomena"]),
            ("证据 stats.json 仍在 figures/ 下", bool(ev["stats_jsons"])),
            ("references/ 齐（归因背景来源）", ev["refs_present"]),
        ]
    return []


def current_stage(cfg, ev):
    """第一个未完成的阶段。四个都完成 → 返回 5（分析已收尾）。"""
    for s in (1, 2, 3, 4):
        if not stage_done(s, cfg, ev):
            return s
    return 5


# ---------------------------------------------------------------- state 和解 & 日志
def reconcile_state(cfg, ev, cur):
    """据真实产物重建 state（不信任旧 state 的 done 标记）。"""
    stages = {}
    for s in (1, 2, 3, 4):
        stages[str(s)] = {
            "status": "done" if stage_done(s, cfg, ev) else ("current" if s == cur else "todo"),
        }
    stages["1"]["artifacts"] = list(ev["metric_excels"]) + (["suspect_days.csv"] if ev["suspect_days"] else [])
    stages["2"]["artifacts"] = [p for p in (ev["corr_png"], ev["corr_stats"]) if p]
    stages["3"]["artifacts"] = list(ev["analysis_mds"])
    stages["4"]["artifacts"] = (["CONCLUSION.md"] if ev["conclusion"] else [])
    return {
        "station": ev["station"],
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
        "current_stage": cur,
        "stages": stages,
    }


def write_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def append_progress(line):
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    new = not _exists(PROGRESS_PATH)
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        if new:
            f.write("# PROGRESS —— 分析进度叙事日志\n\n"
                    "每行：时间 | 动作。orient 每次进入追加一行；阶段收尾由主 agent 追加结论行。\n\n")
        f.write(f"- {stamp} | {line}\n")


# ---------------------------------------------------------------- 报告
def _mark(ok):
    return "✓" if ok else "✗"


def report(cfg, ev, cur, goto=None):
    lines = []
    lines.append("=" * 60)
    lines.append(f"电站: {ev['station'] or '(未设)'}    工作目录: {os.getcwd()}")
    lines.append("-" * 60)
    for s in (1, 2, 3, 4):
        done = stage_done(s, cfg, ev)
        tag = "已完成" if done else ("← 当前" if s == cur else "待做")
        lines.append(f"  Stage {s} {STAGE_NAMES[s]}  [{tag}]")
    if cur == 5:
        lines.append("  四阶段均完成——分析已收尾（可写/刷新 CONCLUSION.md 或按 --goto 复核某阶段）。")
    lines.append("-" * 60)

    target = goto if goto else cur
    if target in (1, 2, 3, 4):
        lines.append(f"进入 Stage {target} 的前置检查：")
        prereqs = stage_prereqs(target, cfg, ev)
        all_ok = all(ok for _, ok in prereqs)
        for desc, ok in prereqs:
            lines.append(f"  [{_mark(ok)}] {desc}")
        if goto:
            if all_ok:
                lines.append(f"→ 前置齐备，可直达 Stage {goto}。")
            else:
                # 找正确入口：从 goto 往前第一个"前置齐备且自身未完成"的阶段，否则用 current
                entry = cur
                lines.append(f"→ 前置不齐，不能直达 Stage {goto}。正确入口 = Stage {entry}"
                             f"（{STAGE_NAMES[entry] if entry in STAGE_NAMES else '已收尾'}）。")
        else:
            lines.append("→ 齐备则开工；有 ✗ 先补上（缺路径回 Step 1 问用户，缺产物回上一阶段）。")
    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Step 0 Orient：定位阶段 + 前置检查")
    ap.add_argument("--goto", type=int, choices=[1, 2, 3, 4], default=None,
                    help="想直达的目标阶段；校验前置，缺则报正确入口")
    ap.add_argument("--config", default=CONFIG_PATH)
    args = ap.parse_args()

    if not _exists(args.config):
        print("=" * 60)
        print(f"未找到 {args.config} —— 此前没有完整跑过。")
        print("→ 回 Stage 1 / Step 1：向用户收集 metric.py、true_label、predicted 路径，写 analysis_config.json。")
        print("  （不要凭记忆猜路径；找不到 config 说明还没建立分析上下文。）")
        print("=" * 60)
        sys.exit(0)

    cfg = json.load(open(args.config, encoding="utf-8"))
    ev = scan_artifacts(cfg)
    cur = current_stage(cfg, ev)

    print(report(cfg, ev, cur, goto=args.goto))

    state = reconcile_state(cfg, ev, cur)
    write_state(state)
    goto_note = f"（--goto {args.goto}）" if args.goto else ""
    append_progress(f"orient{goto_note}：当前 Stage {cur if cur <= 4 else '收尾'}；"
                    f"已完成 {[s for s in (1,2,3,4) if stage_done(s, cfg, ev)]}")


if __name__ == "__main__":
    main()
