---
id: deployment-drift
name: 部署后退化/漂移诊断
goal: 判定上线模型是否真的退化、定位起始时点（区分渐变/突变、双点齐报）、把退化归因到候选诱因
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
  - product: chart_sweep
    required: false
stages:
  - id: 0
    name: 误差序列（口径）
    done_when:
      artifacts: ["error_series_summary.json"]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 考核口径已定
        check: "question:metric-caliber"
      - desc: 上线/训练截止时间已知
        check: "question:deploy-timeline"
    subagent_ok: true
  - id: 1
    name: 退化判定与时点（事实）
    done_when:
      artifacts: ["changepoint_summary.json"]
    prereqs:
      - desc: 误差序列已建
        check: "stage:0"
    subagent_ok: true
  - id: 2
    name: 结构分解（事实）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md"]
      findings_marker: "现象"
    prereqs:
      - desc: 变点事实已知
        check: "stage:1"
    pause_after: true
    subagent_ok: true
    charts: [rolling-stability, intraday-profile, error-breakdown, train-test-drift]
  - id: 3
    name: 诱因筛查（变体）
    done_when:
      artifacts: ["cause_screen.json"]
    prereqs:
      - desc: 变点已定位
        check: "stage:1"
  - id: 4
    name: 机制归因（变体）
    done_when:
      findings_marker: "假设"
    prereqs:
      - desc: 模型档案产物已解决（built/linked 或 declined）
        check: "config:products.model_profile.status"
  - id: 5
    name: 结论
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    subagent_ok: false
    prereqs:
      - desc: 现象清单已停顿汇报
        check: "stage:2"
materials:
  required: [predict, truth]
  optional: [features, train_y, model_code, training_log, experiment_config, data_profile]
variants:
  - id: cause-screen
    when: "material:features"
    unlocks_stages: [3]
  - id: mechanism
    when: "material:model_code"
    unlocks_stages: [4]
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_window=每窗全部 horizon 点的 RMSE，逐窗成序列）"
    why: "口径不同，退化时点与幅度可能都变"
    options: ["rmse_window（默认）", "指定 horizon 子段", "自定义公式"]
    default: "rmse_window"
  - id: deploy-timeline
    stage: 0
    ask: "模型什么时候上线？训练数据截止到哪天？上线后有没有重训/改配置？"
    why: "变点落在训练截止/上线附近与落在平稳运行期，解释完全不同（漂移 vs 一开始就没学会）"
    default: null
  - id: degradation-criterion
    stage: 1
    ask: "退化判定标准？（默认与 Stage 1 菜谱同法：两段最大分离扫描 + 置换基线；渐变形态另报首离 onset）"
    why: "判据不同结论可分岔；默认即菜谱方法，避免两套判据并存"
    options: ["两段最大分离 + 置换基线 + 渐变双点（默认）", "固定基线窗对比（需给窗长）", "自定义"]
    default: "两段最大分离 + 置换基线 + 渐变双点"
evidence_lines:
  - id: error-changepoint
    stage: 1
    output: changepoint_summary.json
  - id: feature-shift
    stage: 3
    output: cause_screen.json
upgrade_rule: "被点名特征的 onset 与误差侧 onset 重合（±7 窗）且方向一致，且误差退化方向在奇偶交错正交重切（changepoint interleave）下一致，才把诱因结论从「现象」升「假设」"
---

# deployment-drift：部署后退化/漂移诊断

## 1. 问题框定与首要陷阱

「模型退化了」不是一句能直接下的结论。它是四个命题的组合，四个都验证过才成立：

1. **误差变化超过噪声线。** 判定必须过置换基线，实际值明显超过纯随机水平才算数。还要做稳健性剔尾：去掉最极端的几个窗口后，结论仍然成立。
2. **起始时点答的是 onset，不是切分点。** onset 指误差首次偏离正常水平的时刻；退化是渐变（ramp）时，切分点会系统性地晚于真实起始时点。所以时间结论必须**双点齐报**：onset 和切分点一起报。这一条对应结论三道门里的反驳门 8「渐变-突变混淆」，是本 playbook 的头号陷阱。
3. **变差不是构成变化冒充的。** 季节进入难预测 regime 会推高整体误差，但这不是模型退化；只有在同类切片内对比出来的变差才算数。
4. **时点不落在训练截止/上线边界上。** onset 恰好落在边界附近时，候选解释是"模型对这段数据分布从来就没学会"（分布外），而不是"从准变不准"。两种说法必须区分。

诱因筛查的纪律：某个特征被点名 ≠ 它是因果原因。"双关"（该特征自身偏移显著 + 与误差序列秩相关）只是入围条件；还要时点重合，才够格进升级判定。没有真实偏移的诱饵特征不许被冤枉。

## 2. 逐阶段菜谱

### Stage 0 误差序列（口径）
输入：setup 产物的规范长表 predictions.csv。orient 会把 manifest 摘要注入上下文；如果 setup 也产出了 features/train_y 长表，同样直接用。
菜谱：写 `analysis_scripts/error_series.py`：按考核口径逐窗算误差，落 `error_series.csv`（列：window_idx,window_ts,rmse）；再落 `error_series_summary.json`，schema：
`{"n":int, "caliber":str, "range":[ts,ts], "n_dropped":int, "deploy_ts":str,
"train_cutoff_ts":str, "note":"缺窗不对称说明"}`。这个 JSON 要自足。
验证步：先造一个只有 3 个窗的合成小样跑通，逐窗 RMSE 与手算结果一致。
done：error_series_summary.json 落盘。

### Stage 1 退化判定与时点（事实）
菜谱：写 `analysis_scripts/changepoint.py`，CLI 契约固定：
`--series error_series.csv --out changepoint_summary.json --seed 0 --n-perm 200`。
脚本要做三件事，缺一不可：

1. **最大分离切分 + 置换基线。** 逐个候选切分点算前后两段的 Welch z，取 |z| 最大的位置为切分点。必须过随机基线：用固定种子把整个序列全序打乱 n-perm 次，得到 null 分布；实际值的 p≤0.05 才算 significant。种子必须显式出现在 CLI 上并落进 JSON。
2. **onset 首离判据。** 基线段 = 切分点前再留出 buffer（默认 10 窗）的纯净前段；band = 基线段的 μ+3σ；onset = 首次连续 2 窗越出 band 的位置。
3. **形态判定。** split − onset ≥ 3 窗 → 判 gradual（渐变）。时间结论双点齐报，措辞如："效应始于约 onset，至 split 附近完全显现"。

另外算两个稳健性量：一是 interleave 正交重切一致性（按奇数窗/偶数窗拆成两半各自重算，方向要一致）；二是剔掉后段最缓和的 3 窗之后，方向是否依然稳定。
产物 schema 见 golden 的 changepoint_summary.json。
**生成闸（硬规则）**：接触真实数据之前，脚本必须先通过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/changepoint.py \
  --playbook deployment-drift --stage 1`。
done：changepoint_summary.json 落盘。

### Stage 2 结构分解（事实）
**不写图代码。** frontmatter charts 声明的图全部用 chartbook 预写脚本（engine-core 对 chartbook 有专门豁免），orient 已经按材料把每张图标好可画/跳过。命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred <setup>/predictions.csv --out-dir charts/ [各图特有参数]

**chart_sweep 产物 built/linked 时**：与它重叠的图直接复用其 charts/*.json 做判读，不重画。

参数补充：D 组图加 `--features <setup>/features.csv`；train-test-drift 加 `--train-y <setup>/train_y.csv`。
判读：读各图 JSON 的描述符（见各 recipe 的判读节）。三个重点：rolling-stability 的时间形态是否与 Stage 1 的双点吻合；intraday-profile 的误差时段集中度（退化集中在哪些物理时刻）；构成对照——同类时段的前后段对比，结果喂给反驳门③（季节构成门）。
产出 FINDINGS.md 现象清单——只写「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。
done：charts/*.json 至少一个 + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 3 诱因筛查（变体，material:features 解锁）
菜谱：写 `analysis_scripts/cause_screen.py`，CLI 契约固定：
`--features <setup>/features.csv --series error_series.csv --split <Stage1的split_index>
--out cause_screen.json`。
逐窗聚合公式必须**写在脚本内**（默认 = 逐窗 K 点均值），跟脚本一起进生成闸受检；禁止用外置的、未经验证的整形脚本。
每个特征算四样：基线段（与误差侧用同一个 buffer）；偏移量 shift_z 与 Welch p；与误差序列全期的秩相关；特征自身的 onset（与 Stage 1 同一首离判据）。
判 shifted 的门槛（双关都命中才算）：p<0.01 且 |shift_z|≥3，且 |秩相关|≥0.3。
**生成闸**：同 Stage 1 的命令，改 `--stage 3`。
done：cause_screen.json 落盘。

### Stage 4 机制归因（变体，material:model_code 解锁）
输入两份：model_profile 产物（upstream 机制）——状态 built/linked 时用其工作目录下 models.md 里的桥接假设，declined 时本阶段虽然解锁也只能停在现象层级、结论要声明缺档案；以及 Stage 2/3 的产物。
菜谱：逐条桥接假设 → 找出它预言的图形态 → 与实际图 JSON 描述符对照 → 按 upgrade_rule 判定是否升级。产出写回 FINDINGS.md，状态只用保留字。
done：FINDINGS.md 出现「假设」。

### Stage 5 结论
主 agent 亲自做（subagent_ok: false）。步骤：三道门（references/mechanisms.md，重点是反驳门 8）加上本 playbook 特有反驳门（§6），逐条过 → 跑 `scripts/provenance.py` 归因闸 → 写 CONCLUSION.md，末尾附 Provenance 块。

## 3. 证据升级规则

- 现象 → 假设：必须同时满足 upgrade_rule **和**置换基线 significant。upgrade_rule 展开就是三条：被点名特征的 onset 与误差侧 onset 重合（±7 窗）、方向一致、interleave 正交重切下误差退化方向一致。
- 假设 → 已证实：仅当机制预言了**未用于生成假设的**新证据，且该证据被验证。合格的例子：换窗口重算得到同样结论；上游事件记录独立印证；用户提供外部实验（如特征换源之后重新预测）。
- 无 features 材料（诱因证据线缺席）：只剩单条证据线，结论上限「现象」——只能说"误差在 T₀-T₁ 间抬升"，不得点名诱因。

## 4. 停顿点与汇报

Stage 2 完成即停，向用户汇报四件事：①退化判定（gap_z、置换 p、稳健性结果）；②时间双点（onset/split、形态、与训练边界的关系）；③已画/跳过图清单；④Top-3 现象，引用图 JSON 里的数字。
然后请用户点名：深挖哪条、补哪张图、能否提供运维事件记录或特征数据。用户只给模糊授权时，按 engine-core 判据选（效应量最大且过功效阈值），并记入 PROGRESS.md。

## 5. subagent 拆分建议

Stage 2 各图相互独立，可以并发：每张图一个子代理。brief 只带三样：命令模板、长表路径、输出目录（各图写不同的文件；brief 写法见 references/subagent-briefs.md）。判读与 FINDINGS 汇总必须由主 agent 做。Stage 0/1/3/5 不拆。

## 6. 结论模板与特有反驳门

CONCLUSION.md 模板（按此顺序写）：口径与对齐声明 → 退化判定（含置换 p）→ 时间双点与形态 → 结构（时段/单元集中度）→ 诱因归因（层级如实）→ 建议（重训/换源/监控）→ Provenance 块。

特有反驳门——写结论前逐条自问并记录：
- **渐变门**（对应通用反驳门 8）：是不是只报了切分点？形态判过吗？如果是渐变，onset 单独估了吗？
- **训练边界门**：onset 落在训练截止/上线 ±7 窗内吗？是 → 候选解释改为"分布外起点"而非"运行中退化"，措辞必须区分这两种情况。
- **季节构成门**：难预测 regime 的占比在前后段变了吗？用 intraday/error-breakdown 做同类切片对比核实；没拆分过 → 标"未排除"。
- **覆盖对齐门**：前后段的缺窗率对称吗？真值口径中途变过吗？
- **上游事件门**：对比窗口内的运维/数据源/配置事件核对过吗（依据用户材料或事件记录）？没有材料 → 显式标"未排除"。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做。没有降级路径，向用户说明后终止。
- features 缺：Stage 3 锁死，诱因证据线缺席，结论上限「现象」（见 §3），CONCLUSION 里要显式声明。
- model_code 缺：Stage 4 锁死，机制归因缺席，升级只能依赖外部证据。
- train_y 缺：train-test-drift 跳过。"世界变了"这类候选解释只剩一个弱替代：y-vs-feature-mapping 的期内 split。
- training_log / experiment_config / data_profile 缺：只影响旁证与事件核验，缺席记录即可。

## 8. chartbook 覆盖声明

声明进 Stage 2 charts（时序稳定组）的四张图与用途：rolling-stability——时间形态主图；intraday-profile——退化在物理时刻上的集中度；error-breakdown——前后段构成对照，喂反驳门③（季节构成门）；train-test-drift——核查"世界变了"这类候选解释。

跳过的图（需要时可经可加画池加画，或复用 chart_sweep 产物），逐组理由：
- horizon-degradation / true-vs-pred-scatter / worst-points：广谱体检切面，由体检类 playbook 覆盖；
- feature-error-conditional / feature-trend-overlay / y-vs-feature-mapping：输入侧三件套；Stage 3 已有专用脚本 cause_screen.py，图形佐证按需加画；
- model-error-correlation / oracle-gap / worst-slice-compare / cross-dim-stability：需要 ≥2 个模型，本目标只有单模型；单模型的正交稳定性由 Stage 1 的 interleave 与口径子段复算承担。
