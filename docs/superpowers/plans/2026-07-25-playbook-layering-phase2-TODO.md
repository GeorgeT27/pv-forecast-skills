# Playbook 分层 Phase 2 待办（试点验证后另出实施计划）

前置：Phase 1 已合入且 model-comparison 试点在真实数据上至少跑通一次。

1. 批量改造剩余 6 个 playbook（逐个 task，模式照 model-comparison 试点）：
   - result-eval / deployment-drift / robustness：upstream setup(required)，
     删各自适配对齐阶段，charts 收窄到目标核心集（result-eval 保留月度归因组；
     deployment-drift 保留时序稳定组；robustness 保留切分稳定组），
     chart_sweep 设为 optional 上游供广谱复用；
   - feature-importance：upstream setup(required)；feature_true 对照与反事实
     材料线不动；
   - subset-influence：upstream setup(required) + model_profile(optional)；
   - training-sufficiency：不依赖 setup（记录源是训练日志不是预测长表）——
     改为读 setup manifest 的 training_log 位置作可选加速（optional），
     Stage 0 探测记录源保留。
2. 各 playbook golden manifest 的 stage 键随阶段重编号平移；正文阶段号与
   gen_gate --stage 参数同步。
3. contexts: 机制退役：spec 删 §contexts、engine_common 删 context_status/
   context_embed_hint、orient 删 contexts 循环、test_engine 删对应用例——
   前提：grep 确认全部 playbook 无 contexts 声明。
4. modelmap_blocker 评估是否降级为普通 upstream 声明（model_code present 时
   model_profile 自动升 required 的规则能否用 variants 表达）。
5. 固化（crystallize）与 profile 机制对 products 的兼容：profile 是否允许携带
   products 登记（倾向不允许——产物是每次运行的现场事实，如 degraded_ok 同理）。
6. 提问纪律文档（question-discipline.md）补「上游产物拥有的问题」一节。
