"""评估器契约：校验 / 单种子 ok·crash·timeout·切片缺失 / 多种子 summary / 未登记 knob。"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)
FAKE = os.path.join(ENGINE_DIR, "playbooks", "model-improve", "golden", "reference", "fake_adapter.py")
sys.path.insert(0, SCRIPTS_DIR)
import evaluator as ev  # noqa: E402

SCRIPT = os.path.join(SCRIPTS_DIR, "evaluator.py")


def _ev(**over):
    d = {"adapter": FAKE,
         "base_config": {"model": "TSMixer", "dropout": 0.1, "learning_rate": 1e-3},
         "knobs": {"dropout": {"family": "training", "type": "float"},
                   "learning_rate": {"family": "training", "type": "float"},
                   "tsmixer_no_channel_mix": {"family": "architecture", "type": "flag"},
                   "crash": {"family": "training", "type": "flag"},
                   "sleep_s": {"family": "training", "type": "float"}},
         "metric": {"id": "val_mse", "direction": "lower_is_better"},
         "slices": ["horizon:near", "horizon:mid", "horizon:far"],
         "seeds": [7, 1337, 2021], "time_limit_s": 5, "kill_grace_s": 0}
    d.update(over)
    return d


def test_validate_catches_contract_errors(tmp_path):
    assert ev.validate(_ev()) == []
    errs = ev.validate(_ev(adapter=str(tmp_path / "nope.py"), seeds=[1, 2],
                           knobs={"x": {"family": "magic"}}, metric={"id": "m", "direction": "up"}))
    joined = " ".join(errs)
    for k in ("adapter", "seeds", "family", "direction"):
        assert k in joined, k


def test_apply_diff_rejects_unknown_knob():
    with pytest.raises(ValueError):
        ev.apply_diff(_ev(), {"n_heads": 1})
    assert ev.apply_diff(_ev(), {"dropout": 0.2})["dropout"] == 0.2


def test_run_one_ok_and_sealed_written(tmp_path):
    m = ev.run_one(_ev(), _ev()["base_config"], 7, str(tmp_path / "s7"))
    assert m["status"] == "ok" and abs(m["primary"] - 0.210866) < 1e-6
    assert set(m["slices"]) == {"horizon:near", "horizon:mid", "horizon:far"}
    assert (tmp_path / "s7" / "sealed" / "test_metrics.json").exists()


def test_run_one_crash_and_timeout_write_metrics(tmp_path):
    m = ev.run_one(_ev(), ev.apply_diff(_ev(), {"crash": True}), 7, str(tmp_path / "c"))
    assert m["status"] == "crash" and (tmp_path / "c" / "metrics.json").exists()
    m2 = ev.run_one(_ev(time_limit_s=1), ev.apply_diff(_ev(), {"sleep_s": 3}), 7, str(tmp_path / "t"))
    assert m2["status"] == "timeout"


def test_run_one_missing_slice_is_crash(tmp_path):
    m = ev.run_one(_ev(slices=["horizon:near", "horizon:bogus"]), _ev()["base_config"], 7, str(tmp_path / "b"))
    assert m["status"] == "crash" and "horizon:bogus" in (m.get("error") or "")


def test_run_one_bad_adapter_path_is_crash_not_exception(tmp_path):
    d = _ev(adapter=str(tmp_path / "no_such_adapter.py"))
    m = ev.run_one(d, d["base_config"], 7, str(tmp_path / "launch_fail"))
    assert m["status"] == "crash" and m["primary"] is None
    assert (tmp_path / "launch_fail" / "metrics.json").exists()


def test_run_seeds_summary(tmp_path):
    s = ev.run_seeds(_ev(), {"dropout": 0.05}, [7, 1337, 2021], str(tmp_path / "root"))
    assert s["run_status"] == ["ok", "ok", "ok"] and len(s["per_seed"]) == 3
    assert abs(s["mean"] - 0.205957) < 1e-5 and s["std"] > 0
    assert len(s["slices_per_seed"]) == 3 and s["metrics_dirs"][0].endswith("seed_7")
    doc = json.loads((tmp_path / "root" / "summary.json").read_text(encoding="utf-8"))
    assert doc["config_diff"] == {"dropout": 0.05} and doc["config"]["dropout"] == 0.05


def test_cli_validate_run_run_seeds(tmp_path):
    p = tmp_path / "evaluator.json"
    p.write_text(json.dumps(_ev()), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT, "validate", str(p)], capture_output=True, text=True)
    assert r.returncode == 0 and "合法" in r.stdout
    r = subprocess.run([sys.executable, SCRIPT, "run", "--evaluator", str(p), "--seed", "7",
                        "--out", str(tmp_path / "one")], capture_output=True, text=True)
    assert r.returncode == 0 and '"status": "ok"' in r.stdout
    r = subprocess.run([sys.executable, SCRIPT, "run-seeds", "--evaluator", str(p),
                        "--config-diff", '{"crash": true}', "--out-root", str(tmp_path / "bad")],
                       capture_output=True, text=True)
    assert r.returncode == 2 and (tmp_path / "bad" / "summary.json").exists()
    r = subprocess.run([sys.executable, SCRIPT, "run", "--evaluator", str(p), "--seed", "7",
                        "--config-diff", '{"n_heads": 1}', "--out", str(tmp_path / "x")],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "未登记" in (r.stdout + r.stderr)
