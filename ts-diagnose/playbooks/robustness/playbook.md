---
id: robustness
name: 鲁棒性分析
goal: 检验结论/模型表现在扰动（剔极端、子期、切片、重采样）下稳不稳——区分"真差异"与"个别极端单位/特定窗口驱动的假差异"
stages:
  - id: 0
    name: 基线复算（被检结论的原始数字）
    done_when:
      artifacts: ["baseline_metrics.json"]
    prereqs:
      - desc: 被检结论清单已答
        check: "question:conclusions-under-test"
      - desc: 指标与配对单位已答
        check: "question:metric-and-pairing"
    pause_after: false
    subagent_ok: true
  - id: 1
    name: 扰动矩阵（剔最差 k / 子期重算 / bootstrap 重采样）
    done_when:
      artifacts: ["perturbation_matrix.json"]
    prereqs:
      - desc: 基线在（Stage 0）
        check: "artifact:baseline_metrics.json"
    pause_after: false
    subagent_ok: true
  - id: 2
    name: 分组切片（按条件维度拆开看方向）
    done_when:
      artifacts: ["group_slices.json"]
    prereqs:
      - desc: 基线在（Stage 0）
        check: "artifact:baseline_metrics.json"
      - desc: 分组维度已填
        check: "config:group_columns"
    pause_after: false
    subagent_ok: true
  - id: 3
    name: 事实提取（现象清单，禁机制语言）
    done_when:
      findings_marker: "现象"
    prereqs:
      - desc: 扰动矩阵在（Stage 1）
        check: "artifact:perturbation_matrix.json"
    pause_after: true
    subagent_ok: true
  - id: 4
    name: 稳定性结论（逐条判稳/不稳 + CONCLUSION.md）
    done_when:
      artifacts: ["CONCLUSION.md"]
    prereqs:
      - desc: 现象清单已有（Stage 3）
        check: "stage:3"
    pause_after: false
    subagent_ok: false
variants:
  - id: grouped-slices
    when: "config:group_columns"
    unlocks_stages: [2]
questions:
  - id: conclusions-under-test
    stage: 0
    ask: "要检验哪些结论/对比？（如『A 比 B 好』『X 段比 Y 段差』，逐条列出；或『整体模型表现』）"
    why: "鲁棒性是对具体结论说的；对象不定，扰动无从设计"
    default: null
  - id: metric-and-pairing
    stage: 0
    ask: "评估指标是什么、按什么单位配对？（如按天配对的 RMSE、按 fold 配对的 loss）数据路径与列名？"
    why: "配对单位决定 Wilcoxon/剔除的粒度；猜错配对粒度检验无效"
    default: null
  - id: perturbation-families
    stage: 1
    ask: "扰动族选哪些？"
    why: "≥2 个独立扰动族才能构成升级证据"
    options: ["剔最差 k 单位 + 子期重算（默认组合）", "加 bootstrap 重采样", "加标签/输入噪声注入（需可重跑）", "自定义"]
    default: "剔最差 k 单位 + 子期重算"
  - id: group-columns
    stage: 2
    ask: "有没有想拆开看的条件维度（天气类型/季节/负载区间等）？列名或分组文件？"
    why: "切片能暴露『整体稳但某类内翻向』的隐患；没有就跳过 Stage 2"
    default: "无（Stage 2 跳过）"
    skip_if: "config:group_columns"
evidence_lines:
  - id: perturbation
    stage: 1
    output: perturbation_matrix.json
  - id: slices
    stage: 2
    output: group_slices.json
upgrade_rule: "结论要升「假设」：≥2 个独立扰动族下方向不变；要升「已证实」：另过配对检验（Wilcoxon 显著）且切片无翻向（或翻向组已解释并注明）"
---

# Playbook：鲁棒性分析

> 泛化自 pv-result-analysis 的稳健性门槛（`data_utils.robustness_check`：Wilcoxon + 剔最差 3 天方向不变）——那里它是"下结论前的一道门"，这里把它升格为**分析对象本身**：系统性地量化每条结论在多族扰动下的稳定性。

## 1. 问题框定与首要陷阱

1. **平均数会说谎**：整体指标差异可能全部由个别极端单位贡献——剔最差 k 后方向翻转 = 假差异。
2. **窗口选择效应**：只在某个子期成立的结论不是结论，是该子期的描述。
3. **切片翻向（Simpson 风险）**：整体 A 优于 B、某类条件内 B 反超——这不是噪声，是结构性发现，必须单独报告。
4. **扰动不独立不算两票**：剔最差 k 与 bootstrap 都吃"极端单位"这一个信号，一致不奇怪；子期重算才是独立视角。选扰动族时想清楚它们各吃什么信号。

## 2. 逐阶段菜谱

脚本生成进 `analysis_scripts/`，验证步过了才可信（记 PROGRESS.md）。

### Stage 0：基线复算 → `baseline_metrics.json`
- 按 `metric-and-pairing` 答案重算被检结论涉及的全部指标（**不信任来路数字，自己算一遍**），逐配对单位落长表 + 汇总。schema：`{conclusions: [{id, claim, baseline_diff, n_units}], per_unit: <路径或内嵌>}`。
- **验证步（对账）**：汇总值与用户提供的原始数字比对，相对差 >1% 必须解释（口径/窗口/取点差异），解释不了不许继续。

### Stage 1：扰动矩阵 → `perturbation_matrix.json`
- 逐（结论 × 扰动族）算扰动后差异方向与幅度：
  - **剔最差 k**：按配对差绝对值降序剔 k=max(3, 10%) 个单位重算；
  - **子期重算**：按时间平分 2–3 段各自重算（段内单位数 <10 则只描述不判定）；
  - **bootstrap**：单位层面重采样 ≥500 次，报方向一致率与 95% CI；
  - **配对检验**：Wilcoxon 符号秩（scipy.stats.wilcoxon）p 值。
- schema：`{conclusion_id: {family: {direction_preserved: bool, effect_before, effect_after, detail}}}` + 每结论 `stability_score`（方向保持的族数/总族数）。
- **验证步（植入回收）**：合成一组"差异全部由 2 个极端单位驱动"的假配对数据，断言剔最差 k 后 direction_preserved=false——过了才跑真数据。

### Stage 2：分组切片 → `group_slices.json`（变体 grouped-slices）
- 按 `group_columns` 拆组，逐组重算方向与幅度；组样本数一并落盘（<10 标"样本不足只描述"）。
- **验证步**：各组样本数之和 = 总数（无静默丢行）。

### Stage 3：事实提取 ⏸
- 只读 json summary 产现象清单：如"[现象] 结论 C1 在 4/4 个扰动族方向不变 | stability_score=1.0"；"[现象] C2 剔最差 3 天后差异从 +0.8% 变 -0.1%（方向翻转）"。禁机制语言。停顿，等用户点名。

### Stage 4：稳定性结论（主 agent）
- 逐条按 upgrade_rule 判级：稳（已证实级）/ 条件稳（假设级，注明在哪类条件下成立）/ 不稳（原结论降级或推翻，写明由什么驱动）。
- 切片翻向的组必须单独成条，不许平均掉。写 CONCLUSION.md（references/conclusion-reporting.md）。

## 3. 证据升级规则（映射三道门）

| 判定 | 条件 | 对应门 |
|---|---|---|
| 结论「稳」 | ≥2 独立扰动族方向不变 + Wilcoxon 显著 + 切片无未解释翻向 | 稳健性门（全量化版） |
| 结论「条件稳」 | 整体过但某切片翻向且可解释 → 加限定语后成立 | 反驳门 |
| 结论「不稳/被推翻」 | 任一主扰动族翻向且可复现 | ——（原结论进 FINDINGS 标被推翻） |

## 4. Subagent 拆分建议

扰动矩阵天然可按（结论 × 扰动族）分片：`--out perturb.<conclusion>.<family>.json` 各写各的，主 agent 合并成 perturbation_matrix.json。Brief-COMPUTE / Brief-FACT 见引擎 references/subagent-briefs.md。

## 5. 本 playbook 特有反驳门条目

1. **扰动族不独立**：两族吃同一信号（见 §1.4）却按"两票一致"升级 → 降级。
2. **剔除标准内生**：按"对我结论有利"的方式挑剔除单位（如只剔对方好的天）→ 作废，剔除只按配对差绝对值。
3. **多重比较**：结论条数 × 扰动族数很大时，个别"显著"是撒网撒出来的——报族数与命中率，别只报命中。
4. **子期切点选择**：切点若恰落在已知事件上，子期差异可能是事件而非时间稳定性。

## 6. 结论模板

一句话（几条结论里几条站得住）→ 逐结论：判级 + 最关键的一个扰动数字 + 大白话解释 → 建议（哪些结论可以对外引用、哪些要补数据再验）→ 可信度说明。
