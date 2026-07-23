"""bad-window-clustering golden:升/降两种坏窗形态 → k=2、成员精确分离。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_bad_window_clustering as cbw  # noqa: E402
from synth import make_long, alt           # noqa: E402

UP = [f"2024-01-{d:02d}" for d in range(1, 7)]     # 升形坏窗
DOWN = [f"2024-01-{d:02d}" for d in range(7, 13)]  # 降形坏窗
GOOD = [f"2024-01-{d:02d}" for d in range(13, 21)]
WINDOWS = UP + DOWN + GOOD


def _y(w, u, s):
    if w in UP:
        return float(s)
    if w in DOWN:
        return float(23 - s)
    return 10.0


def _err(m, u, w, s):
    return alt(5.0 if w in UP + DOWN else 0.1, s)


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_two_shapes_recovered():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 24, _err, y_fn=_y))
    st = cbw.compute(df, top_n=12, seed=0)
    a = st["models"]["A"]
    assert a["chosen_k"] == 2
    assert a["seed"] == 0
    shares = sorted(c["share"] for c in a["clusters"])
    assert np.allclose(shares, [0.5, 0.5])
    protos = [c["prototype"] for c in a["clusters"]]
    trends = sorted(np.sign(p[-1] - p[0]) for p in protos)
    assert trends == [-1.0, 1.0]  # 一升一降


def test_flat_windows_skipped():
    df = _prep(make_long(["A"], ["U1"], GOOD, 24, lambda m, u, w, s: alt(5.0, s),
                         y_fn=lambda w, u, s: 10.0))
    st = cbw.compute(df, top_n=8, seed=0)
    assert st["models"]["A"]["skipped_flat"] == 8
    assert st["models"]["A"]["clusters"] == []


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 24, _err, y_fn=_y)
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    cbw.main(["--pred", str(p), "--out-dir", str(tmp_path),
              "--top-n", "12", "--seed", "0"])
    assert (tmp_path / "bad-window-clustering.json").exists()
    assert (tmp_path / "bad-window-clustering.png").exists()
