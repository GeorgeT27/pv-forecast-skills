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

本 playbook 只做一件事：用户的原始材料 → 规范长表 + 对齐报告 + setup 产物 manifest。
**不画图、不算指标、不下任何结论**——那些是下游 playbook 的活。首要陷阱：适配器
顺手"清洗"数据（去重/填缺/截断）——薄适配器只做重排不做清洗，任何数据问题如实
进 alignment_report 的 note，让下游看得见。第二陷阱：多模型缺窗不对称时静默取
交集不留痕——dropped 统计必须逐模型入报告，否则下游把覆盖差异当模型差异。

## 2. 逐阶段菜谱

### Stage 0 适配与对齐（主 agent 只做步 1-2，步 3 起 subagent）

输入：materials 盘点后的 predict/truth 原始数据（有 features/train_y 材料时一并处理）。
菜谱（编号步骤，逐条建 todo）：

1. （主 agent）确认 freq 与 align-keys 已答（frontmatter questions；orient 报 ✗ 先问）；
2. 【硬规则】（主 agent）按 `references/subagent-briefs.md` 的 **Brief-PRODUCER** 派发
   subagent 执行步 3 起的全部菜谱（含 Stage 1），实参：`<ENGINE>`、工作目录、
   predict/truth 路径、freq/align-keys 答案。主 agent 不得自己写适配器——发现自己在写
   adapter.py 即本步被跳过，停下补派发；
3. （subagent）现场写薄适配器 `analysis_scripts/adapter.py`（用户格式 → 规范长表
   predictions.csv，列：window_ts/unit_id/model/horizon_step/y_true/y_pred，见
   chartbook/_recipe-spec.md §2；features/train_y 同步产 features.csv / train_y.csv），
   CLI 契约固定：
   `--in <用户文件> --n-steps <N> --freq <freq答案> --out predictions.csv --alignment alignment_report.json --report adapter_report.json`；
4. （subagent）**生成闸（硬规则）**：真实数据前先过
   `python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/adapter.py --playbook data-setup --stage 0`
   （golden/ 植入不对称覆盖难例，全 expect 通过），再过**对账两关**（行数守恒 + 抽 3 窗
   数值核对，样例 chartbook/golden/example_adapter/）；
5. （subagent）按 align-keys 答案对齐各模型，落 `alignment_report.json`（schema：
   `{"models":[...], "n_rows_per_model":{}, "n_aligned":int, "n_dropped_per_model":{},
   "freq":str, "note":"dropped 不对称时的说明"}`）与 `adapter_report.json`
   （`{"rows_wide":int, "rows_long":int, "spot_checks":[...], "ok":bool}`）。

验证步：步 4 的闸与对账数字随 Brief-PRODUCER 回传，主 agent 记 PROGRESS.md。
done：三个产物落盘。

### Stage 1 产物清单落盘（subagent 承接）
菜谱：（subagent）跑引擎机制脚本（预写，禁现场重写）：
`python3 <ENGINE>/scripts/setup_manifest.py --pred predictions.csv --alignment alignment_report.json --out setup_manifest.json`。
manifest 记录表路径/模型清单/freq/行数/窗口范围/**完整材料清单（含 training_log 与
experiment_config 的位置与格式——下游训练类 playbook 由此获知日志在哪，不再另问）**/
输入文件指纹（过期检测）/适配器脚本指纹（代码也是依赖——适配逻辑变了 setup 即过期）。
done：setup_manifest.json 落盘。随后主 agent 回父工作目录写
`config.products.setup = {workdir, status: "built"}`（subagent 无权写 config）。

## 3. 证据升级规则

无。本 playbook 不产结论——产物即全部输出（这是它与诊断类 playbook 的边界）。

## 4. 停顿点与汇报

无 pause_after 阶段。产物就绪后一句话汇报：模型清单/行数/窗口范围/dropped 是否
对称/哪些可选材料缺席，然后把控制权还给发起的下游 playbook（或用户）。消费者是
用户本人（直接触发本 playbook）时，主 agent 可读 setup_manifest.json 与
alignment_report.json 补充细节（如 dropped 不对称时的 note 原文）——读落盘产物，
不让 subagent 多回话。

## 5. subagent 拆分建议

**整体外包（硬规则）**：本 playbook 满足 Brief-PRODUCER 三条件（produces + 无结论
阶段 + 执行段无用户裁决/FINDINGS 写入），Stage 0 步 3 起连同 Stage 1 整体交一个
subagent 串行执行（两阶段轻且串行，不再细拆）；模板与派发纪律见
`references/subagent-briefs.md` Brief-PRODUCER。提问（freq/align-keys）、PROGRESS
记录、config.products 回填只在主 agent。

## 6. 结论模板与反驳门

不适用（无结论阶段）。唯一自查：adapter_report.ok=false 或对账任一关不过 →
不许落 predictions.csv，回头修适配器。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做——没有降级路径，
  全部依赖 setup 的下游 playbook 同样不可做，向用户说明后终止；
- features / train_y 缺：对应长表不产，manifest.tables 里没有该键，下游按各自
  材料降级规则跳过相关图；
- training_log / experiment_config 缺：不影响本 playbook 主线，manifest.materials
  如实记 absent，下游训练类 playbook 自行按缺席处理。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 charts（产数据产物，不画图）：全部 28 个 recipe 跳过，
理由统一为「结构性不适用——本 playbook 无分析阶段，图属于下游消费者」。下游
playbook 各自声明目标核心图；大而全体检走对应的体检类 playbook（chart_sweep 产物）。
