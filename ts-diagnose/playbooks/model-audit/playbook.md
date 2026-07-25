---
id: model-audit
name: 模型代码审计（生成 .modelmap 档案）
goal: 把模型代码目录固化为「代码锚定」的模型参考档案（.modelmap/ + 工作目录回执），供其他 playbook 机制归因消费
produces:
  id: model_profile
  manifest: MODELMAP_RECEIPT.json
  marker_files: [MODELMAP_RECEIPT.json]
materials:
  required: [model_code]
  optional: [train_y, experiment_config, data_profile]
stages:
  - id: 0
    name: 定位模型（先问后花）
    done_when: {manual: true}
  - id: 1
    name: 数据画像（可选）
    done_when: {artifacts: ["data-profile-receipt.json"]}
  - id: 2
    name: 逐模型三层抽取（工程/数学/桥接）
    done_when: {manual: true}
    prereqs:
      - desc: 模型清单已与用户确认
        check: "stage:0"
  - id: 3
    name: reconcile + 落盘 + 回执
    done_when: {artifacts: ["MODELMAP_RECEIPT.json"]}
    prereqs:
      - desc: 抽取完成
        check: "stage:2"
  - id: 4
    name: 自检（machinery §5）
    done_when: {artifacts: ["AUDIT_SELFCHECK.md"]}
    subagent_ok: false
    prereqs:
      - desc: 已落盘
        check: "stage:3"
variants:
  - id: data-profile
    when: "material:train_y"
    unlocks_stages: [1]
questions:
  - id: production-version
    stage: 0
    ask: "代码里发现多个候选版本/副本时，哪个是产线版本？（绝不自行裁决）"
    why: "分析错版本 = 整套档案作废"
    default: null
---

# model-audit：模型代码 → 模型参考文档（供人 + 供其他 playbook 机制归因消费）

给定模型代码目录，生成 `<repo>/.modelmap/` 文档集并写 pointer + 工作目录回执。既能从零生成，
也能对已有产物按代码增量核验（reconcile）。纪律与产物格式见 `references/`。

产物固定位置：`<repo>/.modelmap/`；pointer 固定路径见 `references/output-spec.md`。作为分层机制的生产者，本 playbook 的产物注册名为 model_profile（manifest = 工作目录回执 MODELMAP_RECEIPT.json；回执不含 inputs 指纹，产物过期检测对它空转——代码变更后的重审计时机由用户判断）。

## 1. 问题框定与首要陷阱

本 playbook 最容易犯的错误不是"漏抽取"，而是**分析错版本**——代码库里常见同一模型的
多个候选副本（实验分支、旧版遗留、重构中间态），选错一个，整套档案连带下游桥接假设
全部作废且不易察觉（表面看仍"言之有理"）。首要纪律：定位阶段发现多候选，**必须**先问
用户哪个是产线版本，绝不自行裁决（见 questions.production-version）。第二陷阱：把
"代码里没找到" 当成 "不存在"——找不到就留空 + ⚠️，不编造去凑完整性。第三陷阱：叙事
优先于证据——不能为了让桥接假设听起来合理而编无代码支撑的"为什么"，无支撑的推导只能标
📐（且须写清前提）或 ⚠️，不能标 ✅。

## 2. 逐阶段菜谱

### Stage 0：定位模型（先问后花）

输入：模型代码目录路径 + 模型清单来自 intake 问答或 project-context 实验线（不是硬编码的
产线专名列表——每次进入本 playbook 先从 intake 材料盘点或 project-context 里取实际要审计
的模型集合）。

菜谱：按 `references/models-template.md` 的「定位速查表」grep 已知类名定位各模型的用法 +
ensemble 组合器（若适用）；类名搬走了用架构签名兜底（模块名/关键词组合，速查表给了模板，
实际项目按其代码库信息更新）。确认「类名 → 模型 ID」映射。多候选版本（实验副本/旧文件）→
列候选请用户确认哪个是产线（`production-version` 问题），绝不自行裁决。某模型定位不到 →
报「未找到」，该节留空，不硬套。

done：模型清单（含类名映射与候选裁决）已与用户确认（manual 判定）。

### Stage 1：（可选）数据画像

输入：`train_y`（或等价数据样本）material 是否 present。

菜谱：用户给了数据样本（`material:train_y` 为 present，即 variant `data-profile` 激活）→
跑 `scripts/profile_data.py` 落 `data-profile.md`，把模型档案里"为什么"的证据强度从 📐
升到 📊；跑完写回执 `data-profile-receipt.json`（内容
`{"profile_md": <profile_data.md 的路径>, "date": <ISO 日期>}`）。没给数据样本则本阶段
静默跳过（variant 未激活，不阻塞）。

done：`data-profile-receipt.json` 落盘（跳过时视为该 done_when 不适用，orient 按 variant
未激活处理，不阻塞后续阶段）。

### Stage 2：逐模型三层抽取（一模型一子代理，写完即忘；无子代理则串行）

输入：Stage 0 确认的模型清单与类名映射。

菜谱：每个模型产出三层（抽取纪律见 `references/machinery.md`）：
- **工程**（✅ `file:line`）：输入通道与维度、切 patch、模块、**读实际代码的损失**、训练窗口。
- **数学**（📐）：逐方法的数学分析（tokenizer/归一化/正则化/损失形式等——具体方法名从代码
  读出，不预设产线用了哪些技法）。
- **桥接**（架构 → 结果分析含义）：架构事实 → 预期误差形态 → 哪张图检验 → H-ID。桥接须遵
  `references/cross-skill-contract.md`（读消费端 hypotheses.md + 图谱目录，H-ID 写回登记）。

核验优先级：损失函数 > 输入特征 > 训练窗口 > 其余结构。上下文策略见
`references/machinery.md` §4——逐模型串行 + 立即落盘断点续跑，一模型一子代理并行时父代理
只持有小账本汇总。

done：manual 判定（三层抽取对每个已确认模型都完成或显式标注"未找到"）。

### Stage 3：Reconcile + 落盘 + 回执（统一核验流）

输入：Stage 2 的逐模型三层产出；若已有 `.modelmap/`，还需当前仓库 commit。

菜谱：已有 `.modelmap/` 且仓库未变（commit 命中）→ 复用；变了 → 重抽取、与旧产物 diff，
改动条目带日期锚 `【代码核验 YYYY-MM-DD，来源 file:line】`；**前提被推翻的桥接假设必须
重推**（不留半新半旧）。

落盘按 `references/output-spec.md` 写 `.modelmap/` 全套（`models.md` 结构照
`references/models-template.md`）。随后**回执纪律**（见下）：调用
`scripts/pointer.py` 的 `write_pointer`（commit 取 `git -C <repo> rev-parse HEAD`，无 git
用 `no-git`）**并**在诊断工作目录调 `pointer.write_receipt(modelmap_dir, commit)` 写
`MODELMAP_RECEIPT.json`——两步缺一不可，回执是本阶段完成的产物判据。

done：`MODELMAP_RECEIPT.json` 落盘。

### Stage 4：自检（强制，主 agent 亲自做）

输入：Stage 3 落盘的 `.modelmap/` 全套。

菜谱：跑 `references/machinery.md` 第 5 节的自检清单：
- 落盘后置条件：预期文件确实存在（见 `output-spec.md` 清单）。
- 锚点抽查：抽 ✅ 断言，打开引用的 `file:line`，确认确实那么说；不符→降级 ⚠️ 并记
  `open-questions.md`。
- 链接完整：交叉引用条目都能解析。
- 覆盖：模型找到数 vs 建档数；未触达的模型列出（不留静默缺口）。
- 无裸断言：每条非平凡陈述都带置信标签，✅/📊 带锚。

产出 `AUDIT_SELFCHECK.md`（抽查结果/通过率/降级条目/覆盖率的简短报告）。

done：`AUDIT_SELFCHECK.md` 落盘（`subagent_ok: false`——自检必须主 agent 亲自做，不得
外包给子代理，防止"自己抽取、自己自检"的一致性偏差）。

## 3. 证据升级规则

本 playbook 不产出"现象/假设"型结论（它产出的是参考档案，供其他 playbook 消费时再升级
证据等级），因此没有独立的 evidence_lines/upgrade_rule。档案内部证据强度用置信标签体系
（`references/machinery.md` §1：✅ 代码已证 > 📊 数据实测 > 📐 理论推导 > ⚠️ 未证/推断），
标签本身即是"升级规则"——下游 playbook 引用桥接假设时，只有 ✅/📊 支撑的部分可直接作为
归因证据，📐/⚠️ 部分只能作为待验证的假设起点。

## 4. 停顿点与汇报

Stage 0 完成（模型清单与候选裁决确认）后若存在多候选/找不到的模型，需向用户简短汇报再
继续；Stage 4 自检完成后向用户汇报：①覆盖率（找到数/建档数）②降级条目数（✅ 降为 ⚠️
的断言）③未触达模型清单（如有）。无强制 `pause_after`（本 playbook 通常作为其他
playbook 的嵌入上下文供应者运行，停顿由调用方决定），但产出后必须让主 agent 或调用方
知晓自检结果，不能静默收尾。

## 5. subagent 拆分建议

Stage 2 逐模型抽取天然可并发：每个模型一子代理，brief 只带该模型的类名/候选文件路径 +
输出目标节（写完即忘，防止上下文膨胀），互不同文件天然防竞态。Stage 0/1/3/4 不拆——
Stage 0 的多候选裁决、Stage 3 的 reconcile diff、Stage 4 的自检都需要跨模型的全局视角，
拆了反而破坏一致性判断。

## 6. 材料降级说明

- `model_code` 缺（absent-confirmed）：本 playbook 不可做——没有降级路径，代码是唯一
  证据来源，向用户说明后终止；
- `train_y` 缺：Stage 1 数据画像跳过（variant 未激活），models.md 里"为什么"类断言的
  证据强度上限为 📐（无法用 📊 数据实测支撑）；
- `experiment_config` 缺：不影响主线产出，仅在训练窗口/超参核验时少一路交叉验证来源，
  缺席记 `open-questions.md`；
- `data_profile`（若已有现成画像文件而非原始样本）缺：等同 `train_y` 缺的降级路径，
  跳过 Stage 1 重新生成，若有现成 `data-profile.md` 可直接引用并跳过重跑。

## 7. 回执纪律

Stage 3 落盘 `.modelmap/` 后必须调 `python3 <本目录>/scripts/pointer.py` 对应的
`write_pointer` 流程（原 write_pointer 流程，pointer 路径固定见
`references/output-spec.md`）**并**在诊断工作目录调
`pointer.write_receipt(modelmap_dir, commit)` 写 `MODELMAP_RECEIPT.json`——orient 用它
判定 model-audit 阶段是否完成、以及档案相对当前代码 commit 是否新鲜（`is_stale` 比对
`MODELMAP_RECEIPT.json`/pointer 的 commit 与 `git -C <repo> rev-parse HEAD`）。

Stage 1 跑 `scripts/profile_data.py` 后写 `data-profile-receipt.json`（内容
`{"profile_md": <路径>, "date": <ISO 日期>}`），供 orient 判定 Stage 1 完成，不必等到
Stage 3 才落盘。

两处回执都是**阶段闸的产物判据**（`done_when.artifacts`）——只写文档不写回执，orient
视为阶段未完成，会重复提示"数据画像/建档未完成"。

## 8. 纪律（总纲，援引 `references/machinery.md`）

- 证据强度：代码 > 推导 > 空白；多版本"哪个是产线"由用户定（不由 agent 猜）。
- "代码里没找到" ≠ "不存在"——未找到留空，不编造。
- 每处结论带置信标签 + `file:line`；未知永远显式。
- 产出后 `.modelmap/` 三层（事实 / 待确认 / 桥接假设）必须自洽。
- 桥接假设对接消费方的契约见 `references/cross-skill-contract.md`：H-ID 命名与登记、
  读入哪些文件、接口面只通过 pointer / H-ID 登记表 / 图谱目录三样耦合，模型事实不跨
  技能复制粘贴。
