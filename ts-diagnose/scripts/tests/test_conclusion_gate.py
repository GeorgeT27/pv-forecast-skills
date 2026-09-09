"""结论闸测试：subprocess 跑真 gate，断言 exit code 与 receipt。"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(SCRIPTS_DIR, "conclusion_gate.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PB = """---
id: gate-demo
name: g
goal: g
produces_ablation_receipts: true
stages:
  - id: 0
    name: 图
    done_when: {artifacts: ['charts/*.json', 'INDEX.md']}
    charts: [error-breakdown]
  - id: 1
    name: 结论
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
"""

# 非消融 playbook 的对照 fixture：不声明 produces_ablation_receipts——
# 代表 robustness/subset-influence/training-sufficiency/result-eval/
# feature-importance/deployment-drift 这 6 个非 pilot playbook。
PB_NON_ABLATION = """---
id: non-ablation-demo
name: n
goal: n
stages:
  - id: 0
    name: 图
    done_when: {artifacts: ['charts/*.json', 'INDEX.md']}
    charts: [error-breakdown]
  - id: 1
    name: 结论
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
"""

EVIDENCE = "## 证据清单\n- `charts/error-breakdown.png` — 切片版图\n"

GOOD = """# 结论
误差集中在 horizon 末段（见 charts/error-breakdown.png）。
## 模型结构依据
档案 H3：attention 窗口 96 点 → 预期长时效退化，与 charts/error-breakdown.png 一致。
""" + EVIDENCE


def setup(tmp_path, conclusion, with_chart=True, pb_text=PB):
    pb = tmp_path / "pb" / "playbook.md"
    pb.parent.mkdir(exist_ok=True)
    pb.write_text(pb_text, encoding="utf-8")
    ec.dump_json({"playbook": str(pb)}, str(tmp_path / "diagnose_config.json"))
    if with_chart:
        (tmp_path / "charts").mkdir()
        (tmp_path / "charts" / "error-breakdown.png").write_bytes(b"png")
    if conclusion is not None:
        (tmp_path / "CONCLUSION.md").write_text(conclusion, encoding="utf-8")
    return tmp_path


def run_gate(wd):
    return subprocess.run([sys.executable, GATE], cwd=wd,
                          capture_output=True, text=True, timeout=60)


def test_pass_writes_receipt(tmp_path):
    wd = setup(tmp_path, GOOD)
    r = run_gate(wd)
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.load(open(wd / "gate_reports" / "conclusion_gate.json"))
    assert rec["passed"] is True and rec["conclusion_sha256"]


def test_fail_missing_structure_section(tmp_path):
    wd = setup(tmp_path, "# 结论\n没依据。\n")
    r = run_gate(wd)
    assert r.returncode == 1
    assert "模型结构依据" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()


def test_degraded_statement_accepted(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "模型档案缺失（materials.model_code = absent-confirmed），结构性解释降级为猜测级。\n"
         + EVIDENCE)
    assert run_gate(setup(tmp_path, c)).returncode == 0


def test_fail_cited_chart_missing(tmp_path):
    bad = GOOD.replace("error-breakdown.png", "no-such-chart.png")
    wd = setup(tmp_path, bad)
    r = run_gate(wd)
    assert r.returncode == 1 and "no-such-chart.png" in r.stdout


def test_fail_no_chart_citation_when_chart_stage(tmp_path):
    c = "# 结论\n直觉归因。\n## 模型结构依据\n档案 H1 支持。\n"
    r = run_gate(setup(tmp_path, c))
    assert r.returncode == 1 and "图" in r.stdout


def test_decoy_path_containing_charts_substring_rejected(tmp_path):
    wd = setup(tmp_path, None)
    (wd / "mycharts").mkdir()
    (wd / "mycharts" / "decoy.png").write_bytes(b"png")
    c = ("# 结论\n误差分析（见 mycharts/decoy.png）。\n"
         "## 模型结构依据\n档案 H3：attention 窗口 96 点。\n")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "图" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()


def test_malformed_config_nonexistent_playbook_fails_clean(tmp_path):
    """M-k：config 指向不存在的 playbook 时，闸必须干净失败（exit 1 + ✗ 消息），
    不能让 find_playbook/load_frontmatter 的原始异常直接冒穿到 stderr 变成裸 traceback——
    这是脚本被调用方（orient/主 agent）依赖的契约：闸永远只用退出码 + stdout 消息说话。"""
    ec.dump_json({"playbook": "no-such-playbook"}, str(tmp_path / "diagnose_config.json"))
    (tmp_path / "CONCLUSION.md").write_text("# 结论\n", encoding="utf-8")
    r = run_gate(tmp_path)
    assert r.returncode == 1
    assert "✗" in r.stdout
    assert "playbook 加载失败" in r.stdout
    assert "Traceback" not in r.stderr


def test_charts_rooted_citation_required_even_with_lookalike_file(tmp_path):
    wd = setup(tmp_path, None)
    (wd / "archived_charts_summary.json").write_text("{}", encoding="utf-8")
    c = ("# 结论\n误差分析（见 archived_charts_summary.json）。\n"
         "## 模型结构依据\n档案 H3：attention 窗口 96 点。\n")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "图" in r.stdout
    assert not (wd / "gate_reports" / "conclusion_gate.json").exists()


def test_fail_arch_causal_without_ablation_receipt(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "档案 H3：跨变量注意力**导致**近端优势。\n")
    r = run_gate(setup(tmp_path, c))
    assert r.returncode == 1 and "消融" in r.stdout
    assert not (tmp_path / "gate_reports" / "conclusion_gate.json").exists()


def test_pass_arch_causal_with_ablation_receipt(tmp_path):
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "档案 H3：跨变量注意力**导致**近端优势。\n"
         "## 消融证据\n"
         "- H3 confirmed: switch=--itrans_no_attn delta=+0.031 noise_floor=0.0102 seeds=3\n"
         + EVIDENCE)
    assert run_gate(setup(tmp_path, c)).returncode == 0


# ---- 规则 5 溯源闭环 + 规则 6 证据清单 ----

def _traceable_world(tmp_path, **overrides):
    """搭一个溯源闭环完整的工作目录:脚本+回执(正典 schema)+provenance serves+plan 回填。
    overrides 用于逐环破坏。返回 (wd, conclusion_text)。"""
    import hashlib as hl
    wd = setup(tmp_path, None)
    (wd / "analysis_scripts").mkdir()
    script = wd / "analysis_scripts" / "eval_H3.py"
    script.write_text("# eval\n", encoding="utf-8")
    sha = hl.sha256(script.read_bytes()).hexdigest()
    rec = {"hypothesis_id": "H3", "switch": "--itrans_no_attn", "delta": 0.031,
           "noise_floor_3sigma": 0.0102, "seeds": 3,
           "pred_direction": "increase", "verdict": "confirmed",
           "line": "- H3 confirmed: switch=--itrans_no_attn delta=+0.031 "
                   "noise_floor=0.0102 seeds=3",
           "produced_by": "analysis_scripts/eval_H3.py", "script_sha256": sha,
           "t_start": "T0", "t_end": "T1", "script_selftest": "植入回收通过"}
    rec.update(overrides.get("receipt", {}))
    for k in overrides.get("receipt_drop", []):
        rec.pop(k, None)
    (wd / "receipts").mkdir()
    (wd / "receipts" / "H3.json").write_text(json.dumps([rec]), encoding="utf-8")
    prov = {"code": {"files": {"analysis_scripts/eval_H3.py": sha},
                     "serves": {"eval_H3.py": {"episode_id": "H3",
                                               "segment_id": None}}}}
    if overrides.get("no_serves"):
        prov["code"].pop("serves")
    (wd / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    vs = {"interventions": [{"hypothesis_id": "H3", "verdict": "confirmed"}],
          "unexplained_real_slices": []}
    vs.update(overrides.get("verdict_summary", {}))
    (wd / "verdict_summary.json").write_text(json.dumps(vs), encoding="utf-8")
    # 规则 8 收口:harvest.json 由 harvest_check.py 产,这里手造等价物
    # (sha 绑当前 verdict_summary,过期即拦)。
    harv = {"round": 1, "harvest": "full", "n_real_slices": 1, "n_moved": 1,
            "n_confirmed": 1, "n_refuted": 0, "n_undecided": 0, "n_skipped": 0,
            "unexplained": [], "residual_by_dimension": {},
            "verdict_summary_sha256": hl.sha256(
                (wd / "verdict_summary.json").read_bytes()).hexdigest()}
    harv.update(overrides.get("harvest", {}))
    if not overrides.get("no_harvest"):
        (wd / "harvest.json").write_text(json.dumps([harv]), encoding="utf-8")
    plan = [{"hypothesis_id": "H3", "switch": "--itrans_no_attn",
             "script": overrides.get("plan_script",
                                     "analysis_scripts/eval_H3.py")}]
    plan += overrides.get("plan_extra", [])
    (wd / "intervention_plan.json").write_text(
        json.dumps({"interventions": plan}), encoding="utf-8")
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "档案 H3：跨变量注意力**导致**近端优势。\n"
         "## 消融证据\n" + rec.get("line", "- H3 confirmed: switch=--x "
                                            "delta=+0.031 noise_floor=0.0102 "
                                            "seeds=3") + "\n"
         + overrides.get("extra_sections", "")
         + "## 证据清单\n"
         "- `receipts/H3.json` — H3 判定回执\n"
         "- `verdict_summary.json` — 干预汇总\n"
         "- `harvest.json` — 本轮收成\n")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    return wd


def test_traceable_world_passes(tmp_path):
    r = run_gate(_traceable_world(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr


def test_fail_thin_receipt_missing_produced_by(tmp_path):
    wd = _traceable_world(tmp_path, receipt_drop=["produced_by",
                                                  "script_sha256"])
    r = run_gate(wd)
    assert r.returncode == 1 and "缺必填字段" in r.stdout


def test_fail_single_seed_receipt(tmp_path):
    r = run_gate(_traceable_world(tmp_path, receipt={"seeds": 1}))
    assert r.returncode == 1 and "3 种子" in r.stdout


def test_fail_script_hash_mismatch(tmp_path):
    wd = _traceable_world(tmp_path)
    (wd / "analysis_scripts" / "eval_H3.py").write_text("# 改过了\n",
                                                        encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "被改过" in r.stdout


def test_fail_orphan_script_without_serves(tmp_path):
    r = run_gate(_traceable_world(tmp_path, no_serves=True))
    assert r.returncode == 1 and "孤儿脚本" in r.stdout


def test_fail_plan_script_not_backfilled(tmp_path):
    r = run_gate(_traceable_world(tmp_path, plan_script=None))
    assert r.returncode == 1 and "script 为空" in r.stdout


def test_fail_plan_entry_without_receipt_or_skip(tmp_path):
    r = run_gate(_traceable_world(tmp_path, plan_extra=[
        {"hypothesis_id": "H9", "switch": "--y", "script": None}]))
    assert r.returncode == 1 and "H9" in r.stdout


def test_fail_missing_evidence_section(tmp_path):
    wd = _traceable_world(tmp_path)
    text = (wd / "CONCLUSION.md").read_text(encoding="utf-8")
    (wd / "CONCLUSION.md").write_text(text.split("## 证据清单")[0],
                                      encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "证据清单" in r.stdout


def test_fail_evidence_cherry_picks_receipts(tmp_path):
    # 盘上多一张被否证的 H4 回执但清单没列它 → 拦(防只列支持结论的)
    wd = _traceable_world(tmp_path)
    import hashlib as hl
    script = wd / "analysis_scripts" / "eval_H4.py"
    script.write_text("# eval4\n", encoding="utf-8")
    sha = hl.sha256(script.read_bytes()).hexdigest()
    prov = json.load(open(wd / "provenance.json", encoding="utf-8"))
    prov["code"]["files"]["analysis_scripts/eval_H4.py"] = sha
    prov["code"]["serves"]["eval_H4.py"] = {"episode_id": "H4",
                                            "segment_id": None}
    (wd / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    (wd / "receipts" / "H4.json").write_text(json.dumps([{
        "hypothesis_id": "H4", "switch": "--y", "delta": -0.001,
        "noise_floor_3sigma": 0.0102, "seeds": 3,
        "pred_direction": "increase", "verdict": "refuted",
        "produced_by": "analysis_scripts/eval_H4.py",
        "script_sha256": sha}]), encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "漏列" in r.stdout \
        and "receipts/H4.json" in r.stdout


def test_pass_non_ablation_playbook_causal_wording_without_receipt(tmp_path):
    """零破坏回归：非消融 playbook（frontmatter 无 produces_ablation_receipts）的结论，
    「模型结构依据」节含因果词（因为…）+ 合法锚点（H-id），但没有「## 消融证据」节——
    规则 4 不得对它生效（它用置换/反事实/留一法验证因果，不产消融 receipt）。
    修复前：规则 4 对任何 playbook 一律生效，本用例会被误拦，破坏 6 个非 pilot playbook。"""
    c = ("# 结论\n（见 charts/error-breakdown.png）\n## 模型结构依据\n"
         "档案 H1：因为该特征置换后误差显著上升，判定其为主导因子。\n")
    r = run_gate(setup(tmp_path, c, pb_text=PB_NON_ABLATION))
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.load(open(tmp_path / "gate_reports" / "conclusion_gate.json"))
    assert rec["passed"] is True


# ---- 规则 7 改进环（produces_experiment_log） ----

PB_IMPROVE = """---
id: improve-demo
name: i
goal: i
produces_experiment_log: true
stages:
  - id: 0
    name: 环
    done_when: {artifacts: ['champion.json']}
  - id: 1
    name: 结论
    done_when: {artifacts: ['CONCLUSION.md', 'gate_reports/conclusion_gate.json']}
---
"""

IMPROVE_GOOD = """# 结论
冠军 E002（dropout 0.1→0.05）在验证集上超基线（见 receipts/E002.json）；封存测试集终评见 final_test.json。
## 模型结构依据
absent-confirmed：无模型档案，降级为配置级改进结论。
## 改进证据
- E001 discard: hyp=F1 delta=-0.0300 noise_floor=0.0012 seeds=3 guard=regress:horizon:far
- E002 keep: hyp=F2 delta=-0.0050 noise_floor=0.0012 seeds=3 guard=ok
- final_test improved: champion=E002 delta=-0.0150 noise_floor=0.0010 seeds=3
## 证据清单
- `receipts/E001.json` — 守护退化被弃
- `receipts/E002.json` — 留下的冠军
- `experiment_log.jsonl` — 全部候选
- `champion.json` — 冠军状态
- `final_test.json` — 封存终评
"""


def _improve_receipt(tmp_path, exp_id, verdict):
    adapter = tmp_path / "adapter.py"
    adapter.write_text("print(1)\n", encoding="utf-8")
    import hashlib
    sha = hashlib.sha256(adapter.read_bytes()).hexdigest()
    (tmp_path / "receipts").mkdir(exist_ok=True)
    (tmp_path / "receipts" / f"{exp_id}.json").write_text(json.dumps([{
        "exp_id": exp_id, "hypothesis_id": "F", "delta": -0.01, "noise_floor_3sigma": 0.001, "seeds": 3,
        "verdict": verdict, "line": f"- {exp_id} {verdict}: hyp=F delta=-0.0100 noise_floor=0.0010 seeds=3 guard=ok",
        "produced_by": str(adapter), "script_sha256": sha}]), encoding="utf-8")


def _improve_setup(tmp_path, text):
    setup(tmp_path, text, with_chart=False, pb_text=PB_IMPROVE)
    _improve_receipt(tmp_path, "E001", "discard")
    _improve_receipt(tmp_path, "E002", "keep")
    for name in ("experiment_log.jsonl", "champion.json", "final_test.json"):
        (tmp_path / name).write_text("{}\n", encoding="utf-8")


def test_rule7_passes_with_full_improve_evidence(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD)
    r = run_gate(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "gate_reports" / "conclusion_gate.json").exists()


def test_rule7_missing_section_or_receipt_line_fails(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD.replace("## 改进证据", "## 改进"))
    r = run_gate(tmp_path)
    assert r.returncode != 0 and "改进证据" in r.stdout


def test_rule7_unlisted_receipt_or_missing_final_fails(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD.replace("- `receipts/E001.json` — 守护退化被弃\n", ""))
    r = run_gate(tmp_path)
    assert r.returncode != 0 and "E001" in r.stdout
    _improve_setup(tmp_path, IMPROVE_GOOD)
    (tmp_path / "final_test.json").unlink()
    r = run_gate(tmp_path)
    assert r.returncode != 0 and "final_test.json" in r.stdout


def test_rule7_receipt_hash_mismatch_fails(tmp_path):
    _improve_setup(tmp_path, IMPROVE_GOOD)
    (tmp_path / "adapter.py").write_text("print(2)\n", encoding="utf-8")
    r = run_gate(tmp_path)
    assert r.returncode != 0 and "sha256" in r.stdout


def test_rule7_not_applied_to_other_playbooks(tmp_path):
    setup(tmp_path, GOOD, with_chart=True, pb_text=PB_NON_ABLATION)   # 无改进证据节也过闸
    r = run_gate(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


# ---- 规则 5：一支脚本服务多个假设（F12） ----

def _shared_script_world(tmp_path, serves_ids):
    """互补假设 H3b 与母假设 H3 共用 eval_H3.py 和同一判定脚本。
    serves_ids 决定 provenance 里 eval_H3.py 挂回哪些假设。"""
    import hashlib as hl
    wd = _traceable_world(tmp_path)
    sha = hl.sha256((wd / "analysis_scripts" / "eval_H3.py").read_bytes()).hexdigest()
    rec_b = {"hypothesis_id": "H3b", "switch": "--itrans_no_attn", "delta": 0.031,
             "noise_floor_3sigma": 0.0102, "seeds": 3, "pred_direction": "decrease",
             "verdict": "refuted",
             "line": "- H3b refuted: switch=--itrans_no_attn delta=+0.031 "
                     "noise_floor=0.0102 seeds=3",
             "produced_by": "analysis_scripts/eval_H3.py", "script_sha256": sha,
             "t_start": "T0", "t_end": "T1", "script_selftest": "植入回收通过"}
    (wd / "receipts" / "H3b.json").write_text(json.dumps([rec_b]), encoding="utf-8")
    prov = json.loads((wd / "provenance.json").read_text(encoding="utf-8"))
    prov["code"]["serves"] = {"eval_H3.py": {"episode_id": serves_ids[0],
                                             "episode_ids": list(serves_ids),
                                             "segment_id": None}}
    (wd / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    plan = json.loads((wd / "intervention_plan.json").read_text(encoding="utf-8"))
    plan["interventions"].append({"hypothesis_id": "H3b", "switch": "--itrans_no_attn",
                                  "script": "analysis_scripts/eval_H3.py"})
    (wd / "intervention_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    text = (wd / "CONCLUSION.md").read_text(encoding="utf-8").replace(
        "## 证据清单\n", "## 证据清单\n- `receipts/H3b.json` — 互补假设回执\n")
    (wd / "CONCLUSION.md").write_text(text, encoding="utf-8")
    return wd


def test_shared_eval_script_serves_both_hypotheses(tmp_path):
    """H3 与 H3b 共用一支脚本：serves 写全两个就过闸（过去只能挂一个 → 报孤儿脚本）。"""
    r = run_gate(_shared_script_world(tmp_path, ["H3", "H3b"]))
    assert r.returncode == 0, r.stdout + r.stderr


def test_shared_script_missing_one_hypothesis_still_fails(tmp_path):
    """只挂回母假设、漏了互补假设 → 仍是孤儿脚本，照拦。"""
    r = run_gate(_shared_script_world(tmp_path, ["H3"]))
    assert r.returncode == 1 and "孤儿脚本" in r.stdout


def test_legacy_serves_without_episode_ids_still_accepted(tmp_path):
    """旧形态 provenance（只有 episode_id）继续认。"""
    wd = _traceable_world(tmp_path)
    prov = json.loads((wd / "provenance.json").read_text(encoding="utf-8"))
    assert "episode_ids" not in prov["code"]["serves"]["eval_H3.py"]
    assert run_gate(wd).returncode == 0


# ---- 判据②闸：账本升级为 refuted 必须有第二口径同判 ----

def _criterion2_world(tmp_path, receipt_extra, ledger_status="refuted"):
    """脚本判 undecided（|delta| 落在噪声底内），账本把它升级为 refuted（判据②预测落空）。"""
    wd = _traceable_world(tmp_path)
    rec = json.loads((wd / "receipts" / "H3.json").read_text(encoding="utf-8"))[-1]
    rec.update({"verdict": "undecided", "delta": 0.0004, "noise_floor_3sigma": 0.0195,
                "line": "- H3 undecided: switch=--itrans_no_attn delta=+0.000 "
                        "noise_floor=0.0195 seeds=3"})
    rec.update(receipt_extra)
    (wd / "receipts" / "H3.json").write_text(json.dumps([rec]), encoding="utf-8")
    (wd / "hypothesis_ledger.json").write_text(json.dumps(
        {"hypotheses": [{"id": "H3", "status": ledger_status,
                         "kill_receipt": {"note": "预测落空"}}]}), encoding="utf-8")
    text = (wd / "CONCLUSION.md").read_text(encoding="utf-8").replace(
        "- H3 confirmed: switch=--x delta=+0.031 noise_floor=0.0102 seeds=3", rec["line"])
    (wd / "CONCLUSION.md").write_text(text, encoding="utf-8")
    return wd


def test_criterion2_without_second_caliber_is_blocked(tmp_path):
    """全链路联调 F11 的闸：没有第二口径就把假设写成「被推翻」，拦。"""
    wd = _criterion2_world(tmp_path, {"pred_miss": {
        "main": True, "second": None, "eligible": False, "note": "缺第二口径复核"}})
    r = run_gate(wd)
    assert r.returncode == 1 and "判据②" in r.stdout and "pred_miss" in r.stdout


def test_criterion2_legacy_receipt_without_pred_miss_is_blocked(tmp_path):
    """早于第二口径契约的旧回执（没有 pred_miss 字段）同样拦，不许默认放行。"""
    r = run_gate(_criterion2_world(tmp_path, {}))
    assert r.returncode == 1 and "判据②" in r.stdout


def test_criterion2_with_agreeing_second_caliber_passes(tmp_path):
    wd = _criterion2_world(tmp_path, {
        "second_caliber": {"name": "rmse_96", "delta": 0.0003,
                           "noise_floor_3sigma": 0.0210, "verdict": "undecided"},
        "pred_miss": {"main": True, "second": True, "eligible": True,
                      "note": "两口径同判「预测落空」"}})
    r = run_gate(wd)
    assert r.returncode == 0, r.stdout + r.stderr


def test_undecided_receipt_left_undecided_needs_no_second_caliber(tmp_path):
    """账本没升级（仍 undecided）时不要求第二口径——这条闸只管判据②的升级。"""
    wd = _criterion2_world(tmp_path, {}, ledger_status="undecided")
    assert run_gate(wd).returncode == 0


def test_criterion1_refuted_needs_no_second_caliber(tmp_path):
    """判据①（超噪声底但方向反）由脚本直接判 refuted，与第二口径无关。"""
    wd = _traceable_world(tmp_path)
    rec = json.loads((wd / "receipts" / "H3.json").read_text(encoding="utf-8"))[-1]
    rec["verdict"] = "refuted"
    (wd / "receipts" / "H3.json").write_text(json.dumps([rec]), encoding="utf-8")
    (wd / "hypothesis_ledger.json").write_text(json.dumps(
        {"hypotheses": [{"id": "H3", "status": "refuted",
                         "kill_receipt": {"note": "方向反"}}]}), encoding="utf-8")
    assert run_gate(wd).returncode == 0


# ------------------------------------------------- 规则 8：收成收口（解释环）
def test_missing_harvest_blocks(tmp_path):
    """有 Stage 3 汇总却没跑 harvest_check.py → 拦。"""
    wd = _traceable_world(tmp_path, no_harvest=True)
    r = run_gate(wd)
    assert r.returncode == 1 and "harvest_check.py" in r.stdout


def test_stale_harvest_blocks(tmp_path):
    """判定改过之后收成没重算：sha 对不上 → 拦。"""
    wd = _traceable_world(tmp_path, harvest={"verdict_summary_sha256": "dead"})
    r = run_gate(wd)
    assert r.returncode == 1 and "verdict_summary_sha256" in r.stdout


def test_unexplained_slices_must_appear_in_conclusion(tmp_path):
    wd = _traceable_world(tmp_path, harvest={
        "harvest": "partial", "n_confirmed": 1,
        "unexplained": [{"slice": "month:2020-10"}, {"slice": "channel:raining_s"}]})
    r = run_gate(wd)
    assert r.returncode == 1 and "已知缺口" in r.stdout


def test_unexplained_section_must_name_every_slice(tmp_path):
    """列一半也不行——概括不算逐条。"""
    wd = _traceable_world(tmp_path, harvest={
        "harvest": "partial", "n_confirmed": 1,
        "unexplained": [{"slice": "month:2020-10"}, {"slice": "channel:raining_s"}]},
        extra_sections="## 已知缺口\n- `month:2020-10`（其余切片未解释）\n")
    r = run_gate(wd)
    assert r.returncode == 1 and "channel:raining_s" in r.stdout


def test_unexplained_all_named_passes(tmp_path):
    wd = _traceable_world(tmp_path, harvest={
        "harvest": "partial", "n_confirmed": 1,
        "unexplained": [{"slice": "month:2020-10"}, {"slice": "channel:raining_s"}]},
        extra_sections="## 已知缺口\n- `month:2020-10` z=9.8\n- `channel:raining_s` z=11.8\n")
    r = run_gate(wd)
    assert r.returncode == 0, r.stdout + r.stderr


def test_zero_confirmed_needs_explicit_declaration(tmp_path):
    """一条 confirmed 都没有，却把 undecided 写成读起来像发现的说法 → 拦。"""
    wd = _traceable_world(tmp_path, harvest={"harvest": "none", "n_confirmed": 0})
    r = run_gate(wd)
    assert r.returncode == 1 and "本轮未能归因到任何组件" in r.stdout


def test_zero_confirmed_with_declaration_passes(tmp_path):
    wd = _traceable_world(tmp_path, harvest={"harvest": "none", "n_confirmed": 0})
    c = (wd / "CONCLUSION.md").read_text(encoding="utf-8").replace(
        "档案 H3：跨变量注意力**导致**近端优势。",
        "本轮未能归因到任何组件。档案 H3 停在未决。")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 0, r.stdout + r.stderr


def test_declaration_must_be_in_structure_section_not_buried(tmp_path):
    """声明写在证据清单里不算——它必须站在「模型结构依据」节，和因果表述同一处。"""
    wd = _traceable_world(tmp_path, harvest={"harvest": "none", "n_confirmed": 0},
                          extra_sections="## 备注\n本轮未能归因到任何组件。\n")
    r = run_gate(wd)
    assert r.returncode == 1 and "模型结构依据" in r.stdout


def test_non_ablation_playbook_unaffected_by_rule8(tmp_path):
    """零破坏契约：不声明 produces_ablation_receipts 的 6 个 playbook 不过规则 8。"""
    wd = setup(tmp_path, GOOD, pb_text=PB_NON_ABLATION)
    (wd / "verdict_summary.json").write_text("{}", encoding="utf-8")
    assert run_gate(wd).returncode == 0


def test_harvest_json_must_be_in_evidence_list(tmp_path):
    wd = _traceable_world(tmp_path)
    c = (wd / "CONCLUSION.md").read_text(encoding="utf-8").replace(
        "- `harvest.json` — 本轮收成\n", "")
    (wd / "CONCLUSION.md").write_text(c, encoding="utf-8")
    r = run_gate(wd)
    assert r.returncode == 1 and "harvest.json" in r.stdout
