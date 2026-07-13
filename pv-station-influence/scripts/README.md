# pv-station-influence/scripts —— 用法速查

站点影响力归因脚本。每脚本独立可跑、产物落盘自足、脚本只 print ≤30 行摘要（256k 上下文纪律）。`<SKILL>` = 本技能目录。

## 典型流程

```bash
# 每次进入先 orient（识别 Mode A/B + 定位阶段）
python3 <SKILL>/scripts/run_orient.py

# Step 1 后：探日志判断白马湖 RMSE 是否已记录（决定 Mode A 是否零权重）
python3 <SKILL>/scripts/probe_logs.py

# Stage 0 回放分组（Mode B 可 --validate 做 checkpoint 指纹校验）
python3 <SKILL>/scripts/replay_assignments.py [--validate]

# 若日志没记 RMSE 且有 checkpoint（Mode B）：逐 checkpoint 重算白马湖 RMSE
python3 <SKILL>/scripts/ckpt_eval.py

# Stage 1 影响力回归（Mode A 主证据）
python3 <SKILL>/scripts/influence_regression.py [--lam 1.0 --boot 1000]

# Stage 2 梯度 TracIn（Mode B）
python3 <SKILL>/scripts/tracin_influence.py [--every 1 --n-windows 200]

# Stage 3 漂移解释：复用兄弟技能，不重写
python3 ../pv-result-analysis/scripts/run_drift.py --cols GHI-solargis,observe_power_future
```

## 文件

| 文件 | 阶段/模式 | 作用 |
|------|-----------|------|
| `si_common.py` | 共享 | config 读取、模式判定、RMSE、复用 pv-result-analysis/data_utils、adapter 加载 |
| `run_orient.py` | Step 0 | 识别模式 + 定位阶段 + 前置检查，写 `influence_state.json`/`PROGRESS.md` |
| `probe_logs.py` | Step 1 | 扫训练日志找白马湖逐 chunk RMSE，报格式让主 agent 写解析器 |
| `replay_assignments.py` | Stage 0 | 种子回放还原分组 → `assignments.csv`；`--validate` 指纹校验 |
| `ckpt_eval.py` | Stage 1/B | 日志没 RMSE 时逐 checkpoint 重算 → `rmse_series.csv`（续跑） |
| `influence_regression.py` | Stage 1/A | ΔRMSE ~ 站成员回归 → `influence_coefs.json` |
| `tracin_influence.py` | Stage 2/B | TracIn 梯度对齐 → `tracin_scores.json` |
| `adapter_template.py` | Mode B 接缝 | 复制到工作目录改名 `adapter.py`，填入你训练仓库的采样/模型/数据导入 |

## adapter（Mode B 必需）

回放采样、载 checkpoint、算梯度都要调用**你训练仓库的代码**，本技能不假设其结构。把 `adapter_template.py` 复制到工作目录改名 `adapter.py`，实现 4 个函数（`sample_assignments`/`load_model`/`predict_station`/`loss_gradient`）。Mode A（纯统计）不需要它。

## 产物（工作目录）

`influence_config.json`(输入) · `assignments.csv` + `assignments_summary.json` · `rmse_series.csv` · `influence_coefs.json` · `tracin_scores.json` · `influence_state.json` + `PROGRESS.md`(orient 写) · `FINDINGS.md`/`ANALYSIS.md`/`CONCLUSION.md`(主 agent 写)。
