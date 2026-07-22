"""y-vs-feature-mapping golden：前半期 y=0.5f、后半期 y=0.5f−5（物理映射整体
位移）→ 每箱 shift 恰为 −5、mean_abs_shift=5。分箱边界取全期 pooled 保两期可比。

f 取模 10 映射（日 1..10 与 11..20 落到同一 f 值集）⇒ 两期分箱分布逐箱相同，
无边界稀释，每箱位移精确 −5，紧容差可回收。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_y_vs_feature_mapping as cym  # noqa: E402
from synth import make_long                # noqa: E402

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 21)]   # 前 10 天 A 期、后 10 天 B 期


def _f(w, s):
    # 模 10 映射：日 1..10 与 11..20 落到同一 f 值集 ⇒ 两期分箱分布逐箱相同，
    # 位移每箱恰为 −5（无边界稀释）
    return 10.0 * s + ((int(w[-2:]) - 1) % 10) + 1


def _y(w, s):
    base = 0.5 * _f(w, s)
    return base if int(w[-2:]) <= 10 else base - 5.0


def _pred_df():
    df = make_long(["A"], ["U1"], WINDOWS, 16,
                   err_fn=lambda m, u, w, s: 0.1,
                   y_fn=lambda w, u, s: _y(w, s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def _feat_df():
    rows = [{"window_ts": w, "unit_id": "U1", "feature": "ghi",
             "horizon_step": s, "f_pred": _f(w, s), "f_true": _f(w, s)}
            for w in WINDOWS for s in range(16)]
    df = pd.DataFrame(rows)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    return df


def test_shift_recovered():
    st = cym.compute(_pred_df(), _feat_df(), split_date="2024-01-11")
    ghi = st["features"]["ghi"]
    assert np.isclose(ghi["mean_shift"], -5.0, atol=0.2)
    assert np.isclose(ghi["mean_abs_shift"], 5.0, atol=0.2)
    assert ghi["n_a"] == 160 and ghi["n_b"] == 160
    assert len(ghi["curve_a"]) >= 5 and len(ghi["curve_b"]) >= 5


def test_default_split_is_median():
    st = cym.compute(_pred_df(), _feat_df())
    assert st["split_date"].startswith("2024-01-1")   # 中位窗附近


def test_main_writes_outputs(tmp_path):
    pp, fp = tmp_path / "p.csv", tmp_path / "f.csv"
    _pred_df().drop(columns=["err"]).to_csv(pp, index=False)
    _feat_df().to_csv(fp, index=False)
    cym.main(["--pred", str(pp), "--features", str(fp),
              "--out-dir", str(tmp_path)])
    assert (tmp_path / "y-vs-feature-mapping.json").exists()
    assert (tmp_path / "y-vs-feature-mapping.png").exists()
