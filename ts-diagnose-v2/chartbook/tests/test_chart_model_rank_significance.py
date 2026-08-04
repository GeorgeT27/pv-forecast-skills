"""model-rank-significance golden:恒差对显著分离;克隆对不可区分。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_model_rank_significance as cmr  # noqa: E402
from synth import make_long, alt             # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 31)] + \
          [f"2024-02-{d:02d}" for d in range(1, 11)]  # 40 窗


def _err(m, u, w, s):
    widx = WINDOWS.index(w)
    if m == "A":
        return alt(1.0, s)
    if m == "B":
        return alt(3.0 + 0.5 * (widx % 2), s)
    if m in ("C", "D"):
        return alt(2.0, s)
    raise AssertionError(m)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_separated_pair():
    df = _prep(make_long(["A", "B"], ["U1"], WINDOWS, 6, _err))
    st = cmr.compute(df)
    assert st["avg_ranks"]["A"] == 1.0 and st["avg_ranks"]["B"] == 2.0
    assert 1.0 > st["cd"]
    assert st["dm"]["A|B"]["p"] < 0.05
    assert st["best_group"] == ["A"]


def test_clone_pair_indistinguishable():
    df = _prep(make_long(["C", "D"], ["U1"], WINDOWS, 6, _err))
    st = cmr.compute(df)
    assert st["avg_ranks"]["C"] == 1.5 and st["avg_ranks"]["D"] == 1.5
    assert st["dm"]["C|D"]["p"] == 1.0
    assert sorted(st["best_group"]) == ["C", "D"]


def test_single_model_raises():
    df = _prep(make_long(["A"], ["U1"], WINDOWS[:4], 6, _err))
    try:
        cmr.compute(df)
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "2" in str(e)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A", "B"], ["U1"], WINDOWS, 6, _err)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cmr.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "model-rank-significance.json").exists()
    assert (tmp_path / "model-rank-significance.png").exists()
