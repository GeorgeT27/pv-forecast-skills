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

## 2. 待查 → **已解决（2026-08-10，见 §6）**

~~`slice_zcheck` 的 z 量级（近端 13.8）高于 gold 记述的 ≈7-10。~~ 根因已定位并修复：`paired_z` 算的是配对 t 统计量而非效应量。详见 §6。

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
1. ~~**slice_zcheck z 口径**~~ → **已修，见 §6**。
2. `conclusion_gate` 的 `## 消融证据` 切片到 EOF 而非下一个 `## ` heading（permissive，可镜像 `sec` 的截断加固）。
3. model-comparison §6 调色板 chart id 有效但无 CI 守卫（test_charts_decl 只校验 frontmatter）。
4. `validate_ledger` 未强制 `intervention`/`discriminating_power` 字段（生成器 prose always 写，故当前不炸）。
5. test_routing.py docstring 仍写 "10 个 playbook"（pre-existing stale）。
6. `_playbook-spec §4`（固定 8 节/穷举图声明）与新生成器形态冲突——**推广到其余 6 个分析 playbook 前必 reconcile**。

## 5. 结论

pilot 的**代码机器件已验证可用**（12 commits 已合并 main，213/213）；**归因能力的真实提升需 §3 全链路盲跑确认**，建议作为下一步在 lsf-mini + 真 agent loop 上执行。

## 6. slice_zcheck z 口径修复（2026-08-10）

**根因**：`paired_z` 返回配对 t 统计量 `mean/(sd/√n)`，但阈值 3 承载的是「3σ 噪声底」语义——与同一验证脊上的 `ablation_verdict.verdict()`（`abs(delta) < noise_floor_3sigma` → undecided）、`case.json` 的 `noise_floor_3sigma` 字段、playbook Stage 0 的 `noise_floor_3sigma = std * 3` 同族。多出的 √n 因子把实际判据压成 `3/√n · σ`（n=3 时 1.73σ），且**种子越多门槛越松**（n=10 → 0.95σ），与噪声底纪律方向相反。

**证据**（真实 C1 冻结数据，delta 与 gold 逐个精确吻合，只有 z 不同）：

| 切片 | gold 声明 | 修前 `m/(sd/√3)` | 修后 `m/sd` |
|---|---|---|---|
| 近端 lead 1-24 | z≈7-10 | 13.81 ✗ 出界 | **7.97** ✓ |
| 上午 7-12 爬坡 | z≈9 | 12.16 ✗ | **7.02** ✓ |
| 午后 13-15 | z≈5-11 | 15.69 ✗ | **9.06** ✓ |
| 远端 lead 61-96 | 无差异 | 1.03 ~noise ✓ | 0.59 ~noise ✓ |
| I3 干预后近端 | z→0.1 | 0.18 ✗ | **0.11** ✓ |

**能力影响（非数值美观问题）**：修前，I3 消融后中段/远端/午后被判 `real`（-4.09 / -5.00 / -3.60），会报成"干预使这些切片显著反转"；修后全部落噪声内（-2.36 / -2.89 / -2.08），与 gold 叙事「午后优势**消失**」一致。旧口径会凭空造出假阳性并带偏归因叙事。基线切片版图的 real/~noise 判定在两种口径下完全一致，故 §1 的机器件连通结论不受影响。

**改动**：`slice_zcheck.paired_z` 去掉 √n；模块/函数文档串写明口径与其与 `ablation_verdict` 的一致性；`architecture-attribution` golden manifest 的 z 期望带宽随口径重固化（far 6.93→4.0、near 0.15→0.088，verdict 不变）+ make_golden.py 注释同步；playbook §1 实证数值改为可复现的 8.0 / 9.1，Stage 0 判读段加一句 z 口径说明。新增 4 个测试：口径钉死（z 必须 = 4.0 而非 6.93）、加种子不得放松判据、C1 近端 z 落 gold 区间、I3 干预后 z 塌到 ≈0.1。全量 440/440。
