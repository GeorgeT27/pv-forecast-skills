# 子 agent 派发（卡片制）

主 agent 只做编排：提问、派发、收契约 JSON、升级判定、反驳门、FINDINGS/CONCLUSION、
state/config 更新。重活按名字派 `agents/` 卡片；本文件是索引 + 回环规则。

## 卡片索引（playbook → 卡片 · mode · 覆盖）

| playbook | 卡片 | mode | 覆盖 |
|---|---|---|---|
| data-setup | `data-setup-compute` | producer | 全程到 setup 产物落盘 |
| metric-eval | `metric-eval-compute` | producer | 全程到 metric_table 落盘 |
| model-audit | `model-audit-compute` | producer | 全程到 model_profile 落盘 |
| training-sufficiency | `training-sufficiency-compute` | compute | Stage 0 到第一个 pause |
| robustness | `robustness-compute` | compute | 同上 |
| feature-importance | `feature-importance-compute` | compute | 同上；`on_demand_stages` 用户点名后再派 |
| model-comparison | `model-comparison-compute` | compute | 同上 |
| deployment-drift | `deployment-drift-compute` | compute | 同上 |
| fact-scan | `fact-scan-compute` | compute | 同上 |
| result-eval | `result-eval-compute` | compute | Stage 0–3；Stage 4 结论归主 agent，eval_report 产物在主 agent 收尾后才算 built |
| subset-influence | `subset-influence-compute` | compute-fine | 每次一个具名脚本 |
| architecture-attribution | `architecture-attribution-compute` | compute | Stage 0 |
| architecture-attribution | `architecture-attribution-worker` | worker | Stage 0 噪声底重训 / Stage 3 单条干预 |

每张卡的 frontmatter 是契约（name/mode/playbook/compute_stages/tools/model），正文六节：
你是谁 / 输入 / 步骤 / 红线 / 输出契约 / 停顿；规格见 `agents/_agent-spec.md`。

## 派发六步（单 playbook）

1. 读该 playbook frontmatter `questions:`，取 `stage ≤` 卡片区间终点的题，同阶段合并一次
   AskUserQuestion，答案落 `diagnose_config.json`。只取 `questions:`，不取 `evidence_lines`。
2. 按 `upstream[]` 保证 required 产物 built/linked：缺 → 先派对应 producer 卡（先问齐它自己的题）；
   optional 缺 → 三分支必须问用户，卡片不替用户拍板。
3. 把答案、上游目录、`<ENGINE>`、`<workdir>` 填进卡片「输入」节，按名字派发（`subagent_type` = 卡片名）。
   卡片区间含声明 `charts:` 的阶段 → 主 agent 先在工作目录跑 orient 过图表选择门（四步清单），
   把选定图集写进「输入」节再派卡。
   名字不可用 → 回退：卡片全文作 prompt 派 `general-purpose`，PROGRESS.md 记「卡片未注册，走回退」。
4. 收 final message（契约 JSON）：`NEED_INFO` → 问用户、写 config、重派同一张卡；`BLOCKED` →
   修材料/脚本后重派同一张卡。
5. `COMPUTE_DONE` → 只读 `phenomena_file`/`artifacts` 摘要，向用户停顿汇报现象清单，请用户点名深挖。
6. 主 agent 亲跑：变体解锁判定、结论三道门、`conclusion_gate.py`、CONCLUSION.md 直接呈现。

producer 目标：②③坍缩，问齐 → 整体派发 → 产物落盘即 `COMPUTE_DONE, produces_dir`，主 agent 写
`config.products.<id>` 回填与 PROGRESS 验证记录（这两样卡片无权写）。

## 派发纪律（全部卡片共用）

- 并行：互不共享输出文件的卡片可一条消息多派；GPU 任务单卡不分片。
- 单写者：`diagnose_config.json` 只由主 agent 写；`diagnose_state.json / PROGRESS.md` 由主 agent 写，
  卡片在自己的工作目录跑 orient 领阶段是唯一例外（并行派发的卡片必须各有工作目录；分片派发只跑脚本
  不跑 orient，阶段由主 agent 收齐后推进）；`FINDINGS.md` 卡片只许追加自己阶段的「现象」行，
  「假设 / 已证实 / 被推翻」与结论行只由主 agent 写。
- 验证回传：卡片必须在 `verification` 回验证步/闸的名字与数字；主 agent 逐条记入 PROGRESS.md，
  缺记录的产物不可引用。
- 分片防竞态：并发各写各的 `--out <name>.<shard>`，主 agent 收齐后合并。
- 上下文纪律：卡片只读结构化产物，不读 PNG / 逐行原始日志 / 大二进制。
- 无提问权：卡片没有 AskUserQuestion；缺信息走 `NEED_INFO`；报错原样回传，不自行假设、不带病继续、不重试破坏性操作。
- 禁嵌套：卡片不得再派 subagent；要拆分由主 agent 派平级卡片。
- 回传要瘦：只回契约 JSON。

## Brief-EMBED 提示（嵌入运行其他技能）

playbook 需要先跑另一个技能建立上下文时，**由主 agent 亲自编排**：建独立子目录 → 照被嵌入技能的
SKILL.md 走到需要的阶段 → 回填本工作目录 config 的 `<workdir_key>` + `<status_key>="linked"` →
重跑 orient 确认。
