---
id: architecture-attribution
name: 架构归因验证脊（消融验证）
goal: 把切片级误差差异用单变量消融干预因果归因到模型具体组件，产出确认/否证/未决三态判定
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: true
stages:
  - id: 0
    name: 现象定位（噪声底核验 + 切片测量）
    done_when:
      artifacts: ["noise_floor.json", "slice_zcheck.json"]
      findings_marker: "现象"
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 噪声底已定
        check: "question:noise-floor"
    pause_after: true
    subagent_ok: true
  - id: 1
    name: 假设账本校验与选择
    done_when:
      artifacts: ["hypothesis_ledger.json"]
      findings_marker: "假设"
    prereqs:
      - desc: 现象清单已停顿汇报
        check: "stage:0"
      - desc: 账本来源已定
        check: "question:ledger-path"
    subagent_ok: true
  - id: 2
    name: 判别性干预设计
    done_when:
      artifacts: ["intervention_plan.json"]
    prereqs:
      - desc: 假设已选定
        check: "stage:1"
      - desc: 模型档案（含 ablation_switches）就绪
        check: "product:model_profile"
    pause_after: true
    subagent_ok: true
  - id: 3
    name: 执行与判定（强制 subagent 外包）
    done_when:
      artifacts: ["verdict_summary.json"]
    prereqs:
      - desc: 干预计划已设计并停顿汇报
        check: "stage:2"
      - desc: 用户已确认花费本轮训练预算
        check: "question:intervention-budget-confirmed"
    subagent_ok: true
  - id: 4
    name: 结论落笔
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 执行与判定已完成（含降级路径：无可训练框架时的「未验证假设」产出）
        check: "stage:3"
    subagent_ok: false
materials:
  required: [predict, truth, checkpoint, experiment_config]
  optional: [training_log, model_code]
questions:
  - id: noise-floor
    stage: 0
    ask: "噪声底数值是多少（同配置基线模型 ≥3 种子指标标准差 × 3σ）？已算过就直接给数值；没算过，答『需现算』——本阶段用 checkpoint + experiment_config 起 ≥3 个基线种子重训（走 subagent 外包），标准差乘 3 得数"
    why: "无噪声底，池化/切片差异无法判断是不是真实效应——本 playbook 硬性拒绝无噪声底启动"
    options: ["已有数值（直接给）", "需现算（本阶段用基线重训补）"]
    default: null
    skip_if: "artifact:noise_floor.json"
  - id: ledger-path
    stage: 1
    ask: "假设账本 JSON 文件在哪（通常是上一轮生成器阶段产出的 hypotheses[] 文件）？没有就在切片版图基础上现场起草一份最小账本（标注 pre-registered）"
    why: "本 playbook 只验证假设、不重复生成——没有账本要么用户指路，要么现场起草并按 hypothesis_ledger.py 的字段纪律登记"
    options: ["给出文件路径", "现场起草（无既有账本）"]
    default: null
    skip_if: "artifact:hypothesis_ledger.json"
  - id: intervention-budget-confirmed
    stage: 3
    ask: "已核对 intervention_plan.json 里的干预计划（单变量、≥3 种子、双向可判、预算阶梯），同意花费其中的训练预算了吗？"
    why: "干预＝真实重训，烧钱烧时间；花费前必须显式确认，不许 subagent 自行开跑"
    options: ["确认，开始执行", "暂缓，先改计划"]
    default: null
---

# architecture-attribution：架构归因验证脊（消融验证）

## 1. 问题框定与首要陷阱

「模型 A 比 B 好是因为组件 X」不是一句能直接下的结论。没有干预手段的机制叙事，无论多流利，都停留在「猜测」——本 playbook 存在的唯一理由，是把猜测升级成因果结论所必需的第三条腿：**单变量消融干预的实测结果**。

**三条腿纪律（硬规则）**：切片测量（差异在哪、是否超噪声底）+ 机理假设（指向具体组件、可否证、干预前登记）+ 干预验证（实测 delta，判定确认/否证/未决）。三条腿不齐——尤其是没有干预验证——不得出现任何架构/组件因果表述。conclusion_gate 在结论闸层面机械拦截这条（`CAUSAL_RE` 命中但无 `## 消融证据` receipt → 直接 exit 1），但机械拦截是最后一道防线，不是免检牌：写 CONCLUSION.md 之前，主 agent 自己先按本节纪律逐条自查。

首要陷阱——**池化平局 ≠ 无差异**。池化指标差距小于噪声底，不代表两个模型没有真实差异，只代表还没有切到能看见差异的维度。已有实证：池化差距 0.0073 < 噪声底 0.0102，但切到 lead time 维度后 z 高达 10——如果在 Stage 0 看到"池化差距不显著"就停手写"无差异"结论，就是本 playbook 最容易犯、也是危害最大的错误。**Stage 0 永远不许因池化平局而终止**，必须转入切片。

第二陷阱——**机理叙事无干预支撑就是猜测，且往往猜得很像真的**。"patch 保留时间局部性"这类假设读起来专业、流利、符合直觉，但在实证案例里 30 分钟内就被干预直接否证。叙事的说服力和它的真实性没有关系；只有 delta 数字有关系。

第三陷阱——**单一反例不足以支撑家族级解释**。"通道独立模型都更好"这类跨模型家族的断言，需要家族内 ≥2 个成员的独立干预证据；免费判别（如顺手核对同族的 DLinear/NLinear 产物）是加分项，不是必答题，但少于 2 个成员的证据不许写成家族结论。

第四陷阱——**否证之后现编替代故事**。否证一个假设之后，当轮立刻补一个没有新干预支撑的"其实是因为……"是本 playbook 明确禁止的动作：新假设必须标 `provenance: post-hoc`，且必须经**新的**干预才能升级为 confirmed——不许拿同一批数据既生成又确认。

## 2. 逐阶段菜谱

### Stage 0 现象定位（噪声底核验 + 切片测量）

输入：`<setup>` = config.products.setup.workdir 下的规范长表（predict/truth 对齐、时间索引）；同配置 ≥3 种子的基线指标（噪声底来源）。

**第一步，噪声底**。`noise-floor` 问题答"已有数值"→ 直接落 `noise_floor.json`（自足：`{"metric":str,"config":str,"seeds":[...],"per_seed":[float,...],"mean":float,"std":float,"noise_floor_3sigma":float}`）。答"需现算"→ 用 checkpoint + experiment_config 起 ≥3 个基线种子重训（同配置、其余超参不变），走 subagent 外包（见 §5 Brief A），汇总每种子的口径指标，`noise_floor_3sigma = std(per_seed, ddof=1) * 3`。

**第二步，池化对照，不许因平局停手**。若已有其他分析产出的池化差距数值，与噪声底对照：差距 < 噪声底**不是**"无差异"的证据，只说明要往下切片才能看见真实版图（§1 首要陷阱）。

**第三步，切片测量**。写 `analysis_scripts/build_slice_metrics.py`：从各种子的预测/真值长表按标准维度分桶算口径指标，产出 slice_zcheck.py 的输入长表（列：`slice,seed,model_a,model_b`）。标准维度——lead time 分桶、预测时刻（hour-of-day）、变量/通道、目标窗口波动性分位；领域可扩展（光伏：辐照度分档、晴雨天）。**脚本验证步**（本脚本是运行时现场生成的数据整形脚本，不是共享引擎脚本，不接入 gen_gate——按 spec §4.2 用对账代替）：核对产出行数 = 切片数 × 种子数，每个 (slice, seed) 恰出现一次；抽 2 行手算核对与源文件一致，记 PROGRESS.md。

跑：
```bash
python3 <ENGINE>/scripts/slice_zcheck.py --metrics slice_metrics.csv --out slice_zcheck.json [--z-threshold 3.0]
```
`slice_zcheck.py` 是共享引擎脚本（不是运行时现场生成物），已由 CI 的 `playbooks/architecture-attribution/golden/` 金标准 + `scripts/tests/test_slice_zcheck.py` 覆盖，正文直接调用，不必再过 `gen_gate.py`——`gen_gate` 只闸运行时现场生成的分析脚本，引擎共享脚本（`scripts/` 下带 CLI 的机制脚本）一律直接调用。

判读：`slice_zcheck.json` 里 `verdict=="real"` 的切片才算真实差异；`~noise` 的切片如实写"无显著差异"，不得因为数值好看就硬解释。

产出 FINDINGS.md 现象清单——只写现象：哪些切片真实分离（z 值、mean_diff、赢家）、哪些是噪声、池化 vs 噪声底的关系。禁机制语言。

done：`noise_floor.json` + `slice_zcheck.json` 落盘，FINDINGS.md 出现「现象」→ **pause_after 停顿**（§4）。

### Stage 1 假设账本校验与选择

输入：Stage 0 的切片版图；`model_profile` 产物（model-audit 产出的组件清单，供假设指向具体代码位置）。

`ledger-path` 问题答"给出文件路径"→ 读入该 JSON。**先跑校验，再检查非空——两步缺一不可**：
```bash
python3 <ENGINE>/scripts/hypothesis_ledger.py <ledger-path>
```
`validate_ledger` 对"顶层对象没有 `hypotheses` 键"这种畸形账本返回空错误列表（视为合法）——**这是已知的校验盲区，不是"账本没问题"的证明**。校验通过之后必须另外显式核对 `len(ledger.get("hypotheses", [])) > 0`；账本里一条假设都没有，视同没有账本，走"现场起草"分支。

`ledger-path` 问题答"现场起草"（或账本为空）→ 在切片版图基础上生成 2–3 条候选假设，每条必须：①指向 `model_profile` 里的具体组件；②给出可否证预测（"若干预组件 X，某切片的优势方向应当怎样变化"）；③标 `provenance: "pre-registered"`（本步骤发生在任何干预执行之前）。指纹库只是生成器、不是结论器——下表是常见误差签名到候选组件的启发式映射，用来提速生成，不能替代干预验证：

| 误差签名 | 候选组件方向 |
|---|---|
| 近端 lead 分离、远端一致 | 局部性/patch 粒度、位置编码 |
| 跨变量场景下有分离、单变量场景下消失 | 跨变量注意力/通道混合 |
| 特定时段（如爬坡段）分离 | 归一化/去趋势方式、激活饱和 |
| 高波动分位分离、低波动分位一致 | 损失函数形状、抗噪结构（如趋势-季节分解） |

按 `discriminating_power`（一次干预能区分几个候选假设）降序排列，写回 `hypothesis_ledger.json`（schema 见 `scripts/hypothesis_ledger.py` 顶部 `REQUIRED` 字段与 `scripts/tests/test_hypothesis_ledger.py::VALID`）。

产出 FINDINGS.md：登记选中的假设 ID、claim、component、falsifiable_pred、discriminating_power——状态标「假设」。

done：`hypothesis_ledger.json` 落盘且非空、过 `validate_ledger`，FINDINGS.md 出现「假设」。

### Stage 2 判别性干预设计

输入：Stage 1 选中的最高判别力假设；`model_profile` 的 `ablation_switches`（component→switch→kind 三元组）。

菜谱：
1. 在 `ablation_switches` 里查该假设 `component` 对应的条目。`kind=config-flag` → 直接可用现成参数；`kind=code-stub` → 需要新写干预代码（如置零/替换 stub），写清改动范围；`kind=not-intervenable` → 该假设**在当前代码库不可干预**，如实标注，不得强行绕过设计一个不对等的替代干预。
2. **单变量纪律**：一次只动被选中的这一个开关，种子集固定为噪声底同一批种子（或另起但同样 ≥3 个）、数据/训练步数/其余超参全部与基线一致。
3. **双向可判**：写清"什么结果算确认、什么结果算否证"——即预登记 `pred_direction`（`increase`/`decrease`，对应 `ablation_verdict.verdict()` 的方向参数）。设计阶段写不出否证判据的干预不合格，退回重设计。
4. **预算阶梯**：先设计判别力最高的一个干预；单轮训练上限 ~10 次（如 4 个 switch × 3 种子内的裁剪组合）。是否追加取决于 Stage 3 的结果，不在本阶段一次性铺开。

落 `intervention_plan.json`（自足：`[{"hypothesis_id":str,"component":str,"switch":str,"kind":str,"seeds":[...],"pred_direction":"increase"|"decrease","kill_criterion":str,"confirm_criterion":str}]`）。

产出：向用户展示计划（含预计训练次数），**不写 FINDINGS 状态**（这是设计产物，不是现象/假设判定）。

done：`intervention_plan.json` 落盘 → **pause_after 停顿**（§4，等 `intervention-budget-confirmed` 确认再进 Stage 3）。

### Stage 3 执行与判定（强制 subagent 外包）

输入：`intervention_plan.json`；`intervention-budget-confirmed` 已确认。

**强制外包契约（硬规则，见 references/subagent-brief.md）**：`intervention_plan.json` 里的每一条干预，必须派一个 subagent 执行——改 switch、≥3 种子重训、评估、算 delta、跑判定。主 agent **不得亲自跑训练**。subagent 只回一条紧凑 receipt（配置 diff + delta + 噪声底对照 + 种子数 + 判定），不回训练日志、不回中间产物、不回 checkpoint 路径以外的任何中间文件。

主 agent 收到每条 receipt 后，用 `ablation_verdict.py` 复核（subagent 应该已经用同一脚本算过，这里是主 agent 侧的独立复核，不是重新计算）：
```bash
python3 <ENGINE>/scripts/ablation_verdict.py \
  --hypothesis-id H<n> --switch=<switch值> \
  --delta <实测delta> --noise-floor <noise_floor_3sigma> \
  --direction <pred_direction> --seeds <N> \
  --out receipts/receipts.json
```
把打印的 receipt 行原样保留——它已经是 `## 消融证据` 节要贴的格式。

三态判定与后续动作：
- **confirmed**（超噪声底且方向对）→ 更新 `hypothesis_ledger.json` 该假设 `status="confirmed"`；可以支撑因果结论。
- **refuted**（超噪声底但方向反）→ `status="refuted"`，**必须**同时填 `kill_receipt`（配置 diff + delta + 噪声底对照 + 种子数，等同刚才的 receipt）——`validate_ledger` 强制这条，不许省略。允许提出新假设，但新假设 `provenance` 必须标 `"post-hoc"`，且要新的干预才能升级为 confirmed。
- **undecided**（delta 落噪声底内或种子间不稳定）→ `status="undecided"`，如实报告，**不得**当轮硬编一个未经干预的替代故事顶上——这是合法且必须报告的结果，不是失败。

汇总 `verdict_summary.json`（自足：`{"interventions":[{"hypothesis_id":str,"verdict":str,"receipt_line":str}],"n_confirmed":int,"n_refuted":int,"n_undecided":int,"budget_used":int}`）。FINDINGS.md 按结果更新状态：confirmed → 「已证实」；refuted → 「被推翻」（保留行，不删）；undecided → 状态仍写「假设」，结论文字里显式加注"（未决）"。

**降级路径**：`checkpoint`/`experiment_config` 材料 absent-confirmed（§7）→ Stage 2/3 判定为不可执行；主 agent 人工写一份 `verdict_summary.json`，把 Stage 1 全部 pending 假设标 `skipped_reason: "no_trainable_framework"`，`n_confirmed=n_refuted=0`，`n_undecided=`全部待验假设数——满足本阶段 done_when 的产物存在性，进入 Stage 4 出具"未验证假设"结论（design doc §8 的既定回退，对无可重训框架的老用法零破坏）。

done：`verdict_summary.json` 落盘（正常路径含 ≥1 条 receipt；降级路径显式标注 skipped）。

### Stage 4 结论落笔

主 agent 亲自做（`subagent_ok: false`）。步骤：

1. 三道门（`references/mechanisms.md`）＋ 本 playbook 特有反驳门（§6）逐条过。
2. 跑归因闸：
   ```bash
   python3 <ENGINE>/scripts/provenance.py \
     --code analysis_scripts/*.py --data slice_metrics.csv hypothesis_ledger.json --out provenance.json
   ```
3. 写 `CONCLUSION.md`（§6 模板，含 `## 模型结构依据` 与有因果表述时必带的 `## 消融证据`）。
4. 跑结论闸：
   ```bash
   python3 <ENGINE>/scripts/conclusion_gate.py
   ```
   不过闸 → 按报错逐条补（多半是缺 receipt 或缺图引用），不许绕过。

done：`CONCLUSION.md` + `gate_reports/conclusion_gate.json` 落盘。

## 3. 证据升级规则（三条腿）

严格三段式，跳步无效：

1. **现象**（Stage 0）：切片版图落盘，`slice_zcheck.json` 的 `verdict=="real"` 才算真实差异，`~noise` 的不得写成"存在但小"。
2. **假设**（Stage 1）：现象 + 指向具体组件的可否证预测 + 预登记（`provenance="pre-registered"`）→ 升「假设」。`post-hoc` 假设永远不能仅凭"看起来解释得通"升级，必须经它自己专属的新干预。
3. **已证实/被推翻/未决**（Stage 3）：唯一的升级路径是干预验证——`ablation_verdict.verdict()` 判定 `confirmed` 且干预满足单变量纪律（种子集与噪声底同批或另起 ≥3、其余变量固定）→ 升「已证实」；`refuted` → 「被推翻」（保留 kill_receipt，不删）；`undecided` → 停留「假设」层级，结论显式标"未决"。

任何一步不满足 → 停在当前层级，如实写明所在层级；**没有 Stage 3 的 receipt，不得使用因果语言**（conclusion_gate 机械拦截这条，见 §1）。

## 4. 停顿点与汇报

**Stage 0 完成即停**，向用户汇报：①噪声底数值与来源（已有/现算）；②池化差距 vs 噪声底的关系（并声明"平局不等于无差异，已转入切片"）；③各切片的 verdict、z、mean_diff、赢家。请用户点名：还要切哪个维度、切片粒度要不要调。

**Stage 2 完成即停**，向用户汇报：①选中的假设与判别力排序；②干预计划——每条干预的 switch/kind/seeds/双向判据；③预计训练次数（预算阶梯当轮上限）。请用户确认 `intervention-budget-confirmed` 再进 Stage 3——这是真金白银的重训，不许静默开跑。

## 5. subagent 拆分建议

Stage 0 的基线种子重训（噪声底现算）与 Stage 3 的每条干预，都是**强制**外包（不是"建议"）——见 `references/subagent-brief.md`。Stage 1 的账本校验/选择、Stage 2 的计划草拟可以外包起草，但排序判别力与最终拍板留给主 agent。Stage 4 不外包。

## 6. 结论模板与特有反驳门

CONCLUSION.md 按 `references/conclusion-reporting.md` 的通用骨架写，`## 模型结构依据` 一节内追加本 playbook 专属的 `## 消融证据` 子节——每条有因果表述的机制归因必须对应一行 receipt：

```
## 模型结构依据
档案 H3：跨变量注意力混合在近端时段损害预测，净效应为负。
## 消融证据
- H3 confirmed: switch=--itrans_no_attn delta=+0.031 noise_floor=0.0102 seeds=3
```

`## 消融证据` 一字不差抄 Stage 3 `ablation_verdict.py` 打印的 receipt 行——那一行本身就是 `conclusion_gate.RECEIPT_LINE_RE` 要匹配的格式，不要手改措辞。

无 `trainable_framework`（checkpoint/experiment_config absent-confirmed）的降级路径：`## 模型结构依据` 写"模型档案存在但无法验证：checkpoint/experiment_config 为 absent-confirmed，结构性解释降级为未验证假设"——含 `absent-confirmed` 与"降级"两个词，满足 conclusion_gate 的降级豁免。

特有反驳门——写结论前逐条自问并记录：
- **平局停手门**：Stage 0 是不是因为池化平局就没往下切片？没切完就写"无差异"＝违反 §1 首要陷阱，结论不可信。
- **单变量污染门**：干预除了目标 switch，种子/数据/步数/其余超参真的一个没动吗？`intervention_plan.json` 里的 kill_criterion/confirm_criterion 和 receipt 里的实际配置 diff 对得上吗？
- **事后编故事门**：refuted 之后是不是当轮补了一个没经过新干预的替代解释？有 → 结论必须标"post-hoc，未经干预验证"，不许当确认结论写。
- **家族外推门**：结论里出现"这一类模型都……"时，家族内独立干预证据是否 ≥2 个成员？不足 → 只能写单模型结论。
- **不可干预门**：假设的 `component` 在 `ablation_switches` 里标了 `not-intervenable`？→ 该假设结论上限"未验证假设"，不许强行设计不对等替代干预冒充验证。

## 7. 材料降级说明

- `predict`/`truth` 缺：`setup` 产物建不起来，本 playbook 连带不可做——向用户说明后终止。
- `model_profile`（model-audit 产物）缺且用户 declined：Stage 1 无法把假设指向具体组件（`component` 字段没有锚点可查），本 playbook 连带不可做——机制归因离不开代码锚点，这不是可降级项。
- `checkpoint`/`experiment_config` absent-confirmed：Stage 2/3 判定为不可执行——按 Stage 3 recipe 的"降级路径"写占位 `verdict_summary.json`，Stage 4 结论按 §6 的降级模板写"未验证假设"。这是 design doc §8 的既定回退：对没有可重训框架的老用法零破坏。
- `training_log` 缺：不影响主线（仅用于旁证基线重训是否收敛稳定），缺席仅记录。
- `model_code`（可选，独立于 `model_profile`）缺：不影响主线（`model_profile` 已含代码锚点摘要），仅在需要直接读代码消歧时缺席记录。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 `charts:`——核心证据是数值统计（跨种子配对 z、消融 delta），不是可视化对比。conclusion_gate 的图证据规则（规则 3）只在 `has_chart_stage(fm)` 为真时触发，本 playbook 恒为假，不受影响。

`chartbook/recipes/` 全部 28 个 recipe 逐条过一遍，统一跳过，分组理由：

- `worst-slice-compare` / `model-error-correlation` / `oracle-gap` / `horizon-degradation` / `cross-dim-stability` / `model-rank-significance` / `error-breakdown` / `intraday-profile` / `worst-points` / `rolling-stability` / `true-vs-pred-scatter` / `bad-window-clustering` / `good-bad-contrast` / `error-acf` / `horizon-error-quantiles` / `theil-decomposition` / `time-shift-diagnosis` / `pp-calibration` / `baseline-skill` / `revision-stability`：结构性不适用——这些 recipe 消费的是**单种子/跨模型**的池化或切片对比，本 playbook 的核心证据是**跨种子**配对差值（同一模型不同种子），维度不同，图无法直接复用；需要可视化"差距在哪"时应先跑生成假设的上游分析（自带这些图），本 playbook 只消费其产出的假设账本，不重画。
- `feature-error-conditional` / `feature-trend-overlay` / `y-vs-feature-mapping` / `feature-regime-error`：输入侧关联图，需 `features`/`feature_true` 材料，与本 playbook 的组件级机制归因主线无关。
- `train-test-drift` / `lookback-decay`：训练侧材料图，与消融验证主线无关。
- `global-attribution` / `local-waterfall`：归因组图，需 `serving_api` 反事实通道，本 playbook 用消融干预（重训对比）替代反事实调用，两条证据路径不重叠，不需要这两张图。
