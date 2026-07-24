---
id: subset-influence
name: 训练条目/数据子集影响力归因
goal: 找出联合训练的 N 个训练条目（数据子集）里哪些拖累了留出单元的零样本预测（负迁移），并解释训练动力学（为什么不同 iteration/chunk 的 training loss 不同）
materials:
  required: [training_log, predict, truth]
  optional: [checkpoint, experiment_config, model_code]
variants:
  - id: mode-b
    when: "material:checkpoint"
    unlocks_stages: [3, 5]
stages:
  - id: 0
    name: 回放分组（种子/指纹 → assignments.csv）
    done_when:
      artifacts: ["assignments.csv"]
    prereqs:
      - desc: sampler.n_iters（实际迭代数）已填
        check: "config:sampler.n_iters"
      - desc: （可选）Mode B 才需 adapter.py（回放采样用 checkpoint 指纹抽查）
        check: "material:checkpoint"
  - id: 1
    name: 训练动力学（loss 水平/收敛 ~ 条目成员 → chunk_loss_dynamics.json）
    done_when:
      artifacts: ["chunk_loss_dynamics.json"]
    prereqs:
      - desc: 回放已完成（Stage 0）
        check: "stage:0"
      - desc: loss 记录源已定位（loss_records.csv / probe 报 loss_found / Mode B 可 --from-ckpt）
        check: "material:training_log"
  - id: 2
    name: 影响力回归（Mode A 主证据 → influence_coefs.json）
    done_when:
      artifacts: ["influence_coefs.json"]
    prereqs:
      - desc: 回放已完成（Stage 0）
        check: "stage:0"
      - desc: 留出单元逐 chunk RMSE 序列已就位（日志解析或 ckpt_eval 重算）
        check: "material:predict"
  - id: 3
    name: 梯度佐证 TracIn（Mode B → tracin_scores.json）
    done_when:
      artifacts: ["tracin_scores.json"]
    prereqs:
      - desc: 有可用 checkpoint（Mode B）
        check: "material:checkpoint"
  - id: 4
    name: 漂移解释（气候/分布距离 → 现象/假设）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: Stage 2/3 已给出嫌疑条目
        check: "stage:2"
  - id: 5
    name: 确认（Mode B：微调探针 + 剔除重训 → 已证实/CONCLUSION）
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 有可用 checkpoint（Mode B）
        check: "material:checkpoint"
      - desc: Stage 2/3 已给出 top 嫌疑（且最好两法一致）
        check: "stage:2"
    subagent_ok: false
contexts:
  - id: heldout-eval
    name: 留出单元的 result-eval 产物
    workdir_key: heldout_eval_dir
    status_key: heldout_eval_status
    marker_files: [CONCLUSION.md]
    on_absent: ask
    provider_playbook: result-eval
---

# subset-influence：训练条目/数据子集影响力归因（负迁移诊断 + 训练动力学）

对分块联合训练的 N 个训练条目（数据子集，原技能语境下多为电站，本 playbook 已泛化——任何
可枚举、可分块重排的训练数据单元都适用）做**训练集构成 → 目标单元性能**的归因：找出哪些
条目拖累了留出单元的零样本预测（负迁移），并解释训练 loss 为什么因 chunk 而异。本 playbook
由专用技能 pv-station-influence 的方法泛化而来——**续跑/直达能力已由引擎 orient 承接**
（不再需要专属的 run_orient.py：orient 每次进入自动核对产物、定位第一个未完成阶段、支持
`--goto`）。

## 1. 问题框定与首要陷阱

- **震荡本身不是罪证**：顺序分块训练下留出单元 RMSE 逐 chunk 震荡是**预期现象**，不是异常
  ——连训某一 chunk 的条目若干 epoch 会把模型拉向那批条目的分布（灾难性遗忘动力学），就算
  N 个条目全是"好"条目也会震。"有害"必须定义为：**训练到条目 X 会系统性地把留出单元 RMSE
  推高**，在大量随机 chunk 上估计其边际效应——利用每迭代重新随机分组这一天然随机化实验，
  不跟震荡本身较劲。别一看到某 chunk RMSE 跳升就归咎当时的条目，那可能只是遗忘。
- **loss 高 ≠ 有罪**：loss 是训练条目自己身上的量（"难学"），不是负迁移排名；loss 低但
  harm 高才是分布冲突的典型指纹（四象限见 `references/influence-methods.md`）。
- **两法一致才升级**：影响力回归（Stage 2）与梯度 TracIn（Stage 3，仅 Mode B）是两条独立
  证据线；只有排名一致（报 Spearman）才把嫌疑条目从"现象"升"假设"。单证据线不下"假设"
  级结论。
- **功效诚实**：迭代数 < 10 只报排名、不报显著性；分组样本不足只描述、不定论。
- **只有剔除重训改善才算"已证实"**：Stage 5（Mode B 专属）在多口径 + 配对显著性检验上
  改善留出单元表现，才可标"已证实"；其余一律停在"现象/假设"。

## 2. 两种证据模式（由材料自动识别，不用预选）

`checkpoint` 材料 present → Mode B（`variants: mode-b` 激活，解锁 Stage 3/5，且 Stage 1
可 `--from-ckpt`）；否则 Mode A（观测归因，零 GPU）。

| | **Mode A 观测归因（只有预测/日志）** | **Mode B 干预确认（有 checkpoint）** |
|---|---|---|
| 输入 | 逐 chunk 留出单元 RMSE 序列 + 种子回放代码（+ 日志里的 loss） | Mode A **加** checkpoint + 训练代码 |
| 阶段 | 0 回放 → 1 动力学（日志有 loss 才可）→ 2 影响力回归 → 4 漂移解释 | 上面全部 **加** 3 梯度 TracIn + 5 微调探针/剔除重训（且 1 可 --from-ckpt） |
| 证据 | 嫌疑条目**相关性排名** + loss 侧现象 | 独立方法佐证 + 因果确认 |
| 算力 | 几乎零 GPU，纯统计 | GPU 前/反向 + 少量重训 |

**关键前置**：Stage 2 的因变量是"逐 chunk 留出单元 RMSE"，Stage 1 的原料是"逐 epoch
training loss"。任何一次进入本 playbook，orient 之后第一件事是跑
`<本 playbook 目录>/scripts/probe_logs.py` 一次探两样——据 `probe_summary.json` 决定
路线：RMSE 入了日志则 Mode A 全程零权重，没入则靠 `ckpt_eval.py` 重算；loss 没记且拿不到
checkpoint 内 loss 则 Stage 1 跳过（不阻塞）。

## 3. 实验设定载入：project-context 实验线

原技能里"N 站分 K 个 chunk"一类实验参数（条目全集、留出单元、chunk 方案、每 chunk
epoch、模型数）不再由本 playbook 硬编码或临场向用户逐项收集，而是**经
`experiment_config` 材料 + project-context 实验线载入**：

1. `experiment_config` present → 从其指向的 project-context 实验线 json 取
   `held_out_station`/`held_out_station_slug`（留出单元 id）、`training_entries`
   （N 个训练条目，顺序即回归设计矩阵列序）、`chunking`（chunk 方案）、`models`；
   未覆盖的字段保留【待补】，需要时再问一次并回填实验线 json（不重复问已载入字段）。
2. `experiment_config` absent 或实验线里某字段确实没有 → 照 `_playbook-spec.md` 的入口闸
   纪律向用户问，不臆造默认值；下文各阶段提到"条目全集/留出单元/chunk 方案"均指此处载入
   （或补问）的值，不是写死在正文里的专名列表。
3. 工作目录配置文件（`influence_config.json`，字段见
   `<本 playbook 目录>/scripts/si_common.py` 头部）里的 `stations`/`test_station` 等键名
   是原技能遗留命名，语义已泛化为"训练条目列表"/"留出单元 id"，脚本层不改字段名（避免
   连锁改动），正文一律用"训练条目/留出单元"表述。

## 4. 留出单元预测侧上下文：与 result-eval 的接续

本 playbook 的归因要以留出单元的**预测侧分析**（指标基线、天气分型/分组条件、数据质量、
现象清单）为上下文——这正是 frontmatter `contexts[].heldout-eval` 声明的外部上下文，由
result-eval playbook 生产（`provider_playbook: result-eval`）。三分支：

- **linked**（`heldout_eval_status="linked"` 且目录含 `CONCLUSION.md`）→ 直接消费：指标
  表 = 留出单元基线；分组条件（如天气分型）= 归因分组变量；`suspect_days.csv`
  一类质检产物 = 反驳门"数据质量"证据；FINDINGS 现象 = 归因素材；`train-test-drift` 图/
  漂移产物可直接复用于本 playbook Stage 4。
- **absent（还没问过）→ 必须先问用户**：要不要先跑 result-eval 到 `CONCLUSION.md`？
  同意 → 按引擎 `references/engine-core.md`「嵌入执行 provider skill」纪律，在独立目录
  嵌入执行 result-eval，跑完写 `heldout_eval_dir`/`heldout_eval_status=linked` 回填本
  playbook 的 `diagnose_config.json`。拒绝 → `heldout_eval_status=declined`，继续
  influence-only 分析，FINDINGS/CONCLUSION 须注明"缺预测侧上下文"。
- **declined**：继续 influence-only 分析。

## 5. 逐阶段菜谱

复用脚本均在 `<本 playbook 目录>/scripts/`（原 pv-station-influence/scripts，路径随本次
迁移调整，逻辑不变；`si_common.py` 的 data_utils 复用路径已改指向兄弟 playbook
`result-eval/scripts/data_utils.py`）。

### Stage 0：回放分组

输入：`sampler.seeds` + `sampler.n_iters`（实际迭代数）、训练代码仓库根（Mode B 的
adapter 从这里导入采样器/模型类）。

菜谱：`replay_assignments.py` 用训练同款 RNG 复现每迭代把 N 个训练条目重排进 K 个 chunk 的
分组结果；Mode B 下额外做 checkpoint 指纹抽查——训完某 chunk，模型对该 chunk 成员条目的
RMSE 改善应最大，回放成员与"改善 Top-k"重叠 <60% 就判回放不可信（兜底方案见
`references/influence-methods.md`「Stage 0」节）。

done：`assignments.csv` 落盘。

### Stage 1：训练动力学

输入：Stage 0 的 `assignments.csv`；loss 记录源（`loss_records.csv` / probe 报
`loss_found` / Mode B 下 `--from-ckpt`）。

菜谱：`loss_dynamics.py` 逐 (model, iteration, chunk) 算 `final_loss`（尾 3 epoch 均值）/
`conv_slope`（log(loss)~epoch 斜率）/ `plateau_epoch`，再对训练条目做与 Stage 2 同款的
"中心化指示 + 岭回归 + 控制"设计（直接 import 复用 `influence_regression` 的实现），因变量
换成 loss 指标。**无 loss 记录源则本阶段跳过，不阻塞**（frontmatter 未声明该逃逸为
variant——由 `probe_logs.py` 的 `loss_found` 判定驱动，orient 据 Stage 1 的
`done_when.artifacts` 缺失且反复无产物时，主 agent 按本节文字放行，不算失败）。

解读：拿到 `highest_final_loss_entries`/`slowest_converging_entries` 后连接
project-context 的条目档案与 event-log——高 loss + 分布远（与多数训练条目差异大）=
预期内难拟合；高 loss + 分布平凡却难学 = 数据质量红旗，走 suspect_days/event-log 核查。
**逐模型独立，绝不跨模型 pool loss**（不同模型损失函数/量纲不同，只比 Spearman 排名）。

done：`chunk_loss_dynamics.json` 落盘。

### Stage 2：影响力回归

输入：Stage 0 的 `assignments.csv`；留出单元逐 chunk RMSE 序列（`rmse_series.csv`，日志
解析或 `ckpt_eval.py` 重算）。

菜谱：`influence_regression.py`。因变量按全局训练顺序 `(iteration, position)` 差分：
`ΔRMSE(i,c) = RMSE_留出单元(训完 chunk c) − RMSE_留出单元(训完上一个 chunk)`，消掉训练整体
慢趋势。设计矩阵用"中心化条目指示 + 岭回归"处理虚拟变量陷阱（每迭代每条目恰好进一个
chunk ⇒ 指示和与截距/size 共线），θ_entry 解释为**相对平均条目的相对有害度**（sum-to-zero
语义），排名与相对比较有效，绝对数值别过度解读。控制变量：`iteration`/`position`/`size`。
Bootstrap 给 95% CI，**CI 排除 0 才算方向可信**；迭代 < 10 只报排名不报显著性
（`power_note` 字段会提示）。方法细节见 `references/influence-methods.md`「Stage 2」节。

done：`influence_coefs.json` 落盘。

### Stage 3：梯度佐证 TracIn（`mode-b` variant，仅 checkpoint present 时解锁）

输入：checkpoint 序列 + `adapter.loss_gradient`（用户填的 adapter.py，模板见
`scripts/adapter_template.py`）。

菜谱：`tracin_influence.py` 累加多个 checkpoint 上 `⟨g_entry, g_heldout⟩` 的余弦式归一
内积，持续为负 = 训练条目把参数推离留出单元（有害）。输出 `harm_score = −Σ cos(...)`，取负
使"高=拖累"与 Stage 2 的 θ_entry 同向、便于直接比排名。降成本用 `--every N`/
`--n-windows`/`params_filter`；多卡分片各写各的 `--out`，主 agent 合并原始 CSV 后重跑一次
汇总。与 Stage 2 的关系：两条**独立**证据线，脚本报两两 Spearman，**排名一致的条目才从
"现象"升"假设"**。

done：`tracin_scores.json` 落盘。**Mode A 下本阶段不激活（variant 未命中），orient 标"跳过
不阻塞"，不是失败。**

### Stage 4：漂移解释

输入：Stage 2/3 给出的嫌疑条目列表；逐条目训练数据（供分布距离/天气型/kt 等计算）；
`heldout-eval` 上下文 linked 时的漂移产物可直接复用。

菜谱：复用 result-eval 的 `run_drift.py`（跨数据集 PSI/天气型/kt，逐条目对比），解释"为什么
远/为什么有害"：气候或分布距离。产出现象/假设条目（`findings_marker: "现象"`）——只写"看到
了什么"，不越过升级门槛写"已证实"。

done：`FINDINGS.md` 含"现象"标记。

### Stage 5：确认（`mode-b` variant，仅 checkpoint present 时解锁）

输入：Stage 2/3 给出的 top 2-3 嫌疑条目（最好两法排名一致）。

菜谱：两步协议（见 `references/attribution-discipline.md`「Stage 5 确认协议」）——
①**便宜探针**：从最终 checkpoint 出发，只在单个 top 嫌疑条目上短暂微调，测留出单元验证
ΔRMSE，方向对 = 一阶因果信号；②**决定性检验**：剔除 top 2-3 嫌疑**重训一次**，与原全量
训练同种子同协议，留出单元多口径对比 + 配对显著性检验（复用 result-eval 指标流水线里
按天配对做显著性判定的稳健性门槛工具）。过了才升"已证实"；若剔除反而变差 → 推翻假设，
回头查前面阶段是否遗忘伪装或回放错位误报。

`CONCLUSION.md`（面向管理层）：把"已证实"结论翻译成管理层语言——"哪些条目（与留出单元
分布差异最大）系统性拉低留出单元预测，剔除后留出单元指标改善多少"，方法论机器（回归/
TracIn/显著性检验）不进正文，末尾一句话说可信度，附**给未来训练的建议**（逐 chunk 组成与
逐 epoch loss 落结构化日志、混条目 batch/回放缓冲抑制遗忘、相似度加权采样偏向部署目标
分布）。

done：`CONCLUSION.md` 落盘。**Mode A 下本阶段不激活，orient 标"跳过不阻塞"。**
`subagent_ok: false`——因果确认涉及重训授权与结论升级判断，需主 agent 亲自做。

## 6. 证据升级规则

两证据线（`evidence_lines`：Stage 2 影响力回归、Stage 3 TracIn 梯度，仅 Mode B 下 Stage 3
可用）：

- **现象**：Stage 2 回归给出 θ_entry 排名（迭代 ≥10 时 CI 排除 0）。Stage 1 的 loss 效应
  排名同样只到"现象"（且是 loss 侧现象，须注明，不可当负迁移排名）。
- **假设**：Stage 2 与 Stage 3 排名一致（Spearman 显著为正，且该条目两法都靠前）+ Stage 4
  给出可解释机制（分布距离/映射差异），并登记一条假设。Mode A 下无 Stage 3，两证据线机制
  不适用——单证据线（仅 Stage 2）不得升"假设"，只能停在"现象"，除非用户明确接受降级
  举证标准（记入 open-questions）。
- **已证实**：Stage 5 剔除该条目重训，留出单元在多口径 + 配对显著性检验上确实改善，且过
  反驳门。
- **被推翻**：剔除重训无改善，或反驳门发现是数据质量/训练顺序等替代解释。

跨阶段单调：没到条件不许跳级，只有回归排名就写"已证实"是头号错误。

## 7. 停顿点与汇报

Stage 4（漂移解释产出现象清单）完成后向用户汇报嫌疑条目清单（按证据线分组、标注两法是否
一致），请用户点名要不要进 Stage 5 做因果确认（Mode B 时）；Stage 5（若激活）收尾把
`CONCLUSION.md` 内容（含关键数字）直接展示给用户。

## 8. subagent 拆分建议

重活（逐 checkpoint 评估、TracIn、动力学提取、嵌入跑 result-eval、逐条目漂移）外包
subagent，固化 brief 见 `references/subagent-briefs.md`：Stage 2 补料（ckpt_eval 按模型
分片）、Stage 3 TracIn（单卡单跑全量，多卡才分片）、Stage 1 probe→解析 loss→
loss_dynamics（只回数字排名）、Stage 4 run_drift 逐条目漂移（回现象清单）均可并发外包；
Stage 5 因果确认与最终结论/反驳门综合，主 agent 亲自做。

**单写者纪律**：`diagnose_state.json`/`PROGRESS.md`/`FINDINGS.md`/`influence_config.json`
只由主 agent 写；subagent 只读 JSON/CSV（checkpoint/原始日志/PNG 永不进上下文）、只写脚本
产物与自己的分片文件。

## 9. 结论模板与本 playbook 特有反驳门条目

结论模板见引擎 `references/conclusion-reporting.md`。特有反驳门条目（细则见
`references/attribution-discipline.md`）：

- **遗忘伪装**：ΔRMSE 冲击是否只是训练顺序/新近效应？看第二因变量（新近 vs 任意位置有害），
  控制 `position` 后 θ_entry 还在吗。
- **样本量**：该条目出现次数够吗（≈迭代数）？迭代 <10 一律降级。
- **数据质量红旗**：该条目分布与留出单元**相似却有害** = 强烈提示数据质量问题（原始记录
  异常/预报偏差/传感器故障），不是"分布冲突"——走 `heldout-eval` 上下文的质检产物
  （linked 时 `suspect_days.csv` 现成）+ project-context event-log 查该条目原始数据，是
  数据问题就修数据，别删条目。
- **回放错位**：assignments 过了指纹校验吗？没过 → θ_entry 归错条目，先修 Stage 0。
- **单证据线**：只有回归、没有 TracIn 佐证（或 Mode A 结构性无 Stage 3）？→ 只能停在
  "现象"。
- **口径/评估错**：留出单元指标是不是用了错的 label 列/取点口径？
- **共享上游**：若"有害"只在共享同一上游组件（如同一预训练基座）的模型子集同现、其余模型
  无感，可能是上游组件相关而非条目本身——跨模型 Spearman 帮判。

## 10. 材料降级说明

- `training_log`/`predict`/`truth` 缺：不可做——三者是本 playbook 归因的最小闭环（留出单元
  RMSE 序列 + loss 记录源），没有降级路径，须先补齐或明确降级范围（如只做 Stage 2、放弃
  Stage 1 动力学）。
- `checkpoint` 缺：Mode A——Stage 3/5 结构性不适用（`mode-b` variant 不激活），归因停在
  "现象/假设"，不可升"已证实"；`CONCLUSION.md` 若仍需产出，须显式标注"未做因果确认，
  仅观测归因"。
- `experiment_config` 缺：无法从 project-context 实验线自动载入条目全集/留出单元/chunk
  方案，须逐项向用户问齐并写入工作目录配置（不阻塞主线，但每次进入都要重新确认，无法复用
  实验线记忆）。
- `model_code` 缺：不影响主线归因，仅在核验模型架构相关假设（如"某条目只对特定架构有害"）
  时少一路交叉验证来源，缺席记 `open-questions.md`。

## 11. chartbook 覆盖声明

本 playbook 不产出 chartbook 图（无阶段声明 `charts:`）：主线产物是 JSON/CSV 统计量
（回归系数、TracIn 分数、动力学指标），不是标准可视化图集。留出单元的预测侧可视化（误差
结构、时间稳定性等）由 `heldout-eval` 上下文（result-eval playbook）负责，Stage 4 的漂移
可视化复用 result-eval 的 `train-test-drift` 一类图产物，不在本 playbook 内重复声明。

## 12. 运行后回顾

本 playbook 靠"用得越多越准"——每次实跑暴露的问题写回：脚本 bug/字段名 → 改
`<本 playbook 目录>/scripts/`；指令歧义/缺步骤 → 改本文件；确认的新项目事实（条目档案/
event-log）→ 补 project-context；方法类知识 → 补 `<本 playbook 目录>/references/`。给未来
训练的建议固定写进结论：逐 chunk 组成与逐 epoch loss 直接落结构化日志（Stage 0/1 的存在
只因当初没记），并考虑混条目 batch / 小回放缓冲抑制遗忘震荡。
