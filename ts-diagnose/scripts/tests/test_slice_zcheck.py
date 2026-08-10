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
    """3 种子配对差 [0.2, 0.15, 0.25]：mean=0.2, sd(ddof=1)=0.05 → z=4.0 > 3。"""
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


def test_z_is_effect_size_not_t_statistic():
    """口径钉死：z = mean/sd，不含 1/√n 因子。

    阈值 3 承载的是「3σ 噪声底」语义——与同一验证脊上的
    ablation_verdict.verdict()（`abs(delta) < noise_floor_3sigma` → undecided）
    和 case.json 的 `noise_floor_3sigma` 同族。配对 t 统计量 mean/(sd/√n)
    会多出 √n 倍，把实际门槛压成 3/√n σ。
    diffs=[0.2,0.15,0.25]：mean=0.2, sd(ddof=1)=0.05 → z 必须是 4.0，不是 6.93。"""
    mean, z = sz.paired_z([0.2, 0.15, 0.25])
    assert abs(mean - 0.2) < 1e-9
    assert abs(z - 4.0) < 1e-9, f"z={z}：仍含 √n 因子（t 统计量口径）"


def test_threshold_does_not_loosen_as_seeds_increase():
    """加种子不得放松判据。固定效应量 2σ（低于 3σ 噪声底）无论几个种子都必须判 ~noise。

    t 统计量口径下 2σ 效应在 n=3 时 z=3.46、n=12 时 z=6.93，种子越多越容易被判
    「真实差异」——与噪声底纪律方向相反，会让 agent 在噪声上生成假设。"""
    for n in (3, 6, 12):
        # 构造 mean=2·sd 的配对差：半数 +3、半数 +1 → mean=2, sd(ddof=1)≈1.03
        diffs = [3.0, 1.0] * (n // 2)
        _, z = sz.paired_z(diffs)
        assert abs(z) <= 3, f"n={n} 时 z={z:.2f} > 3——效应量仅 2σ 却被判真实差异"


def test_c1_slice_map_reproduces_gold_z_bands():
    """真实数据回归：C1 近端切片的 z 必须落进 gold 声明的区间。

    数值取自 eval-cases（PatchTST vs iTransformer，ETTh1 pl96，3 种子，lead 1-24 的 MSE）。
    gold-reasoning.md 记「PatchTST 赢近端 lead 1-24（z≈10）」，case.json 记该档
    「z≈7-10」；t 统计量口径给出 13.81，出界。"""
    seeds = ("7", "1337", "2021")
    ptst = (0.300391, 0.303101, 0.302855)
    itrans = (0.314720, 0.315687, 0.319045)
    rows = [{"slice": "near", "seed": s, "model_a": str(a), "model_b": str(b)}
            for s, a, b in zip(seeds, ptst, itrans)]
    near = sz.slice_zcheck(rows)["near"]
    assert near["verdict"] == "real"
    assert abs(near["mean_diff"] - 0.01437) < 1e-4      # gold 记 -0.0144（符号相反口径）
    assert 7.0 <= near["z"] <= 10.0, f"z={near['z']:.2f} 落在 gold 区间 7-10 之外"


def test_c1_intervention_collapses_near_slice_z_to_noise():
    """真实数据回归：注意力置零（I3）后近端 z 必须塌到 ~0.1 并判 ~noise。

    gold：「近端劣势 -0.0144 → +0.0003（z 6.8→0.1）」。这条钉住的是消融判读的
    关键跃变——干预抹平了差异，而不是把差异翻转成另一个显著效应。"""
    seeds = ("7", "1337", "2021")
    ptst = (0.300391, 0.303101, 0.302855)
    i3 = (0.303346, 0.301163, 0.302628)
    rows = [{"slice": "near", "seed": s, "model_a": str(a), "model_b": str(b)}
            for s, a, b in zip(seeds, ptst, i3)]
    near = sz.slice_zcheck(rows)["near"]
    assert near["verdict"] == "~noise"
    assert 0.08 <= abs(near["z"]) <= 0.14, f"z={near['z']:.3f}，gold 记 ≈0.1"


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
