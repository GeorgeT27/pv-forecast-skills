# 影响力归因方法细节

本库承接 SKILL.md，放不进正文的方法学。四个方法：训练动力学（Stage 1）、影响力回归（Stage 2）、TracIn 梯度（Stage 3）、回放失效时的指派问题兜底（Stage 0）。

## 为什么随机重分组是天然实验

每迭代把 N 站随机重排进 K 个 chunk，是无混杂的随机化：某站进哪个 chunk 与它自身"好坏"无关。于是"训完含站 s 的 chunk 后留出站 RMSE 变化"的跨多迭代平均，就是**训练到 s 对留出站的因果边际效应**（在给定训练动力学下）。这正是分组随机子集数据估值（Banzhaf / Data-Shapley 的蒙特卡洛近似）的设定——我们不需要枚举子集，随机分组已经在采样子集。

## Stage 1：训练动力学（为什么不同 chunk 的 loss 不同）

### 指标（`loss_dynamics.py`，逐 (model, iteration, chunk)）
- **final_loss**：尾 `tail_k=3` 个 epoch 的均值（20 epoch/chunk 里去掉尾部抖动，比单末 epoch 稳）。
- **conv_slope**：`log(loss) ~ epoch` 的 OLS 斜率（log 让不同量级的 loss 曲线尺度稳健；负得越多 = 收敛越快，越接近 0 = 越慢/平台期）。
- **plateau_epoch**：首个进入 `final_loss×1.05` 的 epoch（多快到平台）。

### 站效应回归
与 Stage 2 **完全同款**的设计（中心化站指示 + 岭 + 控制 iteration/position/size，代码直接
import 复用 `influence_regression` 的实现，同一"和为零"语义）——只是因变量从 ΔRMSE 换成
final_loss / conv_slope。θ_s 读法："含站 s 的 chunk 终态 loss 相对平均站更高 / 收敛更慢"。

**逐模型独立、绝不跨模型 pool loss**：M1–M4 损失函数不同（Huber+正则 / MSE / MSE+频域 L1 / L1），
量纲不可比。跨模型只比 Spearman 排名（脚本已报 `cross_model_spearman`）。

### 解读流程（连接 <project-context>/stations.md / event-log —— 主 agent 的活，脚本只出数字）
拿到 `highest_final_loss_stations` / `slowest_converging_stations` 后，逐站对照
`<project-context>/stations.md` 的气候带/装机/数据质量字段 + `event-log.md`：
- 高 loss + 气候极端（高原/戈壁等，与多数站差异大）= 分布难拟合，**预期内**，不是问题。
- 高 loss + 气候平凡（和多数训练站相似却难学）= **数据质量红旗**（限电/坏 NWP/传感器），
  走 suspect_days / event-log 核查——修数据，别急着怪站。
- stations.md 空字段照旧"不编造"：解释不出就写"待补站点档案"。

### 与负迁移的关系（关键边界：loss 高 ≠ 有罪）
"含 s 的 chunk loss 高"说明 s **自己难学**；"s 拖累留出站"是另一回事——两者可同真、同假、交叉。
四象限（θ_loss = Stage 1 loss 效应，θ_harm = Stage 2 回归系数）：

| | θ_harm 高（拖累留出站） | θ_harm 低 |
|---|---|---|
| **θ_loss 高（难学）** | 脏数据既难学又污染 → 数据质量红旗优先 | 难学但方向无害 → 留着无妨 |
| **θ_loss 低（学得顺）** | **学得顺但把参数拉离留出站 = 真·分布冲突的典型指纹** | 双低，正常站 |

`rmse_link` 的 Spearman（final_loss × ΔRMSE 同现）只是**同现证据**：进反驳门当佐证，
不单独给任何站定罪，也不能替代 Stage 2/3 的两法一致门槛。

## Stage 2：影响力回归

### 因变量：差分去趋势
`ΔRMSE(i,c) = RMSE_留出站(训完 chunk c) − RMSE_留出站(训完上一个 chunk)`。按**全局训练顺序** `(iteration, position)` 差分（`influence_regression._delta_rmse`）。差分消掉"训练整体在缓慢变好/变差"的慢趋势，只留每个 chunk 的**增量冲击**，这才是站效应的载体。

### 设计矩阵与"和为零"参数化（关键坑）
朴素想法：`ΔRMSE = α + Σ_{s∈chunk} θ_s + 控制`。但每迭代每站恰好进一个 chunk ⇒ 一迭代的 K 行里每个站指示恰好 1 次，`Σ_s 指示 = size`，与截距/size 控制**共线**（虚拟变量陷阱的变体）。后果：θ_s 只能识别到一个公共常数的差。

处理（脚本实现）：
1. **中心化站指示**（减去该 chunk 的平均占用）弱化陷阱；
2. **岭回归**（`--lam`，截距不罚）稳住共线方向；
3. 把 θ_s 解释为**相对平均站的相对有害度**（sum-to-zero 语义）——"θ_s 高 = 比平均站更拖累留出站"，不是绝对 RMSE 增量。排名与相对比较有效，绝对数值别过度解读。

> chunk 大小不全相等时其实弱识别了绝对水平（打破了精确共线），但样本少时别指望，仍以相对排名为准。

### 控制变量
`iteration`（学习率/成熟度随训练变化）、`position`（chunk 在迭代内先后 = 新近效应）、`size`（各 chunk 大小不一）。不控制这些，站效应会被训练阶段效应污染。

### 不确定性与功效
- Bootstrap over 观测行（`--boot`）给每个 θ_s 的 95% CI；**CI 排除 0** 才算方向可信。
- 参数数 ≈ 1(截距)+N(站)+3(控制)=N+4；观测数 = 每模型 (K×迭代数 − 1)。迭代数够多时观测量勉强够；**迭代 < 10 ⇒ 观测 < 参数量级，只报排名不报显著性**（脚本 `power_note` 会提示）。
- 想更稳：pooled across 模型（加 model 固定效应）扩大样本；或 leave-one-iteration-out 看排名稳不稳。

### 第二因变量（可选）：新近 vs 任意位置有害
把"每迭代末留出站 RMSE" 回归到"**最后一个 chunk** 有哪些站"，分离"只有排在最后才拖累（新近/遗忘型）"与"在任何位置都拖累（真·分布冲突型）"。两者处理不同：前者是训练顺序问题（混站/回放缓冲可解），后者才是"该不该留这个站"。

## Stage 3：TracIn 梯度佐证

### 原理
一阶泰勒：某步在 batch B 上更新，会让测试损失变化 ≈ −lr·⟨g_B, g_test⟩。累加多个 checkpoint：`influence(s) ≈ Σ_ckpt ⟨g_s, g_test⟩`（TracInCP）。⟨g_s, g_test⟩ **持续为正** = 训 s 也在降留出站损失（有益）；持续为负 = 把参数推离留出站（有害）。

### 脚本约定
- `tracin_influence.py` 用**余弦式**归一内积（除以两侧范数）让跨 checkpoint 可比、不被某站梯度大小主导。
- **符号**：脚本输出的 `harm_score = −Σ cos(g_s, g_test)`，**取负**是为了"高=拖累"与 Stage 2 的 θ_s 同向，便于直接比排名。
- 降成本：`--every N` 每 N 迭代取一个 checkpoint、默认只取每迭代最后一个 chunk 的权重；`--n-windows` 控制每站梯度用多少窗口（固定子样本、固定顺序保证可比）；`adapter.loss_gradient` 的 `params_filter` 可只取最后线性头降内存。
- 多卡/多机分片：`--models M1 --raw tracin_dots.M1.csv --out tracin_scores.M1.json` 各写各的，主 agent 合并原始 CSV 后重跑一次汇总（单卡别分片，无收益）。

### 与 Stage 2 的关系（升级门槛）
两条**独立**证据线：回归吃的是 RMSE 序列（含噪声、含遗忘），TracIn 吃的是梯度几何（与 RMSE 记录无关）。脚本报两两 Spearman；**排名一致的站才从"现象"升"假设"**。不一致要解释（如某站 TracIn 有害但回归无感 = 梯度冲突被后续恢复，非持久损害）。

## Stage 0：回放失效时的指派问题兜底

正常路径：`adapter.sample_assignments(iteration, seed)` 用训练同款 RNG 复现分组。**风险**：numpy/torch 版本或 RNG 流程与训练不一致 → 回放的分组是错的但看起来合理。故 `--validate` 做**新近效应指纹**抽查：训完某 chunk，模型对该 chunk 的成员站 RMSE 改善应最大；回放成员与"改善 Top-k"重叠 <60% 就判回放不可信。

回放不可信时的兜底（未内置、需要时实现）：对**每个 chunk** 用指纹法估成员——`gain[s] = RMSE_before(s) − RMSE_after(s)`（在全部 N 站上评估 before/after checkpoint）。再利用**硬约束**：每迭代必须把 N 站无重叠地分进 K 个 chunk（大小见实验线 chunking）。这是一个指派问题：在 `gain` 矩阵上求"每站恰好归一个 chunk、每 chunk 恰好 size 个站、总 gain 最大"的分配（匈牙利/ILP）。得到的 assignments 再喂 Stage 1/2。成本：每迭代要 before/after 在 N 站上各评估一次，比纯回放贵得多——所以优先修回放。

## 处理决策（Stage 5 之后）

确认某站有害后不是只有"删掉"一条路：
- **真·分布冲突**（气候远、任意位置都有害、气象/功率映射差异大）→ 从训练集剔除，或改**相似度加权采样**（偏向留出站气候的站多采）。
- **新近型有害**（只有排最后才拖累）→ 不必删，改训练顺序 / 混站 batch / 小回放缓冲。
- **数据质量红旗**（气候明明相似却有害）→ 先查限电/坏 NWP/传感器（走 result-eval playbook 的 suspect_days + event-log），修数据而非删站。
