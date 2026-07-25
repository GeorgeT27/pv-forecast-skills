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
  - id: 1
    name: 退化判定与时点（事实）
    done_when:
      artifacts: ["changepoint_summary.json"]
    prereqs:
      - desc: 误差序列已建
        check: "stage:0"
  - id: 2
    name: 结构分解（事实）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md"]
      findings_marker: "现象"
    prereqs:
      - desc: 变点事实已知
        check: "stage:1"
    pause_after: true
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

「模型退化了」不是结论，是四个待验证命题的合取：①误差变化**过噪声线**（置换基线 +
稳健性剔尾）；②起始时点答的是 **onset 不是切分点**——最大分离切分点是效应最大化点，
效应渐变（ramp）时它系统性晚于真实起始，置信窗可能整个不含 onset（结论三道门反驳
门 8「渐变-突变混淆」，本 playbook 的头号陷阱：时间结论必须双点齐报）；③变差不是
**构成变化冒充**——季节进入难预测 regime（如高温时段占比上升）会推高误差却不是模型
退化，同类切片内对比才算数；④时点不落在训练截止/上线边界——落在边界 = 可能从来
没准过（分布外），不是"从准变不准"。诱因筛查纪律：点名 ≠ 因果，双关（偏移显著 +
与误差秩相关）只是准入，时点重合才够格进升级判定，诱饵特征不许被冤枉。

## 2. 逐阶段菜谱

### Stage 0 误差序列（口径）
输入：setup 产物的规范长表 predictions.csv（orient 注入 manifest 摘要；
features/train_y 长表若 setup 产了同样直接用）。
菜谱：写 `analysis_scripts/error_series.py`：按口径逐窗算误差 → `error_series.csv`
（window_idx,window_ts,rmse）+ `error_series_summary.json`（schema：
`{"n":int, "caliber":str, "range":[ts,ts], "n_dropped":int, "deploy_ts":str,
"train_cutoff_ts":str, "note":"缺窗不对称说明"}`，自足）。
验证步：合成 3 窗小样跑通，逐窗 RMSE 与手数一致。
done：error_series_summary.json 落盘。

### Stage 1 退化判定与时点（事实）
菜谱：写 `analysis_scripts/changepoint.py`，CLI 契约固定：
`--series error_series.csv --out changepoint_summary.json --seed 0 --n-perm 200`。
三件事缺一不可：①最大分离切分（逐切分点 Welch z，取 |z| 最大）+ **置换基线**
（argmax 型统计量必须过随机基线：固定种子全序打乱 n-perm 次取 null 分布，
p≤0.05 才 significant；种子显式 CLI 并落 JSON）；②**onset 首离判据**：基线段 =
切分点前留 buffer（默认 10 窗）的纯净前段，band = μ+3σ，onset = 首次连续 2 窗
越带；③形态判定：split − onset ≥ 3 窗 → gradual，时间结论**双点齐报**（"效应始于
约 onset，至 split 附近完全显现"）。另算奇偶交错正交重切一致性（interleave）与
剔后段最缓和 3 窗的方向稳定性。产物 schema 见 golden 的 changepoint_summary.json。
**生成闸（硬规则）**：真实数据前先过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/changepoint.py \
  --playbook deployment-drift --stage 1`。
done：changepoint_summary.json 落盘。

### Stage 2 结构分解（事实）
**不写图代码**——frontmatter charts 声明的图全部用 chartbook 预写脚本（engine-core
chartbook 豁免），orient 已按材料标好可画/跳过；命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred <setup>/predictions.csv --out-dir charts/ [各图特有参数]

**chart_sweep 产物 built/linked 时**：重叠图直接复用其 charts/*.json 判读，不重画。

（D 组图加 `--features <setup>/features.csv`；train-test-drift 加
`--train-y <setup>/train_y.csv`。）
判读读各图 JSON 描述符（recipe 判读节），重点：rolling-stability 的时间形态是否与
Stage 1 双点吻合、intraday-profile 的误差时段集中度（退化集中在哪些物理时刻）、
构成对照（同类时段前后段对比，喂反驳门③）。产出 FINDINGS.md 现象清单——只写
「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。
done：charts/*.json 至少一个 + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 3 诱因筛查（变体，material:features 解锁）
菜谱：写 `analysis_scripts/cause_screen.py`，CLI 契约固定：
`--features <setup>/features.csv --series error_series.csv --split <Stage1的split_index>
--out cause_screen.json`。逐窗聚合公式**写在脚本内**（默认逐窗 K 点均值——口径
进闸，不许外置未验证的整形脚本）。每特征：基线段（与误差侧同 buffer）→ 偏移
shift_z 与 Welch p、与误差序列全期秩相关、特征自身 onset（同一首离判据）。
点名双关都命中才 shifted：p<0.01 且 |shift_z|≥3，且 |秩相关|≥0.3。
**生成闸**：`--stage 3` 同上。
done：cause_screen.json 落盘。

### Stage 4 机制归因（变体，material:model_code 解锁）
输入：model_profile 产物（upstream 机制：built/linked 的工作目录下 models.md 的
桥接假设；declined → 本阶段虽解锁也只能停在现象，结论声明缺档案）+ Stage 2/3 产物。
菜谱：逐条桥接假设 → 找它预言的图形态 → 对照实际描述符；按 upgrade_rule 判定
升级。产出写回 FINDINGS.md（状态用保留字）。
done：FINDINGS.md 出现「假设」。

### Stage 5 结论
主 agent 亲自做（subagent_ok: false）。三道门（references/mechanisms.md，尤其
反驳门 8）+ 本 playbook 特有反驳门（§6）逐条过 → 跑 `scripts/provenance.py`
归因闸 → 写 CONCLUSION.md（末尾附 Provenance 块）。

## 3. 证据升级规则

- 现象 → 假设：upgrade_rule（特征 onset 与误差 onset ±7 窗重合 + 方向一致 +
  interleave 正交重切一致）**且**置换基线 significant；
- 假设 → 已证实：仅当机制预言了**未用于生成假设的**新证据且被验证（换窗口重算、
  上游事件记录独立印证、或用户提供外部实验如特征换源重预测）；
- 无 features 材料（诱因线缺席）：单证据线，结论上限「现象」——只能说"误差在
  T₀-T₁ 间抬升"，不得点名诱因。

## 4. 停顿点与汇报

Stage 2 完成即停：向用户汇报 ①退化判定（gap_z、置换 p、稳健性）②时间双点
（onset/split、形态）与训练边界关系 ③已画/跳过图清单 ④Top-3 现象（引图 JSON
数字）。请用户点名：深挖哪条/补哪张图/是否提供运维事件记录或特征数据。用户给
模糊授权按 engine-core 判据（效应量最大且过功效阈值）并记 PROGRESS.md。

## 5. subagent 拆分建议

Stage 2 各图独立可并发：每图一子代理，brief 只带命令模板+长表路径+输出目录
（互不同文件天然防竞态，见 references/subagent-briefs.md）；判读与 FINDINGS 汇总
由主 agent 做。Stage 0/1/3/5 不拆。

## 6. 结论模板与特有反驳门

模板（CONCLUSION.md）：口径与对齐声明 → 退化判定（含置换 p）→ 时间双点与形态 →
结构（时段/单元集中度）→ 诱因归因（层级如实）→ 建议（重训/换源/监控）→
Provenance 块。特有反驳门（写结论前逐条自问并记录）：
- **渐变门**（= 通用反驳门 8 的本 playbook 主刑）：只报了切分点吗？形态判过吗？
  渐变时 onset 单独估了吗？
- **训练边界门**：onset 落在训练截止/上线 ±7 窗内吗？是 → 候选解释改为"分布外
  起点"而非"运行中退化"，措辞必须区分。
- **季节构成门**：难 regime 占比前后段变了吗（intraday/error-breakdown 同类切片
  对比）？没拆分 → 未排除。
- **覆盖对齐门**：前后段缺窗率对称吗？真值口径中途变过吗？
- **上游事件门**：对比窗口内运维/数据源/配置事件核过吗（用户材料或事件记录）？
  没材料 → 显式标"未排除"。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做——无降级路径，说明后终止；
- features 缺：Stage 3 锁死，诱因线缺席，结论上限「现象」（§3），CONCLUSION 显式声明;
- model_code 缺：Stage 4 锁死，机制归因缺席，升级依赖外部证据；
- train_y 缺：train-test-drift 跳过，"世界变了"类候选只剩 y-vs-feature-mapping 的
  期内 split 弱替代；
- training_log / experiment_config / data_profile 缺：只影响旁证与事件核验，缺席记录。

## 8. chartbook 覆盖声明

声明进 Stage 2 charts（时序稳定组）：rolling-stability（时间形态主图）、
intraday-profile（退化的物理时刻集中度）、error-breakdown（前后段构成对照，
喂反驳门③）、train-test-drift（"世界变了"候选）。

跳过（可加画池或复用 chart_sweep 产物）：horizon-degradation /
true-vs-pred-scatter / worst-points——广谱体检切面，体检类 playbook 覆盖；
feature-error-conditional / feature-trend-overlay / y-vs-feature-mapping——
输入侧三件套，Stage 3 诱因筛查有专用脚本 cause_screen.py，图形佐证按需加画；
model-error-correlation / oracle-gap / worst-slice-compare /
cross-dim-stability——需 ≥2 模型，本目标单模型；单模型正交稳定性由 Stage 1
interleave 与口径子段复算承担。
