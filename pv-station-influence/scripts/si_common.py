"""pv-station-influence —— 共享工具（配置 / 路径 / RMSE / 复用主技能 data_utils）。

设计纪律（见 SKILL.md 上下文预算节）：
- 所有重活在脚本内完成，脚本只 print ≤30 行摘要；产物落盘 CSV/JSON，各带自足 summary。
- 复用兄弟技能 pv-result-analysis/scripts/data_utils.py 读 parquet、算 PSI，不另写一套。

配置文件 influence_config.json（工作目录，字段全部可选、按模式渐进填）：
{
  "test_station": "<留出测试站拼音/id>",      # 留出测试站（= 实验线 held_out_station）
  "test_station_aliases": [],                # 留出站在日志里的可能写法（probe_logs 扫日志用）
  "experiment": "<实验线名>",                 # project-context/experiments/ 下的文件名（Step 0.5 写入）
  "stations": ["s01", ...],                  # 17 个训练站的 id/名（顺序即回归设计矩阵列序）
  "test_label": "<留出站 true_label parquet>",# 算留出站 RMSE 的真值
  "train_repo": "<训练代码仓库根>",           # 供 adapter 导入 sampler / 模型类
  "sampler": {"seeds": [...], "n_iters": N}, # 种子与实际迭代数（Stage 0 回放用）
  "log_dir": "<训练日志目录>",                # Stage 0 前的 probe_logs 扫这里
  "checkpoint_dir": "<checkpoint 根>",        # 有此字段 => 解锁 Mode B（有 optimizer state 更好）
  "models": ["M1", "M2", "M3", "M4"],         # 要分析的模型（缺省四个都做）
  "chunk_layout": {"n_chunks": 4, "sizes": [5, 5, 5, 2]},  # 每迭代的 chunk 结构
  "result_analysis_workdir": "<留出站线 pv-result-analysis 工作目录（绝对路径）>",
      # 预测侧上下文：嵌入运行默认 <influence工作目录>/result_analysis_<留出站拼音>/；
      # 已单独跑过留出站结果分析就填那个目录。orient 据此扫描可消费产物。
  "result_analysis_status": "linked",
      # "linked"=可消费其产物；"declined"=用户拒绝先跑（报告须注明缺预测侧上下文）；
      # 缺失/null=还没问过用户 —— orient 会提示主 agent 先问。
}
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

CONFIG_PATH = "influence_config.json"

# 复用主技能 data_utils（读 parquet / to_matrix / psi）。找不到就降级：本技能不重写。
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIBLING = os.path.normpath(os.path.join(_SKILL_ROOT, "..", "pv-result-analysis", "scripts"))
if os.path.isdir(_SIBLING) and _SIBLING not in sys.path:
    sys.path.insert(0, _SIBLING)
try:
    import data_utils as du  # noqa: E402  复用：load_table / to_matrix / psi / LABEL_COL
except Exception:            # pragma: no cover - 仅在兄弟技能缺失时
    du = None


def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"未找到 {path}。先按 SKILL.md Step 1 收集路径写 influence_config.json（缺字段就先留空）。"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def has_config(path: str = CONFIG_PATH) -> bool:
    return os.path.exists(path)


def mode_from_config(cfg: dict) -> str:
    """有可用 checkpoint_dir => Mode B（解锁 Stage 3/5 与 Stage 1 的 --from-ckpt），否则 Mode A。"""
    ck = cfg.get("checkpoint_dir")
    return "B" if ck and os.path.isdir(ck) else "A"


def stations(cfg: dict) -> list[str]:
    st = cfg.get("stations") or []
    if not st:
        raise ValueError("config.stations 为空：需要 17 个训练站的稳定 id/名（顺序=设计矩阵列序）。")
    return list(st)


# ---------------------------------------------------------------- 指标
def rmse(pred: np.ndarray, true: np.ndarray) -> float:
    """整体 48h RMSE（不取点、不拆天）——Stage 2 因变量默认口径，简单稳定。

    留出站零样本评估用最朴素的 192 点整体 RMSE 即可；细分口径留给确认阶段。
    """
    pred = np.asarray(pred, float)
    true = np.asarray(true, float)
    mask = np.isfinite(pred) & np.isfinite(true)
    if not mask.any():
        return float("nan")
    return float(np.sqrt(np.mean((pred[mask] - true[mask]) ** 2)))


# ---------------------------------------------------------------- 产物落盘 + 自足摘要
def dump_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_test_label_matrix(cfg: dict):
    """载入留出站真值并转 (n,192) 矩阵 + timestamps。复用 data_utils。"""
    if du is None:
        raise RuntimeError("找不到 pv-result-analysis/scripts/data_utils.py，无法读 parquet。")
    df = du.load_table(cfg["test_label"])
    Y = du.to_matrix(df, du.LABEL_COL)
    return df[du.TIMESTAMP_COL].to_numpy(), Y


# ---------------------------------------------------------------- 预测侧上下文（pv-result-analysis 产物探测）
def detect_result_analysis(cfg: dict) -> dict:
    """只读扫描 result_analysis_workdir，返回留出站线 pv-result-analysis 的产物清单。

    判定逻辑镜像主技能 run_orient 的 stage_done（不 import 它——那个脚本假设 cwd
    是分析目录且会写 state；这里纯只读、不改任何文件）。返回 dict 的 status 取值：
      "linked"   工作目录有效且 station 匹配 → 附各产物 flag
      "declined" 用户已明确拒绝先跑（config.result_analysis_status）
      "absent"   没链接 / 目录无效 / 缺 analysis_config.json → 主 agent 该先问用户
    """
    import glob as _glob

    status = cfg.get("result_analysis_status")
    if status == "declined":
        return {"status": "declined"}
    wd = cfg.get("result_analysis_workdir")
    acfg_path = os.path.join(wd, "analysis_config.json") if wd else None
    if not wd or not os.path.isdir(wd) or not os.path.exists(acfg_path):
        return {"status": "absent", "workdir": wd}
    try:
        with open(acfg_path, encoding="utf-8") as f:
            acfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"status": "absent", "workdir": wd}
    station = acfg.get("station", "")
    figdir = os.path.join(wd, "figures", station)
    excels = (_glob.glob(os.path.join(wd, "*.xlsx"))
              + _glob.glob(os.path.join(figdir, "**", "*.xlsx"), recursive=True))
    analysis_mds = _glob.glob(os.path.join(figdir, "**", "ANALYSIS.md"), recursive=True)
    findings_path = os.path.join(wd, "FINDINGS.md")
    findings_txt = ""
    if os.path.exists(findings_path):
        try:
            with open(findings_path, encoding="utf-8") as f:
                findings_txt = f.read()
        except OSError:
            pass
    ev = {
        "status": "linked",
        "workdir": wd,
        "station": station,
        # 并行线保护：链接到另一条实验线的目录 → 拒绝消费
        # test_station 未设时以空串比较 → 任何已链接目录都会判 mismatch（fail-closed）；
        # 预期该字段由 Step 0.5/Step 1 写入
        "station_mismatch": station != cfg.get("test_station", ""),
        "metric_excels": len(excels),
        "suspect_days": os.path.exists(os.path.join(wd, "suspect_days.csv")),
        "weather_class": os.path.exists(os.path.join(wd, "weather_class.csv")),
        "analysis_mds": len(analysis_mds),
        "findings": os.path.exists(findings_path),
        "drift_dir": os.path.isdir(os.path.join(figdir, "drift")),
    }
    # 镜像主技能判定：Stage1=质检+指标；Stage3=现象提取（ANALYSIS.md 或 FINDINGS 有"现象"）
    ev["stage1_done"] = ev["suspect_days"] and ev["metric_excels"] > 0
    ev["stage3_done"] = ev["analysis_mds"] > 0 or ("现象" in findings_txt)
    return ev


# ---------------------------------------------------------------- adapter 加载（Mode B 用户代码接缝）
def load_adapter():
    """从工作目录导入用户填好的 adapter.py（对接其训练仓库）。

    adapter 需实现的函数见 scripts/adapter_template.py。Mode A（纯统计/回放）不需要它。
    """
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        import adapter  # type: ignore  用户在工作目录放的 adapter.py
    except ImportError as e:
        raise ImportError(
            "未找到工作目录下的 adapter.py。Mode B（checkpoint 评估/梯度）需要它——"
            "复制 scripts/adapter_template.py 到工作目录改名 adapter.py，填入你训练仓库的导入。"
        ) from e
    return adapter
