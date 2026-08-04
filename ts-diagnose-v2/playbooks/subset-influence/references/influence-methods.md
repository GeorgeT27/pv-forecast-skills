# 影响力归因方法细节

本文承接 playbook.md 正文，收纳放不进正文的方法学细节：训练动力学（Stage 1）、影响力回归（Stage 2）、TracIn 梯度（Stage 3）、回放失效时的指派问题兜底（Stage 0）。

## 为什么随机重分组是天然实验

每次迭代把 N 站随机重排进 K 个 chunk，是一次无混杂的随机化：某站进哪个 chunk，与它自身数据"好坏"无关。于是把"训完含站 s 的 chunk 后，留出站 RMSE 的变化"在多次迭代上平均，得到的就是**训练到 s 对留出站的因果边际效应**（在给定训练动力学下）。这正是"分组随机子集"数据估值（Banzhaf / Data-Shapley 蒙特卡洛近似）的设定——不需要枚举所有子集，随机分组本身已经在采样子集。

## Stage 1：训练动力学（为什么不同 chunk 的 loss 不同）

### 指标（`loss_dynamics.py`，逐 (model, iteration, chunk)）
- **final_loss**：尾 `tail_k=3` 个 epoch 的均值（取尾部均值去掉末尾抖动，比只看最后一个 epoch 稳）。
- **conv_slope**：`log(loss) ~ epoch` 的 OLS 斜率。斜率负得越多 = 收敛越快，越接近 0 = 收敛越慢/进入平台期。
- **plateau_epoch**：首个进入 `final_loss×1.05` 范围的 epoch，衡量多快到平台。

### 站效应回归
与 Stage 2 **完全同款**的回归设计：中心化站指示 + 岭回归 + 控制 iteration/position/size，同一"和为零"语义；代码直接 import 复用 `influence_regression` 的实现。唯一区别是因变量从 ΔRMSE 换成 final_loss / conv_slope。系数 θ_s 的读法："含站 s 的 chunk，终态 loss 相对平均站更高 / 收敛更慢"。

**逐模型独立、绝不跨模型 pool loss**：M1–M4 四个模型的损失函数不同（Huber+正则 / MSE / MSE+频域 L1 / L1），loss 量纲不可比。跨模型只比 Spearman 排名（脚本已报 `cross_model_spearman`）。

### 解读流程（连接 <project-context>/stations.md / event-log —— 主 agent 的活，脚本只出数字）
拿到 `highest_final_loss_stations` / `slowest_converging_stations` 两个排名后，逐站对照
`<project-context>/stations.md` 的气候带/装机/数据质量字段 + `event-log.md`：
- 高 loss + 气候极端（高原/戈壁等，与多数站差异大）= 分布本身难拟合，**预期内**，不是问题。
- 高 loss + 气候平凡（和多数训练站相似却难学）= **数据质量红旗**（限电/坏 NWP/传感器），
  走 suspect_days / event-log 核查——先修数据，别急着怪站。
- stations.md 有空字段时照旧"不编造"：解释不出来就写"待补站点档案"。

### 与负迁移的关系（关键边界：loss 高 ≠ 有罪）
"含 s 的 chunk loss 高"只说明 s **自己难学**；"s 拖累留出站"是另一回事。两者可以同真、同假，也可以交叉。用四象限判读（θ_loss = Stage 1 的 loss 效应，θ_harm = Stage 2 的回归系数）：

| | θ_harm 高（拖累留出站） | θ_harm 低 |
|---|---|---|
| **θ_loss 高（难学）** | 脏数据既难学又污染 → 数据质量红旗优先 | 难学但方向无害 → 留着无妨 |
| **θ_loss 低（学得顺）** | **学得顺但把参数拉离留出站 = 真·分布冲突的典型指纹** | 双低，正常站 |

`rmse_link` 的 Spearman（final_loss × ΔRMSE 同现）只是**同现证据**：可以进反驳门当佐证，
但不能单独给任何站定罪，也不能替代 Stage 2/3 的两法一致门槛。

## Stage 2：影响力回归

### 因变量：差分去趋势
`ΔRMSE(i,c) = RMSE_留出站(训完 chunk c) − RMSE_留出站(训完上一个 chunk)`。按**全局训练顺序** `(iteration, position)` 做差分（实现在 `influence_regression._delta_rmse`）。差分消掉训练整体缓慢变好/变坏的慢趋势，只留每个 chunk 带来的**增量冲击**——站效应的载体。

### 设计矩阵与"和为零"参数化（关键坑）
朴素回归 `ΔRMSE = α + Σ_{s∈chunk} θ_s + 控制` 有共线陷阱：每次迭代每个站恰好进一个 chunk，一次迭代的 K 行里每个站指示恰好出现 1 次，`Σ_s 指示 = size`，与截距/size 控制**共线**。后果：θ_s 只能识别到"相差一个公共常数"的程度，绝对水平不可辨。

处理办法（脚本已实现）：
1. **中心化站指示**（每个指示减去该 chunk 的平均占用）弱化陷阱；
2. **岭回归**（`--lam`，截距不罚）稳住共线方向；
3. 把 θ_s 解释为**相对平均站的相对有害度**（sum-to-zero 语义）——"θ_s 高 = 比平均站更拖累留出站"，不是绝对 RMSE 增量。排名与相对比较有效，绝对数值别过度解读。

> 补充：chunk 大小不全相等时精确共线被打破，绝对水平弱可识别；但样本少时别指望这一点，仍以相对排名为准。

### 控制变量
`iteration`（学习率/模型成熟度随训练变化）、`position`（chunk 在迭代内的先后 = 新近效应）、`size`（各 chunk 大小不一）。不控制这些，站效应会被训练阶段效应污染。

### 不确定性与功效
- Bootstrap over 观测行（`--boot`）给每个 θ_s 的 95% CI；**CI 排除 0** 才算方向可信。
- 参数数 ≈ 1(截距)+N(站)+3(控制)=N+4；观测数 = 每模型 (K×迭代数 − 1)。迭代数够多时观测量勉强够；**迭代 < 10 ⇒ 观测数与参数数同量级甚至更少，只报排名不报显著性**（脚本 `power_note` 会提示）。
- 想更稳的两个办法：pooled across 模型（加 model 固定效应）扩大样本；或 leave-one-iteration-out 看排名稳不稳。

### 第二因变量（可选）：新近 vs 任意位置有害
把"每次迭代末的留出站 RMSE"回归到"**最后一个 chunk** 有哪些站"上，分离两种有害：只有排在最后才拖累（新近/遗忘型），与在任何位置都拖累（真·分布冲突型）。两者处理完全不同：前者是训练顺序问题，混站 batch 或回放缓冲可解；后者才涉及"该不该留这个站"。

## Stage 3：TracIn 梯度佐证

### 原理
一阶泰勒展开：某一步在 batch B 上做参数更新，会让测试损失变化 ≈ −lr·⟨g_B, g_test⟩。在多个 checkpoint 上累加，得到 `influence(s) ≈ Σ_ckpt ⟨g_s, g_test⟩`（TracInCP）。⟨g_s, g_test⟩ **持续为正** = 训 s 也在降低留出站损失（有益）；持续为负 = 把参数推离留出站（有害）。

### 脚本约定
- `tracin_influence.py` 用**余弦式**归一内积（除以两侧梯度范数），让不同 checkpoint 之间可比、不被某个站的梯度大小主导。
- **符号**：脚本输出的 `harm_score = −Σ cos(g_s, g_test)`，**取负**让"数值高 = 拖累"，与 Stage 2 的 θ_s 同向，便于直接比排名。
- 降成本手段：`--every N` 每 N 个迭代取一个 checkpoint，且默认只取每次迭代最后一个 chunk 的权重；`--n-windows` 控制每站梯度用多少窗口（固定子样本、固定顺序，保证可比）；`adapter.loss_gradient` 的 `params_filter` 可只取最后线性头的梯度，降内存。
- 多卡/多机分片：`--models M1 --raw tracin_dots.M1.csv --out tracin_scores.M1.json` 各写各的分片文件，主 agent 合并原始 CSV 后重跑一次汇总（单卡别分片，没有收益）。

### 与 Stage 2 的关系（升级门槛）
两条**独立**证据线：回归吃的是 RMSE 序列（含噪声、含遗忘效应），TracIn 吃的是梯度几何（与 RMSE 记录完全无关）。脚本报两两 Spearman；**排名一致的站才从"现象"升"假设"**。不一致时要解释原因（如某站 TracIn 有害但回归无感 = 梯度冲突被后续训练恢复，没造成持久损害）。

## Stage 0：回放失效时的指派问题兜底

正常路径：`adapter.sample_assignments(iteration, seed)` 用与训练同款的 RNG 复现分组。**风险**：numpy/torch 版本或 RNG 调用流程与训练当时不一致 → 回放出来的分组是错的，但表面上看起来完全合理。所以 `--validate` 做**新近效应指纹**抽查：训完某个 chunk，模型对该 chunk 成员站的 RMSE 改善应该最大；若回放出的成员与"改善 Top-k"重叠 <60%，判回放不可信。

回放不可信时的兜底（未内置，需要时再实现）：对**每个 chunk** 用指纹法反推成员——在全部 N 站上分别评估该 chunk 前后的 checkpoint，得 `gain[s] = RMSE_before(s) − RMSE_after(s)`。再利用**硬约束**：每次迭代必须把 N 站无重叠地分进 K 个 chunk（各 chunk 大小见实验线 chunking）。这是一个指派问题：在 `gain` 矩阵上求"每站恰好归一个 chunk、每 chunk 恰好 size 个站、总 gain 最大"的分配（匈牙利/ILP）。得到的 assignments 再喂给 Stage 1/2。成本提醒：每次迭代都要在 N 站上各评估一次 before/after checkpoint，比纯回放贵得多——优先把回放修好。

## 处理决策（Stage 5 之后）

确认某站有害后，不是只有"删掉"一条路，按类型选处理：
- **真·分布冲突**（气候远、任意位置都有害、气象/功率映射差异大）→ 从训练集剔除；或改**相似度加权采样**——气候与留出站相似的站多采一些。
- **新近型有害**（只有排最后才拖累）→ 不必删，改训练顺序 / 混站 batch / 小回放缓冲即可。
- **数据质量红旗**（气候明明相似却有害）→ 先查限电/坏 NWP/传感器（走 result-eval playbook 的 suspect_days + event-log），修数据而非删站。
