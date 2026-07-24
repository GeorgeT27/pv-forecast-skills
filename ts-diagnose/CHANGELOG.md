# CHANGELOG —— ts-diagnose

<!-- 每行：日期 | 改了哪个文件的哪节 | 触发这次改动的反馈原文（一句话） | 为什么这么改 -->

- 2026-07-14 | 首版落地（机制层 + SKILL + references 五篇 + playbook 三个） | 用户："现有技能针对特有情况写死，需要提取 workflow 做泛化技能，不确定时必须问用户，且要能固化回专用技能" | 引擎+playbook+profile 三层：workflow 与领域解耦；设计 spec 见 docs/superpowers/specs/2026-07-14-ts-diagnose-engine-design.md
- 2026-07-14 | 验证记录 | —— | 机制层 pytest 23 项全绿；training-sufficiency 合成数据影子验证全程走通（植入效应 m03/m08 均召回、五个验证步 PASS、必答题零跳过）；robustness / feature-importance orient dry-run 通过；crystallize 固化演练三步验证（冷启动 --profile / 快照冒烟 / 影子重跑 Stage 0 一致）全 PASS
- 2026-07-14 | 加固轮（三层加载/两道闸/三关判据/路由消歧/接口版本化，spec：docs/superpowers/specs/2026-07-14-ts-diagnose-hardening-design.md） | 用户："这些建议非常好，可不可以借鉴一下加强 skill？不一定全用，挑好的 idea" | SKILL.md 压成 41 行纯路由层（执行细节下沉 references/engine-core.md，test_layering.py 守预算 ≤60 行/~6K token）；playbook 目录化并各自带 golden/ 金标准（确定性植入效应）+ gen_gate.py 生成闸（金标准算错不许碰真实数据）+ provenance.py 归因闸（结论必附代码/数据 hash）；crystallize 升级三关判据（crystallize_gate.py 可执行：多样性 N≥3/ts=5、held-out、快照自洽）；路由优先级进四技能 description（test_routing.py 漂移守卫）；profile 的 experiment_line 打 interface_version: v0-draft 占位不生效。裁剪：模拟打分路由器（伪测试）→ 存在性守卫；held-out 场景库 / regression baselines 只预留接口位置（spec §6）。pytest 56 项全绿
- 2026-07-22 | 引擎 v2 框架：materials 盘点（11 类+三值状态+material: DSL+orient 盘点段）、contexts provider_skill 嵌入执行、profile 固化 materials | 用户："所有 skill 开始时都该搞清楚我们有什么…如何让一个 skill 调用一个 skill 然后回主流程" | 泛化 intake 与 skill 委托，为 chartbook（Plan 2）与 model-comparison/fact-scan（Plan 3）铺路
- 2026-07-22 | v2 chartbook 轮（A-C 组）：新增引擎级图谱库 chartbook/（规范长表 window_ts|unit_id|model|horizon_step|y_true|y_pred、chart_common 公共件、_recipe-spec 规范+一致性闸、9 个预写图脚本 A:error-breakdown/intraday-profile/worst-points B:horizon-degradation/rolling-stability C:true-vs-pred-scatter/model-error-correlation/worst-slice-compare/oracle-gap 全部合成植入回收 golden、example_adapter 对账两关样例）；engine-core 增 chartbook 豁免（预写图禁现场重写）；test_layering 守卫扩展至 chartbook | 用户："这些图工作量特别大，是要把代码写好吗，还是跑这个 skill 时现场写？"（决策：预写） | 预写+pytest 一次验证胜过每次现场写；JSON 一等产物/PNG 副产品；现场只写薄适配器过对账
- 2026-07-22 | v2 Plan 3 收口：D 组 3 图（feature-error-conditional/feature-trend-overlay/y-vs-feature-mapping）+E 组 train-test-drift、playbook 阶段级 charts 声明（orient 逐图可画性）、model-comparison 五阶段 playbook+fact-scan 体检 playbook（各带 golden 过 gen_gate）、路由表加两行+pv-result-analysis 反向让路 | 用户："用户进站直接跑 /ts-diagnose…比如用户想问模型A为什么比模型B要好" | 完成"盘点材料→自动画图→对比归因"闭环；体检与诊断分离（fact-scan 无结论阶段）
- 2026-07-23 | 证据可靠性加固：worst-slice-compare 内置按日块置换基线（统计量=最差片正差距，未过基线不点名切片）+ 新图 cross-dim-stability（时间对半/口径切换正交稳定性）+ mechanisms §2「证据维度」纪律 + model-comparison 升级三条腿（两线一致·噪声门·时间稳定；口径翻转限定口径不阻塞）+ golden 固定种子豁免边界 | 用户："我觉得你说的两个 suggestion 非常好，帮我写一个 spec" | 堵多重比较虚警与多图同源伪收敛；spec：docs/superpowers/specs/2026-07-23-ts-diagnose-evidence-hardening-design.md
- 2026-07-23 | 弱模型压力测试修复轮：test_layering/test_gen_gate 改动态发现（PLAYBOOK_IDS 目录扫描+下限断言、REFS 从 manifest reference 字段收集，新 playbook 不再静默脱守卫）+ spec §4.8 chartbook 覆盖声明硬规则（逐 recipe 声明或跳过）+ spec §5 植入难例形态规则 + spec §7 default 与菜谱同法自查 + mechanisms 反驳门 8「渐变-突变混淆」（时间定位双点齐报）+ engine-core 对账两关扩到一切整形脚本 + 停顿点模糊授权操作判据 + 新 playbook deployment-drift（部署后退化/漂移：切分点+onset 首离双点、置换基线、诱因双关筛查、ramp 难例 golden） | 用户："do a pressure test with another question…switch to sonnet…find out what need to be changed" | Sonnet 全流程压测（非光伏负荷退化+埋点数据）：路由/授权/新写 playbook/闸全过，但 onset 答错一周仍标高置信（切分点≠起始点）、日内维度整段漏查（无 chartbook 清单强制）、硬编码守卫盲区（GAPS G-1~G-7）；修复全部落 CI，pytest 263 绿
- 2026-07-23 | 图表选择门（画前增删图，engine 级）：任何声明 charts: 的阶段画图前必停一次 AskUserQuestion 多选——默认全选可画图（被动接受=画全套，守完整性），用户可删图（记 PROGRESS+CONCLUSION 声明覆盖缺口）或从「可加画池」加图（跨 playbook 任取材料满足的 recipe）；选择门=画前定范围 vs pause_after=画后定深挖，二者不合并。engine_common 加 declared_recipes/addable_recipes/has_chart_stage/recipe_min_models，orient 打印三组图+可加画池；recipe frontmatter 加 needs_models（对比类图=2，可加画池标注「需 ≥2 模型」防单模型误加，<N 运行时 ValueError 兜底），4 对比图（worst-slice-compare/oracle-gap/model-error-correlation/cross-dim-stability）已标；spec §4.8 补选择门与可加画池的衔接 | 用户："we might want to delete or add extra images for final analysis task"（压测追问后确认）+ 选 draw-all-default 与 add-any-applicable | pytest 266 绿

## 2026-07-23 chartbook 扩展第四轮(呈现层收口,28 图工程完结)
- orient 图表选择门按六类 category 分组:声明图带类别标签,可加画池分组呈现
  (engine_common.recipe_category);
- 新增 `chartbook/scripts/build_index.py`:扫产物目录生成 INDEX.md,按类别分节、
  只索引实际产物(28 图是库存非必画清单,不为没画的留空位);
- true-vs-pred-scatter 增强:Mincer-Zarnowitz 回归(y_true=a+b·y_pred)+
  a=0,b=1 联合 F 检验注记,配对正交噪声零随机精确 golden;
- Plan3 延后清单清扫:死 pandas import×4、背景集退化分支如实标 all-windows、
  双 RNG 播种注释、tests/conftest.py 集中 OpenMP 豁免(全套件回到 0 warnings)、
  lookback ref≈0 与负 φ 瀑布渲染补覆盖。

## 2026-07-23 chartbook 扩展第一轮:地基

- recipe frontmatter 强制 `category`(六类,engine_common.CATEGORY_IDS,conform CI 闸)
- id 领域名词闸(weather/station/solar/irradiance)+ 领域中立硬规则进 _recipe-spec §5.6
- `setup_font` 硬化为 CJK 回退链(返回命中列表);回填 row_analysis / analyze_row 两外围脚本
- 28 图扩展总设计:docs/superpowers/specs/2026-07-23-chartbook-expansion-design.md

## 2026-07-23 chartbook 扩展第三轮:模型归因层

- predict_adapter 契约进 _recipe-spec §6(CAPABILITIES+predict(requests)+get_model 白盒路);合成线性/lookback 双 golden 适配器
- attribution_common:加载校验、BudgetedAdapter(预算+请求哈希 jsonl 缓存)、background_set(kmeans-medoid,meta 落盘=守卫一)、feature_corr_groups(守卫二)
- 三图:global-attribution(KernelSHAP 双面板,梯度白盒路 --explainer auto)、lookback-decay(按桶遮蔽+逐窗有效历史)、local-waterfall(单行 φ 解析回收+防冤枉诱饵)
- chartbook 25→28 recipe,attribution 类首次有图,六类全满;依赖新增 shap==0.44.1(numpy 必须保持 1.26.4)
- 2026-07-24 | 弱模型加固 A+B：orient.py 目标阶段块打印「引擎级恒问五类·开工前自检」横幅（schema/判据/降级/破坏性/多版本，playbook 没声明也提醒——恒问五类此前只靠模型自觉，orient 不主动surфacing）+ 输出末尾打印「每回合先跑 orient 再动手」脚注；engine-core Step 0 增「引擎第一纪律：每回合先 orient 再动手、做完重跑、不凭记忆推进」（test_engine 新增横幅+脚注断言，109 绿） | 用户："我要用 256k 的 deepseek flash 弱模型跑这个 skill，检查是否够频繁用 subagent、小模型能否不漏步跑通" | 弱模型两大失效模式=不 notice 该问就假设开工 + 跑一次 orient 后脱离清单凭记忆推进；A 把恒问五类摆到每回合眼前，B 把 orient 重跑立为第一纪律并每回合脚注提醒
- 2026-07-24 | 弱模型加固 C：密集散文改即时打印编号清单——orient.py 图表选择门印 4 步编号清单（多选默认全勾/删图不静默记 PROGRESS+CONCLUSION/可加画/画完出 INDEX 再停顿），产 CONCLUSION.md 的结论阶段印「三道门自检」清单（门1 稳健·门2 假设登记·门3 反驳门 + 证据线/功效/provenance 收尾，just-in-time 不靠模型追 mechanisms.md 指针）；engine-core 同步两处 prose→编号清单（test_engine 三道门正/负例、test_charts_decl 清单断言，110 绿） | 用户："do c and commit and push"（弱模型加固 A+B 之后） | 弱模型失效模式之一=多分支密集散文只执行一支、指针懒得追；把最判断重的两处（画图门/结论三门）在该动手的那一回合直接打到眼前
