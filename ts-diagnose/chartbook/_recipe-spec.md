# chartbook recipe 编写规范（_recipe-spec）

chartbook = ts-diagnose 引擎级共享图谱库（**不是独立 skill**；layering：引擎层共享合法，
playbook 只许按 recipe id 引用，playbook 之间照旧互不引用）。一图一 recipe：
`recipes/<id>.md`（本规范）+ `scripts/chart_<id 蛇形>.py`（预写脚本）+
`tests/test_chart_<id 蛇形>.py`（合成植入回收 golden）。

## 1. 预写纪律

图脚本**预写、随引擎提交、pytest 验证**——运行时禁止现场重写 chartbook 已覆盖的图；
现场唯一要写的代码是薄适配器 `analysis_scripts/adapter.py`（用户数据 → §2 规范长表，
由 `materials.<id>.schema` 驱动），写完必须过**对账验证步**：
①行数守恒（长表行数 == 源数据行数 × horizon 步数，缺测另行说明）；
②抽 3 个窗口人工核对数值与源一致。对账记录写 PROGRESS.md。

## 2. 规范长表（canonical long format）

```
predictions: window_ts | unit_id | model | horizon_step | y_true | y_pred
```

- `window_ts` 预报发起时刻（datetime）；`unit_id` 单元（站点/序列）；
  `horizon_step` 0 起整数；误差恒为 `err = y_pred − y_true`。
- 单模型场景 model 列填一个常量名即可；单单元场景 unit_id 同理。

## 3. Frontmatter schema（orient/校验测试机器读）

```yaml
---
id: horizon-degradation            # 必填，== 文件名（去 .md），kebab-case
category: error-structure          # 必填,∈ engine_common.CATEGORY_IDS
                                   #   (error-structure/temporal-stability/input-side/
                                   #    model-comparison/sample-contrast/attribution)
                                   #   呈现层按类归组(orient 选择门 + INDEX.md)
needs_materials: [predict, truth]  # 必填，⊆ engine_common.MATERIAL_IDS；orient 据此报可用性
needs_models: 1                    # 可选，默认 1；对比类图填 2（<该数模型抛 ValueError，见 §5.5）——
                                   #   图表选择门的「可加画池」据此标注「需 ≥N 模型」，避免误加结构性不适用的图
适用问题: 短期准长期崩？退化速度对比？   # 必填，一句话（路由与 playbook 选图依据）
outputs:
  json: horizon-degradation.json   # 必填，== "<id>.json"（一等产物）
  png: horizon-degradation.png     # 必填，== "<id>.png"（人看的副产品）
json_schema: >                     # 必填，JSON 关键字段的自然语言描述
  每模型每 horizon 指标曲线（curve_stats）、早/晚段斜率、模型交叉点、per-unit 崩溃点
bridge_hooks: >                    # 必填，形状描述符 → 架构假设的映射指引
  晚段斜率陡且早段平 → 长程依赖衰减类假设
验证步: 合成已知退化曲线 → 脚本必须回收植入的斜率与交叉点   # 必填，一句话
---
```

## 4. 正文必备节

1. **适用问题**——什么诊断问题该看这张图；
2. **CLI 与参数**——精确命令行（含默认值）；
3. **JSON schema**——逐字段说明（完整、自足：判读只读它）;
4. **`## 判读`**——形状描述符 → 候选机制 → 去哪张图交叉验证。只给**候选假设**，
   结论必须回 playbook 三道门；判读读 `curve/trend/max_jump/roughness/argmax` 等
   描述符数字，**不 Read PNG**；
5. **验证步**——本图 golden 植入了什么、回收断言是什么（对应 tests/ 文件）。

## 5. 硬规则

1. JSON 一等、PNG 副产品——没有 JSON 的图不算完成；JSON 必须自足（完整数字+描述符）。
2. compute()（纯计算，被 golden 测）与 render()（画图）分离；main(argv=None) 可注入。
3. golden 决定论：合成数据零随机（幅度+奇偶交替符号 ⇒ 单元格 RMSE == 幅度）；
   脚本内固定种子置换例外——种子显式 CLI 参数并落 JSON，期望由同种子实跑钉住。
4. 每脚本 CLI 公共参数：`--pred`（规范长表路径）、`--out-dir`；其余 recipe 特有。
5. 多模型才有意义的图（对比类）在 <2 模型时抛 ValueError 并说明，不静默出空图。
6. **领域中立**:recipe 的 id/frontmatter 字段/图内标签/判读不得出现领域名词
   (天气/站点/光伏/医学等;id 英文黑名单 weather/station/solar/irradiance 由
   test_recipes_conform 闸)。领域语义只允许运行时经 intake 背景(data_profile)
   注入呈现层——如给聚类簇起领域名。周期性假设图(如 intraday-profile)须在
   recipe 内标注"周期性数据专用",orient 按 data_profile 判断适用。

## 6. 模型访问契约(predict adapter;attribution 类图专用)

attribution 类图(needs_materials 含 serving_api)不碰用户模型,只认运行时
薄适配器 `analysis_scripts/predict_adapter.py`(与 §1 的 adapter.py 同款纪律:
现场唯一要写的代码;golden 模板在 `golden/example_predict_adapter/`):

```python
CAPABILITIES = {
    "perturb_features": True,    # 支持特征替换(global-attribution/local-waterfall 需要)
    "perturb_lookback": False,   # 支持历史窗遮蔽(lookback-decay 需要)
    "torch_module": False,       # True 时须实现 get_model()(梯度白盒加速路)
    "lookback_steps": 0,         # perturb_lookback=True 时必填:历史窗长度(步)
    "features": ["..."],         # 可扰动特征名全集
}

def predict(requests):
    """requests: list[dict]——unit_id, window_ts,
       feature_overrides: {特征名: list[float] 长=horizon} | 缺省用模型自己的输入,
       lookback_mask: list[[start,end]] 半开步区间(0=最旧) | 缺省不遮蔽。
    返回 DataFrame: request_idx | horizon_step | y_pred(request_idx=请求在本批的
    下标——同一批可含同窗不同扰动的请求,必须靠它区分;unit_id/window_ts 列可选)。"""

def get_model():
    """torch_module=True 时实现:返回 (torch_model, background_X, explain_X,
    feature_names)——model 输入 (N,D) tensor、输出 (N,B);GradientExplainer 用。"""
```

用户给 FastAPI 就在 predict 里打 API,给本地模型就本地推理——预写脚本无感。
能力不满足的图由选择门如实标注不可画。归因脚本经 attribution_common 的
BudgetedAdapter 调用:预算上限(--max-calls,超限截断记 coverage)+ 请求哈希
缓存(jsonl,重跑不重打)。背景集定义与所用 explainer/种子必须落盘进归因
JSON(background_meta)——换背景集=换归因基线。
