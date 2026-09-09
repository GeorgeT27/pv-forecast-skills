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

给定一个模型代码目录，读代码，生成一套「代码锚定」的模型参考档案：档案里每条关键断言
都指向具体代码位置（`file:line`），不凭印象写。档案落在 `<repo>/.modelmap/`，同时写
一个 pointer（固定路径见 `references/output-spec.md`）和一个工作目录回执。档案可从零
生成；`.modelmap/` 已存在时对照当前代码做增量核验（reconcile）。抽取纪律与产物格式见
`references/` 目录。

本 playbook 是分层机制的生产者，产物注册名 model_profile，manifest 就是工作目录回执
MODELMAP_RECEIPT.json。这份回执不含 inputs 指纹，引擎的"产物过期自动检测"对它不起
作用——代码变更之后要不要重新审计，由用户自己判断。

## 1. 问题框定与首要陷阱

本 playbook 最容易犯的错误不是"漏抽取"，而是**分析错版本**：代码库里常见同一个模型
有多个副本（实验分支、旧版遗留、重构中间态），选错一个，整套档案连带下游桥接假设
（见 Stage 2）全部作废，且不易察觉。三条对应纪律：

1. **版本由用户定**：定位阶段发现多个候选版本时，**必须**先问用户哪个是产线版本，
   绝不自行裁决。对应 frontmatter 的 questions.production-version。
2. **找不到 ≠ 不存在**：代码里没找到某个东西，只说明没找到。对应字段留空并标 ⚠️
   （标签定义见 `references/machinery.md`），不许编造内容去凑完整性。
3. **证据优先于叙事**：不能为了让桥接假设听起来合理，编一个没有代码支撑的"为什么"。
   无支撑的推导只能标 📐（且必须写清前提）或 ⚠️，不能标 ✅。

## 2. 逐阶段菜谱

### Stage 0：定位模型（先问后花）

输入：模型代码目录路径，加上一份模型清单。清单来自 intake 问答或 project-context
实验线，**不是**硬编码的产线专名列表——每次进入本 playbook，都要先从这两处取实际要
审计的模型集合。

菜谱：按 `references/models-template.md` 的「定位速查表」，用 grep 搜已知类名，定位
每个模型的代码位置，有 ensemble 时把组合器代码也定位到；类名被改名或搬走时，用架构
签名兜底（按模块名、关键词组合去搜，速查表给了模板，实际项目按它自己代码库的信息
更新）；确认「类名 → 模型 ID」映射。发现多个候选版本（实验副本、旧文件）→ 列出候选，
请用户确认哪个是产线（问 `production-version`），绝不自行裁决。某个模型定位不到 →
如实报「未找到」，该节留空，不硬套。

done：模型清单（含类名映射与候选裁决）已与用户确认，人工判定（manual）——本阶段没有产物判据，确认完把 `0` 追加进 `diagnose_state.json` 的 `manual_done` 数组，orient 才判它完成。

### Stage 1：（可选）数据画像

输入：material `train_y`（训练标签数据，或等价的数据样本）是否 present。

菜谱：`material:train_y` 为 present（variant `data-profile` 激活）→ 跑
`scripts/profile_data.py`，产出 `data-profile.md`，把模型档案里"为什么"类断言的证据
强度从 📐 升到 📊；跑完立即写回执 `data-profile-receipt.json`，内容为
`{"profile_md": <profile_data.md 的路径>, "date": <ISO 日期>}`。用户没给数据样本 →
本阶段静默跳过（variant 未激活，不阻塞后续）。

done：`data-profile-receipt.json` 落盘（跳过时该 done_when 不适用，orient 按 variant
未激活处理）。

### Stage 2：逐模型三层抽取（一模型一子代理，写完即忘；无子代理则串行）

输入：Stage 0 确认的模型清单与类名映射。

菜谱：对每个模型产出三层内容（抽取纪律见 `references/machinery.md`）：
- **工程层**（标 ✅，带 `file:line`）：输入通道与维度、切 patch 的方式、模块构成、
  损失函数（**必须读实际代码，不能只看注释或函数名**）、训练窗口。
- **数学层**（标 📐）：逐方法的数学分析——tokenizer、归一化、正则化、损失形式等。
  具体用了哪些方法要从代码里读出来，不预设产线用了哪些技法。
- **桥接层**（架构 → 结果分析含义）：把架构事实翻译成对结果分析的预期，链条是：
  架构事实 → 预期误差形态 → 哪张图能检验 → H-ID（桥接假设编号，供下游引用）。桥接
  必须遵守 `references/cross-skill-contract.md` 的契约（H-ID 写工作目录的 `references/hypotheses.md`，引擎包那份只读）：读消费端的 hypotheses.md 与
  图谱目录，H-ID 写回登记表。

核验的优先级排序：损失函数 > 输入特征 > 训练窗口 > 其余结构。上下文策略见
`references/machinery.md` §4：逐模型串行处理、写完立即落盘、支持断点续跑；一模型
一子代理并行时，父代理只保留一份小账本做汇总。

done：人工判定（manual）——每个已确认的模型，三层抽取要么完成，要么显式标注"未找到"；本阶段没有产物判据，抽取完把 `2` 追加进 `diagnose_state.json` 的 `manual_done` 数组，orient 才判它完成。

### Stage 3：Reconcile + 落盘 + 回执（统一核验流）

输入：Stage 2 的逐模型三层产出；`.modelmap/` 已存在时还需要当前仓库的 git commit。

第一步 reconcile（增量核验）：已有 `.modelmap/` 且仓库没变（commit 命中）→ 直接复用
旧档案；仓库变了 → 重新抽取，与旧产物做 diff，有改动的条目带日期锚
`【代码核验 YYYY-MM-DD，来源 file:line】`。**前提被推翻的桥接假设必须整条重推**，
不许留半新半旧的假设。

第二步落盘 + 回执：按 `references/output-spec.md` 写 `.modelmap/` 全套文件，其中
`models.md` 的结构照 `references/models-template.md`——每个模型的桥接假设之后追加
「组件→可干预开关映射」（`ablation_switches`：component/switch/kind 三元组，kind ∈
{config-flag, code-stub, not-intervenable}，须覆盖 `__init__`/初始化/默认参数，不能
只看 forward）；本次审计涉及 ≥2 个模型对比时，末尾追加「模型间差异清单」
（`diff_list`：逐行列出两模型差异，同样覆盖 `__init__`/初始化/默认参数，附完备性
自检声明——清单不完备＝假设空间有洞＝错误归因）。随后执行**回执纪律**（步骤详见
§7）：①写 pointer；②写 `MODELMAP_RECEIPT.json`——commit 取
`git -C <repo> rev-parse HEAD`，仓库没有 git 就填 `no-git`。**两步缺一不可**，回执是
本阶段完成的产物判据。

done：`MODELMAP_RECEIPT.json` 落盘。

### Stage 4：自检（强制，主 agent 亲自做）

输入：Stage 3 落盘的 `.modelmap/` 全套。

菜谱：跑 `references/machinery.md` §5 的自检清单，共六项：
- 落盘后置条件：预期的文件确实都存在（对照 `output-spec.md` 的清单）。
- 锚点抽查：抽几条标 ✅ 的断言，打开它引用的 `file:line`，确认代码确实那么写；
  不符 → 降级为 ⚠️ 并记入 `open-questions.md`。
- 链接完整：档案里的交叉引用条目都能解析，不指空。
- 覆盖检查：代码里找到的模型数 vs 实际建档的模型数；没触达的模型逐个列出，
  不留静默缺口。
- 无裸断言：每条非平凡陈述都带置信标签；标 ✅/📊 的必须带锚点。
- 开关映射完备性：每个模型的 `ablation_switches` 是否覆盖 `__init__`/初始化/默认
  参数（不能只看 forward）；涉及模型对比时 `diff_list` 是否带完备性自检声明，
  声明缺失按未完成处理。

产出 `AUDIT_SELFCHECK.md`：简短报告，含抽查结果、通过率、降级条目、覆盖率。

done：`AUDIT_SELFCHECK.md` 落盘。frontmatter 标了 `subagent_ok: false`：自检必须主
agent 亲自做，不得外包给子代理（防止"自己抽取、自己自检"）。

## 3. 证据升级规则

本 playbook 不产出「现象/假设」这类分级结论——证据分级留给消费档案的其他 playbook
去做，所以没有独立的 evidence_lines/upgrade_rule 字段。

档案内部用置信标签体系表达证据强度（定义见 `references/machinery.md` §1），从强到弱：
✅ 代码已证 > 📊 数据实测 > 📐 理论推导 > ⚠️ 未证/推断。下游 playbook 引用桥接假设时，
只有 ✅/📊 支撑的部分可以直接当归因证据；📐/⚠️ 的部分只能当作待验证的假设起点。

## 4. 停顿点与汇报

两处要向用户汇报：Stage 0 完成后，若存在多候选版本或有定位不到的模型，先简短汇报再
继续；Stage 4 自检完成后，汇报①覆盖率（找到数/建档数）②降级条目数（✅ 降为 ⚠️ 的
断言数）③未触达模型清单（如有）。

本 playbook 没有强制的 `pause_after`：它通常作为其他 playbook 的嵌入上下文供应者运行，
停不停由调用方决定。但产出后必须让主 agent 或调用方知晓自检结果，不能静默收尾。

## 5. subagent 拆分建议

Stage 2 的逐模型抽取天然适合并发：每个模型开一个子代理，brief 只带该模型的类名、
候选文件路径和输出目标节。写完即忘，防止上下文膨胀；各子代理写不同文件，天然没有
竞态。

Stage 0/1/3/4 不拆：Stage 0 的多候选裁决、Stage 3 的 reconcile diff、Stage 4 的自检
都需要跨模型的全局视角，拆给子代理反而破坏一致性判断。

## 6. 材料降级说明

- `model_code` 缺（absent-confirmed）：本 playbook 直接不可做。代码是唯一证据来源，
  没有降级路径，向用户说明后终止。
- `train_y` 缺：Stage 1 数据画像跳过（variant 未激活），models.md 里"为什么"类断言
  的证据强度上限是 📐，无法用 📊 数据实测支撑。
- `experiment_config` 缺：不影响主线产出。只是核验训练窗口/超参时少一路交叉验证来源，
  缺口记入 `open-questions.md`。
- `data_profile` 缺（指"已有现成画像文件"这种材料形态，而非原始样本）：降级路径与
  `train_y` 缺相同，跳过 Stage 1 重新生成；手头有现成的 `data-profile.md` 时可直接
  引用并跳过重跑。

## 7. 回执纪律

回执是写在诊断工作目录里的小 JSON 文件，orient 靠它判定阶段是否完成。本 playbook 有
两处回执：

- Stage 3 落盘 `.modelmap/` 后，必须①调 `python3 <本目录>/scripts/pointer.py` 对应的
  `write_pointer` 流程写 pointer（固定路径见 `references/output-spec.md`），**并**
  ②在诊断工作目录调 `pointer.write_receipt(modelmap_dir, commit)` 写
  `MODELMAP_RECEIPT.json`。orient 用这份回执判定 model-audit 阶段是否完成、档案相对
  当前代码 commit 是否新鲜——`is_stale` 比对 `MODELMAP_RECEIPT.json`/pointer 里记的
  commit 与 `git -C <repo> rev-parse HEAD`。
- Stage 1 跑完 `scripts/profile_data.py` 后，立即写 `data-profile-receipt.json`
  （内容 `{"profile_md": <路径>, "date": <ISO 日期>}`），供 orient 判定 Stage 1 完成。
  不要攒到 Stage 3 才落盘。

两处回执都是**阶段闸的产物判据**（对应 frontmatter 的 `done_when.artifacts`）。只写
文档、不写回执，orient 会视为阶段未完成，反复提示"数据画像/建档未完成"。

## 8. 纪律（总纲，细则援引 `references/machinery.md`）

- 证据强度排序：代码 > 推导 > 空白。多版本"哪个是产线"由用户定，不由 agent 猜。
- "代码里没找到" ≠ "不存在"——未找到就留空，不编造。
- 每处结论带置信标签 + `file:line` 锚点；未知的东西永远显式写出来。
- 产出后 `.modelmap/` 的三层内容（事实 / 待确认 / 桥接假设）必须自洽，互相不矛盾。
- 桥接假设与消费方的对接契约见 `references/cross-skill-contract.md`：H-ID 的命名与
  登记方式、要读入哪些文件。接口面只通过 pointer、H-ID 登记表、图谱目录三样耦合。
  模型事实不跨技能复制粘贴——消费方要用，顺着 pointer 来读。
