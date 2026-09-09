"""现场写图样板：拷了就能跑、对账两关真的会 FAIL、产物带 verification 供索引归组。
样板腐烂了这里先红——它是「chartbook 未覆盖就现场写」那条路的起点。"""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

CHARTBOOK = Path(__file__).resolve().parents[1]
ENGINE = CHARTBOOK.parent
TEMPLATE = CHARTBOOK / "adhoc-template.py"

sys.path.insert(0, str(CHARTBOOK / "scripts"))


def _pred_csv(tmp_path):
    rows = []
    for m, bias in (("A", 0.1), ("B", 0.3)):
        for w in ("2024-01-01 00:00:00", "2024-01-02 00:00:00"):
            for s in range(8):
                rows.append({"window_ts": w, "unit_id": "U1", "model": m,
                             "horizon_step": s, "y_true": 1.0,
                             "y_pred": 1.0 + bias * (1 if s % 2 else -1)})
    p = tmp_path / "pred.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def _run(tmp_path, *extra):
    dst = tmp_path / "mine.py"
    dst.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(dst), "--pred", str(_pred_csv(tmp_path)),
         "--out-dir", str(tmp_path / "charts"), "--engine", str(ENGINE), *extra],
        capture_output=True, text=True)


def test_template_runs_and_verifies(tmp_path):
    proc = _run(tmp_path, "--verify")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "关1 行数守恒" in proc.stdout and "FAIL" not in proc.stdout
    d = json.loads((tmp_path / "charts" / "my-adhoc-chart.json").read_text(
        encoding="utf-8"))
    assert d["verification"]["tier"] == "reconcile-2"
    assert d["verification"]["passed"] is True
    assert (tmp_path / "charts" / "my-adhoc-chart.png").exists()


def test_template_carries_metric_through_both_halves(tmp_path):
    """口径开关必须贯穿 compute 与 verify——只改一半时对账关会 FAIL。"""
    proc = _run(tmp_path, "--verify", "--metric", "mse")
    assert proc.returncode == 0, proc.stdout
    d = json.loads((tmp_path / "charts" / "my-adhoc-chart.json").read_text(
        encoding="utf-8"))
    assert d["metric"] == "mse"
    e = 0.1 ** 2  # A 的每点平方误差恒定
    assert d["per_model"]["A"] == pytest.approx(e, rel=1e-6)


def test_template_warns_when_verification_skipped(tmp_path):
    proc = _run(tmp_path)
    assert proc.returncode == 0
    assert "未跑 --verify" in proc.stdout
    d = json.loads((tmp_path / "charts" / "my-adhoc-chart.json").read_text(
        encoding="utf-8"))
    assert "verification" not in d, "没验证过就不许带 verification 字段冒充一等证据"


def test_template_output_lands_in_adhoc_group_of_index(tmp_path):
    """端到端：样板产物必须被 build_index 认成现场脚本，不是「未识别产物」。"""
    assert _run(tmp_path, "--verify").returncode == 0
    import build_index as bi
    text = bi.build(tmp_path / "charts")
    assert "## 现场脚本（chartbook 未覆盖）" in text
    assert "验证档位: reconcile-2" in text
