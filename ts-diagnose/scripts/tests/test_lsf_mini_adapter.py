"""lsf-mini 适配器集成测试：ETTh1 + DLinear 1 epoch（几秒）；lsf-mini 或 torch 缺席则 skip。"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ADAPTER = os.path.join(REPO, "eval-cases", "adapters", "lsf_mini_adapter.py")


def _main_checkout_root():
    """REPO 可能是一个 git worktree（隔离开发/测试用），lsf-mini 是主仓库的同级目录，不是
    worktree 目录自己的同级目录——用 git-common-dir 找回主仓库根，worktree 与主仓库里跑都对。"""
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=REPO,
                            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            common = os.path.abspath(os.path.join(REPO, r.stdout.strip()))
            return os.path.dirname(common)
    except Exception:
        pass
    return REPO


LSF = os.path.join(os.path.dirname(_main_checkout_root()), "lsf-mini")

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(LSF, "run.py")) or importlib.util.find_spec("torch") is None,
    reason="需要同级目录的 lsf-mini 与 torch")


def test_adapter_end_to_end_etth1(tmp_path):
    cfg = {"lsf_mini_dir": LSF, "model": "DLinear", "data": "ETTh1",
           "root_path": os.path.join(LSF, "dataset"), "features": "M", "target": "OT",
           "seq_len": 96, "label_len": 48, "pred_len": 24, "enc_in": 7,
           "train_epochs": 1, "patience": 1, "batch_size": 32, "learning_rate": 1e-3}
    (tmp_path / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    out = tmp_path / "s7"
    r = subprocess.run([sys.executable, ADAPTER, "--config", str(tmp_path / "cfg.json"), "--seed", "7",
                        "--out", str(out), "--time-limit", "600"], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-2000:]
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert m["status"] == "ok" and m["metric_id"] == "val_mse" and m["primary"] > 0
    for s in ("horizon:near", "horizon:mid", "horizon:far", "channel:OT"):
        assert s in m["slices"], s
    sealed = json.loads((out / "sealed" / "test_metrics.json").read_text(encoding="utf-8"))
    assert sealed["test_primary"] > 0 and "test_slices" in sealed
    assert not (out / "pred.npy").exists() and not (out / "true.npy").exists()
    assert (out / "results" / "results.csv").exists()          # results.csv 落在 out 目录，不污染 lsf-mini


def test_adapter_crash_writes_metrics(tmp_path):
    cfg = {"lsf_mini_dir": LSF, "model": "NoSuchModel", "data": "ETTh1",
           "root_path": os.path.join(LSF, "dataset"), "enc_in": 7, "train_epochs": 1}
    (tmp_path / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    r = subprocess.run([sys.executable, ADAPTER, "--config", str(tmp_path / "cfg.json"), "--seed", "7",
                        "--out", str(tmp_path / "bad")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 2
    m = json.loads((tmp_path / "bad" / "metrics.json").read_text(encoding="utf-8"))
    assert m["status"] == "crash" and m["error"]
