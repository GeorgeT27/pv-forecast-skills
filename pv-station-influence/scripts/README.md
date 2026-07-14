# pv-station-influence/scripts —— 用法速查

站点影响力归因脚本。每脚本独立可跑、产物落盘自足、脚本只 print ≤30 行摘要（256k 上下文纪律）。`<SKILL>` = 本技能目录。

## 典型流程

```bash
# 每次进入先 orient（识别 Mode A/B + 预测侧上下文 + 定位阶段）
python3 <SKILL>/scripts/run_orient.py

# Step 1 后：探日志——一次探两样（留出站 RMSE + training loss）→ probe_summary.json
python3 <SKILL>/scripts/probe_logs.py

# Stage 0 回放分组（Mode B 可 --validate 做 checkpoint 指纹校验）
python3 <SKILL>/scripts/replay_assignments.py [--validate]

# Stage 1 训练动力学（日志解析出 loss_records.csv 后；Mode B 无日志可 --from-ckpt）
python3 <SKILL>/scripts/loss_dynamics.py [--from-ckpt] [--lam 1.0 --tail-k 3]

# 若日志没记 RMSE 且有 checkpoint（Mode B）：逐 checkpoint 重算留出站 RMSE
python3 <SKILL>/scripts/ckpt_eval.py [--models M1 --out rmse_series.M1.csv]  # --out 供分片

# Stage 2 影响力回归（Mode A 主证据）
python3 <SKILL>/scripts/influence_regression.py [--lam 1.0 --boot 1000]

# Stage 3 梯度 TracIn（Mode B）
python3 <SKILL>/scripts/tracin_influence.py [--every 1 --n-windows 200]

# Stage 4 漂移解释：复用兄弟技能，不重写（预测侧 linked 时优先消费其已有 drift 产物）
python3 ../pv-result-analysis/scripts/run_drift.py --cols GHI-solargis,observe_power_future
```

## 文件

| 文件 | 阶段/模式 | 作用 |
|------|-----------|------|
| `si_common.py` | 共享 | config 读取、模式判定、RMSE、预测侧上下文探测(detect_result_analysis)、复用 pv-result-analysis/data_utils、adapter 加载 |
| `run_orient.py` | Step 0 | 识别模式 + 预测侧上下文三分支 + 定位阶段 + 前置检查，写 `influence_state.json`/`PROGRESS.md` |
| `probe_logs.py` | Step 1 | 一次扫描同时探留出站逐 chunk RMSE 与 training loss → `probe_summary.json`，报样例行让主 agent 写解析器 |
| `replay_assignments.py` | Stage 0 | 种子回放还原分组 → `assignments.csv`；`--validate` 指纹校验 |
| `loss_dynamics.py` | Stage 1 | 逐 chunk loss 指标 ~ 站成员回归 + RMSE 关联 → `chunk_loss_dynamics.json`；`--from-ckpt` 从 checkpoint 抽 loss（Mode B） |
| `ckpt_eval.py` | Stage 2 补料/B | 日志没 RMSE 时逐 checkpoint 重算 → `rmse_series.csv`（续跑；`--out` 分片） |
| `influence_regression.py` | Stage 2/A | ΔRMSE ~ 站成员回归 → `influence_coefs.json` |
| `tracin_influence.py` | Stage 3/B | TracIn 梯度对齐 → `tracin_scores.json`（`--raw`/`--out` 分片） |
| `adapter_template.py` | Mode B 接缝 | 复制到工作目录改名 `adapter.py`，填 5 个函数（第 5 个 `load_loss_history` 可选，只服务 Stage 1 的 checkpoint 路径） |

## adapter（Mode B 必需）

回放采样、载 checkpoint、算梯度都要调用**你训练仓库的代码**，本技能不假设其结构。把 `adapter_template.py` 复制到工作目录改名 `adapter.py`，实现 `sample_assignments`/`load_model`/`predict_station`/`loss_gradient`（+可选 `load_loss_history`）。Mode A（纯统计）不需要它。

## subagent 分片（防并发写竞态）

多 subagent 并行时各写各的输出：`ckpt_eval.py --models M1 --out rmse_series.M1.csv`、`tracin_influence.py --models M1 --raw tracin_dots.M1.csv --out tracin_scores.M1.json`。主 agent 收齐后 concat 合并（rmse 分片 → `rmse_series.csv`；tracin 分片 concat 原始 CSV 后重跑一次汇总）。派发 brief 见 `../references/subagent-briefs.md`。

## 产物（工作目录）

`influence_config.json`(输入) · `probe_summary.json`(probe_logs 写) · `assignments.csv` + `assignments_summary.json` · `rmse_series.csv` · `loss_records.csv` + `chunk_loss_curves.csv` + `chunk_loss_dynamics.json` · `influence_coefs.json` · `tracin_scores.json` · `influence_state.json` + `PROGRESS.md`(orient 写) · `FINDINGS.md`/`ANALYSIS.md`/`CONCLUSION.md`(主 agent 写) · `result_analysis_<留出站拼音>/`(嵌入式主技能运行目录，可选；其中的最小 `analysis_config.json` 若只为 run_drift 而写，不代表跑过主技能)。
