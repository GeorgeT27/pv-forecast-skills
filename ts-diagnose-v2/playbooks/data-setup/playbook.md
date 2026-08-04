---
id: data-setup
name: 数据就位（普适前置）
goal: 把用户原始预测/真值材料规范成长表并对齐，产 setup 产物供全部分析 playbook 复用
produces:
  id: setup
  manifest: setup_manifest.json
  marker_files: [predictions.csv, alignment_report.json]
stages:
  - id: 0
    name: 适配与对齐
    done_when:
      artifacts: [predictions.csv, alignment_report.json, adapter_report.json]
    prereqs:
      - desc: 步长已确认
        check: "question:freq"
      - desc: 对齐键已确认
        check: "question:align-keys"
  - id: 1
    name: 产物清单落盘
    done_when:
      artifacts: [setup_manifest.json]
    prereqs:
      - desc: 长表与对齐就绪
        check: "stage:0"
materials:
  required: [predict, truth]
  optional: [features, train_y, training_log, experiment_config]
questions:
  - id: freq
    stage: 0
    ask: "horizon 步长（freq）是多少？（如 15min / 1h——hour/tod 维度全靠它）"
    why: "freq 错则时段维度全错，污染全部下游图与结论"
    default: null
  - id: align-keys
    stage: 0
    ask: "各模型/各文件按什么键对齐？缺窗如何处理？（默认 window_ts+unit_id 内连接）"
    why: "对齐错位会把数据覆盖差异误判成模型差异"
    options: ["window_ts+unit_id 内连接（默认）", "其他"]
    default: "window_ts+unit_id 内连接"
---

# data-setup：数据就位（全部分析 playbook 的必需上游）

## 1. 问题框定与首要陷阱

本 playbook 只做一件事：把用户给的原始预测数据和真值数据，整理成三样产物——规范长表
`predictions.csv`、对齐报告 `alignment_report.json`、产物清单 `setup_manifest.json`。
**不画图、不算指标、不下任何结论。** 那些是下游分析 playbook 的活。

首要陷阱：适配器顺手"清洗"数据。适配器必须是"薄"的：
只做格式重排，禁止去重、填缺、截断。发现数据有问题时，如实写进 alignment_report 的
note 字段，不替下游把问题抹掉。

第二陷阱：多模型窗口覆盖不一致时，静默取交集、不留痕迹。每个模型被对齐丢弃的行数
（dropped）必须逐模型写进对齐报告；否则下游会把"数据覆盖不同"误判成"模型能力不同"。

## 2. 逐阶段菜谱

### Stage 0 适配与对齐（主 agent 只做步 1-2，步 3 起 subagent）

输入：materials 盘点后的 predict/truth 原始数据。用户还提供了 features/train_y
材料时，一并处理。

菜谱（编号步骤，逐条建 todo）：

1. （主 agent）确认两个前置问题已有答案：freq（horizon 步长）和 align-keys（对齐键）。
   orient 报 ✗ 时，先向用户提问，再继续；
2. 【硬规则】（主 agent）按 `references/subagent-briefs.md` 里的 **Brief-PRODUCER**
   模板派发一个 subagent，由它执行步 3 起的全部菜谱（含 Stage 1）。派发时传实参：
   `<ENGINE>`、工作目录、predict/truth 路径、freq 与 align-keys 的答案。主 agent
   不得自己写适配器；发现自己在写 adapter.py，就说明本步被跳过了，停下补派发；
3. （subagent）现场写薄适配器 `analysis_scripts/adapter.py`：用户格式 → 规范长表
   predictions.csv。长表列固定为
   window_ts/unit_id/model/horizon_step/y_true/y_pred，各列定义见
   chartbook/_recipe-spec.md §2。有 features/train_y 材料时，同步产出
   features.csv / train_y.csv。CLI 契约固定：
   `--in <用户文件> --n-steps <N> --freq <freq答案> --out predictions.csv --alignment alignment_report.json --report adapter_report.json`；
4. （subagent）**生成闸（硬规则）**：碰真实数据之前，适配器必须先通过引擎的生成检查：
   `python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/adapter.py --playbook data-setup --stage 0`。
   golden/ 里的难例数据（含"多模型覆盖不对称"情况）全部 expect 通过才算过。
   过闸之后还要过**对账两关**：第一关行数守恒，转换前后的数据点数量必须对得上；
   第二关抽 3 个窗口，逐点核对转换前后数值一致。对账样例见
   chartbook/golden/example_adapter/；
5. （subagent）按 align-keys 的答案对齐各模型，落两个报告文件。
   `alignment_report.json` 的 schema：
   `{"models":[...], "n_rows_per_model":{}, "n_aligned":int, "n_dropped_per_model":{},
   "freq":str, "note":"dropped 不对称时的说明"}`；
   `adapter_report.json` 的 schema：
   `{"rows_wide":int, "rows_long":int, "spot_checks":[...], "ok":bool}`。

验证步：步 4 的过闸结果与对账数字随 Brief-PRODUCER 回传，主 agent 记入 PROGRESS.md。
done：predictions.csv、alignment_report.json、adapter_report.json 三个产物落盘。

### Stage 1 产物清单落盘（subagent 承接）
菜谱：（subagent）跑引擎预写的机制脚本，禁止现场重写：
`python3 <ENGINE>/scripts/setup_manifest.py --pred predictions.csv --alignment alignment_report.json --out setup_manifest.json`。
manifest 里记录：

- 长表路径、模型清单、freq、行数、窗口范围；
- **完整材料清单，含 training_log 与 experiment_config 的位置与格式**——下游做
  训练类分析的 playbook 从这里得知日志在哪，不再问用户一遍；
- 输入文件指纹，用于过期检测：输入数据变了，setup 产物即算过期；
- 适配器脚本自身的指纹：适配逻辑改了，即使输入没变，setup 同样算过期。

done：setup_manifest.json 落盘。随后主 agent 回到父工作目录，写
`config.products.setup = {workdir, status: "built"}`。这一步必须由主 agent 做——
subagent 无权写 config。

## 3. 证据升级规则

无。本 playbook 不产结论，产物文件就是全部输出。

## 4. 停顿点与汇报

本 playbook 没有 pause_after 阶段。产物就绪后，用一句话汇报：模型清单、行数、
窗口范围、各模型 dropped 是否对称、哪些可选材料缺席。汇报完，把控制权还给发起
本 playbook 的下游 playbook（或用户）。若消费者是用户本人，主 agent 可读
setup_manifest.json 与 alignment_report.json 补充细节（如 dropped 不对称时 note
字段的原文）；细节从落盘产物里读，不让 subagent 额外多回话。

## 5. subagent 拆分建议

**整体外包（硬规则）**：Stage 0 的步 3 起连同 Stage 1，整体交给同一个 subagent
串行执行，不再细拆。模板与派发纪律见 `references/subagent-briefs.md` 的
Brief-PRODUCER。只能由主 agent 做的三件事：向用户提问（freq/align-keys）、
记录 PROGRESS、回填 config.products。

## 6. 结论模板与反驳门

不适用——本 playbook 没有结论阶段。唯一自查：adapter_report.ok=false，或对账两关
任何一关不过，就不许落 predictions.csv，必须回头修适配器。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 做不了，没有降级路径；
  全部依赖 setup 产物的下游 playbook 同样做不了。向用户说明后终止；
- features / train_y 缺：对应长表不产出，manifest.tables 里没有该键；下游按
  各自的材料降级规则跳过相关图；
- training_log / experiment_config 缺：不影响本 playbook 主线；manifest.materials
  如实记 absent，下游训练类 playbook 自行按材料缺席处理。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 charts：它产数据产物，不画图。chartbook 共 28 个 recipe
全部跳过，理由统一为「结构性不适用——本 playbook 无分析阶段，图属于下游消费者」。
下游 playbook 各自声明目标核心图；想要大而全的体检图，走对应的体检类 playbook，
其产物为 chart_sweep。
