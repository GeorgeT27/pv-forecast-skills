---
id: model-comparison
name: 多模型对比归因
goal: 量化「模型 A 为什么比 B 好/差」，把差距分解到片段/时效/输入并归因到机制
stages:
  - id: 0
    name: 口径与对齐
    done_when:
      artifacts: ["alignment_report.json"]
    prereqs:
      - desc: 考核口径已定
        check: "question:metric-caliber"
      - desc: 对比模型集已定
        check: "question:model-set"
  - id: 1
    name: 总差距事实
    done_when:
      artifacts: ["gap_summary.json"]
    prereqs:
      - desc: 对齐完成
        check: "stage:0"
  - id: 2
    name: 差距分解（事实）
    done_when:
      artifacts: ["charts/*.json"]
      findings_marker: "现象"
    prereqs:
      - desc: 总差距已知
        check: "stage:1"
    pause_after: true
    charts: [error-breakdown, intraday-profile, worst-points,
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             model-error-correlation, worst-slice-compare, oracle-gap,
             feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, train-test-drift]
  - id: 3
    name: 机制归因（变体）
    done_when:
      findings_marker: "假设"
    prereqs:
      - desc: 模型档案上下文已解决（linked 或 declined）
        check: "config:model_profile_status"
  - id: 4
    name: 结论
    done_when:
      artifacts: ["CONCLUSION.md"]
    subagent_ok: false
    prereqs:
      - desc: 现象清单已停顿汇报
        check: "stage:2"
materials:
  required: [predict, truth]
  optional: [model_code, training_log, experiment_config, features, train_y]
variants:
  - id: mechanism
    when: "material:model_code"
    unlocks_stages: [3]
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_192=每行全部 horizon 点的 RMSE；也可指定子段或自定义）"
    why: "口径不同结论可反转——horizon 交叉存在时尤甚"
    options: ["rmse_192（默认）", "指定 horizon 子段", "自定义公式"]
    default: "rmse_192"
  - id: align-keys
    stage: 0
    ask: "各模型预测按什么键对齐？缺窗如何处理？（默认 window_ts+unit_id 内连接）"
    why: "对齐错位会把数据覆盖差异误判成模型差异"
    options: ["window_ts+unit_id 内连接（默认）", "其他"]
    default: "window_ts+unit_id 内连接"
  - id: model-set
    stage: 0
    ask: "这次对比哪些模型？多于 2 个时，最关注哪一对（如 A vs B）？"
    why: "全集对比与定向配对的分解深度不同；配对决定 Stage 1 的差距检验对象"
    default: null
contexts:
  - id: model-profile
    name: 模型架构档案
    workdir_key: model_profile_dir
    status_key: model_profile_status
    marker_files: ["models.md"]
    on_absent: ask
    provider_skill: pv-model-analysis
    trigger_material: model_code
evidence_lines:
  - id: total-gap
    stage: 1
    output: gap_summary.json
  - id: slice-gap
    stage: 2
    output: charts/worst-slice-compare.json
upgrade_rule: "总差距方向（gap_summary 排名）与主导切片方向（worst-slice 片内排名）一致才把差距结论从「现象」升「假设」"
---

# model-comparison：多模型对比归因

## 1. 问题框定与首要陷阱

「A 比 B 好」不是结论，是三个待验证命题的合取：①在**这个口径**下好（口径换了
可反转——horizon-degradation 的交叉点存在时必须先回 Stage 0 确认口径再比）；
②在**对齐样本**上好（缺窗不对称时，差距可能是覆盖差异——先看 alignment_report
的 dropped 统计）；③好得**稳定**（差距集中在一个月 ≠ 普遍领先——看
worst-slice-compare 的集中度）。首要陷阱：**排名≠机制**——Stage 1/2 全部是事实
阶段，禁机制语言；机制只能在 Stage 3 经模型档案桥接假设 + 图 JSON 证据合流产生。
量纲纪律：点级 pool 口径（error-breakdown/horizon 等）与行 RMSE 均值口径
（rolling-stability/oracle-gap 等）两族数值不可直接比大小，只比走势与排名。

## 2. 逐阶段菜谱

### Stage 0 口径与对齐
输入：materials 盘点后的 predict/truth 原始数据。
菜谱：现场只写薄适配器 `analysis_scripts/adapter.py`（用户格式 → 规范长表
predictions，见 chartbook/_recipe-spec.md §2；有 feature/train_y 材料时同步产
features/train_y 长表），过**对账两关**（行数守恒 + 抽 3 窗数值核对，样例
chartbook/golden/example_adapter/），对账记录写 PROGRESS.md。随后写
`analysis_scripts/align.py`：按 align-keys 答案对齐各模型 → 落
`alignment_report.json`（schema：`{"models":[...], "n_rows_per_model":{},
"n_aligned":int, "n_dropped_per_model":{}, "caliber":"rmse_192|...",
"note":"dropped 不对称时的说明"}`，自足）。
验证步：合成 3 窗小样跑 align.py，n_aligned 与手数一致。
done：alignment_report.json 落盘。

### Stage 1 总差距事实
菜谱：写 `analysis_scripts/gap_metrics.py`，CLI 契约固定：
`--pred predictions.csv --pair A,B --out gap_summary.json`。
计算（口径=rmse_192 时）：每 (model,unit,window) 行 RMSE → 每模型均值与排名；
配对差 d_i = rmse_focal_i − rmse_other_i（对齐行内逐样本）→ mean_diff、
win_rate（d<0 占比）、符号检验正态近似 z=(wins−n/2)/sqrt(n/4) 与双侧 p。
落 `gap_summary.json`（schema：`{"caliber":str, "per_model":{m:mean},
"ranking":[...], "pair":[A,B], "n":int, "mean_diff":float, "win_rate":float,
"sign_z":float, "sign_p":float, "note":"差距是真的还是噪声：|z|<2 时只写现象
不写方向"}`）。
**生成闸（硬规则）**：真实数据前先过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/gap_metrics.py \
  --playbook model-comparison --stage 1`。
验证步：gen_gate 金标准（golden/ 植入已知差距结构）全 expect 通过。
done：gap_summary.json 落盘。

### Stage 2 差距分解（事实）
**不写图代码**——frontmatter charts 声明的图全部用 chartbook 预写脚本
（engine-core chartbook 豁免），orient 已按材料标好可画/跳过；命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred predictions.csv --out-dir charts/ [各图特有参数]

（worst-slice-compare 传 `--focal-model` = model-set 答案里的关注模型；D 组图
加 `--features features.csv`；train-test-drift 加 `--train-y train_y.csv`。）
判读读各图 JSON 的描述符（recipe 判读节），产出 FINDINGS.md 现象清单——
只写「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。
done：charts/*.json 至少一个 + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 3 机制归因（变体，material:model_code 解锁）
输入：model-profile 上下文（contexts 机制：linked 目录下 models.md 的桥接假设
H-ID）+ Stage 2 图 JSON。
菜谱：逐条桥接假设 → 找它预言的图形态（bridge_hooks）→ 对照实际描述符；
两条证据线（total-gap 与 slice-gap）方向一致才把「现象」升「假设」
（upgrade_rule）。产出写回 FINDINGS.md（状态用保留字）。
done：FINDINGS.md 出现「假设」。

### Stage 4 结论
主 agent 亲自做（subagent_ok: false）。三道门（references/mechanisms.md）+
本 playbook 反驳门（§6）逐条过 → 跑 `scripts/provenance.py` 归因闸 → 写
CONCLUSION.md（末尾附 Provenance 块）。

## 3. 证据升级规则

- 现象 → 假设：upgrade_rule（两线方向一致）**且** |sign_z| ≥ 2（差距非噪声）；
- 假设 → 已证实：仅当机制预言了**未用于生成假设的**新图形态且被验证（三道门
  之门 2），或用户提供外部实验（换 checkpoint/换输入重跑）证实；
- 任何一步不满足 → 停在当前层级，结论如实写层级。

## 4. 停顿点与汇报

Stage 2 完成即停：向用户汇报 ①gap_summary 的排名与 z ②已画/跳过图清单
③Top-3 现象（引用图 JSON 数字）。请用户点名：补画哪张图/调参数（top-N、切片
粒度）/指定下一步关注的配对或片段。用户不点名则按 orient 推荐推进。

## 5. subagent 拆分建议

Stage 2 各图独立可并发：每图一子代理，brief 只带命令模板+长表路径+输出目录
（互不同文件天然防竞态，见 references/subagent-briefs.md）；判读与 FINDINGS
汇总由主 agent 做。Stage 0/1/4 不拆。

## 6. 结论模板与特有反驳门

模板（CONCLUSION.md）：口径与对齐声明 → 总差距（含 z）→ 差距结构（集中/普遍，
引 concentration_ratio）→ 机制归因（层级如实）→ 建议（换模/组合/维持，引
oracle-gap）→ Provenance 块。
特有反驳门（写结论前逐条自问并记录）：
- **对齐偏置门**：dropped 不对称吗？只在对齐子集上比较的结论声明了子集吗？
- **口径反转门**：horizon 交叉点存在吗？换口径（子段）后排名保持吗？
- **切片挑拣门**：结论引用的片段是事先声明的（最差片规则）还是事后挑的？
- **同质化门**：模型间误差相关 >0.95 时，「A 略好」的差距有实际意义吗
  （与 sign_z 联判）？

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做——没有降级路径，
  向用户说明后终止；
- model_code 缺：Stage 3 锁死（变体不解锁），结论上限=「假设」，机制归因缺席
  要在 CONCLUSION 显式声明；
- features 缺：D 组三图跳过，输入侧归因缺席（现象清单注明）；
- train_y 缺：train-test-drift 跳过，「世界变了」类候选只能靠
  y-vs-feature-mapping 的期内 split 弱替代；
- training_log / experiment_config 缺：不影响本 playbook 主线（它们只服务
  Stage 3 的旁证），缺席仅记录。
