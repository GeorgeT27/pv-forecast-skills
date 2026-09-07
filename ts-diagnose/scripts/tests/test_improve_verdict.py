"""改进判定：四态 + 守护切片 + receipt 行格式 + CLI 两种模式。"""
import json
import os
import re
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import improve_verdict as iv  # noqa: E402

SCRIPT = os.path.join(SCRIPTS_DIR, "improve_verdict.py")
LINE_RE = re.compile(r"(keep|discard|undecided).*delta.*seeds?=\d")


def test_verdict_four_states():
    assert iv.verdict(-0.02, 0.006, False) == "keep"
    assert iv.verdict(-0.02, 0.006, True) == "discard"
    assert iv.verdict(0.02, 0.006, False) == "discard"
    assert iv.verdict(-0.002, 0.006, False) == "undecided"


def test_guard_check_regress_only_when_worse_beyond_floor():
    g = iv.guard_check({"far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.26, "noise_floor": 0.006},
                        "near": {"per_seed": [0.10, 0.11, 0.09], "champion_mean": 0.12, "noise_floor": 0.006},
                        "mid": {"per_seed": [0.201, 0.199, 0.200], "champion_mean": 0.20, "noise_floor": 0.006}})
    assert g["far"]["regress"] is True
    assert g["near"]["regress"] is False      # 变好
    assert g["mid"]["regress"] is False       # 噪声内


def test_judge_line_and_fields():
    r = iv.judge("E003", "F1", [0.180, 0.181, 0.179], 0.200, 0.006)
    assert r["verdict"] == "keep" and abs(r["delta"] + 0.02) < 1e-9 and r["seeds"] == 3
    assert LINE_RE.search(r["line"]) and r["line"].startswith("- E003 keep: hyp=F1 ")
    r2 = iv.judge("E004", "F2", [0.178, 0.179, 0.180], 0.200, 0.006,
                  guards={"far": {"per_seed": [0.30, 0.31, 0.29], "champion_mean": 0.26, "noise_floor": 0.006}})
    assert r2["verdict"] == "discard" and "guard=regress:far" in r2["line"]


def test_higher_is_better_flips_sign():
    r = iv.judge("E005", None, [0.92, 0.93, 0.91], 0.90, 0.006, higher_is_better=True)
    assert r["verdict"] == "keep" and r["delta"] < 0


def test_judge_round_batch():
    obj = {"champion_mean": 0.200, "noise_floor_3sigma": 0.006,
           "candidates": [{"exp_id": "E001", "hypothesis_id": "F1", "per_seed": [0.180, 0.181, 0.179]},
                          {"exp_id": "E002", "hypothesis_id": "F2", "per_seed": [0.221, 0.220, 0.219]}]}
    v = iv.judge_round(obj)["verdicts"]
    assert v["E001"]["verdict"] == "keep" and v["E002"]["verdict"] == "discard"


def test_cli_summary_mode_writes_receipt_with_provenance(tmp_path):
    summary = {"per_seed": [0.180, 0.181, 0.179],
               "slices_per_seed": [{"far": 0.25}, {"far": 0.26}, {"far": 0.25}],
               "t_start": "2026-09-07T10:00:00", "t_end": "2026-09-07T10:03:00"}
    champ = {"mean": 0.200, "noise_floor_3sigma": 0.006,
             "slices_mean": {"far": 0.26}, "slices_noise_floor": {"far": 0.006}}
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "champion.json").write_text(json.dumps(champ), encoding="utf-8")
    adapter = tmp_path / "adapter.py"
    adapter.write_text("print('x')\n", encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "--exp-id", "E003", "--hypothesis-id", "F1",
                        "--summary", "summary.json", "--champion", "champion.json", "--guard", "far",
                        "--config-diff", '{"tsmixer_no_channel_mix": true}', "--script", str(adapter),
                        "--selftest", "assert ok", "--out", "receipts/E003.json"],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert LINE_RE.search(r.stdout)
    rec = json.loads((tmp_path / "receipts" / "E003.json").read_text(encoding="utf-8"))[-1]
    for k in ("exp_id", "hypothesis_id", "config_diff", "per_seed", "mean", "std", "champion_mean",
              "delta", "noise_floor_3sigma", "seeds", "guard", "verdict", "line",
              "produced_by", "script_sha256", "t_start", "t_end", "script_selftest"):
        assert k in rec, k
    assert rec["verdict"] == "keep" and rec["script_sha256"] and rec["t_start"] == "2026-09-07T10:00:00"


def test_cli_refuses_fewer_than_three_seeds(tmp_path):
    (tmp_path / "summary.json").write_text(json.dumps({"per_seed": [0.18, 0.18], "slices_per_seed": [{}, {}]}), encoding="utf-8")
    (tmp_path / "champion.json").write_text(json.dumps({"mean": 0.2, "noise_floor_3sigma": 0.006, "slices_mean": {}, "slices_noise_floor": {}}), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "--exp-id", "E009", "--summary", "summary.json",
                        "--champion", "champion.json", "--out", "receipts/E009.json"],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode != 0 and "种子" in (r.stdout + r.stderr)


def test_cli_round_mode(tmp_path):
    obj = {"champion_mean": 0.200, "noise_floor_3sigma": 0.006,
           "candidates": [{"exp_id": "E001", "hypothesis_id": "F1", "per_seed": [0.199, 0.198, 0.200]}]}
    (tmp_path / "round.json").write_text(json.dumps(obj), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "--round", "round.json", "--out", "verdicts.json"],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads((tmp_path / "verdicts.json").read_text(encoding="utf-8"))
    assert out["verdicts"]["E001"]["verdict"] == "undecided"
