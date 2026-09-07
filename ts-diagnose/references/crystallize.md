# Crystallize：把一次成功运行固化成薄专用技能

<!-- "泛化 → 特化"的操作程序。产物是薄代理技能：触发词 + profile.yaml + 脚本快照，
     workflow 逻辑仍在引擎——引擎升级时所有固化技能自动受益。 -->

## 0. 何时提议

- 一次运行到达结论阶段（orient 报全部阶段完成，CONCLUSION.md 在），且
- 用户表示"以后还要跑这类分析"，或你在运行后回顾时判断该场景会复发 → **主动提议**，用户点头才做。

前置核验（不满足不固化）：`analysis_scripts/` 里**要快照的每个脚本在 PROGRESS.md 有验证记录**（验证步 PASS 行 + gen_gate 过闸报告）；diagnose_config.json 的 questions 块完整。

**注意**：单次成功 ≠ 可固化。转正门槛是 §3 三关判据（`scripts/crystallize_gate.py` 判定）——
第一次成功运行后通常先提议"记入 crystallize_record，攒够 N 个 case 再固化"，而不是当场固化。

## 1. AskUserQuestion 收集固化参数（一次问齐）

1. **新技能名**（kebab-case，建议 `<领域>-<目标>` 如 `pv-chunk-training`）；
2. **触发词**：用户会怎么说这件事？要 3–5 条**用户原话**（决定 description 的召回）；
3. **路径分层**：本次 config 里哪些路径/字段是跨次稳定的、哪些每次都会变？
   稳定的进 profile 的 config_defaults（或写成实验线引用）；会变的**不进 profile**，
   留给下次运行现场问；
4. **问答固化范围**：questions 块里哪些答案下次还成立？schema、结构、判据类的答案
   通常成立；样例行若来自会轮换的日志，则不固化。
   **materials 同为固化原料**：config.materials 里跨次稳定的条目（layout、schema）
   搬进 profile.yaml 的 `materials:` 块，结构与 config 条目相同；具体路径通常每次
   不同，不要固化。orient --profile 合并时只补缺、不覆盖，source 记 `profile`。
   有两样东西**绝不固化**：
   - `degraded_ok`：降级豁免必须每次运行都经用户确认，merge 时强制剥除；
   - `products` 登记：产物是每次运行的现场事实，固化它等于把上次会话的产物路径
     当成这次的；
5. **入库**：新技能目录要不要提交 git 主仓？profile 含项目路径等事实，仓库公开时
   需用户知情同意（与 project-context 同一先例）。

## 2. 生成薄技能 `<仓库根>/<new-skill>/`

```
<new-skill>/
├── SKILL.md        # ~50 行
├── CHANGELOG.md    # 首行 = 固化来源 + 三步验证结果
├── profile.yaml
└── scripts/        # 只拷有验证记录的 analysis_scripts/*.py
```

**SKILL.md 骨架**（保持薄——领域细节多到写不下 = 该改 playbook 而不是塞这里）：

```markdown
---
name: <new-skill>
description: <触发词原话拼接>。本技能是 ts-diagnose 引擎的固化实例（playbook=<id>）：
  按 profile 进入，已固化问题不再问。<一句话领域定位>
---

# <name>

固化自 <日期> 的一次 ts-diagnose 运行（来源工作目录见 CHANGELOG）。

## 进入

    python3 "<ENGINE>/scripts/orient.py" --profile "<本技能绝对路径>/profile.yaml"

（<ENGINE> = ts-diagnose 引擎目录。）之后照引擎 SKILL.md + playbook <id> 正文执行；
orient 报 ✓固化 的问题不再问，✗ 的照常问。

## 脚本快照优先

工作目录建 analysis_scripts/ 时**先拷本技能 scripts/ 下的同名脚本**（已验证），
schema 没变就不重写；变了按 playbook 菜谱重生成并重跑验证步。

## 领域注意事项（≤10 行，从本次 FINDINGS/回顾提炼）
- <本领域特有的坑/事实>
```

**profile.yaml schema**：

```yaml
profile_version: 1            # 与 engine_common.PROFILE_VERSION 对齐；不匹配时 orient 警告
                              # 并降级为"按 playbook 现问"（config_defaults 仍合并）
engine: ts-diagnose           # 相对仓库根；引擎搬家用 engine_path 绝对路径兜底
playbook: training-sufficiency
goal: "<一句话：这个固化实例回答什么问题>"
experiment_line:              # 可选。与实验线重叠的字段一律写引用，不复制数值——
  path: <project-context 实验线 json 绝对路径>   # 防 profile 与注册表两处漂移
  interface_version: v0-draft # project-context 消费接口未定稿：v0-draft = 占位不生效
                              # （orient 不合并、相关问题照常问；固化技能不得对该字段做
                              # 逻辑依赖）。定稿轮统一 v0→v1 迁移后才生效。
config_defaults:              # 只放跨次稳定且不属于实验线的字段（缺则不写）
  log_glob: "logs/train_*.log"
questions:                    # 已固化问答（source 会标 profile；answer 存原话）
  loss-source: {answer: "<原话>", date: 2026-07-14}
  unit-structure: {answer: "<原话>", date: 2026-07-14}
materials:                    # 跨次稳定的材料条目（layout/schema；路径每次不同别固化）
  predict: {status: "present", layout: "per-model", schema: {y_col: "power"}}
scripts:                      # 快照清单（审计：从哪来、何时验证过、对应哪个阶段）
  - {file: extract_loss.py, from_run: "<工作目录>", validated: 2026-07-14, stage: 1}
```

**scripts/ 快照**：只拷 PROGRESS.md 有验证记录的脚本；每个文件头部加 provenance 注释：

```python
# [crystallized 2026-07-14] 来源运行: <工作目录>；playbook=<id> Stage <N>；
# 验证步: <PASS 摘要>。schema 变了别缝补——按 playbook 菜谱重生成并重跑验证步。
```

## 3. 三关判据（转正门槛——`crystallize_gate.py` 判定，任一不过不许写 profile/SKILL）

```bash
python3 <ENGINE>/scripts/crystallize_gate.py --record crystallize_record.json --skill-dir <候选技能目录>
```

1. **关1 多样性**：≥N 个 `input_hash` 互异的成功 case（N = playbook frontmatter
   `crystallize_min_cases`，默认 3；training-sufficiency 为 5）。case 不能是同一场景微调，
   每个要注明覆盖的**适用域边界**（boundary 字段：如"文本日志源/单曲线退化形态/大规模多 series"）。
2. **关2 held-out**：一个**从未参与开发调参**的留出场景，固化前跑一遍且 passed=true，
   `input_hash` 不与任何开发 case 重合。
   （held-out 场景库排后续轮；本轮判据要求该记录存在且通过。）
3. **关3 快照自洽**：每个待快照脚本经 `gen_gate.py` 在其 playbook 金标准上重跑 PASS。
   golden 未覆盖的阶段列 unchecked 警告，须有 PROGRESS.md 验证记录人工确认。

**crystallize_record.json schema**（主 agent 跨运行汇总；input_hash 取各次运行
provenance.json 的 `data.combined`）：

```json
{
  "playbook": "training-sufficiency",
  "cases": [
    {"name": "chunk轮换-文本日志", "input_hash": "<provenance data.combined>",
     "workdir": "<该次运行目录>", "date": "2026-07-14",
     "boundary": "文本日志源 + 多 series；覆盖 grouped 变体"}
  ],
  "heldout": {"name": "<留出场景>", "input_hash": "<...>", "passed": true, "date": "..."},
  "snapshots": [{"file": "scripts/dynamics.py", "stage": 2}]
}
```

## 3.5 交付检查（三关过后、交付前）

1. **冷启动 orient**：空临时目录跑 `orient.py --profile <new>/profile.yaml`，断言：
   playbook 正确加载；profile 固化的问题全部标 ✓固化；无 ✗ 遗漏本应固化的题；
   报的当前 Stage = 第一个真实未完成阶段（空目录应为最早阶段）。
2. **脚本快照冒烟**：每个快照脚本 `python3 -m py_compile` 通过；有 `--selfcheck`/`--verify`
   的跑一遍自检模式。
3. **影子重跑**（可选，推荐）：临时目录里用原数据把最早一个阶段重跑，关键数字与原运行
   相对差 <1%。

三关 + 交付检查的结果一并写新技能 CHANGELOG 首行。

## 4. 收尾

- 按当前运行时的技能目录安装或登记新技能，并更新仓库 CHANGELOG；

## 5. 维护约定

- **引擎升级**：机制层改动若动了 PROFILE_VERSION，逐个固化技能重跑三步验证后把
  profile_version 抬上来；orient 对版本不匹配的 profile 自动降级（不会错答，只会多问）。
- **profile 漂移**：某固化答案被现实推翻（日志格式变了）→ 改 profile 对应条目 + 技能
  CHANGELOG 记一行；连续两次都要现场改 → 考虑该字段本就不该固化，移回"每次问"。
- **反向回流**：固化技能运行中暴露的**通用**问题（菜谱歧义、机制 bug）改回引擎/playbook
  并跑 pytest——不要在薄技能里就地打补丁。
