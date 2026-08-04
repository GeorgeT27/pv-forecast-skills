---
id: model-comparison
name: 多模型对比归因
goal: 量化「模型 A 为什么比 B 好/差」，把差距分解到片段/时效/输入并归因到机制
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
    name: 机制归因（变体）
    done_when:
      findings_marker: "假设"
    prereqs:
      - desc: 模型档案产物已解决（built/linked 或 declined）
        check: "config:products.model_profile.status"
  - id: 3
    name: 结论
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    subagent_ok: false
    prereqs:
      - desc: 现象清单已停顿汇报
        check: "stage:1"
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
upgrade_rule: "总差距方向与主导切片方向一致（slice-gap 仅在 worst-slice perm.verdict=significant 时计入）且 cross-dim time_split 两半同向，才把差距结论从「现象」升「假设」"
---

# model-comparison：多模型对比归因

## 1. 问题框定与首要陷阱

「A 比 B 好」不是一句能直接下的结论。它是三个命题的组合，三个都验证过才成立：

1. **在这个口径下好。** 口径换了，结论可能反转。horizon-degradation 图里两条误差曲线存在交叉点时，必须先回 Stage 0 与用户确认口径，再往下比。
2. **在对齐样本上好。** 两个模型的缺窗不对称时，差距可能只是覆盖差异。先看 `<setup>/alignment_report.json` 的 dropped 统计。
3. **好得稳定。** 差距全集中在某一个月 ≠ 普遍领先。看 worst-slice-compare 的集中度。

首要陷阱：**排名 ≠ 机制**。Stage 0/1 全部是事实阶段，禁止使用机制语言。机制结论只能在 Stage 2 产生：由模型档案的桥接假设与图 JSON 证据合流得出。

量纲纪律：点级 pool 口径（error-breakdown/horizon 等：所有点混在一起算）与行 RMSE 均值口径（rolling-stability/oracle-gap 等：先按行算 RMSE 再取均值），两族数值不可直接比大小，只比走势与排名。

第四陷阱：**多图同源 ≠ 多证据**。多张图方向一致，只说明同一证据维度内部自洽（mechanisms.md §2「证据维度」），不构成第二条独立证据。升「假设」还必须过 cross-dim-stability 的正交切分稳定性检查（见 §3 三条腿）。

## 2. 逐阶段菜谱

长表与对齐由 setup 产物提供：`<setup>` = config.products.setup.workdir，alignment_report.json 与各长表都在这个目录里。本 playbook 不再写适配器。

### Stage 0 总差距事实
输入：`<setup>/predictions.csv` + `<setup>/alignment_report.json`。先读 dropped 统计；缺窗不对称时，后续结论必须声明"只在对齐子集上成立"。

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

### Stage 1 差距分解（事实）
**不写图代码。** frontmatter charts 声明的 5 张对比核心图全部用 chartbook 预写脚本（engine-core 对 chartbook 有专门豁免），orient 已经按材料把每张图标好可画/跳过。命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred <setup>/predictions.csv --out-dir charts/ [各图特有参数]

参数补充：worst-slice-compare 与 cross-dim-stability 要传 `--focal-model`，值 = model-set 答案里最关注的那个模型。worst-slice 的置换基线默认开启：`--n-perm 200 --perm-seed 0`。改种子等于改期望结果，必须连 golden 一起改。

广谱图（error-breakdown/intraday-profile 等）不在默认集里：已有 chart_sweep 产物（体检类 playbook 跑过）→ 直接复用其图 JSON 做判读；没有 → 需要时经图表选择门从可加画池加画，或先跑体检类 playbook。
判读：读各图 JSON 的描述符（见各 recipe 的判读节），产出 FINDINGS.md 现象清单——只写「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。
done：charts/*.json 至少一个 + INDEX.md + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 2 机制归因（变体，material:model_code 解锁）
输入两份：model_profile 产物（upstream 机制）——状态 built/linked 时用其工作目录下 models.md 里的桥接假设 H-ID，declined 时本阶段虽然解锁也只能停在现象层级、结论要声明缺档案；以及 Stage 1 的图 JSON。
菜谱：逐条桥接假设 → 找出它预言的图形态（bridge_hooks）→ 与实际描述符对照；是否升级按 §3 的三条腿判定。产出写回 FINDINGS.md，状态只用保留字。
done：FINDINGS.md 出现「假设」。

### Stage 3 结论
主 agent 亲自做（subagent_ok: false）。步骤：三道门（references/mechanisms.md）加上本 playbook 反驳门（§6），逐条过 → 跑 `scripts/provenance.py` 归因闸 → 写 CONCLUSION.md（末尾附 Provenance 块）→ 跑 conclusion_gate.py 拿 receipt。

## 3. 证据升级规则

- 现象 → 假设，三条腿缺一不可：①upgrade_rule 的两线方向一致（总差距方向与主导切片方向一致；slice-gap 线仅在 worst-slice `perm.verdict=significant` 时计入，not-significant → 该线弃权，弃权后只剩单线 → 上限「现象」）；②|sign_z| ≥ 2，差距不是噪声；③cross-dim `time_stable=true`，时间对半切后两半的差距方向相同。
  另：`caliber_stable=false` 不阻塞升级，但结论必须限定口径——例如「A 更好」只在行 RMSE 均值口径下成立。
- 假设 → 已证实：仅当机制预言了**未用于生成假设的**新图形态且被验证（三道门之门 2），或用户提供外部实验（换 checkpoint、换输入重跑）证实。
- 任何一步不满足 → 停在当前层级，结论如实写明所在层级。

## 4. 停顿点与汇报

Stage 1 完成即停，向用户汇报五件事：①gap_summary 的排名与 z；②已画/跳过图清单；③Top-3 现象，引用图 JSON 里的数字；④worst-slice 的置换基线判定——significant → 点名最差片，否则明说「集中未超随机基线，不点名」；⑤cross-dim 两个维度是否稳定。
然后请用户点名：补画哪张图、调什么参数（top-N、切片粒度）、下一步关注哪个配对或片段。用户不点名，则按 orient 推荐推进。

## 5. subagent 拆分建议

Stage 1 各图相互独立，可以并发：每张图一个子代理。brief 只带三样：命令模板、长表路径、输出目录（各图写不同的文件，天然防竞态；brief 写法见 references/subagent-briefs.md）。判读与 FINDINGS 汇总必须由主 agent 做。Stage 0/3 不拆。

## 6. 结论模板与特有反驳门

CONCLUSION.md 模板（按此顺序写）：口径与对齐声明 → 总差距（含 z）→ 差距结构（集中还是普遍，引 concentration_ratio）→ 机制归因（层级如实）→ 建议（换模/组合/维持，引 oracle-gap）→ Provenance 块。

特有反驳门——写结论前逐条自问并记录：
- **对齐偏置门**：dropped 不对称吗？只在对齐子集上比较得出的结论，声明子集了吗？
- **口径反转门**：horizon 交叉点存在吗？换口径后差距方向保持吗？引 cross-dim caliber_switch 数字；方向翻转 → 结论必须限定口径。
- **切片挑拣门**：结论引用的片段，是事先声明的规则选出来的（最差片规则），还是看完结果事后挑的？
- **随机集中门**：点名的最差片过置换基线了吗？把 perm_p、null_q95 抄进结论。
- **半程运气门**：时间对半切之后，差距方向保持吗？引 cross-dim time_split 数字。
- **同质化门**：模型间误差相关 >0.95 时，「A 略好」的差距还有实际意义吗？与 sign_z 联判。

## 7. 材料降级说明

- predict / truth 缺：setup 产物建不起来，本 playbook 连带不可做——向用户说明后终止。
- model_code 缺：Stage 2 锁死（变体不解锁），结论上限=「假设」，机制归因缺席要在 CONCLUSION 显式声明。
- features 缺：D 组三图跳过，输入侧归因缺席（现象清单注明）。
- train_y 缺：train-test-drift 跳过。"世界变了"这类候选解释只剩一个弱替代：y-vs-feature-mapping 的期内 split。
- training_log / experiment_config 缺：不影响本 playbook 主线（它们只服务 Stage 2 的旁证），缺席仅记录。

## 8. chartbook 覆盖声明

已声明（frontmatter Stage 1，对比核心 5 张）：worst-slice-compare /
model-error-correlation / oracle-gap / horizon-degradation / cross-dim-stability。

跳过的图（默认不画；可经图表选择门加画，或复用 chart_sweep 产物），逐组理由：
- error-breakdown、intraday-profile、worst-points、rolling-stability、true-vs-pred-scatter：单模型广谱体检图，对比结论非必需，chart_sweep 覆盖；
- feature-error-conditional、feature-trend-overlay、y-vs-feature-mapping、feature-regime-error：输入侧关联图，需 features 材料，对比主线可选加画；
- train-test-drift、lookback-decay：需 train_y／训练侧材料，属训练类目标的默认集；
- bad-window-clustering、good-bad-contrast、error-acf、horizon-error-quantiles、theil-decomposition、time-shift-diagnosis、pp-calibration、baseline-skill、revision-stability：误差结构细察图，深挖阶段按需加画；
- model-rank-significance：与 Stage 0 的 sign_z 判定重叠，需要更细的排名显著性时加画；
- global-attribution、local-waterfall：归因组图，需 serving_api 反事实通道，本目标默认不开。

（已声明的 5 张不重复列出。）
