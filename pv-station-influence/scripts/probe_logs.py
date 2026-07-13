#!/usr/bin/env python3
"""Stage 0 前置 —— 探测训练日志里有没有「逐 (迭代,chunk) 的白马湖 RMSE 序列」。

这一步决定走哪条路（用户当前不确定 RMSE 是否入日志）：
  找到      → Mode A 全程零权重：解析出 rmse_series.csv，直接进 Stage 1。
  没找到+有ckpt → 需 ckpt_eval.py 逐 checkpoint 重算（Mode B 前向）。
  没找到+无ckpt → Stage 1 被阻塞，只能做 Stage 3（漂移）。

不臆测格式：扫 log_dir 下常见文本/表格/事件文件，用宽松正则找「白马湖 + rmse + 数字」，
报告命中文件与样例行，让主 agent 据实决定解析器。**不自动改写任何东西。**

用法：
  python <skill>/scripts/probe_logs.py            # 扫 config.log_dir
  python <skill>/scripts/probe_logs.py --dir PATH
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import si_common as sic

# 白马湖可能的写法：中文 / 拼音 / 站 id
STATION_PAT = re.compile(r"(白马湖|baima|baimahu|bmh)", re.IGNORECASE)
RMSE_PAT = re.compile(r"\brmse\b", re.IGNORECASE)
NUM_PAT = re.compile(r"[-+]?\d*\.?\d+")
TEXT_EXT = (".log", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".out", ".err", ".md")


def _scan_file(path, max_hits=5):
    hits = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln, line in enumerate(f, 1):
                if RMSE_PAT.search(line) and (STATION_PAT.search(line) or "val" in line.lower()):
                    hits.append((ln, line.rstrip()[:200]))
                    if len(hits) >= max_hits:
                        break
    except (OSError, UnicodeError):
        pass
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()

    log_dir = args.dir
    if log_dir is None:
        try:
            cfg = sic.load_config()
            log_dir = cfg.get("log_dir")
        except FileNotFoundError:
            pass
    if not log_dir or not os.path.isdir(log_dir):
        sys.exit("未指定可用的 log_dir（config.log_dir 或 --dir）。若确无日志目录，"
                 "直接判定‘RMSE 未入日志’，据 checkpoint 有无决定 Mode A(阻塞)/Mode B(重算)。")

    files = [p for p in glob.glob(os.path.join(log_dir, "**", "*"), recursive=True)
             if os.path.isfile(p) and p.lower().endswith(TEXT_EXT)]
    print("=" * 56)
    print(f"探测日志目录: {log_dir}   文本类文件 {len(files)} 个")
    found_any = False
    shown = 0
    for p in sorted(files):
        hits = _scan_file(p)
        if hits:
            found_any = True
            shown += 1
            print(f"\n[命中] {os.path.relpath(p, log_dir)}")
            for ln, txt in hits[:3]:
                print(f"   L{ln}: {txt}")
            if shown >= 12:
                print("   …(更多命中略)")
                break
    print("-" * 56)
    if found_any:
        print("→ 疑似找到白马湖 RMSE 记录。主 agent：核对上面样例行的字段，写一个小解析器把")
        print("  (iteration, chunk, position, model, rmse) 落成 rmse_series.csv，然后进 Stage 1（Mode A）。")
    else:
        print("→ 未在日志里找到白马湖逐 chunk RMSE。")
        print("  有 checkpoint_dir → 用 ckpt_eval.py 逐 checkpoint 重算（Mode B）。")
        print("  无 checkpoint     → Stage 1 阻塞，只能做 Stage 3 漂移分析。")
    print("=" * 56)


if __name__ == "__main__":
    main()
