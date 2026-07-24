# models.md 目标结构模板（不是事实，是产出骨架）

> 本文件规定 `.modelmap/models.md` 的章节骨架与桥接假设写法。产出时逐字段按代码填写并带
> 置信标签；空字段留空或标 ⚠️/待确认。**不得把本模板里的占位/示例当作已知事实。**

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

## M2 —— 类名 PatchRegForecast
（同上骨架）

## M3 —— 类名 MoiraiPvForecaster
（同上骨架）

## M4 —— 类名 PatchTSTPvForecaster
（同上骨架）

## ensemble
- **组合方式** / **成员** / **权重确定方法** / **强弱项**：<…；若代码里找不到组合器，留空+⚠️>

## 定位速查表（locate 步用）
| 模型 | 类名（grep 首选） | 容错前缀 | 架构签名兜底关键词 |
|------|------|------|------|
| M1 | FourierMobaTransformer | FourierMoba | MoBA / vicreg / ortho / fourier / customTSTiEncoder |
| M2 | PatchRegForecast | PatchReg | stat_embd / GHIembedding / Patch1d / weather_source_names |
| M3 | MoiraiPvForecaster | MoiraiPv | moirai / MultiInSizeLinear / loss_auxi / rfft |
| M4 | PatchTSTPvForecaster | PatchTSTPv | PatchTST / RevIN / TSTencoder / pinball / quantile |
| 共用 | — | — | chronos / observe_power_predicted |
