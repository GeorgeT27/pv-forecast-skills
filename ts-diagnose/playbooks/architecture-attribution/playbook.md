---
id: architecture-attribution
name: 架构归因验证脊（消融验证）
goal: 把切片级误差差异用单变量消融干预因果归因到模型具体组件，产出确认/否证/未决三态判定
produces_ablation_receipts: true   # conclusion_gate 规则 4 只对本 playbook 生效——其余
                                    # playbook 用各自方法（置换/反事实/留一法）验证因果，不产消融 receipt
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
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
      # 账本是跨轮累积的一个文件，它在盘上说明不了「这一轮登记过假设」——
      # 按轮的章由 hypothesis_ledger.py 在校验通过且本轮有假设时盖（new_round.py 后重开）。
      artifacts: ["hypothesis_ledger.json", "gate_reports/ledger_round_{round}.json"]
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
    pause_after: true
    subagent_ok: true
  - id: 3
    name: 执行或复核与判定
    done_when:
      artifacts: ["verdict_summary.json", "harvest.json"]
    prereqs:
      - desc: 干预计划已设计并停顿汇报
        check: "stage:2"
      - desc: 用户已确认新跑或仅复核
        check: "question:intervention-budget-confirmed"
    pause_after: true
    subagent_ok: true
  - id: 4
    name: 结论落笔
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    prereqs:
      - desc: 执行与判定已完成（含降级路径：无可训练框架时的「未验证假设」产出）
        check: "stage:3"
      - desc: 收成已汇报、用户已点名下一步
        check: "question:harvest-decision"
    subagent_ok: false
materials:
  required: [predict, truth]
  optional: [checkpoint, experiment_config, training_log, model_code]
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
    ask: "如何执行 intervention_plan.json：新跑干预，还是只复核已有 receipt？"
    why: "新跑需要确认训练预算；复用 receipt 不得重复训练"
    options: ["确认并执行新干预", "仅复核已有 receipt", "暂缓"]
    default: null
  - id: harvest-decision
    stage: 4
    ask: "本轮收成已汇报（harvest_check.py 打印的未解释切片清单）。下一步：①换角度再取一轮证据、重提假设；②以未决收口写结论；③换方向停手？"
    why: "假设全落空或只解释了一部分时，写结论与再来一轮是两条完全不同的路，代价也不同——这一步由用户点名，agent 不得自选，更不得在没有新证据的情况下把未决写成发现"
    options: ["① 换角度再取一轮证据", "② 以未决收口", "③ 换方向停手"]
    default: null
---

# architecture-attribution：架构归因验证脊（消融验证）

## 1. 问题框定与首要陷阱

「模型 A 比 B 好是因为组件 X」不是一句能直接下的结论。没有干预手段的机制叙事，无论多流利，都停留在「猜测」——本 playbook 存在的唯一理由，是把猜测升级成因果结论所必需的第三条腿：**单变量消融干预的实测结果**。

**三条腿纪律（硬规则）**：切片测量（差异在哪、是否超噪声底）+ 机理假设（指向具体组件、可否证、干预前登记）+ 干预验证（实测 delta，判定确认/否证/未决）。三条腿不齐——尤其是没有干预验证——不得出现任何架构/组件因果表述。conclusion_gate 在结论闸层面机械拦截这条（`CAUSAL_RE` 命中但无 `## 消融证据` receipt → 直接 exit 1），但机械拦截是最后一道防线，不是免检牌：写 CONCLUSION.md 之前，主 agent 自己先按本节纪律逐条自查。

首要陷阱——**池化平局 ≠ 无差异**。池化差距低于噪声底只说明要继续切片；Stage 0 不得据此终止或写“无差异”。

第二陷阱——**机理叙事无干预支撑就是猜测，且往往猜得很像真的**。"patch 保留时间局部性"这类假设读起来专业、流利、符合直觉，但在实证案例里 30 分钟内就被干预直接否证。叙事的说服力和它的真实性没有关系；只有 delta 数字有关系。

第三陷阱——**单一反例不足以支撑家族级解释**。"通道独立模型都更好"这类跨模型家族的断言，需要家族内 ≥2 个成员的独立干预证据；免费判别（如顺手核对同族的 DLinear/NLinear 产物）是加分项，不是必答题，但少于 2 个成员的证据不许写成家族结论。

第四陷阱——**否证之后现编替代故事**。否证一个假设之后，当轮立刻补一个没有新干预支撑的"其实是因为……"是本 playbook 明确禁止的动作：新假设必须标 `provenance: post-hoc`，且必须经**新的**干预才能升级为 confirmed——不许拿同一批数据既生成又确认。

## 2. 逐阶段菜谱

### Stage 0 现象定位（噪声底核验 + 切片测量）

输入：`<setup>` = config.products.setup.workdir 下的规范长表（predict/truth 对齐、时间索引）；同配置 ≥3 种子的基线指标（噪声底来源）。setup 的规范长表本身未固定 `seed` 列；跨种子分析必须使用用户明确提供的 seed/run 映射或已有逐种子产物，禁止把 model 名称臆当 seed。没有可识别的 seed 维度且没有已有噪声底/receipt 时，只能登记缺口，不能现算噪声底。

**第一步，噪声底**。`noise-floor` 问题答"已有数值"→ 直接落 `noise_floor.json`（自足：`{"metric":str,"config":str,"seeds":[...],"per_seed":[float,...],"mean":float,"std":float,"noise_floor_3sigma":float}`）。答"需现算"→ 用 checkpoint + experiment_config 起 ≥3 个基线种子重训（同配置、其余超参不变），走 subagent 外包（见 §5 Brief A），汇总每种子的口径指标，`noise_floor_3sigma = std(per_seed, ddof=1) * 3`。

**第二步，池化对照，不许因平局停手**。若已有其他分析产出的池化差距数值，与噪声底对照：差距 < 噪声底**不是**"无差异"的证据，只说明要往下切片才能看见真实版图（§1 首要陷阱）。

**第三步，切片测量**。写 `analysis_scripts/build_slice_metrics.py`：从各种子的预测/真值长表按
预先登记的时间、horizon、通道或目标状态分桶，产出 `slice,seed,model_a,model_b` 长表。
切片定义只能依赖真值、时间或外生变量，不能依赖模型误差；周期桶按自然最小粒度测量，
非周期桶在符号变化或过阈时细分。合并只允许相邻且同号的桶。验证行数守恒、每个
`(slice, seed)` 唯一，并抽查 2 行与源数据一致，结果记 PROGRESS.md。

本阶段 golden 只钉 `slice_zcheck.py` 的 CLI（manifest 的 `covers`），`build_slice_metrics.py`
没有 golden 覆盖：对它跑 `gen_gate.py` 会得到退出码 3「无 golden 覆盖」并且不写闸报告——
这不是 FAIL，也不算过闸；上一段的对账三项就是它的验证，缺一不可。

跑：
```bash
python3 <ENGINE>/scripts/slice_zcheck.py --metrics slice_metrics.csv --out slice_zcheck.json [--z-threshold 3.0]
```
`slice_zcheck.py` 是共享引擎脚本（不是运行时现场生成物），已由 CI 的 `playbooks/architecture-attribution/golden/` 金标准 + `scripts/tests/test_slice_zcheck.py` 覆盖，正文直接调用，不必再过 `gen_gate.py`——`gen_gate` 只闸运行时现场生成的分析脚本，引擎共享脚本（`scripts/` 下带 CLI 的机制脚本）一律直接调用。

判读：`slice_zcheck.json` 里 `verdict=="real"` 的切片才算真实差异；`~noise` 的切片如实写"无显著差异"，不得因为数值好看就硬解释。`z` 读作"该切片的配对差值是其自身跨种子标准差的几倍"（效应量，非 t 统计量），阈值 3 即 3σ 噪声底，与 Stage 3 `ablation_verdict` 的 `delta vs noise_floor_3sigma` 同口径；z 不随种子数增加而放大。

产出 FINDINGS.md 现象清单——只写现象：哪些切片真实分离（z 值、mean_diff、赢家）、哪些是噪声、池化 vs 噪声底的关系。禁机制语言。

done：`noise_floor.json` + `slice_zcheck.json` 落盘，FINDINGS.md 出现「现象」→ **pause_after 停顿**（§4）。

### Stage 1 假设账本校验与选择

输入：Stage 0 的切片版图；可用的 `model_profile`；已有单开关 receipt 及其原计划。

`ledger-path` 问题答"给出文件路径"→ 读入该 JSON。先跑校验，再核对 `hypotheses` 非空：
```bash
python3 <ENGINE>/scripts/hypothesis_ledger.py <ledger-path>
# 在本工作目录跑——它会自动读 slice_zcheck.json 做认领核对：
# 每个 real 切片必须在 slice_map 或 uncovered 里，漏登记直接 exit 1
```
账本为空视同没有账本，走“现场起草”分支。若 Stage 0 没有任何 `verdict=="real"` 切片，
不要编造候选；落一个 `component="unknown"`、`status="undecided"`、
`provenance="no_candidate"` 的占位条目，并在 FINDINGS 标明“无可验证假设”。

第三步，切片认领核对（硬规则）：把账本 `slice_map` 与 Stage 0 `slice_zcheck.json` 里 `verdict=="real"` 的切片逐条对照。每个 real 切片必须处于三种状态之一：①被某条假设的 `falsifiable_pred` 认领；②在账本里标注为某条已认领机制在另一维度的同源表现并写出对应关系；③登记进账本 `uncovered` 列表。方向与池化总差距相反的 real 切片，不认领就必须进 `uncovered`，不得留在隐性状态。`uncovered` 非空 → 回生成器补登记（干预执行前补的标 `provenance: "pre-registered"`），或把该切片写进结论的已知缺口。读入的账本若用其他字段名表达未认领切片（如 `not_registered`），先重命名为 `uncovered` 再继续核对，不得双名并存。**这一步现在由 `hypothesis_ledger.py` 机检**：在本工作目录跑它，它自动读 `slice_zcheck.json`，任何 real 切片既不在 `slice_map` 也不在 `uncovered` → exit 1 并逐条点名；同一切片既被认领又列进 `uncovered`、`slice_map` 重复登记、内嵌 `zcheck` 副本与权威产物不符，同样拦。

`ledger-path` 问题答"现场起草"（或账本为空）→ 在切片版图基础上生成 2–3 条候选假设，每条必须：①有档案时指向具体组件；无档案但有 receipt 时只锚定 switch，并标“代码锚点未核验”；无档案且无 receipt 时用 `component="unknown"`、标“代码锚点未核验”的 `undecided` 条目占位；②给出可否证预测；③标明实际 provenance，干预前登记才写 `"pre-registered"`；④claim 中每个断言都被 confirm/kill 判据覆盖，未覆盖的拆开或留在现象清单。每条押注方向的假设同步登记同 component、同干预、方向取反的互补假设 `H<n>b`，共用 receipt。指纹库只生成候选，不能替代干预验证：

候选组件必须来自 `model_profile` 的代码/配置锚点；没有锚点时只登记带作用域的待验
假设，不用泛化的“签名→组件”表替代干预验证。

按 `discriminating_power`（一次干预能区分几个候选假设）降序排列，写回 `hypothesis_ledger.json`（schema 见 `scripts/hypothesis_ledger.py` 顶部 `REQUIRED` 字段与 `scripts/tests/test_hypothesis_ledger.py::VALID`）。

产出 FINDINGS.md：登记选中的假设 ID、claim、component、falsifiable_pred、discriminating_power——状态标「假设」。

done：`hypothesis_ledger.json` 落盘且非空、过 `validate_ledger`，FINDINGS.md 出现「假设」。

### Stage 2 判别性干预设计

输入：Stage 1 选中的最高判别力假设；可用时读取 `model_profile.ablation_switches`。已有合规单开关 receipt 时，可复用其关联计划。

菜谱：
1. 在 `ablation_switches` 里查该假设 `component` 对应的条目。`kind=config-flag` → 直接可用现成参数；`kind=code-stub` → 需要新写干预代码（如置零/替换 stub），写清改动范围；`kind=not-intervenable` → 该假设**在当前代码库不可干预**，如实标注，不得强行绕过设计一个不对等的替代干预。
2. **单变量纪律**：一次只动被选中的这一个开关，种子集固定为噪声底同一批种子（或另起但同样 ≥3 个）、数据/训练步数/其余超参全部与基线一致。
3. **双向可判**：写清"什么结果算确认、什么结果算否证"——即预登记 `pred_direction`（`increase`/`decrease`，对应 `ablation_verdict.verdict()` 的方向参数）。设计阶段写不出否证判据的干预不合格，退回重设计。
4. **预算阶梯**：先设计判别力最高的一个干预；单轮训练上限 ~10 次（如 4 个 switch × 3 种子内的裁剪组合）。是否追加取决于 Stage 3 的结果，不在本阶段一次性铺开。

`model_profile` declined 时不设计新 switch：有可复核 receipt，就从原计划填同一结构，`script=produced_by`；没有 receipt，则计划项加 `skipped_reason: "no_model_profile"`，机制假设保持未验证。

落 `intervention_plan.json`（结构：`[{"hypothesis_id", "component", "switch", "kind", "seeds", "pred_direction", "kill_criterion", "confirm_criterion", "script"}]`）。新计划 `script=null`，复用 receipt 时填 `produced_by`；不可执行项加 `skipped_reason`。每条已执行干预都必须能找到 eval 脚本。

产出：向用户展示计划（含预计训练次数），**不写 FINDINGS 状态**（这是设计产物，不是现象/假设判定）。

done：`intervention_plan.json` 落盘 → **pause_after 停顿**（§4，等 `intervention-budget-confirmed` 确认再进 Stage 3）。

### Stage 3 执行与判定

输入：`intervention_plan.json`；`intervention-budget-confirmed` 已确认。

**执行契约**：先跳过带 `skipped_reason` 的项；`script==null` 的新干预仅在 checkpoint 与 experiment_config 在场时派 subagent 执行改 switch、≥3 种子重训、评估和判定，否则标 `no_trainable_framework`；主 agent 不亲自训练。`script` 非空的既有 receipt 只复核脚本 hash、配置 diff、真实输入、逐种子 delta 与判定，不重训。新跑 subagent 只回紧凑 receipt。

**第二口径随产随算（硬规则）**：派 worker 时把保守第二口径名与其噪声底一并给出；worker 在
清理预测数组之前必须算出第二口径 delta 并写进 receipt（`--delta2/--noise-floor2/--caliber2`）。
预测数组一旦删掉就再也补不出来，判据②的复核会永久悬空——那时该假设只能停在 undecided。

主 agent 收到每条 receipt 后：①把 `intervention_plan.json` 该条的 `script` 字段回填为 receipt 里的 `produced_by`（eval 脚本路径）；②用 `ablation_verdict.py` 复核（subagent 应该已经用同一脚本算过，这里是主 agent 侧的独立复核，不是重新计算）：
```bash
python3 <ENGINE>/scripts/ablation_verdict.py \
  --hypothesis-id H<n> --switch=<switch值> \
  --delta <实测delta> --noise-floor <noise_floor_3sigma> \
  --delta2 <第二口径delta> --noise-floor2 <第二口径噪声底> --caliber2 <第二口径名> \
  --direction <pred_direction> --seeds <N> \
  --out receipts/receipts.json
```
把打印的 receipt 行原样保留——它已经是 `## 消融证据` 节要贴的格式。

**切片重算（硬规则，不占训练预算）**：每条干预产物落盘后，在 Stage 0 `slice_zcheck.json` 全部 `verdict=="real"` 的切片上，用同一口径和同一批种子直读产物重算 delta；每个切片保留 receipt，并按该切片噪声底判定。结果写入 `verdict_summary.json`，标注归零、反转、残留、加强（同向优势变大）或对手差距缩小。各类及正负方向都必须进入 CONCLUSION；只报一个类别的计数不算完成。归零/反转且超噪声底的证据挂到对应假设；无认领者只允许补同组件、同干预、取反方向的 `complement` 假设。其他 post-hoc 假设仍需新干预。未被推动的 real 切片逐条标为未解释。

三态判定与后续动作：
- **confirmed**（超噪声底且方向对）→ 更新 `hypothesis_ledger.json` 该假设 `status="confirmed"`；可以支撑因果结论。
- **refuted**（两条判据，命中任一即判）：①超噪声底但方向反；②预测落空——`falsifiable_pred` 预登记了"|delta| 应超噪声底"，实测 |delta| ≤ 噪声底的一半，且保守口径复核同判。判据②的机器信号是 receipt 的 `pred_miss.eligible`：第二口径缺席时它恒为 false，该假设**只能**停在 undecided，不许仅凭主口径判 refuted。两条同样 `status="refuted"`，**必须**同时填 `kill_receipt`（判据①：配置 diff + delta + 噪声底对照 + 种子数，等同刚才的 receipt；判据②：逐项登记预登记预测原文、实测 delta、两种口径噪声底、逐种子符号）——`validate_ledger` 强制这条，不许省略。判据②的升级由主 agent 在账本层执行，`## 消融证据` 节仍照抄脚本 receipt 原行不改。脚本判定与账本 `status` 不一致的每一条假设，都必须在 `verdict_summary.json` 该条的 note 与 CONCLUSION 中逐条披露升级判据（预登记原文、实测 delta、两口径复核）——披露一条而漏另一条视同未披露。kill_receipt 引用的判定切片必须是预登记判据点名的切片；确需替换，写明替换理由并核对替换切片仍在该假设认领组内。允许提出新假设，但新假设 `provenance` 必须标 `"post-hoc"`（切片重算里限定形态的 complement 除外，见上），且要新的干预才能升级为 confirmed。
- **undecided**（噪声底的一半 < |delta| < 噪声底，或两种口径判定不一致，或种子间不稳定且不满足判据②）→ `status="undecided"`，如实报告，**不得**当轮硬编一个未经干预的替代故事顶上——这是合法且必须报告的结果，不是失败。

汇总 `verdict_summary.json`（自足：`{"interventions":[{"hypothesis_id":str,"verdict":str,"receipt_line":str}],"n_confirmed":int,"n_refuted":int,"n_undecided":int,"budget_used":int}`）。FINDINGS.md 按结果更新状态：confirmed → 「已证实」；refuted → 「被推翻」（保留行，不删）；undecided → 状态仍写「假设」，结论文字里显式加注"（未决）"。FINDINGS 与 CONCLUSION 的判定措辞必须与账本 `status` 逐条同源：「被否掉」「被推翻」「被排除」只许用于 `status="refuted"` 的假设；`status="undecided"` 的只许写「未决」「无证据支持」。

宣告循环收敛引用「confirmed 且能解释切片版图」这一终止条件前，先核对切片重算结果与 Stage 1 的认领清单——这件事由下面的收口脚本机器做，不用手数：`harvest.json` 的 `harvest` 不是 `full` → 该终止条件不成立，收敛只能引用预算耗尽或生成器提不出新假设，且未解释切片逐条写进结论的已知缺口。

**收口（硬规则，Stage 3 的最后一步）**：`verdict_summary.json` 落盘后跑

```bash
python3 <ENGINE>/scripts/harvest_check.py
```

它从 `slice_zcheck.json` 的 real 切片全集里减去被干预推动过的切片（`slice_recompute` 的 `beyond_noise_floor`），把剩下的算成未解释清单，与 `verdict_summary.unexplained_real_slices` 逐条对账，不符或缺字段直接 exit 1；通过则追加写 `harvest.json`。收成分三档：`full`（无未解释切片）、`partial`（解释了一部分）、`none`（confirmed 为零且没推动任何切片）。

它同时补查 Stage 1 认领核对有没有走完：real 切片既不在 `slice_map` 也不在 `uncovered` 的，报 exit 1 并逐条点名——**漏登记不是「无人认领」**，前者是那道核对没走完，后者是走完之后的合法出口，清单里也分开印（`claim_state` 三态：`claimed` / `uncovered` / `unregistered`）。补进账本再重跑收口。

拿到打印结果后向用户汇报（§4 Stage 3 停顿），并对每个还有残留的维度各说一个**本轮没试过**的取证角度——例如按月切没出结果时改按波动强度、按天气状态、按目标量级切。说角度不等于已经有证据：这些角度只能作为下一轮取证的起点写进汇报，不许当结论写。然后由用户答 `harvest-decision` 三选一：

- **①换角度再取一轮**：跑 `python3 <ENGINE>/scripts/new_round.py --note "<这轮换的什么角度>"`（先 `--dry-run` 看它要动什么）。它把本轮的取证与判定产物（`slice_zcheck.json`/`slice_metrics.csv`/`intervention_plan.json`/`verdict_summary.json`，图剧本还含 `chart_plan.json`/`charts/`/`INDEX.md`）**移**进 `rounds/round_<N>/`，`state.round` +1，并给账本里每条还没标轮次的假设补上 `round`。账本、`receipts/`、`harvest.json`、`runs/`、噪声底**不归档**——账本跨轮累积（新一轮得看得见上一轮否掉了什么），receipt 归档掉等于把否证藏起来（结论闸要求盘上每张都进证据清单），收成本来就是追加的。
  归档完重跑 orient：产物一没，Stage 0/1 的入口就回来了。新一轮的假设登记时必须带 `"round": <N>`——`hypothesis_ledger.py` 校验时按 `state.round` 盖一张 `gate_reports/ledger_round_<N>.json`，本轮一条新假设都没有就 exit 1，Stage 1 也就判不了完成。**先读账本再提**：上一轮 `refuted` 的不许原样再提，`undecided` 的要提就得换一个可否证预测或换一个干预，否则是拿同一批数据反复问同一个问题。
- **②以未决收口**：进 Stage 4；未解释清单逐条进结论的 `## 已知缺口` 节，切片名连前缀原样抄。
- **③换方向**：记 PROGRESS.md 后停，不写 CONCLUSION.md。

三个选项都是合法结果。收成为 `none` 不是失败，是本轮的实测结论——但它绝对不许被写成一个读起来像发现的说法（§6 空收成门，结论闸机检）。

**降级路径**：`checkpoint`/`experiment_config` absent-confirmed 只禁止新跑；`model_profile` declined 且没有可复核 receipt 时记 `no_model_profile`。没有 receipt 的机制假设写 `skipped_reason` 并记为未验证；既有 receipt 按其实际 verdict 更新精确限定的 switch 效应，源码组件解释仍记 `undecided`。汇总后进 Stage 4。

done：`verdict_summary.json` + `harvest.json` 落盘（正常路径含 ≥1 条 receipt；降级路径显式标注 skipped）。

### Stage 4 结论落笔

主 agent 亲自做（`subagent_ok: false`）。步骤：

1. 三道门（`references/mechanisms.md`）＋ 本 playbook 特有反驳门（§6）逐条过。
2. 跑归因闸：
   ```bash
   python3 <ENGINE>/scripts/provenance.py \
     --code analysis_scripts/*.py --data slice_metrics.csv hypothesis_ledger.json \
     --serves eval_H1.py=H1 eval_H2.py=H2 ... --out provenance.json
   ```
   `--serves` 把每个 eval 脚本挂回它服务的假设（有段号时写 `eval_H1.py=H1@<segment_id>`）；只服务事实层的脚本（如 `build_slice_metrics.py`）不用挂。**互补假设 `H<n>b` 与母假设共用同一支脚本和同一张 receipt 时，写逗号列全：`--serves eval_H1.py=H1,H1b`**——一个脚本只挂一个假设会让另一个在规则 5 报孤儿脚本。写完核对：每条经过干预的假设，其 eval 脚本都在 serves 里，一个孤儿脚本都不许剩。
3. 写 `CONCLUSION.md`（§6 模板，含 `## 模型结构依据`、有因果表述时必带的 `## 消融证据`，以及必带的 `## 证据清单`——逐条点名结论所站的证据文件，反引号包路径；盘上每张 `receipts/H*.json`（含被否证的）与 `verdict_summary.json` 都必须列出，只列支持结论的过不了闸）。数字复算先把计数谓语翻成逐条明细的布尔判据，再从明细重数；汇总字段只作交叉核对。派生数字写明分子、分母、聚合/测量目标和来源；逐种子数组按产物固定顺序并标注 seed，禁止无标签排序。符号约定在文首声明并全文一致。复算不上的改写或删除，记录记 PROGRESS.md。
4. 跑结论闸：
   ```bash
   python3 <ENGINE>/scripts/conclusion_gate.py
   ```
   不过闸 → 按报错逐条补（多半是缺 receipt 或缺图引用），不许绕过。闸对本 playbook 额外机检两组（规则 5+6）：**溯源闭环**——每张 `receipts/H*.json` 必须是 `ablation_verdict.py --out` 生成的完整 schema（含 `produced_by`+`script_sha256`，脚本在盘且指纹相符、seeds≥3），`provenance.json` 的 serves 必须把该脚本挂回对应假设（一支脚本服务多个假设时列全），`intervention_plan.json` 每条已执行干预的 `script` 必须已回填；**判据②闸**——脚本判 `undecided` 而账本升级为 `refuted` 的假设，其 receipt 的 `pred_miss.eligible` 必须为真（即保守第二口径同判），否则不放行；**证据清单**——见上一步。这些不是新增动作，是把 Stage 3/4 已有纪律变成机器拦截。

done：`CONCLUSION.md` + `gate_reports/conclusion_gate.json` 落盘。

## 3. 证据升级规则（三条腿）

严格三段式，跳步无效：

1. **现象**（Stage 0）：切片版图落盘，`slice_zcheck.json` 的 `verdict=="real"` 才算真实差异，`~noise` 的不得写成"存在但小"。
2. **假设**（Stage 1）：现象 + 指向具体组件的可否证预测 + 预登记（`provenance="pre-registered"`）→ 升「假设」。`post-hoc` 假设永远不能仅凭"看起来解释得通"升级，必须经它自己专属的新干预。
3. **已证实/被推翻/未决**（Stage 3）：唯一的升级路径是干预验证——`ablation_verdict.verdict()` 判定 `confirmed` 且干预满足单变量纪律（种子集与噪声底同批或另起 ≥3、其余变量固定）→ 升「已证实」；`refuted` → 「被推翻」（保留 kill_receipt，不删）；`undecided` → 停留「假设」层级，结论显式标"未决"。

任何一步不满足 → 停在当前层级，如实写明所在层级。既有 receipt 只支撑其实际域/配置下的实现级干预事实；没有 Stage 3 receipt，不得把源码组件机制写成因果结论。

## 4. 停顿点与汇报

**Stage 0 完成即停**，向用户汇报：①噪声底数值与来源（已有/现算）；②池化差距 vs 噪声底的关系（并声明"平局不等于无差异，已转入切片"）；③各切片的 verdict、z、mean_diff、赢家。请用户点名：还要切哪个维度、切片粒度要不要调。

**Stage 2 完成即停**，向用户汇报：①选中的假设与判别力排序；②干预计划——每条干预的 switch/kind/seeds/双向判据；③新跑次数与待复核 receipt 数。请用户确认 `intervention-budget-confirmed` 再进 Stage 3；仅复核已有 receipt 不重训。

**Stage 3 完成即停**，向用户汇报 `harvest_check.py` 打印的收成：①收成档位与三态计数；②未解释的 real 切片逐条（切片名、z、mean_diff、是谁认领的）；③每个残留维度各一个本轮没试过的取证角度。请用户答 `harvest-decision` 三选一再动——没拿到答复不许进 Stage 4，也不许自己开下一轮。收成为 `none`（一条 confirmed 都没有）时，汇报的第一句必须是「本轮未能归因到任何组件」，不许用"倾向于""基本可以认为"这类措辞把未决讲成结论。

## 5. subagent 拆分建议

Stage 0 的基线种子重训（噪声底现算）与 Stage 3 的每条新干预，都是**强制**外包——每条派一次 `architecture-attribution-worker` 卡（一次一条任务，回 receipt）；Stage 0 的切片长表与 z 检验派 `architecture-attribution-compute` 卡；索引与回退见引擎 `references/subagent-briefs.md`；已有 receipt 只由主 agent 复核。Stage 1 的账本校验/选择、Stage 2 的计划草拟可以外包起草，但排序判别力与最终拍板留给主 agent。Stage 4 不外包。Claude Code 下 Stage 3 的一轮干预可调 workflow：Workflow 工具 `scriptPath="<ENGINE>/workflows/ts-train-batch.js"`，`args={"engine", "workdir", "agent_type": "architecture-attribution-worker", "task": "intervention", "candidates": <intervention_plan 里未执行且无 skipped_reason 的条目>}`；返回的 results 逐条复核后再更新账本。

## 6. 结论模板与特有反驳门

CONCLUSION.md 按 `references/conclusion-reporting.md` 的通用骨架写，`## 模型结构依据` 一节内追加本 playbook 专属的 `## 消融证据` 子节——每条有因果表述的机制归因必须对应一行 receipt：

```
## 模型结构依据
档案 H3：跨变量注意力混合在近端时段损害预测，净效应为负。
## 消融证据
- H3 confirmed: switch=--itrans_no_attn delta=+0.031 noise_floor=0.0102 seeds=3
## 已知缺口
- `horizon:mid`（z=4.93，mean_diff=+0.036，H1 认领但干预未推动）
- `month:2020-10`（z=9.76，mean_diff=+0.044，无人认领）
## 证据清单
- `receipts/H3.json` — H3 判定回执（produced_by: analysis_scripts/eval_H3.py）
- `receipts/H4.json` — H4 判定回执（refuted，同样列出）
- `verdict_summary.json` — 全部干预汇总与切片重算
- `harvest.json` — 本轮收成与未解释清单
- `explanatory_power.json` — 焦点切片闭合率
```

`## 已知缺口` 节按 `harvest.json` 的 `unexplained` 逐条列名，切片名连 `channel:`/`month:` 前缀一起原样抄；结论闸逐个字符串核对，只写后缀（`raining_s` 代替 `channel:raining_s`）或合并成"其余切片未解释"这类概括都过不了闸。收成为 `full`（无未解释切片）时这一节不受本规则约束。

`## 消融证据` 一字不差抄 Stage 3 `ablation_verdict.py` 打印的 receipt 行——那一行本身就是 `conclusion_gate.RECEIPT_LINE_RE` 要匹配的格式，不要手改措辞。

复用 receipt 且无 model_profile 时，`## 模型结构依据` 仍引用对应 H-ID，并写“代码锚点未核验”；因果措辞只限该 switch、模型、配置和数据域，不外推源码组件或跨域迁移。

Stage 3 降级时，只写实际命中的句子，禁止为过闸虚构另一项缺失：

- `no_model_profile`：`model_profile` 档案 declined 且无可复核 receipt（档案 absent-confirmed）→ 无结构锚点，结论降级为未验证假设。
- `no_trainable_framework`：checkpoint/experiment_config absent-confirmed → 无法干预，结论降级为未验证假设。

两项都命中才写两句；`model_profile` declined 不等于 `model_code` 缺失。

特有反驳门——写结论前逐条自问并记录：
- **平局停手门**：Stage 0 是不是因为池化平局就没往下切片？没切完就写"无差异"＝违反 §1 首要陷阱，结论不可信。
- **单变量污染门**：干预除了目标 switch，种子/数据/步数/其余超参真的一个没动吗？`intervention_plan.json` 里的 kill_criterion/confirm_criterion 和 receipt 里的实际配置 diff 对得上吗？
- **事后编故事门**：refuted 之后是不是当轮补了一个没经过新干预的替代解释？有 → 结论必须标"post-hoc，未经干预验证"，不许当确认结论写。
- **家族外推门**：结论里出现"这一类模型都……"时，家族内独立干预证据是否 ≥2 个成员？不足 → 只能写单模型结论。
- **不可干预门**：假设的 `component` 在 `ablation_switches` 里标了 `not-intervenable`？→ 该假设结论上限"未验证假设"，不许强行设计不对等替代干预冒充验证。
- **背景与前提陈述门**：关于数据性质或比较前提（覆盖范围、配置、种子、训练/评估协议）的每句话，都必须引用匹配口径的量测或配置摘录；给不出就标“未核实”，不得用自述 note 代替证据。
- **状态口径门**：结论里每个假设的判定动词与账本 `status` 字段逐条比对，措辞强于状态（undecided 写成"被否掉/被排除"）或弱于状态 → 改账本或改措辞，二者取其一后重过本门。
- **头条对账门**：一句话结论/执行摘要里 confirmed 机制的清单与计数，与账本 `status=="confirmed"` 集合一一对应——多一条、少一条、或与正文任何一处的数量表述不一致，改到对上再出稿。confirmed 的细化假设（`H<n>b` 类）进头条时必须并置其母假设已被否证的边界与自身的池化方向，不得写成模型的整体优势机制。标题句与加粗结论句单独摘出后仍须与账本 status 相容：否定式断言（「不是 X」）只许覆盖 `status=="refuted"` 的假设；涉及 undecided 或未执行假设的组件，标题句自带作用域限定，或不在标题句点名。
- **版图降级门**：按配对差绝对值或分歧幅度选择性剔除样本/单元的裁剪是影响力集中度检验，不是抗噪检验——不得据其宣称任何 `verdict=="real"` 切片「方向翻转」或「经不起检验」，只许写「该优势集中在少数高分歧单元」并保留 Stage 0 判定。推翻 real 切片方向的唯一途径是同口径的跨种子重算证据。
- **数字复算门**：计数、比例、倍数能否从逐条产物按声明口径复算？计数先核谓语再核数字；阈值和量级词必须有同粒度数字及适用判据，否则改写为可证事实。
- **空收成门**：`harvest.json` 的 `n_confirmed` 为零时，`## 模型结构依据` 节第一句必须是「本轮未能归因到任何组件」（结论闸逐字符串机检），随后才允许写各假设停在什么状态、下一轮该从哪个角度取证。一条 confirmed 都没有时，`undecided` 的假设只能作为下一轮的输入登记，不许改写成读起来像发现的说法，也不许把"没测出效应"讲成"该组件无作用"（后者要 refuted 才成立）。
- **否证边界门**：每个 `refuted` 都写清“推翻的范围”和“没有推翻的已测效应”；pooled null 不得写成组件无作用。pooled 近零而切片异号时，正文说明正负相消并各举代表切片。

## 7. 材料降级说明

- `predict`/`truth` 缺：`setup` 产物建不起来，本 playbook 连带不可做——向用户说明后终止。
- `model_profile` declined：Stage 0/1 照常；有 receipt 则复核限定 switch 效应，无 receipt 才降级。缺档案不等于已有事实消失。
- `checkpoint`/`experiment_config` absent-confirmed：禁止新跑，不影响既有 receipt 复核。
- `training_log` 缺：不影响主线（仅用于旁证基线重训是否收敛稳定），缺席仅记录。
- `model_code`（可选，独立于 `model_profile`）缺：不影响主线（`model_profile` 已含代码锚点摘要），仅在需要直接读代码消歧时缺席记录。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 `charts:`——核心证据是数值统计（跨种子配对 z、消融 delta），不是可视化对比。conclusion_gate 的图证据规则（规则 3）只在 `has_chart_stage(fm)` 为真时触发，本 playbook 恒为假，不受影响。

`chartbook/recipes/` 统一不在本 playbook 重画：跨模型/池化/切片图由上游分析产出，本 playbook 只消费其假设账本；输入关联图和训练侧图不属于组件消融验证主线。
- `global-attribution` / `local-waterfall`：归因组图，需 `serving_api` 反事实通道，本 playbook 用消融干预（重训对比）替代反事实调用，两条证据路径不重叠，不需要这两张图。
