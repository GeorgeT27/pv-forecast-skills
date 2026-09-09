"""实验日志与冠军：init / candidates / confirm-round / append（Task 5）；decide / new-round / stop / finalize（Task 6）。
全部走 subprocess 跑真 CLI；receipt 用 improve_verdict.judge 现造。"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
FAKE = os.path.join(ENGINE_DIR, "playbooks", "model-improve", "golden", "reference", "fake_adapter.py")
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402
import improve_verdict as iv  # noqa: E402

XL = os.path.join(SCRIPTS_DIR, "experiment_log.py")

EVALUATOR = {"adapter": FAKE,
             "base_config": {"model": "TSMixer", "dropout": 0.1, "learning_rate": 1e-3},
             "knobs": {"dropout": {"family": "training", "type": "float"},
                       "learning_rate": {"family": "training", "type": "float"},
                       "tsmixer_no_channel_mix": {"family": "architecture", "type": "flag"},
                       "n_heads": {"family": "architecture", "type": "int"}},
             "metric": {"id": "val_mse", "direction": "lower_is_better"},
             "slices": ["horizon:near", "horizon:mid", "horizon:far"],
             "seeds": [7, 1337, 2021], "time_limit_s": 5}
EVALUATOR_HIB = dict(EVALUATOR, metric={"id": "val_r2", "direction": "higher_is_better"})
BASELINE = {"per_seed": [0.2109, 0.2114, 0.2106], "seeds": [7, 1337, 2021],
            "slices_per_seed": [{"horizon:far": 0.274, "horizon:near": 0.169},
                                {"horizon:far": 0.275, "horizon:near": 0.169},
                                {"horizon:far": 0.274, "horizon:near": 0.168}],
            "metrics_dirs": ["runs/E000/seed_7", "runs/E000/seed_1337", "runs/E000/seed_2021"],
            "run_status": ["ok", "ok", "ok"]}
LEDGER = {"slice_map": [], "hypotheses": [
    {"id": "H1", "claim": "c", "component": "tsmixer.channel_mix", "falsifiable_pred": "p",
     "discriminating_power": 3, "status": "pending", "provenance": "pre-registered", "kill_receipt": None},
    {"id": "H2", "claim": "c", "component": "tsmixer.dropout", "falsifiable_pred": "p",
     "discriminating_power": 1, "status": "pending", "provenance": "pre-registered", "kill_receipt": None},
    {"id": "F2", "kind": "improvement", "derived_from": "H2", "claim": "c", "component": "tsmixer.dropout",
     "falsifiable_pred": "p", "fix": {"target_model": "TSMixer", "config_diff": {"dropout": 0.05},
                                     "predicted_gain": "降 0.005", "guard_slices": ["horizon:far"]},
     "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None},
    {"id": "F1", "kind": "improvement", "derived_from": "H1", "claim": "c", "component": "tsmixer.channel_mix",
     "falsifiable_pred": "p", "fix": {"target_model": "TSMixer", "config_diff": {"tsmixer_no_channel_mix": True},
                                     "predicted_gain": "降 0.03", "guard_slices": ["horizon:far"]},
     "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None},
    {"id": "F9", "kind": "improvement", "derived_from": "H1", "claim": "c", "component": "x",
     "falsifiable_pred": "p", "fix": {"target_model": "TiDE", "config_diff": {"dropout": 0.3},
                                     "predicted_gain": "g", "guard_slices": []},
     "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None}]}


def run(wd, *args, ok=True):
    r = subprocess.run([sys.executable, XL, *args], cwd=str(wd), capture_output=True, text=True, timeout=60)
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def _setup(tmp_path, evaluator=EVALUATOR, sealed=(0.23, 0.23, 0.23)):
    ec.dump_json(evaluator, str(tmp_path / "evaluator.json"))
    ec.dump_json(BASELINE, str(tmp_path / "baseline.json"))
    ec.dump_json(LEDGER, str(tmp_path / "hypothesis_ledger.json"))
    ec.dump_json({"playbook": "model-improve"}, str(tmp_path / "diagnose_config.json"))
    for d, v in zip(BASELINE["metrics_dirs"], sealed):
        os.makedirs(tmp_path / d / "sealed", exist_ok=True)
        (tmp_path / d / "sealed" / "test_metrics.json").write_text(json.dumps({"test_primary": v}), encoding="utf-8")
    run(tmp_path, "init", "--evaluator", "evaluator.json", "--baseline", "baseline.json",
        "--max-trainings", "30", "--max-rounds", "3", "--max-per-round", "10", "--stagnation-rounds", "2")
    return tmp_path


@pytest.fixture
def wd(tmp_path):
    return _setup(tmp_path)


@pytest.fixture
def wd_hib(tmp_path):
    """metric.direction = higher_is_better；基线封存值有方差，测试集噪声底非 0。"""
    return _setup(tmp_path, EVALUATOR_HIB, sealed=(0.230, 0.232, 0.228))


def _cand_diff(wd, exp_id):
    """receipt 的 config_diff 必须与本轮候选一致（append 门 2 会校验），从 candidates.json 取。"""
    rnd = (ec.read_json(str(wd / "diagnose_state.json")) or {}).get("round", 1)
    doc = ec.read_json(str(wd / "rounds" / f"round_{rnd}" / "candidates.json")) or {}
    for c in doc.get("candidates") or []:
        if c["exp_id"] == exp_id:
            return c["config_diff"]
    return {}


def receipt(wd, exp_id, hyp, per_seed, guards=None, sealed_seed_vals=(0.20, 0.20, 0.20), higher=False):
    champ = ec.read_json(str(wd / "champion.json"))
    r = iv.judge(exp_id, hyp, per_seed, champ["mean"], champ["noise_floor_3sigma"], guards=guards,
                 higher_is_better=higher)
    adapter = wd / "adapter.py"
    adapter.write_text("print(1)\n", encoding="utf-8")
    r.update({"config_diff": _cand_diff(wd, exp_id), "produced_by": str(adapter),
              "script_sha256": iv._sha256(str(adapter)),
              "t_start": "t0", "t_end": "t1", "script_selftest": "ok"})
    os.makedirs(wd / "receipts", exist_ok=True)
    (wd / "receipts" / f"{exp_id}.json").write_text(json.dumps([r]), encoding="utf-8")
    dirs = []
    for i, v in enumerate(sealed_seed_vals):
        d = wd / "runs" / exp_id / f"seed_{i}"
        os.makedirs(d / "sealed", exist_ok=True)
        (d / "sealed" / "test_metrics.json").write_text(json.dumps({"test_primary": v}), encoding="utf-8")
        dirs.append(str(d.relative_to(wd)))
    return {"status": "COMPUTE_DONE", "task": "candidate", "exp_id": exp_id, "hypothesis_id": hyp,
            "receipt_file": f"receipts/{exp_id}.json", "receipt_line": r["line"], "per_seed": per_seed,
            "run_status": ["ok"] * 3, "metrics_dirs": dirs,
            "slices_per_seed": [{"horizon:far": 0.26, "horizon:near": 0.16}] * 3}


def test_init_writes_champion_log_state_and_refuses_twice(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    assert champ["exp_id"] == "E000" and abs(champ["mean"] - 0.21097) < 1e-5
    assert champ["budget"]["used_trainings"] == 3 and champ["converged"] is False
    assert champ["base_config"] == EVALUATOR["base_config"]
    assert "horizon:far" in champ["slices_mean"] and "horizon:far" in champ["slices_noise_floor"]
    rows = [json.loads(l) for l in (wd / "experiment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["exp_id"] == "E000" and rows[0]["verdict"] == "baseline"
    assert ec.read_json(str(wd / "diagnose_state.json"))["round"] == 1
    r = run(wd, "init", "--evaluator", "evaluator.json", "--baseline", "baseline.json", ok=False)
    assert r.returncode != 0 and "只 init 一次" in r.stdout + r.stderr


def test_candidates_from_ledger_filters_orders_and_numbers(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    doc = ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))
    ids = [c["hypothesis_id"] for c in doc["candidates"]]
    assert ids == ["F1", "F2"]                       # F9 目标模型不符被滤掉；按父假设判别力排序
    assert [c["exp_id"] for c in doc["candidates"]] == ["E001", "E002"]
    assert doc["confirmed"] is False and doc["seeds"] == [7, 1337, 2021]


def test_candidates_from_switches_parses_flags_and_caps_by_budget(wd):
    ec.dump_json({"ablation_switches": [
        {"component": "b", "switch": "--n_heads=1", "kind": "config-flag"},
        {"component": "a", "switch": "--tsmixer_no_channel_mix", "kind": "config-flag"},
        {"component": "c", "switch": "--zero_attn", "kind": "code-stub"},
        {"component": "d", "switch": "", "kind": "not-intervenable"}]}, str(wd / "switches.json"))
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"]["max_per_round"] = 2
    ec.dump_json(champ, str(wd / "champion.json"))
    run(wd, "candidates", "--switches", "switches.json", "--target", "TSMixer", "--guard", "horizon:far")
    doc = ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))
    diffs = [c["config_diff"] for c in doc["candidates"]]
    assert diffs == [{"tsmixer_no_channel_mix": True}, {"n_heads": 1}]   # config-flag 先、按 component 排
    assert doc["deferred"][0]["config_diff"] == {"zero_attn": True} and len(doc["candidates"]) == 2
    assert doc["candidates"][0]["guard_slices"] == ["horizon:far"]


def test_append_requires_confirm_and_rejects_sealed_unknown_duplicate(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    res = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179])
    res["latest_ckpt"] = "runs/E001/seed_7/latest.pth"   # 含 test 子串但不是封存键——必须放行
    ec.dump_json({"results": [res]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    r = run(wd, "append", "--batch", "rounds/round_1/batch_result.json", ok=False)
    assert r.returncode != 0 and "未确认" in r.stdout + r.stderr
    run(wd, "confirm-round")
    bad = dict(res, sealed_test_primary=0.1)
    ec.dump_json({"results": [bad]}, str(wd / "bad.json"))
    r = run(wd, "append", "--batch", "bad.json", ok=False)
    assert r.returncode != 0 and "封存" in r.stdout + r.stderr
    bad2 = dict(res, test_mse=0.1)
    ec.dump_json({"results": [bad2]}, str(wd / "bad2.json"))
    r = run(wd, "append", "--batch", "bad2.json", ok=False)
    assert r.returncode != 0 and "封存" in r.stdout + r.stderr
    ec.dump_json({"results": [dict(res, exp_id="E077")]}, str(wd / "unk.json"))
    assert run(wd, "append", "--batch", "unk.json", ok=False).returncode != 0
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")
    r = run(wd, "append", "--batch", "rounds/round_1/batch_result.json", ok=False)
    assert r.returncode != 0 and "重复" in r.stdout + r.stderr
    rows = [json.loads(l) for l in (wd / "experiment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["exp_id"] == "E001" and rows[-1]["verdict"] == "keep" and rows[-1]["round"] == 1
    assert rows[-1]["receipt_line"].startswith("- E001 keep")


def test_append_marks_blocked_or_crashed_as_untested(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    blocked = {"status": "BLOCKED", "task": "candidate", "exp_id": "E001", "hypothesis_id": "F1",
               "run_status": ["ok", "crash", "ok"], "blocked_reason": "seed 1337 NaN loss"}
    ec.dump_json({"results": [blocked]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")
    rows = [json.loads(l) for l in (wd / "experiment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["verdict"] == "untested" and "NaN" in rows[-1]["untested_reason"]


def test_append_rejects_duplicate_exp_id_within_same_batch(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    res = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179])
    before = (wd / "experiment_log.jsonl").read_text(encoding="utf-8")
    ec.dump_json({"results": [res, dict(res)]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    r = run(wd, "append", "--batch", "rounds/round_1/batch_result.json", ok=False)
    assert r.returncode != 0 and "重复" in r.stdout + r.stderr
    assert (wd / "experiment_log.jsonl").read_text(encoding="utf-8") == before


def _round1(wd, keep=True):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    guards = {"horizon:far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.274, "noise_floor": 0.002}}
    r1 = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179], guards=guards, sealed_seed_vals=(0.19, 0.19, 0.19))
    r2 = receipt(wd, "E002", "F2", [0.205, 0.206, 0.204] if keep else [0.2109, 0.2114, 0.2106],
                 sealed_seed_vals=(0.215, 0.216, 0.214))
    ec.dump_json({"results": [r1, r2]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")


def test_decide_updates_champion_budget_summary_and_refuses_twice(wd):
    _round1(wd)
    r = run(wd, "decide")
    assert "E000 → E002" in r.stdout
    champ = ec.read_json(str(wd / "champion.json"))
    assert champ["exp_id"] == "E002" and champ["config"]["dropout"] == 0.05 and champ["since_round"] == 1
    assert champ["budget"]["used_trainings"] == 9 and champ["converged"] is False
    s = ec.read_json(str(wd / "rounds" / "round_1" / "summary.json"))
    assert s["counts"] == {"discard": 1, "keep": 1} and s["guard_regress"] == ["E001"]
    assert s["new_champion"] == "E002" and len(s["receipt_lines"]) == 2
    r = run(wd, "decide", ok=False)
    assert r.returncode != 0 and "已裁决" in r.stdout + r.stderr


def test_decide_requires_all_candidates_logged(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    r = run(wd, "decide", ok=False)
    assert r.returncode != 0 and "先 append" in r.stdout + r.stderr


def test_new_round_bumps_and_reenters_candidates(wd):
    _round1(wd)
    run(wd, "decide")
    run(wd, "new-round")
    assert ec.read_json(str(wd / "diagnose_state.json"))["round"] == 2
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    doc = ec.read_json(str(wd / "rounds" / "round_2" / "candidates.json"))
    assert doc["candidates"] == [] and doc["round"] == 2      # F1/F2 的 config_diff 已跑过，去重后为空


def test_convergence_max_rounds_and_stagnation_and_budget(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"].update({"max_rounds": 1})
    ec.dump_json(champ, str(wd / "champion.json"))
    _round1(wd)
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "max_rounds"
    r = run(wd, "new-round", ok=False)
    assert r.returncode != 0 and "已收敛" in r.stdout + r.stderr


def test_convergence_stagnation_two_rounds_without_keep(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"].update({"max_rounds": 5, "max_trainings": 100})
    ec.dump_json(champ, str(wd / "champion.json"))
    _round1(wd, keep=False)                       # E001 守护退化 discard，E002 噪声内 undecided
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged"] is False
    run(wd, "new-round")
    ec.dump_json({"ablation_switches": [{"component": "h", "switch": "--n_heads=4", "kind": "config-flag"}]},
                 str(wd / "sw.json"))
    run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    r3 = receipt(wd, "E003", None, [0.2110, 0.2113, 0.2108])
    ec.dump_json({"results": [r3]}, str(wd / "rounds" / "round_2" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_2/batch_result.json")
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "stagnation"


def test_convergence_budget_exhausted(wd):
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"].update({"max_trainings": 9, "max_rounds": 5})
    ec.dump_json(champ, str(wd / "champion.json"))
    _round1(wd)
    run(wd, "decide")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "budget_exhausted"


def test_stop_then_finalize_reads_sealed_once(wd):
    _round1(wd)
    run(wd, "decide")
    r = run(wd, "finalize", ok=False)
    assert r.returncode != 0 and "未收敛" in r.stdout + r.stderr
    run(wd, "stop", "--reason", "够了")
    assert ec.read_json(str(wd / "champion.json"))["converged_reason"] == "user:够了"
    r = run(wd, "finalize")
    doc = ec.read_json(str(wd / "final_test.json"))
    assert doc["champion"]["exp_id"] == "E002" and abs(doc["baseline"]["mean"] - 0.23) < 1e-12
    assert doc["verdict"] == "improved" and doc["champion"]["config_diff_vs_baseline"] == {"dropout": 0.05}
    assert "final_test improved" in r.stdout
    r = run(wd, "finalize", ok=False)
    assert r.returncode != 0 and "只评一次" in r.stdout + r.stderr


def test_status_prints_json(wd):
    r = run(wd, "status")
    doc = json.loads(r.stdout)
    assert doc["champion"] == "E000" and doc["round"] == 1 and doc["verdicts"] == {"baseline": 1}


def test_decide_refuses_champion_without_slices_per_seed(wd):
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    guards = {"horizon:far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.274, "noise_floor": 0.002}}
    r1 = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179], guards=guards, sealed_seed_vals=(0.19, 0.19, 0.19))
    r2 = receipt(wd, "E002", "F2", [0.205, 0.206, 0.204], sealed_seed_vals=(0.215, 0.216, 0.214))
    r2["slices_per_seed"] = []                     # 契约违规：worker 没交 slices_per_seed
    ec.dump_json({"results": [r1, r2]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_1/batch_result.json")
    before = ec.read_json(str(wd / "champion.json"))
    r = run(wd, "decide", ok=False)
    assert r.returncode != 0 and "E002" in r.stdout + r.stderr and "slices_per_seed" in r.stdout + r.stderr
    assert ec.read_json(str(wd / "champion.json")) == before
    assert not os.path.exists(str(wd / "rounds" / "round_1" / "summary.json"))


def test_champion_config_is_base_plus_current_diff_not_stacked(wd):
    """两轮各留下一个不同 knob：冠军 config = base_config + 本轮 diff。
    evaluator.apply_diff 永远把候选 diff 打在 base_config 上（不叠加），冠军 config 必须同口径，
    否则 champion.json 描述的是没人训练过的配置。"""
    _round1(wd)                                     # 第 1 轮 keep = E002，config_diff={"dropout": 0.05}
    run(wd, "decide")
    run(wd, "new-round")
    ec.dump_json({"ablation_switches": [{"component": "lr", "switch": "--learning_rate=0.0005",
                                         "kind": "config-flag"}]}, str(wd / "sw.json"))
    run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    r3 = receipt(wd, "E003", None, [0.190, 0.191, 0.189], sealed_seed_vals=(0.19, 0.19, 0.19))
    ec.dump_json({"results": [r3]}, str(wd / "rounds" / "round_2" / "batch_result.json"))
    run(wd, "append", "--batch", "rounds/round_2/batch_result.json")
    run(wd, "decide")
    champ = ec.read_json(str(wd / "champion.json"))
    assert champ["exp_id"] == "E003"
    assert champ["config"] == dict(EVALUATOR["base_config"], learning_rate=0.0005)
    assert champ["config"]["dropout"] == EVALUATOR["base_config"]["dropout"]   # 第 1 轮的 0.05 不残留
    run(wd, "stop", "--reason", "够了")
    run(wd, "finalize")
    doc = ec.read_json(str(wd / "final_test.json"))
    assert doc["champion"]["config_diff_vs_baseline"] == {"learning_rate": 0.0005}


def test_higher_is_better_picks_max_keep_and_finalizes_improved(wd_hib):
    """metric.direction=higher_is_better：decide 取均值最大的 keep；finalize 的 improved 按方向判。"""
    run(wd_hib, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd_hib, "confirm-round")
    r1 = receipt(wd_hib, "E001", "F1", [0.300, 0.301, 0.299], sealed_seed_vals=(0.30, 0.30, 0.30), higher=True)
    r2 = receipt(wd_hib, "E002", "F2", [0.250, 0.251, 0.249], sealed_seed_vals=(0.24, 0.24, 0.24), higher=True)
    ec.dump_json({"results": [r1, r2]}, str(wd_hib / "rounds" / "round_1" / "batch_result.json"))
    run(wd_hib, "append", "--batch", "rounds/round_1/batch_result.json")
    r = run(wd_hib, "decide")
    assert "E000 → E001" in r.stdout
    champ = ec.read_json(str(wd_hib / "champion.json"))
    assert champ["exp_id"] == "E001" and abs(champ["mean"] - 0.300) < 1e-9   # 0.300 > 0.250，取大者
    run(wd_hib, "stop", "--reason", "够了")
    run(wd_hib, "finalize")
    doc = ec.read_json(str(wd_hib / "final_test.json"))
    assert doc["delta"] > 0                                   # 原始 delta 照旧保留（未做符号归一）
    assert doc["delta"] > doc["noise_floor_3sigma_test"] > 0
    assert doc["verdict"] == "improved"


def test_append_rejects_receipt_config_diff_differing_from_candidate(wd):
    """门 2：receipt 的 config_diff 与本轮候选不一致 → 拒收（不许事后改配置差异）。"""
    run(wd, "candidates", "--ledger", "hypothesis_ledger.json", "--target", "TSMixer")
    run(wd, "confirm-round")
    res = receipt(wd, "E001", "F1", [0.180, 0.181, 0.179])
    recs = json.loads((wd / "receipts" / "E001.json").read_text(encoding="utf-8"))
    recs[-1]["config_diff"] = {"tsmixer_no_channel_mix": True, "dropout": 0.05}
    (wd / "receipts" / "E001.json").write_text(json.dumps(recs), encoding="utf-8")
    ec.dump_json({"results": [res]}, str(wd / "rounds" / "round_1" / "batch_result.json"))
    before = (wd / "experiment_log.jsonl").read_text(encoding="utf-8")
    r = run(wd, "append", "--batch", "rounds/round_1/batch_result.json", ok=False)
    out = r.stdout + r.stderr
    assert r.returncode != 0 and "E001" in out and "config_diff" in out
    assert (wd / "experiment_log.jsonl").read_text(encoding="utf-8") == before


def test_candidates_expand_switch_values(wd):
    """全链路联调 F9：素版候选的取值来自 ablation_switches 的 values，一个取值一条候选；
    没给 values 才退回开关自带的 =值/布尔真（旧档案继续能用）。"""
    ec.dump_json({"ablation_switches": [
        {"component": "a", "switch": "--e_layers", "kind": "config-flag", "values": [1, 4]},
        {"component": "b", "switch": "--learning_rate=0.0005", "kind": "config-flag"},
        {"component": "c", "switch": "--tsmixer_no_channel_mix", "kind": "config-flag",
         "values": [True]}]}, str(wd / "sw.json"))
    champ = ec.read_json(str(wd / "champion.json"))
    champ["budget"]["max_per_round"] = 5
    ec.dump_json(champ, str(wd / "champion.json"))
    run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    diffs = [c["config_diff"] for c in
             ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))["candidates"]]
    assert {"e_layers": 1} in diffs and {"e_layers": 4} in diffs      # 逐值排队
    assert {"learning_rate": 0.0005} in diffs                        # 无 values → 用 =值
    assert {"tsmixer_no_channel_mix": True} in diffs
    assert len(diffs) == 4


# ------------------------------------------------ R2-8：素版候选入口的三处
def test_candidates_skip_prose_switch(wd):
    """model-audit 的开关列允许写「无（需改代码）」这类散文（code-stub 行）。
    裸解析会把整句散文当 knob 名，排出永远过不了 apply_diff 的废候选。"""
    ec.dump_json({"ablation_switches": [
        {"component": "NLinear 锚定", "switch": "无（需改代码）", "kind": "code-stub",
         "values": ["-"]},
        {"component": "正则", "switch": "--dropout", "kind": "config-flag",
         "values": [0.3]}]}, str(wd / "sw.json"))
    r = run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    diffs = [c["config_diff"] for c in
             ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))["candidates"]]
    assert diffs == [{"dropout": 0.3}]
    assert "不是 CLI 开关字面量" in r.stdout, "跳过必须有交代，不许静默吞掉"


def test_candidates_filter_switches_by_target(wd):
    """--target 此前只筛账本条目，switches 分支完全不筛——别的模型的开关照样排进来。"""
    ec.dump_json({"ablation_switches": [
        {"component": "a", "switch": "--dropout", "kind": "config-flag",
         "values": [0.3], "model": "TSMixer"},
        {"component": "b", "switch": "--n_heads", "kind": "config-flag",
         "values": [8], "model": "NLinear"}]}, str(wd / "sw.json"))
    r = run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    diffs = [c["config_diff"] for c in
             ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))["candidates"]]
    assert diffs == [{"dropout": 0.3}]
    assert "≠ --target TSMixer" in r.stdout


def test_candidates_keep_all_when_no_switch_declares_model(wd):
    """单模型档案（一条都没写 model）= 这份表就是该模型的，不许误筛成空。"""
    ec.dump_json({"ablation_switches": [
        {"component": "a", "switch": "--dropout", "kind": "config-flag", "values": [0.3]},
        {"component": "b", "switch": "--n_heads", "kind": "config-flag", "values": [8]}]},
        str(wd / "sw.json"))
    run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    diffs = [c["config_diff"] for c in
             ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))["candidates"]]
    assert {"dropout": 0.3} in diffs and {"n_heads": 8} in diffs


def test_candidates_drop_noop_against_champion(wd):
    """与冠军当前配置逐键相同的候选 = 空转：训出来必然一样，白烧一轮种子。
    此前只与「已跑过的 diff」去重，没跟 champion.json 的 config 比过。"""
    champ = ec.read_json(str(wd / "champion.json"))
    assert champ["config"]["dropout"] == 0.1, "夹具前提：冠军 dropout 就是 0.1"
    ec.dump_json({"ablation_switches": [
        {"component": "正则", "switch": "--dropout", "kind": "config-flag",
         "values": [0.1, 0.3]}]}, str(wd / "sw.json"))
    r = run(wd, "candidates", "--switches", "sw.json", "--target", "TSMixer")
    diffs = [c["config_diff"] for c in
             ec.read_json(str(wd / "rounds" / "round_1" / "candidates.json"))["candidates"]]
    assert diffs == [{"dropout": 0.3}], "0.1 与冠军一致，应被剔"
    assert "空转" in r.stdout


def test_switch_to_diff_unit():
    import experiment_log as xl
    assert xl._switch_to_diff("--dropout", 0.3) == {"dropout": 0.3}
    assert xl._switch_to_diff("--learning_rate=0.0005") == {"learning_rate": 0.0005}
    assert xl._switch_to_diff("--flag") == {"flag": True}
    for prose in ("无", "无（需改代码）", "需要改代码", "—", ""):
        assert xl._switch_to_diff(prose) is None, prose
