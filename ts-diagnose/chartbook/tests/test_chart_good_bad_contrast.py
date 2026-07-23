"""good-bad-contrast golden:真凶 quality 分离(d≥1.5)居首、同分布诱饵 |d|<0.2。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_good_bad_contrast as cgb  # noqa: E402
from synth import make_long, alt       # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 21)]  # 20 窗;前 10 坏后 10 好
BAD = set(WINDOWS[:10])


def _prep(df):
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feats():
    rows = []
    for w in WINDOWS:
        widx = WINDOWS.index(w)
        for s in range(6):
            # 真凶:坏/好窗质量差 4/0.5 量级,按窗序微抖动(组内方差>0,d 分母才有意义)
            culprit_q = (4.0 + 0.1 * (widx % 3)) if w in BAD else (0.5 + 0.1 * (widx % 3))
            # 诱饵:两组近同分布(widx%3 在两组计数只差 1,d≈0.1)
            decoy_q = 1.0 + 0.2 * (widx % 3)
            for name, q in (("culprit", culprit_q), ("decoy", decoy_q)):
                rows.append({"window_ts": w, "unit_id": "U1", "feature": name,
                             "horizon_step": s, "f_pred": 10.0,
                             "f_true": 10.0 + q})
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def _err(m, u, w, s):
    return alt(5.0 if w in BAD else 0.5, s)


def test_culprit_ranked_first_decoy_cleared():
    df = _prep(make_long(["A"], ["U1"], WINDOWS, 6, _err))
    st = cgb.compute(df, _feats(), k=10)
    a = st["models"]["A"]
    assert a["k"] == 10
    assert a["ranked"][0] == "culprit"
    culprit = a["features"]["culprit"]
    assert culprit["basis"] == "quality" and culprit["d"] >= 1.5
    assert culprit["direction"] == 1
    assert abs(a["features"]["decoy"]["d"]) < 0.2


def test_k_too_small_raises(tmp_path):
    df = _prep(make_long(["A"], ["U1"], WINDOWS[:4], 6, _err))
    try:
        cgb.compute(df, _feats(), k=2)
        assert False, "应抛 ValueError"
    except ValueError as e:
        assert "5" in str(e)


def test_main_writes_outputs(tmp_path):
    df = make_long(["A"], ["U1"], WINDOWS, 6, _err)
    p, f = tmp_path / "pred.csv", tmp_path / "feat.csv"
    df.to_csv(p, index=False)
    _feats().to_csv(f, index=False)
    cgb.main(["--pred", str(p), "--features", str(f),
              "--out-dir", str(tmp_path), "--k", "10"])
    assert (tmp_path / "good-bad-contrast.json").exists()
    assert (tmp_path / "good-bad-contrast.png").exists()
