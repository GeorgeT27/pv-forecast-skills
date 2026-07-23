---
id: lookback-decay
category: attribution
needs_materials: [predict, truth, serving_api]
适用问题: 模型依赖多长的历史?短期记忆还是长期记忆?
outputs:
  json: lookback-decay.json
  png: lookback-decay.png
json_schema: >
  lookback_steps、bucket_defs(步区间,近→远)、delta_by_bucket(遮蔽该桶后
  预测相对未遮蔽的 RMSE 变化;预算截断时短于 bucket_defs)、
  buckets_evaluated(已完成桶数)、weights(Δ⁺ 归一,全零或桶不全时 null)、
  short_term_share(近期桶权重和;近期=1 主周期内,无周期时=最近一步+近
  四分位段;桶不全时 null)、per_instance{hist,median}(可选:逐窗有效历史
  步数)、coverage(含 truncated)、seed。
bridge_hooks: >
  weights 集中最近桶 → 短记忆模型:远端 horizon 退化时优先查输入质量而非
  历史长度;远桶权重可观 → 长程依赖:训练数据的久远分布漂移会伤它
  (与 train-test-drift 交叉);全桶 Δ≈0 → 模型几乎不用历史(用协变量),
  与 global-attribution 互证。
验证步: 只读最近一步的合成适配器 → 最近桶 weight=1、其余 0、per-instance 中位数 1;无 lookback 能力适配器抛 ValueError;预算中途耗尽 → 已完成桶保留、weights/short_term_share 置 null、truncated=true(tests/test_chart_lookback_decay.py)
---

# lookback-decay:按桶遮蔽的历史依赖衰减

## 适用问题
"模型的记忆有多长"——按窗遮蔽(整桶置基线)比逐点便宜一个量级;
Δ 相对**未遮蔽预测**度量(纯依赖度量,与真值无关)。

## CLI 与参数
```bash
python3 chartbook/scripts/chart_lookback_decay.py \
  --pred predictions.parquet --adapter analysis_scripts/predict_adapter.py \
  --out-dir <workdir>/charts [--period-steps N] [--max-windows 30] \
  [--seed 0] [--max-calls 5000] [--per-instance]
```
适配器需 perturb_lookback=True(否则 ValueError,选择门如实标注)。

## JSON schema
见 frontmatter;桶从最近向最远:[最近 1 步] [近四分位] [至主周期(或半窗)]
[更远],由 lookback_steps 与 --period-steps 推出,def 落 JSON。

## 判读
- weights 集中最近桶且曲线陡衰减 → 短记忆——**这在 Transformer 系是文献
  常态,平坦/短依赖 ≠ 模型差**,勿据此单独下负面结论;
- per_instance 分布双峰 → 部分样本依赖长历史,可与 bad-window-clustering
  的坏窗簇交叉(某簇是否都在长依赖侧);
- 全桶 Δ≈0 → 历史几乎不被使用,转 global-attribution 看协变量侧。
只给候选假设;结论回 playbook 三道门。

## 验证步
只读最近一步的适配器(L=8)→ 遮最近桶 Δ=1、其余桶 Δ=0 → weights=[1,0,0,0]、
short_term_share=1;--per-instance 全窗 h*=1;线性(无 lookback)适配器抛 ValueError;
预算中途耗尽(如 max_calls 只够 base+前 2 桶)→ delta_by_bucket 只保留已完成的
桶(如实变短)、buckets_evaluated 对应变小、weights/short_term_share 置 null(桶
不全不做归一,避免误导)、coverage.truncated=true——一个桶都没完成才抛
ValueError,已完成的桶不再因超预算被整体丢弃。
