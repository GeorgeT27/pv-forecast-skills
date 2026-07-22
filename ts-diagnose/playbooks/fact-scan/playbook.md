---
id: fact-scan
name: 图谱体检（只看现象不下结论）
goal: 把手头材料能画的标准分析图一次画全，产出现象清单——终点即停顿，不进任何归因
stages:
  - id: 0
    name: 口径与对齐
    done_when:
      artifacts: ["alignment_report.json"]
    prereqs:
      - desc: 步长/口径已确认
        check: "question:scan-caliber"
  - id: 1
    name: 画图与现象清单（终点）
    done_when:
      artifacts: ["charts/*.json"]
      findings_marker: "现象"
    prereqs:
      - desc: 对齐完成
        check: "stage:0"
    pause_after: true
    charts: [error-breakdown, intraday-profile, worst-points,
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             model-error-correlation, worst-slice-compare, oracle-gap,
             feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, train-test-drift]
materials:
  required: [predict, truth]
  optional: [features, train_y]
questions:
  - id: scan-caliber
    stage: 0
    ask: "horizon 步长（freq）是多少？单模型还是多模型？（对比类图需 ≥2 模型）"
    why: "freq 错则 hour/tod 维度全错；模型数决定哪些图可画"
    default: null
---

# fact-scan：图谱体检

## 1. 问题框定与首要陷阱

用户只要"看一遍"，不要诊断。本 playbook **没有结论阶段**：产出止于现象清单，
FINDINGS.md 只许「现象」状态、禁一切机制语言（"因为/导致/说明模型…"都不许出现）。
首要陷阱：把体检写成诊断——发现的形态只登记，归因走别的 playbook（用户想深挖时
回路由层重新选择；本清单与图 JSON 全部可复用，materials 盘点结果同样复用）。

## 2. 逐阶段菜谱

### Stage 0 口径与对齐
同标准 intake：薄适配器 → 规范长表 → 对账两关（样例
chartbook/golden/example_adapter/）→ `alignment_report.json`
（schema：`{"models":[...], "n_rows":int, "freq":str}`）。单模型数据合法
（对比类图会自动因 <2 模型不可画，跳过即可，不算失败）。

### Stage 1 画图与现象清单（终点）
orient 已按材料/模型数标好可画集；逐图跑 chartbook 预写脚本（命令模板同
chartbook 各 recipe 的 CLI 节），产物进 `charts/`。对比类图在单模型数据上会
抛 ValueError——捕获后在清单记「因模型数 <2 未画」，不算失败。
判读各图 JSON 描述符 → FINDINGS.md 现象清单（每条：图 id + 描述符数字 + 一句
现象陈述，禁机制词）。跳过的图逐条注明原因（缺材料/模型数）。
done：charts/*.json ≥1 + FINDINGS.md 含「现象」→ 停顿汇报，**流程终点**。

## 3. 证据升级规则

无。本 playbook 不升级——现象即产出上限（这正是它与诊断类 playbook 的边界）。

## 4. 停顿点与汇报

终点停顿：向用户交付 ①已画/跳过清单（含原因）②按图分组的现象清单 ③提示
"想深挖哪条现象，请回到技能入口重新描述目标"（材料盘点与图产物自动复用）。

## 5. subagent 拆分建议

各图独立可并发（每图一子代理，互不同输出文件）；FINDINGS 汇总主 agent 做。

## 6. 结论模板与反驳门

不适用（无结论阶段）。唯一自查：FINDINGS.md 里出现机制语言 = 越界，删改后再交付。

## 7. 材料降级说明

predict/truth 缺 → 不可做；features 缺 → 输入关联三图跳过；train_y 缺 → 漂移图
跳过。跳过永远注明、永远不算失败——体检报告如实写"未查项"。
