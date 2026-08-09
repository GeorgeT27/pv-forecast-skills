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

## 4. 结论

pilot 的**代码机器件已验证可用**；**归因能力的真实提升需上述全链路盲跑确认**，建议作为下一步在 lsf-mini + 真 agent loop 上执行。
