# 假设验证循环（pilot）验收记录

对应实施计划 Task 7。分支 `refactor/hypothesis-loop-pilot`。验收日期 2026-08-09。

## 1. 已验证：机器件在真 C1 冻结数据上端到端连通（无重训）

用 `eval-cases/tier2-c1/` 的冻结产物（无重新训练）驱动 pilot 全链路，真实数值：

| 环节 | 脚本 | 真实结果 | 与 gold 对照 |
|---|---|---|---|
| 切片测量 | `slice_zcheck.py` | 近端(1-24) z=13.81 real；中段(25-60) z=12.09 real；远端(61-96) z=1.03 ~noise；池化 gap=0.0073 | 方向一致、池化 gap **精确吻合** gold |
| 假设账本 | `hypothesis_ledger.py` | H1(component=itransformer.attention, switch=--itrans_no_attn, pre-registered)→ `validate_ledger`=[]（合法） | schema 一致 |
| 干预判定 | `ablation_verdict.py` | 真 I3(注意力置零) vs 基线 iTransformer 近端 delta=-0.0141（3 种子均值）vs 噪声底 0.0102 → **confirmed** | gold -0.0144→+0.0003，magnitude 吻合 |
| 结论闸 | `conclusion_gate.py` | 正控：带 receipt 的架构因果结论 → exit 0 过闸；负控：删掉 receipt 行 → exit 1 拦截、不写 receipt | 反伪造拦截在真实拼装结论上生效 |

全量单测 208/208，无回归。

结论：**生成器→账本→验证脊→结论闸这条主链，在真实数据上连通且产出与 gold 一致的判定。**

## 2. 待查（不阻塞，verdict 不受影响）

- `slice_zcheck` 的 z 量级（近端 13.8）高于 gold 记述的 ≈7-10。方向与池化 gap 一致，且 z 远超阈值 3（13.8 与 7-10 都 ≫3，判定不变），但 z 聚合口径可能与 gold 构造时的方法不同。需核对 `slice_zcheck` 的跨种子聚合是否与阶段 2 gold 构造脚本一致，以免真实使用中 z 数值口径漂移。

## 3. 尚未验证（deferred 到 lsf-mini 全环境，非本机可做）

本次是 **机器件连通性验收**，不是全链路盲跑。以下需用户在可重训环境跑：

1. **真 agent 无 gold 盲推**：本次直接用 gold 选定 H1/切片/开关；未验证 agent 自主从版图形成假设、选干预。
2. **C2/C3 盲跑**：仅跑了 C1 确认路径。
3. **subagent 成本轴**：本次全程在主上下文执行；未验证"每个干预强制外包、主 agent 只见 receipt"的实际 token 隔离。
4. **无 `trainable_framework` 回退路径**：未验证退化为"未验证假设"+ conclusion_gate 对无因果结论放行。
5. **refuted / kill_receipt 路径**：仅跑了 confirmed 路径（H1/I3），未跑 decoy 否证（I1/I4）。

## 4. 遗留加固项（whole-branch review 记录，非阻塞，已合并）

最终整分支评审（opus）确认 spec 覆盖完整、跨任务接口端到端对齐、213/213；已修两项后合并 main：
- **已修** FINAL-1：conclusion_gate rule 4 曾对全部 7 个过闸 playbook 生效（破坏 6 个非 pilot 的 zero-break）→ 改为仅当 playbook frontmatter 声明 `produces_ablation_receipts: true` 时触发（仅 architecture-attribution），加回归测试。
- **已修** FINAL-2：`validate_ledger` 对畸形顶层对象静默判合法 → 加顶层守卫 + 4 测试。

以下低优先加固项**未做、留待后续**（不影响 pilot 机器件正确性）：
1. **slice_zcheck z 口径**：C1 近端 z=13.8 高于 gold 述 ≈7-10（判定不受影响 ∵ 均≫3），但 z 聚合口径需与阶段 2 gold 构造脚本对齐——**lsf-mini 实跑前必解**，否则显示 z 数值漂移。
2. `conclusion_gate` 的 `## 消融证据` 切片到 EOF 而非下一个 `## ` heading（permissive，可镜像 `sec` 的截断加固）。
3. model-comparison §6 调色板 chart id 有效但无 CI 守卫（test_charts_decl 只校验 frontmatter）。
4. `validate_ledger` 未强制 `intervention`/`discriminating_power` 字段（生成器 prose always 写，故当前不炸）。
5. test_routing.py docstring 仍写 "10 个 playbook"（pre-existing stale）。
6. `_playbook-spec §4`（固定 8 节/穷举图声明）与新生成器形态冲突——**推广到其余 6 个分析 playbook 前必 reconcile**。

## 5. 结论

pilot 的**代码机器件已验证可用**（12 commits 已合并 main，213/213）；**归因能力的真实提升需 §3 全链路盲跑确认**，建议作为下一步在 lsf-mini + 真 agent loop 上执行。
