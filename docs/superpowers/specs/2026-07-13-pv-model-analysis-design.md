# Design: `pv-model-analysis` — code-anchored model reference producer

**Date:** 2026-07-13
**Status:** Approved (design), pending spec review → implementation plan
**Supersedes:** `pv-model-verify` (renamed; scope expanded from verify-only to produce)

## Problem

`pv-result-analysis` reasons about *why* forecast accuracy changed by consulting a
per-model archive (`references/models.md`): what each model sees / can't see, its loss,
its training window, and an "架构 → 结果分析含义" layer mapping architecture to expected
error patterns. Today that archive is **hand-dictated** and therefore drifts from the real
code (documented precedent: M3 loss-normalization direction was recorded backwards).
`pv-model-verify` exists only to *reconcile* that dictated archive against code — it never
produces anything from scratch, and a human still has to write the archive first.

We want the model reference to be **generated from code**, trustworthy (anchored,
confidence-tagged), readable by humans, and **consumed directly by `pv-result-analysis`** —
so the analysis is always grounded in what the models actually are, not in stale dictation.

## Goals

1. Given a **model-code directory**, produce a code-anchored model reference set that
   serves **both** humans (understand the models) and **`pv-result-analysis`** (mechanism
   attribution) — including the "architecture → analysis implications" bridge.
2. **Flip the dependency:** `pv-model-analysis` is the *producer*; `pv-result-analysis` is
   a pure *consumer* that locates the produced docs, or triggers production if absent.
3. Fold in `project-cartographer`'s proven machinery (anchored training flowchart, per-method
   math, confidence tags, anti-fabrication, data profiling, per-module context strategy,
   self-check/audit) — **lean**, not the full onboarding mode surface.
4. Delete hand-dictated `references/models.md`; retire the verify-only posture (it survives
   as the "reconcile against prior output" branch).

## Non-goals

- Not a general codebase onboarding tool. No `focus`/`compare`/`impact`/`ask`/`variants` as
  separate commands (cartographer keeps those; here 4–5 fixed models make them unnecessary).
- Does not train or run the models. Reads code (+ optional data sample) only.
- Does not change how `pv-result-analysis` computes metrics or draws figures — only how it
  loads the model reference.

## Decisions (locked with user)

| # | Decision |
|---|----------|
| D1 | **Unified reconcile flow.** `analyze <dir>` extracts from code, then per section: empty → generate, filled → verify & correct. "Verify" is the already-filled branch. |
| D2 | **Produce description + bridge.** Docs carry code-anchored engineering + math **and** the 架构→结果分析含义 hypotheses (figure-# and H-ID linked) that `pv-result-analysis` consumes. |
| D3 | **Rename** `pv-model-verify` → `pv-model-analysis`. |
| D4 | **Pointer file + flexible location.** Docs default to `<repo>/.modelmap/`; a fixed pointer at `pv-result-analysis/references/model-ref.pointer` records their location + repo + commit + date. Consumer reads pointer first; missing → trigger producer. |
| D5 | **Lean cartographer import** (machinery yes, full mode surface no). |

## Architecture

```
pv-model-analysis  (PRODUCER)                 pv-result-analysis  (CONSUMER)
  input:  model-code dir                        at mechanism / "why" stage:
  output: <repo>/.modelmap/  ───────────►         1. read model-ref.pointer (fixed path)
          pv-result-analysis/references/          2. found + fresh → follow to .modelmap/models.md
          model-ref.pointer                       3. missing / stale → dispatch pv-model-analysis
                                                     subagent (ask for code dir) → then read
```

### Discovery contract

`pv-result-analysis/references/model-ref.pointer` — fixed path, always written by the
producer. Schema (YAML-ish, human-readable):

```
path:   /abs/path/to/<repo>/.modelmap      # where the docs live
repo:   /abs/path/to/<repo>                # source code root analyzed
commit: <git sha or "no-git">              # for staleness detection
date:   YYYY-MM-DD
models: [M1, M2, M3, M4, ensemble]         # which model sections were produced
```

Consumer logic: pointer absent → trigger. Pointer present but `path` missing on disk →
trigger. Pointer present, docs on disk, `commit` != current repo HEAD → warn "docs may be
stale, re-run pv-model-analysis?" but proceed with existing docs unless the user re-triggers.

## `pv-model-analysis` pipeline

Given a directory (and optionally a data sample path):

0. **Locate models — ask before spending.** Grep the known class names first
   (`FourierMobaTransformer`=M1, `PatchRegForecast`=M2, `MoiraiPvForecaster`=M3,
   `PatchTSTPvForecaster`=M4; plus Chronos usage and the ensemble combiner). Fall back to
   architecture-signature grep (from cartographer's keyword table) if class names moved.
   Confirm the class→M-id mapping. Multiple candidate versions (experiment copies, old
   files) → **list candidates + ask which is production**, never auto-pick. A model not
   found → report "未找到", leave its section unproduced (do not force similar code to fit).

1. **(Optional) data profiling.** If a data file is given, run `scripts/profile_data.py`
   to record measured stats in `data-profile.md`; use them to upgrade "why" claims from 📐
   to 📊. Skip silently if no data.

2. **Per model — one subagent each, checkpoint then forget** (context strategy from
   cartographer; `pv-result-analysis` already dispatches subagents so the runtime supports
   it — fall back to sequential if not). Each subagent reads only that model's files and
   returns three layers:
   - **Engineering (✅, `file:line`):** input channels + dims, patching, blocks, the actual
     loss (read code, not comments/function names), training window. This is the fact base.
   - **Math (📐):** each method the model uses — Fourier tokenizer, MoBA orthogonal MoE
     attention, RevIN, pinball (with the ≡4.5·MAE equivalence), MSE+rfft, Moirai encoder —
     definitions, formulas, what each computes, why it fits (📐/📊/⚠️ tagged).
   - **Bridge (架构→结果分析含义):** architecture fact → expected error pattern → the figure
     that checks it → an `H-<model>-<n>` hypothesis id. Produced by reading
     `pv-result-analysis/references/hypotheses.md` + the figure catalog (see Cross-skill
     contract). Derived claims are 📐 and must state the premise they hang on (e.g. the
     4.5·MAE ⇒ median-regression chain hangs on "single output + 9 symmetric quantiles").

3. **Reconcile (D1).** If a prior `.modelmap/` exists: repo unchanged (commit match) → reuse;
   changed → re-extract, diff against prior, update changed assertions with dated anchors
   `【代码核验 YYYY-MM-DD，来源 <file:line>】`, and **re-derive any bridge hypothesis whose
   premise moved** (no half-old/half-new state). A premise being overturned invalidates the
   derivation that cited it.

4. **Write** the doc set + the pointer file.

5. **Self-check (mandatory, from cartographer).** Files-on-disk post-condition; anchor audit
   (sample ✅ claims, open each `file:line`, confirm it says what the doc claims, downgrade
   mismatches to ⚠️ + `open-questions.md`); link integrity; coverage (models found vs
   produced, unreached model files listed); no naked claims (every non-trivial claim tagged
   + anchored). End with a short self-check report.

## Output: `<repo>/.modelmap/`

| File | Audience | Content |
|------|----------|---------|
| `START-HERE.md` | human | 5-line TL;DR + reading order + where-to-look table |
| `pipeline.md` | human | per-model **engineering flowchart** (Mermaid/ASCII): dims on every node, concrete blocks, named loss(es), forward→loss→optimizer. The four flowchart requirements from cartographer's Map pass apply. |
| `math.md` | human | per-method **math**, one `##` per method; symbols consistent with `symbol-map.md`, dims consistent with the flowchart |
| **`models.md`** | **pv-result-analysis** | the analysis-ready archive: per model 代码类名 / 架构 / 输入特征 / 损失函数 / 训练窗口 / 已知强弱项 + the **架构→结果分析含义 bridge hypotheses**. Same section structure `pv-result-analysis` expects today, but generated & code-anchored. Includes the top "全体共同约定" cross-station block. |
| `symbol-map.md` | both | symbol ↔ code var ↔ location ↔ shape/dtype |
| `ledger.md` | both | assertion ↔ `file:line` evidence (the reconcile audit trail) |
| `open-questions.md` | both | ⚠️ + 待确认 items a human must resolve |

Confidence tags (✅ code / 📊 data / 📐 derived / ⚠️ unverified) appear on every non-trivial
claim. **Unknown stays explicit** (empty field / ⚠️ / 待确认), preserving
`pv-result-analysis`'s "已填写的字段才可引用；空字段视为未知，不编造" rule — the tag IS the
filled/unfilled signal.

Note: `models.md` here is a *distilled, analysis-facing* view derived from `pipeline.md` +
`math.md`; the two human files are the deep reference. The producer keeps them consistent
(same facts, same anchors).

## `pv-result-analysis` rewiring

1. **Delete** `references/models.md`.
2. **Reference loading:** replace every `models.md` mention (Stage 4 gate, Playbook B, the
   `references/` table row, the discipline note at the bottom of the references section) with
   pointer-resolved lookup: read `references/model-ref.pointer` → follow `path:` →
   `.modelmap/models.md`.
3. **Locate-or-produce brief:** add a brief to `references/subagent-briefs.md` — read the
   pointer; if absent/stale, ask the user for the model-code dir and dispatch
   `pv-model-analysis` on it; then consume the produced `models.md`. Runs when the analysis
   first needs a mechanism-layer fact (Stage 4 / Playbook B), not during metric computation.
4. Keep the "只引用已填字段" discipline, now realized via confidence tags (cite ✅/📊/📐 with
   stated premises; never cite ⚠️/待确认/absent as fact).
5. Update the memory note + CHANGELOG.

## Cross-skill contract

The bridge hypotheses reference figure numbers and `hypotheses.md` H-IDs, both owned by
`pv-result-analysis`. Therefore:

- **Producer reads** `pv-result-analysis/references/hypotheses.md` and the figure catalog
  (`SKILL.md` 图谱目录 + `references/figure-diagnostics.md`) as inputs, so its bridge
  hypotheses point at real figures and real/new H-IDs.
- **Producer registers new H-IDs** back into `hypotheses.md` (append, dated, marked
  "预注册 by pv-model-analysis") so the consumer's H-ID gate resolves. Never silently
  invents an H-ID the registry doesn't know.
- **Interface surface** between the skills = { the pointer file, the `hypotheses.md`
  registry, the figure catalog }. No copy-paste of model facts between skills.

## Cartographer import scope (D5 — lean)

**Import (machinery):** anchoring discipline (`file:line`/`doc p.X`), confidence tags, the
four flowchart requirements, the math layer, anti-fabrication rules, `scripts/profile_data.py`
(+ `read_pptx.py` if design docs/PPTs exist), per-model subagent context strategy
(checkpoint→forget→resume), self-check/audit.

**Do not import (mode surface):** `focus` / `compare` / `impact` / `ask` / `variants` as
separate commands. For 4–5 fixed models the per-model doc already carries the detail;
`reconcile` (D1) replaces `update`; the audit self-check covers what `ask`/`impact` would.

## Risks / open questions

- **Staleness policy:** pointer commit-mismatch → warn + proceed vs. force re-produce. Chosen:
  warn + proceed (don't block analysis), let user re-trigger. Revisit if drift bites.
- **H-ID collision:** producer-registered H-IDs must not clash with human-authored ones — use
  a producer namespace/prefix or check-before-append. To settle in the plan.
- **No-git repos:** `commit: no-git` disables staleness detection; reconcile falls back to
  content diff. Acceptable.
- **Cross-skill coupling:** the producer now depends on `pv-result-analysis`'s hypotheses +
  figure catalog. Documented as the interface surface; acceptable since they ship together.
```

