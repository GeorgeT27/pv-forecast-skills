"""切片配对 z 检验测试：跨种子成对差值的 z 统计，z>3 记真实差异、否则 `~noise`
（阶段1-architecture-attribution-playbook.md §3.1 的判定纪律）。"""
import csv
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import slice_zcheck as sz  # noqa: E402


def test_paired_z_real_difference():
    """3 种子配对差 [0.2, 0.15, 0.25]：mean=0.2, std=0.05, se=0.05/sqrt(3) → z≈6.93 > 3。"""
    mean, z = sz.paired_z([0.2, 0.15, 0.25])
    assert abs(mean - 0.2) < 1e-9
    assert z > 3


def test_paired_z_noise():
    """3 种子配对差 [0.01, -0.02, 0.015]：均值接近 0、方差主导 → |z| 落噪声底内。"""
    mean, z = sz.paired_z([0.01, -0.02, 0.015])
    assert abs(z) <= 3


def test_paired_z_insufficient_seeds_returns_zero():
    """n<2 时统计量不可算，z 记 0.0（呼叫方靠 n_seeds 字段判样本量不足）。"""
    assert sz.paired_z([])[1] == 0.0
    assert sz.paired_z([0.1])[1] == 0.0


def test_slice_zcheck_labels_real_vs_noise():
    rows = [
        {"slice": "far", "seed": "7", "model_a": "1.0", "model_b": "1.2"},
        {"slice": "far", "seed": "1337", "model_a": "1.0", "model_b": "1.15"},
        {"slice": "far", "seed": "2021", "model_a": "1.0", "model_b": "1.25"},
        {"slice": "near", "seed": "7", "model_a": "1.0", "model_b": "1.01"},
        {"slice": "near", "seed": "1337", "model_a": "1.0", "model_b": "0.98"},
        {"slice": "near", "seed": "2021", "model_a": "1.0", "model_b": "1.015"},
    ]
    out = sz.slice_zcheck(rows)
    assert out["far"]["n_seeds"] == 3
    assert out["far"]["verdict"] == "real"
    assert out["near"]["verdict"] == "~noise"


def test_slice_zcheck_threshold_is_configurable():
    rows = [{"slice": "s", "seed": str(i), "model_a": "1.0", "model_b": str(1.0 + d)}
            for i, d in enumerate([0.20, 0.15, 0.25])]
    assert sz.slice_zcheck(rows, z_threshold=3.0)["s"]["verdict"] == "real"
    assert sz.slice_zcheck(rows, z_threshold=100.0)["s"]["verdict"] == "~noise"


def test_cli_writes_self_describing_json(tmp_path):
    csv_path = tmp_path / "metrics.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slice", "seed", "model_a", "model_b"])
        for seed, b in zip(("7", "1337", "2021"), ("1.2", "1.15", "1.25")):
            w.writerow(["far", seed, "1.0", b])
        for seed, b in zip(("7", "1337", "2021"), ("1.01", "0.98", "1.015")):
            w.writerow(["near", seed, "1.0", b])
    out_path = tmp_path / "slice_zcheck.json"
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "slice_zcheck.py"),
         "--metrics", str(csv_path), "--out", str(out_path)],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.load(open(out_path, encoding="utf-8"))
    assert data["n_slices"] == 2
    assert data["n_real"] == 1
    assert data["n_noise"] == 1
    assert data["slices"]["far"]["verdict"] == "real"
    assert data["slices"]["near"]["verdict"] == "~noise"
    assert data["z_threshold"] == 3.0
