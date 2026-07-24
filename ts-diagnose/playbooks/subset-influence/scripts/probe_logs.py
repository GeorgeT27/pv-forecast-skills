#!/usr/bin/env python3
"""Stage 0 前置 —— 一次扫描同时探测训练日志里的两类记录：

  ① 逐 (迭代,chunk) 的留出站 RMSE 序列（Stage 2 回归的因变量）
  ② 逐 epoch/chunk 的 training loss 记录（Stage 1 训练动力学的原料）

RMSE 结论决定走哪条路（用户当前不确定是否入日志）：
  找到      → Mode A 全程零权重：解析出 rmse_series.csv，直接进 Stage 2。
  没找到+有ckpt → 需 ckpt_eval.py 逐 checkpoint 重算（Mode B 前向）。
  没找到+无ckpt → Stage 2 被阻塞，只能做 Stage 4（漂移）。
loss 结论决定 Stage 1 是否可跑：
  找到      → 主 agent 据样例行写小解析器落 loss_records.csv。
  没找到+有ckpt → loss_dynamics.py --from-ckpt（需 adapter.load_loss_history）。
  都没有    → Stage 1 跳过（orient 自动不阻塞）。

不臆测格式：宽松正则报命中文件与样例行，让主 agent 据实决定解析器；
**落盘 probe_summary.json**（orient 据它判 Stage 1 可用性），除此不改写任何东西。

用法：
  python <skill>/scripts/probe_logs.py            # 扫 config.log_dir
  python <skill>/scripts/probe_logs.py --dir PATH
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic

# 留出站在日志里的可能写法：config 的 test_station + test_station_aliases（中文/拼音/站 id）。
# 两者都空时回退默认（历史项目兼容）。
DEFAULT_STATION_PAT = re.compile(r"(白马湖|baima|baimahu|bmh)", re.IGNORECASE)


def station_pattern(cfg):
    names = [cfg.get("test_station", "")] + list(cfg.get("test_station_aliases", []))
    parts = [re.escape(n) for n in names if n]
    if not parts:
        return DEFAULT_STATION_PAT
    return re.compile("(" + "|".join(parts) + ")", re.IGNORECASE)


RMSE_PAT = re.compile(r"\brmse\b", re.IGNORECASE)
# training loss：要求同行有 epoch/iter/chunk/step 线索才算命中（降误报——"loss" 一词太常见）
LOSS_PAT = re.compile(r"\b(train[_ ]?loss|loss)\b\s*[:=]?\s*[-+]?\d*\.?\d+", re.IGNORECASE)
CTX_PAT = re.compile(r"\b(epoch|iter(ation)?|chunk|step)\b", re.IGNORECASE)
TEXT_EXT = (".log", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".out", ".err", ".md")

SUMMARY_PATH = "probe_summary.json"


def _scan_file(path, station_pat, max_hits=5):
    """一次遍历同时收两类命中，返回 {"rmse": [...], "loss": [...]}。"""
    hits = {"rmse": [], "loss": []}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln, line in enumerate(f, 1):
                if (len(hits["rmse"]) < max_hits
                        and RMSE_PAT.search(line)
                        and (station_pat.search(line) or "val" in line.lower())):
                    hits["rmse"].append((ln, line.rstrip()[:200]))
                if (len(hits["loss"]) < max_hits
                        and LOSS_PAT.search(line) and CTX_PAT.search(line)):
                    hits["loss"].append((ln, line.rstrip()[:200]))
                if len(hits["rmse"]) >= max_hits and len(hits["loss"]) >= max_hits:
                    break
    except (OSError, UnicodeError):
        pass
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()

    log_dir = args.dir
    station_pat = DEFAULT_STATION_PAT
    if log_dir is None:
        try:
            cfg = sic.load_config()
            log_dir = cfg.get("log_dir")
            station_pat = station_pattern(cfg)
        except FileNotFoundError:
            pass
    if not log_dir or not os.path.isdir(log_dir):
        # 无日志目录也落盘结论（两类都未找到），orient 才能判 Stage 1 跳过
        sic.dump_json(SUMMARY_PATH, {
            "probed_at": dt.datetime.now().isoformat(timespec="seconds"),
            "log_dir": log_dir, "rmse_found": False, "loss_found": False,
            "rmse_hit_files": [], "loss_hit_files": [], "sample_lines": {},
            "note": "log_dir 缺失/无效，未扫描",
        })
        sys.exit("未指定可用的 log_dir（config.log_dir 或 --dir）。若确无日志目录，"
                 "直接判定'RMSE/loss 均未入日志'（已落 probe_summary.json），"
                 "据 checkpoint 有无决定 Mode A(阻塞)/Mode B(重算)。")

    files = [p for p in glob.glob(os.path.join(log_dir, "**", "*"), recursive=True)
             if os.path.isfile(p) and p.lower().endswith(TEXT_EXT)]
    print("=" * 56)
    print(f"探测日志目录: {log_dir}   文本类文件 {len(files)} 个")
    rmse_files, loss_files = [], []
    samples = {"rmse": [], "loss": []}
    shown = 0
    for p in sorted(files):
        hits = _scan_file(p, station_pat)
        rel = os.path.relpath(p, log_dir)
        if hits["rmse"]:
            rmse_files.append(rel)
        if hits["loss"]:
            loss_files.append(rel)
        if hits["rmse"] or hits["loss"]:
            shown += 1
            if shown <= 12:
                tags = "+".join(k for k in ("rmse", "loss") if hits[k])
                print(f"\n[命中:{tags}] {rel}")
                for kind in ("rmse", "loss"):
                    for ln, txt in hits[kind][:2]:
                        print(f"   [{kind}] L{ln}: {txt}")
                        if len(samples[kind]) < 6:
                            samples[kind].append(f"{rel}:L{ln}: {txt}")
            elif shown == 13:
                print("   …(更多命中文件略，见 probe_summary.json)")

    rmse_found, loss_found = bool(rmse_files), bool(loss_files)
    sic.dump_json(SUMMARY_PATH, {
        "probed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "log_dir": log_dir,
        "rmse_found": rmse_found, "loss_found": loss_found,
        "rmse_hit_files": rmse_files[:20], "loss_hit_files": loss_files[:20],
        "sample_lines": samples,
    })

    print("-" * 56)
    if rmse_found:
        print("→ [RMSE] 疑似找到留出站 RMSE 记录。主 agent：核对样例行字段，写小解析器把")
        print("  (iteration, chunk, position, model, rmse) 落成 rmse_series.csv → Stage 2（Mode A）。")
    else:
        print("→ [RMSE] 未在日志找到留出站逐 chunk RMSE。")
        print("  有 checkpoint_dir → ckpt_eval.py 逐 checkpoint 重算（Mode B）；无 → Stage 2 阻塞。")
    if loss_found:
        print("→ [loss] 疑似找到 training loss 记录。主 agent：据样例行写小解析器落 loss_records.csv")
        print("  （列 iteration,chunk,position,model,epoch,loss；step 级记录先按 epoch 聚合均值）")
        print("  → 然后 loss_dynamics.py 跑 Stage 1 训练动力学。")
    else:
        print("→ [loss] 未找到 training loss 记录。")
        print("  有 checkpoint_dir 且 adapter.load_loss_history 可用 → loss_dynamics.py --from-ckpt；")
        print("  都没有 → Stage 1 训练动力学跳过（orient 自动不阻塞）。")
    print(f"（结论已落 {SUMMARY_PATH}）")
    print("=" * 56)


if __name__ == "__main__":
    main()
