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

本 playbook 只做一件事：用户指定口径 + setup 长表 → 逐模型指标表 + 指标表 manifest。
**不画图、不做归因、不下任何结论**——数字算出来即终点，那些是下游归因/评估类 playbook
的活。首要陷阱：①**口径必须落 `metrics_summary.json` 的 `caliber` 字段原文**（含取点/
聚合定义，不是口径的别名或简写）——下游核对口径是否匹配，靠逐字对比这个字段，写得含糊
下游就没法安全复用；②**外部脚本先对账**——用户提供外部指标脚本时，首次调用后任选一段
数据自算一遍与脚本输出比对，相对差 <1% 才算理解一致，未过对账不许把脚本结果当数（与
下游归因类 playbook 评估外部脚本时的同一纪律，不重新发明）；③**只算不评**——数字大小、
模型排名好坏一律不解读，哪怕差距很显眼也不写"因此模型 A 更好"这类判断句，解读是下游
归因类 playbook 的职责边界，本 playbook 越界解读即污染下游对"事实 vs 归因"的物理隔离。

## 2. 逐阶段菜谱

### Stage 0 口径确认与计算（主 agent 只做步 1-2，步 3 起 subagent）

输入：setup 产物的规范长表（`<setup>/predictions.csv`，orient 注入的 manifest 摘要给出
位置与模型清单，不再自行摸文件）；`metric-spec` 问题的答案。

菜谱（编号步骤，逐条建 todo）：

1. （主 agent）确认 metric-spec 已答（orient 报 ✗ 先问）；
2. 【硬规则】（主 agent）按 `references/subagent-briefs.md` 的 **Brief-PRODUCER** 派发
   subagent 执行步 3 起的全部菜谱（含 Stage 1），实参：`<ENGINE>`、工作目录、setup 产物
   workdir、metric-spec 答案（外部脚本时含其路径与调用方式）。主 agent 不得自己写
   metrics.py——发现自己在写即本步被跳过，停下补派发；
3. （subagent）按答案选定口径，现场写生成脚本 `analysis_scripts/metrics.py`，CLI 契约固定：
   `--pred <setup>/predictions.csv --caliber <口径答案> --out metrics.csv --summary metrics_summary.json`。
   逐模型按口径计算（默认 rmse_192：每行全部 horizon 点的 RMSE，逐行值再按模型聚合）；若
   答案是用户外部脚本，先对账（见 §1 陷阱②，对账数字随回传交主 agent 记 PROGRESS.md）
   再复用其输出，不重复现写口径逻辑；
4. （subagent）**生成闸（硬规则）**：真实数据前先过
   `python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/metrics.py --playbook metric-eval --stage 0`。

落两个产物：
- `metrics.csv`——逐模型 × 逐单元长表，列：`model,unit_id,window_ts,metric,value`；
- `metrics_summary.json`——自足汇总（**下游只读这个，不重摸 csv**），schema：
  `{"caliber": str（口径定义原文）, "models": {name: value}（逐模型汇总值）,
  "n_rows": int, "window_range": [起, 止]}`。

done：`metrics.csv` + `metrics_summary.json` 落盘。

### Stage 1 产物清单落盘（subagent 承接）

菜谱：（subagent）跑引擎机制脚本（预写，禁现场重写）：

```bash
python3 <ENGINE>/scripts/product_manifest.py --product metric_table \
  --out metric_table_manifest.json \
  --input predictions=<setup workdir>/predictions.csv \
  --input setup_manifest=<setup workdir>/setup_manifest.json
```

done：`metric_table_manifest.json` 落盘。随后主 agent 回父工作目录写
`config.products.metric_table = {workdir, status: "built"}`（subagent 无权写 config）。

## 3. 证据升级规则

无。本 playbook 不产结论——产物即全部输出（这是它与诊断类 playbook 的边界）。

## 4. 停顿点与汇报

无 pause_after 阶段。产物就绪后一句话汇报：口径原文/模型清单与各自汇总值/n_rows/窗口
范围，然后把控制权还给发起的下游 playbook（或用户）。消费者是用户本人时，主 agent 可读
`metrics_summary.json` 补充细节（读落盘产物，不让 subagent 多回话）。

## 5. subagent 拆分建议

**整体外包（硬规则）**：本 playbook 满足 Brief-PRODUCER 三条件（produces + 无结论
阶段 + 执行段无用户裁决/FINDINGS 写入），Stage 0 步 3 起连同 Stage 1 整体交一个
subagent 串行执行（两阶段轻且串行，不再细拆）；模板与派发纪律见
`references/subagent-briefs.md` Brief-PRODUCER。提问（metric-spec）、PROGRESS 记录、
config.products 回填只在主 agent。

## 6. 结论模板与反驳门

不适用（无结论阶段）。唯一自查：口径答案是否已逐字写入 `metrics_summary.json.caliber`——
写得含糊等于没写，下游口径核对会因此失效。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做——没有降级路径，setup
  产物本身也建不起来，向用户说明后终止。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 charts（产数字产物，不画图）：全部 28 个 recipe 跳过，理由统一为
「结构性不适用——本 playbook 只算指标不画图，图属于下游归因/评估类 playbook」。
