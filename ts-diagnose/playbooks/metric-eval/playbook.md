---
id: metric-eval
name: 指标计算（只算不评）
goal: 按用户指定口径从 setup 长表算逐模型指标表，产 metric_table 产物——终点即数字，不画图不归因不下结论
produces:
  id: metric_table
  manifest: metric_table_manifest.json
  marker_files: [metrics.csv, metrics_summary.json]
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 口径确认与计算
    done_when:
      artifacts: [metrics.csv, metrics_summary.json]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 指标口径已确认
        check: "question:metric-spec"
  - id: 1
    name: 产物清单落盘
    done_when:
      artifacts: [metric_table_manifest.json]
    prereqs:
      - desc: 指标表就绪
        check: "stage:0"
materials:
  required: [predict, truth]
questions:
  - id: metric-spec
    stage: 0
    ask: "要算什么指标？（可多选；默认 rmse_192=每行全部 horizon 点的 RMSE；外部脚本则给路径与调用方式）"
    why: "口径是本 playbook 的全部语义——猜口径等于白算"
    options: ["rmse_192（默认）", "指定 horizon 子段 RMSE", "MAE/ACC 等其他标准指标", "用户外部指标脚本（给路径）"]
    default: null
---

# metric-eval：指标计算（只算不评）

## 1. 问题框定与首要陷阱

本 playbook 只做一件事：拿用户指定的指标口径，加上上游 setup 产物里的规范长表，
算出逐模型的指标表，并落一份指标表 manifest。
**不画图、不做归因、不下任何结论。** 数字算出来即终点；解读数字是下游归因/评估类
playbook 的活。

三个首要陷阱：

① **口径必须逐字落进 `metrics_summary.json` 的 `caliber` 字段**。写口径定义的原文，
含取点方式与聚合方式；不许写口径的别名或简写（下游靠逐字对比这个字段核对口径）。

② **外部脚本先对账**。用户提供自己的指标脚本时，首次调用后任选一段数据，按自己对
口径的理解自算一遍，与脚本输出比对；相对差 <1% 才算通过。对账没过，不许把脚本结果
当数。

③ **只算不评**。数字大小、模型排名好坏，一律不解读；哪怕差距很显眼，也不写
"因此模型 A 更好"这类判断句。

## 2. 逐阶段菜谱

### Stage 0 口径确认与计算（主 agent 只做步 1-2，步 3 起 subagent）

输入：

- setup 产物的规范长表 `<setup>/predictions.csv`。位置与模型清单由 orient 注入的
  manifest 摘要给出，不许自己摸文件去找；
- `metric-spec` 问题的答案。

菜谱（编号步骤，逐条建 todo）：

1. （主 agent）确认 metric-spec 已有答案。orient 报 ✗ 时，先向用户提问，再继续；
2. 【硬规则】（主 agent）按 `references/subagent-briefs.md` 里的 **Brief-PRODUCER**
   模板派发一个 subagent，由它执行步 3 起的全部菜谱（含 Stage 1）。派发时传实参：
   `<ENGINE>`、工作目录、setup 产物的 workdir、metric-spec 的答案（答案是外部脚本时，
   一并传脚本路径与调用方式）。主 agent 不得自己写 metrics.py；发现自己在写，
   就说明本步被跳过了，停下补派发；
3. （subagent）按答案选定口径，现场写生成脚本 `analysis_scripts/metrics.py`，
   CLI 契约固定：
   `--pred <setup>/predictions.csv --caliber <口径答案> --out metrics.csv --summary metrics_summary.json`。
   逐模型按口径计算。默认口径 rmse_192：每行取全部 horizon 点算一个 RMSE，
   逐行值再按模型聚合。答案是用户外部脚本时：先按 §1 陷阱② 对账，对账数字随
   回传交主 agent 记 PROGRESS.md；对账通过后复用脚本的输出，不再重写口径逻辑；
4. （subagent）**生成闸（硬规则）**：碰真实数据之前，脚本必须先通过
   `python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/metrics.py --playbook metric-eval --stage 0`。

落两个产物：
- `metrics.csv`——逐模型 × 逐单元长表，列：`model,unit_id,window_ts,metric,value`；
- `metrics_summary.json`——自足的汇总文件（**下游只读这个，不重摸 csv**），schema：
  `{"caliber": str（口径定义原文）, "models": {name: value}（逐模型汇总值）,
  "n_rows": int, "window_range": [起, 止]}`。

done：`metrics.csv` + `metrics_summary.json` 落盘。

### Stage 1 产物清单落盘（subagent 承接）

菜谱：（subagent）跑引擎预写的机制脚本，禁止现场重写：

```bash
python3 <ENGINE>/scripts/product_manifest.py --product metric_table \
  --out metric_table_manifest.json \
  --input predictions=<setup workdir>/predictions.csv \
  --input setup_manifest=<setup workdir>/setup_manifest.json
```

done：`metric_table_manifest.json` 落盘。随后主 agent 回到父工作目录，写
`config.products.metric_table = {workdir, status: "built"}`。这一步必须由主 agent
做——subagent 无权写 config。

## 3. 证据升级规则

无。本 playbook 不产结论，产物文件就是全部输出。

## 4. 停顿点与汇报

本 playbook 没有 pause_after 阶段。产物就绪后，用一句话汇报：口径原文、模型清单与
各自汇总值、n_rows、窗口范围。汇报完，把控制权还给发起本 playbook 的下游 playbook
（或用户）。若消费者是用户本人，主 agent 可读 `metrics_summary.json` 补充细节；
细节从落盘产物里读，不让 subagent 额外多回话。

## 5. subagent 拆分建议

**整体外包（硬规则）**：Stage 0 的步 3 起连同 Stage 1，整体交给同一个 subagent
串行执行，不再细拆。模板与派发纪律见 `references/subagent-briefs.md` 的
Brief-PRODUCER。只能由主 agent 做的三件事：向用户提问（metric-spec）、
记录 PROGRESS、回填 config.products。

## 6. 结论模板与反驳门

不适用——本 playbook 没有结论阶段。唯一自查：口径答案是否已逐字写入
`metrics_summary.json.caliber`；写得含糊等于没写。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 做不了，没有降级路径——
  连 setup 产物也建不起来。向用户说明后终止。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 charts：它产数字产物，不画图。chartbook 共 28 个 recipe
全部跳过，理由统一为「结构性不适用——本 playbook 只算指标不画图，图属于下游
归因/评估类 playbook」。
