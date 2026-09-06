---
id: model-comparison
name: 多模型对比归因
goal: 量化「模型 A 为什么比 B 好/差」——按题型分解差距事实，产出指向模型组件的可否证假设账本；不产结论，交验证主脊做干预判定
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: chart_sweep
    required: false
  - product: metric_table
    required: false
stages:
  - id: 0
    name: 总差距事实
    done_when:
      artifacts: ["gap_summary.json"]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 考核口径已定
        check: "question:metric-caliber"
      - desc: 对比模型集已定
        check: "question:model-set"
    subagent_ok: true
  - id: 1
    name: 差距分解（事实）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md"]
      findings_marker: "现象"
    prereqs:
      - desc: 总差距已知
        check: "stage:0"
    pause_after: true
    subagent_ok: true
    charts: [worst-slice-compare, model-error-correlation, oracle-gap,
             horizon-degradation, cross-dim-stability]
  - id: 2
    name: 机制归因（变体，产假设账本）
    done_when:
      artifacts: ["hypothesis_ledger.json"]
      findings_marker: "假设"
    prereqs:
      - desc: 模型档案产物已解决（built/linked 或 declined）
        check: "config:products.model_profile.status"
    pause_after: true
materials:
  required: [predict, truth]
  optional: [model_code, training_log, experiment_config, features, train_y]
variants:
  - id: mechanism
    when: "material:model_code"
    unlocks_stages: [2]
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_192=每行全部 horizon 点的 RMSE；也可指定子段或自定义）"
    why: "口径不同结论可反转——horizon 交叉存在时尤甚"
    options: ["rmse_192（默认）", "指定 horizon 子段", "自定义公式"]
    default: "rmse_192"
  - id: model-set
    stage: 0
    ask: "这次对比哪些模型？多于 2 个时，最关注哪一对（如 A vs B）？"
    why: "全集对比与定向配对的分解深度不同；配对决定 Stage 0 的差距检验对象"
    default: null
evidence_lines:
  - id: total-gap
    stage: 0
    output: gap_summary.json
  - id: slice-gap
    stage: 1
    output: charts/worst-slice-compare.json
  - id: cross-dim
    stage: 1
    output: charts/cross-dim-stability.json
upgrade_rule: "总差距方向与主导切片方向一致（slice-gap 仅在 worst-slice perm.verdict=significant 时计入）且 cross-dim time_split 两半同向，才把总差距从「现象」升级为可登记进假设账本的「假设」"
---

# model-comparison：多模型对比归因

## 1. 问题框定与首要陷阱

「A 比 B 好」不是一句能直接下的结论。它是三个命题的组合，三个都验证过才成立：

1. **在这个口径下好。** 口径换了，结论可能反转。horizon-degradation 图里两条误差曲线存在交叉点时，必须先回 Stage 0 与用户确认口径，再往下比。
2. **在对齐样本上好。** 两个模型的缺窗不对称时，差距可能只是覆盖差异。先看 `<setup>/alignment_report.json` 的 dropped 统计。
3. **好得稳定。** 差距全集中在某一个月 ≠ 普遍领先。看 worst-slice-compare 的集中度。

首要陷阱：**排名 ≠ 机制**。Stage 0/1 全部是事实阶段，禁止使用机制语言。机制假设只能在 Stage 2 产生：由模型档案的桥接假设与图 JSON 证据合流得出，产出的是可否证的假设账本，不是结论——机制判定移交验证主脊做干预确认。

量纲纪律：比较两端必须同指标公式、同聚合口径、同测量目标；不满足时只比各自内部走势/排名，并明确不可直接比值。delta 符号约定写入产物，全文一致。

第四陷阱：**多图同源 ≠ 多证据**。多张图方向一致，只说明同一证据维度内部自洽（mechanisms.md §2「证据维度」），不构成第二条独立证据。总差距要登记进假设账本，还必须过 cross-dim-stability 的正交切分稳定性检查（判据见 frontmatter `upgrade_rule`）。

## 2. 逐阶段菜谱

长表与对齐由 setup 产物提供：`<setup>` = config.products.setup.workdir，alignment_report.json 与各长表都在这个目录里。本 playbook 不再写适配器。

### Stage 0 总差距事实
输入：`<setup>/predictions.csv` + `<setup>/alignment_report.json`。先读 dropped 统计；缺窗不对称时，后续结论必须声明"只在对齐子集上成立"。关于配置对称的陈述须引用 experiment_config/training_log 摘录；未核实项明写 unknown。

**metric_table 产物复用规则**：metric_table 产物 built/linked，且其 `metrics_summary.json` 的 `caliber` 与本次 `metric-caliber` 答案一致 → 直接复用其汇总值作为指标表，不重算。口径不一致 → 视同 absent：照常自算，并在 FINDINGS 注明存在另一口径的指标表。

菜谱：写 `analysis_scripts/gap_metrics.py`，CLI 契约固定：
`--pred <setup>/predictions.csv --pair A,B --out gap_summary.json`。
计算内容（口径=rmse_192 时）：每 (model,unit,window) 行算 RMSE，得到每个模型的均值与排名；配对差 d_i = rmse_focal_i − rmse_other_i（对齐行内逐样本相减）；汇总 mean_diff、win_rate（d<0 的占比）、符号检验的 z 与 p（正态近似 z=(wins−n/2)/sqrt(n/4)，取双侧 p）。
落 `gap_summary.json`（schema：`{"caliber":str, "per_model":{m:mean},
"ranking":[...], "pair":[A,B], "n":int, "mean_diff":float, "win_rate":float,
"sign_z":float, "sign_p":float, "note":"差距是真的还是噪声：|z|<2 时只写现象
不写方向"}`）。
**生成闸（硬规则）**：接触真实数据之前，脚本必须先通过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/gap_metrics.py \
  --playbook model-comparison --stage 0`。
验证步：gen_gate 的金标准数据（golden/ 植入已知差距结构）全部 expect 通过。
done：gap_summary.json 落盘。

**Stage 0 之后按题型分流（硬规则）**：

1. 题目问「谁好 / 有无差异」且 |sign_z|<2、|mean_diff| 落在噪声底内 → 结论性事实就是「无显著差距」：FINDINGS.md 记现象 + 配对 z + 噪声底对照，汇报后本 playbook 止步，Stage 1/2 不进入。禁止对 null 差距做切片再从中挑显著片编机制叙事——切得够细总有噪声片显著，这是负分行为。
2. 题目问「差异在哪 / 为什么 / 归因」（含池化平局但要求归因真实差异的题）→ 进 Stage 1。
3. Stage 0 显著、且 model_profile 的 diff_list ≤2 个差异组件 → 允许跳过 Stage 1 直接进 Stage 2 登记消融假设；验证主脊要求签名级 falsifiable_pred 时，回头补画对应的单张图，不补全套。

### Stage 1 差距分解（事实）
**不写图代码。** frontmatter charts 是预检池——orient 按材料把每张图标好可画/跳过，**不是必画清单**。按当前疑问从 §6 调色板选图，每张图在 INDEX.md 登记「服务哪个疑问」；没有疑问支撑的图不画。两条例外是硬前置：要点名最差片必须画 worst-slice-compare（带置换基线）；要把总差距升级登记进假设账本必须画 cross-dim-stability（`upgrade_rule` 的输入）。全部用 chartbook 预写脚本（engine-core 对 chartbook 有专门豁免）。命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred <setup>/predictions.csv --out-dir charts/ [各图特有参数]

参数补充：worst-slice-compare 与 cross-dim-stability 要传 `--focal-model`，值 = model-set 答案里最关注的那个模型。worst-slice 的置换基线默认开启：`--n-perm 200 --perm-seed 0`。改种子等于改期望结果，必须连 golden 一起改。

广谱图（error-breakdown/intraday-profile 等）不在默认集里：已有 chart_sweep 产物（体检类 playbook 跑过）→ 直接复用其图 JSON 做判读；没有 → 需要时经图表选择门从可加画池加画，或先跑体检类 playbook。
判读：读各图 JSON 的描述符（见各 recipe 的判读节），产出 FINDINGS.md 现象清单——只写「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。已有真实输入上的单开关 receipt 也在此按 switch、逐种子 delta、适用域记录为实现级干预事实，不解释源码组件或跨域迁移。
done：charts/*.json 至少一个 + INDEX.md + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 2 机制归因（变体，material:model_code 解锁）

输入：model_profile 产物（upstream 机制）——状态 built/linked 时用其工作目录下 `models.md` 里的桥接假设 H-ID、`ablation_switches`（component→switch→kind 三元组）与（本次涉及 ≥2 模型对比时的）`diff_list`；declined 时见下方降级；以及 Stage 1 的图 JSON。

菜谱：逐条桥接假设 → 找出它预言的图形态（bridge_hooks）→ 与 Stage 1 实际描述符对照，挑出图证据支持的候选（只筛选可否证候选，不判定真假）。每条候选写成一条假设，落 `hypothesis_ledger.json`（顶层 `{"slice_map":[...], "hypotheses":[...]}`，schema 见 `scripts/hypothesis_ledger.py` 的 `REQUIRED` 字段），每条假设必须含：

- `id`：H1/H2...
- `claim`：一句话机制主张；claim 中每一个断言都必须落在 `falsifiable_pred` 的判定范围内，判定范围外的断言拆成独立假设或留在 FINDINGS.md 现象清单
- `component`：必须是 `models.md` 里登记的具体组件（写到子模块，如 `itransformer.attention (cross-variable)`，不许只写模型名）；`diff_list` 里出现的差异行优先选，判别力更高
- `falsifiable_pred`：可否证预测——"若干预该 component，某切片/机制的优势方向应如何变化"
- `discriminating_power`：一次干预能区分几条候选假设的整数打分，验证主脊按此排序优先
- `intervention`：`{"switch": ..., "seeds": ...}`——`switch` 从 `ablation_switches` 查该 component 对应条目填；`kind=not-intervenable` 的组件不得作为假设的 component（换一条可干预的候选，或如实标注该机制暂不可验证）；`seeds` 与噪声底同种子数，无噪声底材料时留空待验证主脊定
- `status`：固定 `"pending"`（本阶段只登记，不判定）
- `provenance`：固定 `"pre-registered"`（干预执行前登记）
- `kill_receipt`：固定 `null`（本阶段不产生，键必须保留）

**切片认领规则（硬规则）**：`slice_map` 必须收录 Stage 1 全部超噪声底的显著切片，覆盖每个已切维度（时段、波动分位、lead、单元/通道、时间段），不得只保留单一维度。其中方向与总差距相反（对照模型显著占优）的每个切片，必须被至少一条假设的 `falsifiable_pred` 显式认领——写明干预后该切片 delta 的预期方向；无假设可认领的，逐条写进顶层 `uncovered` 列表并注明「无假设认领」——未认领切片只用 `uncovered` 这一个字段名表达，不得另造同义字段（如 `not_registered`），下游验证按此字段核对。每条押注方向的假设，登记时同步登记互补假设（编号 `H<n>b`）：同 component、同干预，`falsifiable_pred` 为原方向取反——组件移除使对手模型的劣势切片追平或反超，即确认「该组件损害这些切片」。互补假设的 confirm/kill 判据各自独立成文，`provenance` 同标 `"pre-registered"`，判定共用同一次干预的 receipt，不占新预算。

Stage 2 已因 `model_code` 解锁、但 `model_profile` declined 时：不能产出源码锚定的机制账本。若已有真实输入上的单开关 receipt，最小账本只登记其机制解释为 `component="unknown"`、`status="undecided"`、`provenance="switch-label-only"` 的待验假设，并附 switch、逐种子 delta、适用域与 receipt；receipt 本身仅作为限该域/配置的实现级干预事实，不升级为源码组件机制或跨域结论。没有 receipt 的架构先验同样停在待验假设。若 `model_code` 与 `model_profile` 均缺，Stage 2 不解锁；receipt 只在 Stage 1 的事实清单中记录。

按 `discriminating_power` 降序排列。产出写回 FINDINGS.md：登记选中假设的 id/claim/component/falsifiable_pred/discriminating_power——状态只用「假设」保留字，不写"已验证"类字样。

若 Stage 1 没有任何显著切片，不编造机制；落一个 `component="unknown"`、
`status="undecided"`、`provenance="no_candidate"` 的占位条目，并在 FINDINGS 标明
“无可验证假设”。

done：`hypothesis_ledger.json` 落盘、`hypotheses` 数组非空、通过
`python3 <ENGINE>/scripts/hypothesis_ledger.py hypothesis_ledger.json`，FINDINGS.md 出现「假设」→ pause_after 停顿，移交验证主脊。

## 3. 停顿点与汇报

Stage 0 止步（分流规则 1 命中）时，向用户汇报：配对 z、噪声底对照、「无显著差距」的现象记录，并说明据此不做分解。

Stage 1 完成即停，向用户汇报五件事：①gap_summary 的排名与 z；②已画图各自服务的疑问 + 跳过/未选图清单；③Top-3 现象，引用图 JSON 里的数字；④若画了 worst-slice：置换基线判定——significant → 点名最差片，否则明说「集中未超随机基线，不点名」；⑤若画了 cross-dim：两个维度是否稳定。然后请用户点名：补画哪张图、调什么参数（top-N、切片粒度）、下一步关注哪个配对或片段。用户不点名，则按 orient 推荐推进。

Stage 2（若解锁）完成即停，止步于交接——不产结论。向用户汇报：①`hypothesis_ledger.json` 里每条假设的 id/claim/component/falsifiable_pred/discriminating_power；②按 discriminating_power 排好的验证优先序；③因组件不可干预（`ablation_switches` 标 `not-intervenable`）或缺 model_profile 而未能登记的候选，逐条注明原因。产出：假设账本 → 移交验证主脊做干预验证，本 playbook 到此为止。

## 4. subagent 拆分建议

Stage 1 各图相互独立，可以并发：每张图一个子代理。brief 只带三样：命令模板、长表路径、输出目录（各图写不同的文件，天然防竞态；brief 写法见 references/subagent-briefs.md）。判读与 FINDINGS 汇总必须由主 agent 做。Stage 0/2 不拆——Stage 2 的桥接假设筛选与排序是整体判断，拆了会丢跨假设的判别力比较。

## 5. 材料降级说明

- predict / truth 缺：setup 产物建不起来，本 playbook 连带不可做——向用户说明后终止。
- model_code/model_profile 缺：不产源码锚定账本；已有干预事实由 Stage 1 保留并标清域/配置边界，纯架构叙事停在待验假设。
- features 缺：D 组三图跳过，输入侧归因缺席（现象清单注明）。
- train_y 缺：train-test-drift 跳过。"世界变了"这类候选解释只剩一个弱替代：y-vs-feature-mapping 的期内 split。
- training_log / experiment_config 缺：不影响本 playbook 主线（它们只服务 Stage 2 的旁证），缺席仅记录。

## 6. 主题调色板 + 假设驱动选图

规则：每一轮只画"生成或区分当前假设所必需"的图；不画固定清单，从下面调色板按需选——没有假设不画，post-hoc 需要新证据时"再挑一张"是正常动作。

model-comparison 主题调色板（recipe id 均为 chartbook 已注册的合法 id；标 * 的在 frontmatter 预检池内，orient 已标好可画/缺材料；Stage 1 已画过的图直接复用其 JSON，不重画）：

| 主题 | recipe id | 何时用 |
|---|---|---|
| 分 lead-time 误差曲线 | `horizon-degradation` * | 想看"差距在远端还是近端"——生成/验证长程依赖衰减（attention 有效窗口/位置编码外推）或起报对齐类假设时画 |
| 分时段/hour 误差热图 | `intraday-profile` | 想看"差距集中在一天中的哪些物理时刻"——生成系统性标定/损失不对称或输入分辨率/滞后类假设时画 |
| 分单元误差柱 | `error-breakdown` | 想看"哪个单元(站点)+月/时段组合吃亏最重"——区分局部事件/数据质量假设 vs 季节漂移假设时画 |
| 高波动/极值段误差对比 | `worst-points` | 想看"是不是高波动/极值段吃亏"——生成高频容量不足或幅值压缩类假设时画（context.local_std/y_quantile 自带波动标签）|
| 模型间残差相关 | `model-error-correlation` * | 想区分两个机制假设——全对高相关→降级为共享输入/标签缺陷候选，某对独低→架构差异候选成立——时画 |

palette 之外的需求（如需 features 的输入侧关联图、需 train_y 的漂移图）：走图表选择门从可加画池按需加，不在本节穷举——加画理由要写清"服务哪条假设"。
