---
id: train-test-drift
needs_materials: [predict, truth, train_y]
适用问题: 测试期标签分布还像训练期吗？哪些月漂了、漂多少？
outputs:
  json: train-test-drift.json
  png: train-test-drift.png
json_schema: >
  by_month（日历月 → psi/ks_p/train-test 双侧 n/mean/std/p10..p90 分位摘要）、
  alert_months（PSI>阈值月列表）、psi_alert。
bridge_hooks: >
  某月 PSI 告警且该月误差也峰值（error-breakdown per_month）→ 分布漂移主导候选
  ——所有模型同时受害，与 model-error-correlation 高相关联判；PSI 全绿但误差
  抬升 → 排除标签漂移，转输入质量/模型侧。
验证步: 2 月 test 整体+20（PSI>0.25）、1 月同分布（PSI≈0）→ 告警列表恰为 ["2"]（tests/test_chart_train_test_drift.py）
---

# train-test-drift：训练/测试标签分布漂移

## 适用问题
"世界变了吗"的分布级证据；与 y-vs-feature-mapping（映射级）互为印证。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_train_test_drift.py \
  --pred predictions.parquet --train-y train_y.parquet \
  --out-dir <workdir>/charts [--psi-alert 0.25]
```
train_y 长表：`ts|unit_id|y`。v1 只做标签漂移；feature 漂移待训练期 feature
材料定义后扩展。

## JSON schema
见 frontmatter；月样本 <10 双侧任一即跳过该月（不进 by_month）。

## 判读
- `alert_months` 非空 → 候选：季节性/结构性漂移——对照 error-breakdown 的
  per_month 边际曲线看漂移月是否同为误差峰值月（两线一致才升假设）；
- PSI 高但 mean 差小（分位摘要形变）→ 候选：分布形状变（双峰/截断），看
  p10/p90 差异定位哪一侧；
- scipy 缺席时 ks_p=null，仅凭 PSI 判读（阈值 0.25 为业界惯例、可调）。
只给候选假设；结论回 playbook 三道门。

## 验证步
见 frontmatter。
