---
id: fact-scan
name: 图谱体检（只看现象不下结论）
goal: 把手头材料能画的标准分析图一次画全，产出现象清单与 chart_sweep 产物——终点即停顿，不进任何归因
produces:
  id: chart_sweep
  manifest: chart_sweep_manifest.json
  marker_files: [INDEX.md, FINDINGS.md]
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 画图与现象清单（终点）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md", "chart_sweep_manifest.json"]
      findings_marker: "现象"
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
    pause_after: true
    subagent_ok: true
    charts: [error-breakdown, intraday-profile, worst-points,
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             model-error-correlation, worst-slice-compare, oracle-gap,
             feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, train-test-drift]
materials:
  required: [predict, truth]
  optional: [features, train_y]
---

# fact-scan：图谱体检

## 1. 问题框定与首要陷阱

使用场景：用户只想"把图都画出来看一遍"，不要诊断。本 playbook **没有结论阶段**：产出止步于现象清单。FINDINGS.md 里只允许「现象」状态，禁一切机制语言——"因为/导致/说明模型…"这类解释性说法都不许出现。

首要陷阱：把体检写成诊断。发现值得注意的形态，只登记，不解释；用户想深挖时，回到技能入口的路由层重新描述目标，已产出的现象清单、图 JSON、materials 盘点结果全部复用。

本 playbook 的图产物（charts/*.json + INDEX.md + 现象清单）合起来就是 chart_sweep 产物。下游 playbook 把 chart_sweep 声明为可选上游时，重叠的图直接复用这里的判读，不重画。

## 2. 逐阶段菜谱

### Stage 0 画图与现象清单（终点）

输入：setup 产物，位置在 config.products.setup.workdir 下，包括 predictions.csv 等长表和 setup_manifest.json。模型数、freq 从 manifest 里读，不再问用户。所有图命令的 --pred 参数一律指向 <setup_workdir>/predictions.csv。

步骤：
- orient 已按材料与模型数标好"可画集"。
- 逐图跑 chartbook 的预写脚本，命令模板与 chartbook 各 recipe 的 CLI 节相同；产物写进 `charts/`。
- 对比类图在单模型数据上会抛 ValueError——捕获它，在清单里记「因模型数 <2 未画」，这不算失败。
- 判读每张图 JSON 里的描述符，写成 FINDINGS.md 现象清单。每条的格式：图 id + 描述符数字 + 一句现象陈述，禁机制词。
- 跳过的图逐条注明原因（缺材料 / 模型数不够）。
- 画完、建好索引后，跑：

```
python3 <ENGINE>/scripts/product_manifest.py --product chart_sweep \
  --out chart_sweep_manifest.json \
  --input setup_manifest=<setup 产物 workdir>/setup_manifest.json
```

- 随后主 agent 写 `config.products.chart_sweep = {workdir: ".", status: "built"}`。本 playbook 直接在自己的工作目录里产出。setup 产物重建后，chart_sweep 会因 manifest 里的 setup 指纹不匹配自动判 stale。

done：charts/*.json ≥1 + FINDINGS.md 含「现象」→ 停顿汇报，**流程终点**。

## 3. 证据升级规则

无。本 playbook 不做证据升级——「现象」就是产出的上限。

## 4. 停顿点与汇报

终点停顿，向用户交付三样东西：①已画/跳过清单（跳过的带原因）；②按图分组的现象清单；③一句提示："想深挖哪条现象，请回到技能入口重新描述目标"（材料盘点与图产物会自动复用）。

## 5. subagent 拆分建议

各图相互独立，可以并发：每图一个子代理，各写各的输出文件，互不冲突。FINDINGS 的汇总由主 agent 做。

## 6. 结论模板与反驳门

不适用——本 playbook 没有结论阶段。唯一自查：FINDINGS.md 里出现机制语言 = 越界，删改干净后再交付。

## 7. 材料降级说明

- predict/truth 缺：setup 产物本身建不起来，本 playbook 连带不可做。
- features 缺：依赖输入特征的三张关联图跳过。
- train_y 缺：漂移图跳过。
- 通用规则：跳过永远注明原因，永远不算失败——体检报告如实写"未查项"即可。
