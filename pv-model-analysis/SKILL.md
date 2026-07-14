---
name: pv-model-analysis
description: 给定光伏功率预测项目的模型代码目录，生成「代码锚定」的模型参考文档——每个模型（M1-M4 + ensemble + Chronos）的工程流程图（I/O 维度、模块、损失）、逐方法数学分析、以及「架构→结果分析含义」桥接假设，产物同时供人阅读与供 pv-result-analysis 机制归因消费。当用户给出模型代码仓库/目录路径，要求"分析模型/生成模型档案/核验模型描述是否与代码一致/在代码库里找 M1-M4/为结果分析准备模型参考"时，务必使用本技能。既能从零生成，也能对已有产物按代码增量核验（reconcile）。路由优先级：本技能是专用技能，在上述场景内优先于泛化引擎 ts-diagnose，但让位于覆盖同场景的已固化代理技能。
---

# 模型代码 → 模型参考文档（供人 + 供 pv-result-analysis）

给定模型代码目录，生成 `<repo>/.modelmap/` 文档集并写 pointer。既能从零生成，也能对已有产物
按代码增量核验（reconcile）。纪律与产物格式见 `references/`。

产物固定位置：`<repo>/.modelmap/`；pointer 固定路径见 `references/output-spec.md`。

## Step 0：定位模型（先问后花）
按 `references/models-template.md` 的「定位速查表」grep 类名定位 M1-M4 + Chronos 用法 +
ensemble 组合器；类名搬走了用架构签名兜底。确认 类名→M-id 映射。多候选版本（实验副本/旧文件）
→ 列候选请用户确认哪个是产线，绝不自行裁决。某模型定位不到 → 报"未找到"，该节留空，不硬套。

## Step 1：（可选）数据画像
用户给了数据样本 → 跑 `scripts/profile_data.py` 落 `data-profile.md`，把"为什么"从 📐 升 📊；
没给则静默跳过。

## Step 2：逐模型抽取（一模型一子代理，写完即忘；无子代理则串行）
每个模型产出三层（纪律见 `references/machinery.md`）：
- 工程（✅ `file:line`）：输入通道与维度、切 patch、模块、**读实际代码的损失**、训练窗口。
- 数学（📐）：每个方法（Fourier tokenizer、MoBA、RevIN、pinball≡4.5·MAE、MSE+rfft、Moirai…）。
- 桥接（架构→结果分析含义）：架构事实 → 预期误差形态 → 哪张图检验 → H-ID。桥接须遵
  `references/cross-skill-contract.md`（读 hypotheses.md + 图谱目录，H-ID 写回登记）。
核验优先级：损失函数 > 输入特征 > 训练窗口 > 其余结构。

## Step 3：Reconcile（统一核验流）
已有 `.modelmap/` 且仓库未变（commit 命中）→ 复用；变了 → 重抽取、与旧产物 diff，改动条目带
日期锚 `【代码核验 YYYY-MM-DD，来源 file:line】`；**前提被推翻的桥接假设必须重推**（不留半新半旧）。

## Step 4：落盘 + 写 pointer
按 `references/output-spec.md` 写 `.modelmap/` 全套（models.md 结构照 `references/models-template.md`）；
用 `scripts/pointer.py` 的 `write_pointer` 写 pointer（commit 取 `git -C <repo> rev-parse HEAD`，
无 git 用 `no-git`）。

## Step 5：自检（强制）
跑 `references/machinery.md` 第 5 节：落盘后置条件 + 锚点抽查 + 链接 + 覆盖 + 无裸断言，
末尾给自检报告。

## 纪律
- 证据强度：代码 > 推导 > 空白；多版本"哪个是产线"由用户定。
- "代码里没找到" ≠ "不存在"——未找到留空，不编造。
- 每处结论带置信标签 + `file:line`；未知永远显式。
- 产出后 `.modelmap/` 三层（事实 / 待确认 / 桥接假设）必须自洽。
