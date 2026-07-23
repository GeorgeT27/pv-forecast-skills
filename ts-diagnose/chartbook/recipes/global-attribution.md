---
id: global-attribution
category: attribution
needs_materials: [predict, truth, features, serving_api]
适用问题: 哪些输入特征对模型输出贡献最大?哪些只影响短期、哪些拖累远端 horizon?
outputs:
  json: global-attribution.json
  png: global-attribution.png
json_schema: >
  ranking(按 mean|SHAP| 降序的特征列表)、overall{特征: mean|SHAP|}、
  by_bucket(桶×特征矩阵,桶=horizon 等分)、bucket_defs、corr_groups
  (|ρ|≥0.8 特征组,组内归因需合并判读)、background_meta、explainer、seed、
  coverage{windows_evaluated, calls_used, truncated}。
bridge_hooks: >
  某特征 by_bucket 远端桶贡献占比高 → 该输入主导长程预测,其质量恶化优先
  拖累远端(与 horizon-degradation 晚段斜率交叉);corr_groups 内多特征
  分摊贡献 → 按组解读,勿点名单个;贡献极低的特征 → 冗余输入候选,
  剔除验证走 feature-importance playbook 的消融线。
验证步: 线性适配器 y=3fa+1fb+0fc、双簇背景 → overall 比值 3:1、fc≈0 精确回收;预算截断 coverage 如实(tests/test_chart_global_attribution.py)
---

# global-attribution:全局 Shapley 贡献与 horizon 分辨

## 适用问题
"模型主要在用哪些输入"的量化答案:玩家=特征,mask=0 用背景序列、=1 用
实际序列,KernelSHAP 分解每个 horizon 桶的输出。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_global_attribution.py \
  --pred predictions.parquet --features features.parquet \
  --adapter analysis_scripts/predict_adapter.py \
  --out-dir <workdir>/charts [--buckets 4] [--max-windows 30] \
  [--background-k 5] [--seed 0] [--max-calls 5000]
```
适配器需 perturb_features=True;shap 缺失时报错并提示 `pip install shap==0.44.1`。

## JSON schema
见 frontmatter;D≤8 全枚举(精确、零随机),D>8 采样(seed 落盘);
评估窗为 features∩predict 的完整窗采样(--max-windows,seed 同源)。

## 判读
- ranking 首位与末位差一个量级以上 → 输入重要性高度集中,末位是冗余候选;
- by_bucket 某特征远端桶份额显著高于近端 → 长程依赖该输入,与
  horizon-degradation/lookback-decay 交叉;
- corr_groups 非平凡组存在时,组内特征的贡献必须合并判读(相关特征分摊);
- coverage.truncated=true 时只下"已评估窗口内"的结论,不外推。
只给候选假设;结论回 playbook 三道门。

## 验证步
线性适配器(3/1/0)+ 8 窗双簇特征(0/1 各半,背景 k=2 → medoid 均值 0.5)
→ 每窗贡献 = coef×(x−0.5),overall 比值 fa/fb=3、fc≈0 精确回收;
by_bucket 每桶与 overall 同比值;max_calls 压小 → truncated=true 且
windows_evaluated < 全量,不抛崩。
