# models.md 目标结构模板（不是事实，是产出骨架）

> 本文件规定 `.modelmap/models.md` 的章节骨架与桥接假设的写法。产出时逐字段读代码
> 填写，每条断言带置信标签（✅/📊/📐/⚠️，定义见 machinery.md §1）；查不到的字段留空，
> 或标 ⚠️/待确认。**模板里的占位符和示例只是骨架，不得当作已知事实照抄。**

## 全体共同约定（跨站设定）
<按代码与用户确认填写：联合训练站、留出测试站、零样本跨站迁移等>

## M1 —— 类名 FourierMobaTransformer
- **代码类名**：FourierMobaTransformer  ✅ `file:line`
- **模型类型/架构**：<…>
- **输入特征**：<…（看得见/看不见什么，决定可归因边界）>
- **损失函数**：<…读实际代码，非注释/函数名>  ✅ `file:line`
- **训练数据窗口**：<…>
- **已知强项/弱项**：<…>
- **版本历史**：<…>

### M1 架构 → 结果分析含义（桥接假设；每条 → 图# + H-ID）
- <架构事实> → <预期误差形态> → <哪张图检验> （H-M1-<n>，📐 前提：<…>）

### M1 组件 → 可干预开关映射（ablation_switches）
> 覆盖范围含 `__init__`/初始化/默认参数，不能只看 forward。

| 组件 | 开关 | kind | 锚点/理由 |
|---|---|---|---|
| <组件名> | <--flag，或"无"> | config-flag／code-stub／not-intervenable | <file:line；或需加代码的理由；或不可干预的原因> |

## M2 —— 类名 PatchRegForecast
（同上骨架，含 ablation_switches 小节）

## M3 —— 类名 MoiraiPvForecaster
（同上骨架，含 ablation_switches 小节）

## M4 —— 类名 PatchTSTPvForecaster
（同上骨架，含 ablation_switches 小节）

## ensemble
- **组合方式** / **成员** / **权重确定方法** / **强弱项**：<…；若代码里找不到组合器，留空+⚠️>

## 模型间差异清单（diff_list，仅本次审计涉及模型对比时产出）
> 逐行对比，覆盖范围含 `__init__`/初始化/默认参数，不能只对比 forward。

| 差异项 | 模型 A | 模型 B | 锚点 |
|---|---|---|---|
| <差异项> | <值/写法> | <值/写法> | <file:line> |

**完备性自检**：<声明已逐项核对 forward + `__init__` + 默认参数三处，未见遗漏；或
如实列出未覆盖处>

## 定位速查表（locate 步用）

供 Stage 0 定位模型使用。查找顺序：先按「类名」列 grep，搜不到再试「容错前缀」，
还搜不到就用「架构签名兜底关键词」。表中内容是示例模板，实际项目按其代码库的信息更新。

| 模型 | 类名（grep 首选） | 容错前缀 | 架构签名兜底关键词 |
|------|------|------|------|
| M1 | FourierMobaTransformer | FourierMoba | MoBA / vicreg / ortho / fourier / customTSTiEncoder |
| M2 | PatchRegForecast | PatchReg | stat_embd / GHIembedding / Patch1d / weather_source_names |
| M3 | MoiraiPvForecaster | MoiraiPv | moirai / MultiInSizeLinear / loss_auxi / rfft |
| M4 | PatchTSTPvForecaster | PatchTSTPv | PatchTST / RevIN / TSTencoder / pinball / quantile |
| 共用 | — | — | chronos / observe_power_predicted |
