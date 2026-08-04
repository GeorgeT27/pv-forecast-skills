"""单行诊断 analyze_row.py 的金标准锚定：拿 golden 的埋点行钉死点名/洗清纪律。

钉住的不变量（与 golden/manifest.json 的埋点一致）：
  - pred_M1 × ultra_short 最坏行（2025-01-02 09:00）→ 必点名 f_blame、绝不点名 f_decoy。
  - pred_M4res × rmse_192 最坏行 → 必点名 f_res_culprit；f_sys_bias 被「补偿闸」洗清、
    f_irreducible 被「可约性闸」洗清（都不点名）。
  - 单行证据级别恒为 phenomenon；被点名的共线簇成员进 named_in_cluster。
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK_DIR = os.path.dirname(HERE)
# golden-feature-blame（非 golden/）：本 playbook 自身的 golden/ 是 feature-importance 引擎
# 金标准（gen_gate 用），与本文件迁自 pv-feature-blame 的金标准数据是两回事，迁移时改名
# 隔离，避免误当成引擎 golden（2026-07-24）。
GOLDEN = os.path.join(PLAYBOOK_DIR, "golden-feature-blame")
TOOL = os.path.join(HERE, "analyze_row.py")


def run(workdir, extra):
    args = [sys.executable, TOOL,
            "--feature-true", os.path.join(GOLDEN, "golden_feature_true.parquet"),
            "--test", os.path.join(GOLDEN, "golden_test.parquet"),
            "--predict", os.path.join(GOLDEN, "golden_predict.parquet"),
            "--no-plots", "--prefix", "t"] + extra
    r = subprocess.run(args, cwd=workdir, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    js = [f for f in os.listdir(workdir) if f.startswith("t_") and f.endswith(".json")]
    assert js, "没产出 JSON"
    return json.load(open(os.path.join(workdir, js[0]), encoding="utf-8"))


@pytest.fixture
def wd(tmp_path):
    for f in os.listdir(GOLDEN):
        if f == "feature_decomp.json" or f == "feature_pairs.json" or f.startswith("eps_res_"):
            (tmp_path / f).write_bytes(open(os.path.join(GOLDEN, f), "rb").read())
    return str(tmp_path)


def test_blame_named_decoy_cleared_on_worst(wd):
    """M1 ultra_short 最坏行：点名 f_blame、洗清 f_decoy（诱饵防冤枉）。"""
    s = run(wd, ["--model", "pred_M1", "--metric", "ultra_short", "--worst"])
    assert s["timestamp_win"] == "2025-01-02 09:00:00"
    assert s["focus"]["named_features"] == ["f_blame"]
    assert s["focus"]["features"]["f_decoy"]["blamed"] is False
    assert s["evidence_level"] == "phenomenon"


def test_residual_culprit_named_sysbias_compensated(wd):
    """M4res rmse_192 最坏行：点名 f_res_culprit；f_sys_bias 补偿闸、f_irreducible 可约性闸洗清。"""
    s = run(wd, ["--model", "pred_M4res", "--metric", "rmse_192", "--worst"])
    feats = s["focus"]["features"]
    assert "f_res_culprit" in s["focus"]["named_features"]
    assert feats["f_sys_bias"]["blamed"] is False
    assert "compensated" in feats["f_sys_bias"]["gate_reason"]
    assert feats["f_irreducible"]["blamed"] is False
    assert "irreducible" in feats["f_irreducible"]["gate_reason"]
    # 被点名者落在共线簇里 → 必须登记进 named_in_cluster（不单点名）
    assert "f_res_culprit" in s["focus"]["named_in_cluster"]


def test_decoy_never_named_anywhere(wd):
    """f_decoy 误差可以很大，但零耦合——任何口径×模型都不许点名。"""
    for model, metric in (("pred_M1", "ultra_short"), ("pred_M1", "rmse_192"),
                          ("pred_ensemble", "short")):
        s = run(wd, ["--model", model, "--metric", metric, "--worst"])
        assert "f_decoy" not in s["focus"]["named_features"], (model, metric)


def test_missing_row_reports_range(wd):
    """越界时间戳：非零退出且提示可用范围（不静默乱点名）。"""
    r = subprocess.run(
        [sys.executable, TOOL,
         "--feature-true", os.path.join(GOLDEN, "golden_feature_true.parquet"),
         "--test", os.path.join(GOLDEN, "golden_test.parquet"),
         "--predict", os.path.join(GOLDEN, "golden_predict.parquet"),
         "--no-plots", "--row", "2099-01-01 00:00:00"],
        cwd=wd, capture_output=True, text=True)
    assert r.returncode != 0
    assert "不在 feature_true" in (r.stdout + r.stderr)
