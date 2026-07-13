"""pv-station-influence —— 共享工具（配置 / 路径 / RMSE / 复用主技能 data_utils）。

设计纪律（见 SKILL.md 上下文预算节）：
- 所有重活在脚本内完成，脚本只 print ≤30 行摘要；产物落盘 CSV/JSON，各带自足 summary。
- 复用兄弟技能 pv-result-analysis/scripts/data_utils.py 读 parquet、算 PSI，不另写一套。

配置文件 influence_config.json（工作目录，字段全部可选、按模式渐进填）：
{
  "test_station": "baimahu",                 # 留出测试站（白马湖）
  "stations": ["s01", ...],                  # 17 个训练站的 id/名（顺序即回归设计矩阵列序）
  "test_label": "<白马湖 true_label parquet>",# 算白马湖 RMSE 的真值
  "train_repo": "<训练代码仓库根>",           # 供 adapter 导入 sampler / 模型类
  "sampler": {"seeds": [...], "n_iters": N}, # 种子与实际迭代数（Stage 0 回放用）
  "log_dir": "<训练日志目录>",                # Stage 0 前的 probe_logs 扫这里
  "checkpoint_dir": "<checkpoint 根>",        # 有此字段 => 解锁 Mode B（有 optimizer state 更好）
  "models": ["M1", "M2", "M3", "M4"],         # 要分析的模型（缺省四个都做）
  "chunk_layout": {"n_chunks": 4, "sizes": [5, 5, 5, 2]}  # 每迭代的 chunk 结构
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
    """有可用 checkpoint_dir => Mode B（解锁 Stage 2/4），否则 Mode A。"""
    ck = cfg.get("checkpoint_dir")
    return "B" if ck and os.path.isdir(ck) else "A"


def stations(cfg: dict) -> list[str]:
    st = cfg.get("stations") or []
    if not st:
        raise ValueError("config.stations 为空：需要 17 个训练站的稳定 id/名（顺序=设计矩阵列序）。")
    return list(st)


# ---------------------------------------------------------------- 指标
def rmse(pred: np.ndarray, true: np.ndarray) -> float:
    """整体 48h RMSE（不取点、不拆天）——Stage 1 因变量默认口径，简单稳定。

    白马湖零样本评估用最朴素的 192 点整体 RMSE 即可；细分口径留给确认阶段。
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
    """载入白马湖真值并转 (n,192) 矩阵 + timestamps。复用 data_utils。"""
    if du is None:
        raise RuntimeError("找不到 pv-result-analysis/scripts/data_utils.py，无法读 parquet。")
    df = du.load_table(cfg["test_label"])
    Y = du.to_matrix(df, du.LABEL_COL)
    return df[du.TIMESTAMP_COL].to_numpy(), Y


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
