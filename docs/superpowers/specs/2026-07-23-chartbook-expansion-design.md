# ts-diagnose chartbook 扩展设计:14 张新图 + 模型归因层 + 图表归组

日期:2026-07-23 · 状态:待实施
前置调研:技能生态无同类轮子(四候选均为提示模板/前向工作流/占位脚手架);
可解释性与评估实践两路调研结论已并入本设计(方法选型、守卫规则、6 张补充图)。

## 1. 目标

chartbook 从 14 张 recipe 扩到 28 张,补齐四个缺口:

1. **样本对比**:好/坏样本的特征特性对比(现有图只看"坏",没有 best-K vs worst-K);
2. **模型归因**:全局特征贡献(SHAP 式)、lookback 依赖衰减、worst-K 局部 waterfall
   ——需模型推理入口,作为材料声明,运行时问用户、有就画;
3. **评估实践缺口**:朴素基线参照系、排名显著性、翻新稳定性、误差性质三分、
   经验置信带(调研确认的 22 图共同盲区);
4. **归组呈现**:所有 recipe 按类别归组,同类图放一起给用户看。

不改变 chartbook 既有纪律:一图一 recipe、JSON 一等 PNG 副产品、compute/render
分离、合成植入回收 golden、预写禁现场重写。

## 2. 结构决策

- **全部进 chartbook**(引擎级共享层),不做 playbook 阶段脚本——归因图对
  feature-importance / model-comparison / robustness 多个 playbook 都有用;
  feature-importance Stage 1(permutation)后续可改调 chartbook 脚本消除重复。
- **模型访问 = 材料**:归因三图 `needs_materials` 含 `serving_api`(已在
  MATERIAL_IDS),orient 图表选择门自动按材料可用性标"可画/缺推理入口跳过",
  与 `needs_models` 同款机制。Stage 0/intake 问一次落盘,不新增机制。
- **领域中立硬纪律**(新增规范条目):recipe 的 id/字段/标签/判读不得出现领域
  名词(天气/站点/医学等);领域语义只允许在运行时经 intake 背景(data_profile)
  注入呈现层(如给聚类簇起名)。既有 `intraday-profile` 标注为"周期性数据
  专用,orient 按 data_profile 判断适用"。

## 3. 模型访问契约(predict adapter)

预写脚本不碰用户模型,只认运行时薄适配器 `analysis_scripts/predict_adapter.py`
(与 `adapter.py` 同款纪律:现场唯一要写的代码,写完过对账):

```python
CAPABILITIES = {"perturb_features": True, "perturb_lookback": False}

def predict(windows, feature_overrides=None, lookback_mask=None):
    """windows: 规范长表行集; 返回同形 y_pred。
    feature_overrides: {feature: 替换值序列} — 特征扰动
    lookback_mask: 步数区间列表 — 历史窗遮蔽(能力可选)
    """
```

- 用户给 FastAPI 包 FastAPI、给本地模型包本地模型,脚本无感;
- `lookback-decay` 要求 `perturb_lookback=True`,不满足时选择门如实标注不可画;
- 契约文档进 `_recipe-spec.md` 新 §6,模板进 `chartbook/golden/example_predict_adapter/`
  (含 golden 用合成线性模型适配器——线性模型 Shapley 解析可知,零网络)。

### attribution_common.py(共享层)

- 背景集:`shap.kmeans(data, K)` 摘要(默认 K=25)或分层采样;**背景集定义
  (来源、K、采样期、种子)必须落盘进每个归因 JSON 的 `background_meta`**
  ——换背景集 = 换归因基线,这是复现性关键(守卫一);
- Shapley 估计:直接调 `shap` 库(KernelExplainer / PermutationExplainer +
  自带 waterfall 绘图),不手写采样;192 步输出按 shap 官方多输出实践逐输出
  独立算再聚合(mean|SHAP| 全局 + per-horizon 桶保留);
- **成组置换守卫(守卫二)**:permutation 口径必须先做特征相关性聚类
  (|ρ|>0.8 成组),组内整体置换——独立置换强相关特征会造分布外样本、
  重要性虚高;分组结果落 JSON;
- **调用预算**:`--max-calls`(默认 5000)截断时 JSON 如实记录 coverage,
  不静默;结果按扰动内容哈希缓存到 workdir,重跑不重打 API;
- 依赖:`shap`(新增,缺失时报错并给安装指引,不静默降级)、sklearn(已有)。

## 4. 新图清单(14 张,含类别与 golden 要点)

### 样本对比类(sample-contrast)

**good-bad-contrast** `[predict, truth, features]`
按行 RMSE 取 worst-K 与 best-K 窗口(K 默认 min(50, 10%行数)),逐特征三层对比:
量值分布、质量(有 f_true 时 |f_pred−f_true|)、通用上下文(周期内相位·检测到
周期才有/真值水平/局部波动率)。描述符:每特征 Cohen's d + KS + 方向,按分离度
排名。PNG:成对小提琴网格。golden:worst 行植入质量差 d=2 真凶 + 分布相同诱饵,
诱饵不得上榜。

**bad-window-clustering** `[predict, truth]`
worst-K 窗口真值曲线归一化后 k-means(k 由轮廓系数在 2–4 选,种子 CLI+落 JSON),
输出簇原型曲线、占比、簇内误差。回答"坏样本是一种失败模式还是几种"。簇的领域
命名交运行时判读层结合 intake 背景。golden:植入两种确定形状 → k=2、成员精确回收。

### 误差结构类(error-structure)

**error-acf** `[predict, truth]`
目标时刻对齐误差序列的 ACF。**纪律:h 步预测最优残差天然是 MA(h−1),lag≤h−1
自相关属正常,只有超出的显著自相关才算病灶**——按 horizon 段分组画,标
Ljung-Box(lag>h−1) p 值。golden:植入周期 P 确定性正弦误差 → lag P 峰精确回收。

**pp-calibration** `[predict, truth]`
y_pred vs y_true 分位数-分位数;描述符:高尾压缩比 q95_pred/q95_true、低尾、
整体斜率。golden:y_pred=0.8·y_true → 斜率与尾比 0.8 精确回收。

**theil-decomposition** `[predict, truth]`
Theil U 分解:U_bias/U_var/U_cov 占比堆叠条(每 model×unit×horizon 段)——
误差是水平偏移、幅度不匹配还是形状错位,修法完全不同。golden:纯偏移
(y_pred=y_true+c)→ U_bias=1;纯幅度 → U_var 主导,精确回收。

**time-shift-diagnosis** `[predict, truth]`
逐窗最优互相关平移量分布——预测是否整体提前/滞后。描述符:众数平移、非零占比。
golden:y_pred = y_true 平移 2 步 → 众数 =2 精确回收。

**horizon-error-quantiles** `[predict, truth]`
每 horizon_step 的经验误差 P5/P25/P75/P95 扇形带——h 步预测该配多宽的置信带、
分布是否偏斜厚尾(点预测下"覆盖率"传统的替身)。golden:误差幅度随 h 线性增长
+奇偶交替符号(零随机)→ 分位带精确回收。

### 输入侧类(input-side)

**feature-regime-error** `[predict, truth, features]`
窗口级特征向量 k-means 聚出"制式",各制式 RMSE 与占比;JSON 输出**每簇特征
质心**(事实),领域命名(晴/多云/阴或医学制式)由运行时判读层结合 intake 背景
给出,不进脚本。golden:两个分离特征簇、一簇 3× 误差 → 制式与比值精确回收。

### 模型对比类(model-comparison)

**baseline-skill** `[predict, truth]`(needs_models 1)
persistence / 季节朴素(主周期由 `--period-steps` 或 ACF 自动检测,无周期退化为
persistence-only)/ 气候均值三条基线 + 各模型的 skill = 1 − RMSE_model/RMSE_naive,
按 unit/horizon/时间片分面。附加检测:预测与滞后真值的相关 > 与真值的相关 →
"退化成抄 persistence"病灶。**这是全图库唯一的朴素参照系,回答模型值不值得存在。**
golden:构造 y_pred 恰等于季节朴素 → skill=0;半误差模型 → skill=0.5,精确回收。

**model-rank-significance** `[predict, truth]`(needs_models 2)
上半:MCB/CD 图(平均秩+不可区分连线);下半:成对 Diebold-Mariano p 值热图
(处理误差自相关);MCS 成员星标。M4/M5 官方排名背书标配——回答"排名差异是
真是噪声"。golden:A 恒为 B 误差 3 倍 → DM 显著、秩分离;两同款模型 → 不可区分。

### 时间稳定类(temporal-stability)

**revision-stability** `[predict, truth]`
以**目标时刻**为锚,聚合覆盖它的多个 window 的预测:随 lead time 缩短,预测收敛
到真值还是跳变(刺猬图/翻新漏斗 + sMAPC 汇总;面条图形态还能一眼识别"回归均值
塌缩""复制输入"退化)。同一 target_ts 无 ≥2 窗覆盖时抛 ValueError 说明(结构性
不适用,同 §5.5 纪律)。与 pv-feature-blame 的特征侧翻新分析构成预测侧-特征侧
闭环。golden:植入确定性收敛轨迹 vs 跳变轨迹 → sMAPC 与跳变标记精确回收。

### 模型归因类(attribution,均需 serving_api)

**global-attribution** `[predict, truth, features, serving_api]`
背景集摘要 + KernelSHAP(或成组置换口径)→ 全局 mean|贡献| 排名;PNG 双面板:
排名条图 + **特征×horizon 贡献热力图**(复用逐输出 SHAP 中间产物,horizon 按桶,
回答"哪些特征只影响短期、哪些拖累远端")。golden:线性合成适配器 y=3a+1b+0c →
贡献比 3:1:0 回收(容差),c≈0。

**lookback-decay** `[predict, truth, serving_api]`(要求 perturb_lookback)
按窗遮蔽历史(WindowSHAP 思想,比逐点省一个量级):lag 桶默认步数相对制
[第1步, 前四分位, 至主周期, 超主周期](主周期来自 data_profile/`--period-steps`,
无周期退化为四分位桶)→ ΔRMSE 衰减曲线;描述符 `short_term_share`(≤1 主周期
贡献占比)。`--per-instance` 选项:逐实例"贡献≥90% 所需最近历史步数"分布
(TimeSHAP 剪枝思想),可按好/坏样本分组与 bad-window-clustering 交叉。
判读话术:曲线平坦 ≠ 模型差,Transformer 系依赖短历史是文献常态。
golden:只读最后一步的合成适配器 → 全部质量落桶 1。

**local-waterfall** `[predict, truth, features, serving_api]`
worst-K 行(默认 20)逐行局部 SHAP → shap 自带 waterfall,top 行拼网格 PNG +
逐行贡献 JSON。golden:线性适配器 → 贡献 = 系数×(x−背景) 精确回收。

## 5. 既有图增强(2 处)

- **true-vs-pred-scatter**:加 Mincer-Zarnowitz 回归线(y_true = a + b·y_pred)
  与 a=0,b=1 联合检验 p 值注记——系统性衰减/放大真值的检验量。golden 补断言。
- **intraday-profile**:recipe 标注"周期性数据专用"(见 §2 领域中立)。

## 6. 图表归组机制

- 所有 28 个 recipe frontmatter 加必填 `category:`,合法集
  `engine_common.CATEGORY_IDS = ("error-structure", "temporal-stability",
  "input-side", "model-comparison", "sample-contrast", "attribution")`,
  CI 校验(test_charts_decl 扩展);
- 类别指派(合计 28):误差结构 9(error-breakdown, horizon-degradation,
  intraday-profile, true-vs-pred-scatter, error-acf, pp-calibration,
  theil-decomposition, time-shift-diagnosis, horizon-error-quantiles)
  /时间稳定 5(rolling-stability,
  cross-dim-stability, train-test-drift, y-vs-feature-mapping, revision-stability)
  /输入侧 3(feature-error-conditional, feature-trend-overlay, feature-regime-error)
  /模型对比 5(model-error-correlation, oracle-gap, worst-slice-compare,
  baseline-skill, model-rank-significance)/样本对比 3(worst-points,
  good-bad-contrast, bad-window-clustering)/模型归因 3;
- orient 图表选择门**按类别分组呈现**可画池(缺材料的标注缺什么);
- 新增 `chartbook/scripts/build_index.py`:扫 charts/ 产物生成 `charts/INDEX.md`
  ——按类别分节、每图缩略引用 + 一句"适用问题" + JSON 关键描述符摘录;
- PNG 文件保持平铺(不动现有脚本输出路径,零 golden 扰动),归组只在呈现层。

## 7. 测试与 CI

- 每张新图:`tests/test_chart_<蛇形>.py` 合成植入回收 golden(植入值见 §4);
- 归因图另加:预算截断守卫(超 `--max-calls` 必须截断且 JSON 记 coverage)、
  背景集元数据落盘断言、成组置换分组落盘断言;
- `test_charts_decl` 扩展:category 必填且 ∈ CATEGORY_IDS、id/正文领域名词
  黑名单抽查(轻量:id 与 frontmatter 字段不含 weather/station/pv 等);
- golden 决定论遵守 §5.3:零随机或固定种子落 JSON;shap 调用固定种子。

## 8. Stage 2 接线

无需改 playbook:图表选择门的"可加画池"机制会在材料满足时自动把新 recipe
按类别呈现(默认全选声明图、可勾选加画)。后续各 playbook 迭代时可把高价值图
(baseline-skill、model-rank-significance 等)升级为显式 `charts:` 声明,不在
本轮范围。

## 9. 明确不做(记录否决理由)

- attention map 分析:黑盒拿不到权重;学界共识 attention 非忠实归因
  (Jain & Wallace 2019 之争),扰动类本来就是其忠实性检验基准。路由规则:
  用户模型恰暴露 attention(如 TFT)时可人工补看,但不进标准图池,且必须与
  扰动证据交叉验证才能进结论;
- Dynamask / FIT / WinIT:需梯度或需训练生成模型,与黑盒契约冲突;
- LEFTIST / TSInterpret / time_interpret / InterpretML:分类向或无时序回归支持;
- 目标动力学分层误差(catch22 全样本分层):坏窗聚类+特征制式聚类已各盖一半,
  增量最小,记入 future;
- OmniXAI 反事实(MACE):与 pv-feature-blame 反事实功能重叠。

## 10. 实施顺序建议

1. 规范与地基:_recipe-spec §6(adapter 契约)+ category 字段 + CATEGORY_IDS
   + test_charts_decl 扩展;
2. 纯数据侧 11 张(无 serving_api 依赖,可并行):样本对比 2、误差结构 6、
   输入侧 1、模型对比 2、时间稳定 1;
3. attribution_common + 归因 3 张(shap 依赖 + 合成线性适配器 golden);
4. 归组呈现:orient 分组 + build_index.py;
5. 既有图增强 2 处 + CHANGELOG + engine-core.md 选择门描述更新。
