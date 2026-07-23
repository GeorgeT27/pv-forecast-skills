"""worst-slice-compare golden：A 仅 2024-02 差（RMSE 3，其余 1），B 恒 1 →
最差片=2024-02、片内 A=3/B=1、gap 全部集中该片（concentration_ratio=1）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_worst_slice_compare as cwsc  # noqa: E402
from synth import make_long, alt          # noqa: E402


def _df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]

    def err(m, u, w, s):
        amp = 3.0 if (m == "A" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_worst_slice_and_compare():
    st = cwsc.compute(_df(), focal_model="A")
    assert st["worst_slice"] == "2024-02"
    assert np.isclose(st["in_slice"]["A"], 3.0)
    assert np.isclose(st["in_slice"]["B"], 1.0)
    assert np.isclose(st["slice_gaps"]["2024-02"], 2.0)
    assert np.isclose(st["slice_gaps"]["2024-01"], 0.0)
    assert np.isclose(st["concentration_ratio"], 1.0)
    assert "2024-02-15" in st["daily_in_slice"]["A"]


def test_unknown_focal_raises():
    with pytest.raises(ValueError, match="focal"):
        cwsc.compute(_df(), focal_model="Z")


def test_single_model_raises():
    df = _df()
    with pytest.raises(ValueError, match="2"):
        cwsc.compute(df[df["model"] == "A"], focal_model="A")


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cwsc.main(["--pred", str(p), "--out-dir", str(tmp_path),
               "--focal-model", "A"])
    assert (tmp_path / "worst-slice-compare.json").exists()
    assert (tmp_path / "worst-slice-compare.png").exists()


def _df_perm():
    """置换基线专用加密版：8 日/月——A 的 8 个坏日全在 2024-02。
    随机重排把 8 个坏日重聚同一片的概率 ~4e-6 ⇒ perm_p 恰为 1/201，
    判定稳不依赖种子运气（3 日/月的原构造 null 概率 1/28，太贴 0.05 线）。"""
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (2, 5, 8, 11, 14, 17, 20, 23)]

    def err(m, u, w, s):
        amp = 3.0 if (m == "A" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A", "B"], ["U1"], windows, 4, err)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_perm_significant_on_planted():
    st = cwsc.compute(_df_perm(), focal_model="A")
    perm = st["perm"]
    assert perm["stat"] == "worst_slice_gap"
    assert perm["n_perm"] == 200 and perm["seed"] == 0
    assert np.isclose(perm["real_stat"], 2.0)
    assert perm["perm_p"] < 0.05
    assert perm["null_q95"] < perm["real_stat"]
    assert perm["verdict"] == "significant"


def test_perm_not_significant_on_diffuse_decoy():
    """弥散诱饵：A 各月同幅小差 → 任意重排统计量不变 → perm_p 精确 = 1.0。
    防「逢集中必点名」——conc 描述量照算，但置换判 not-significant。"""
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]
    df = make_long(["A", "B"], ["U1"], windows, 4,
                   lambda m, u, w, s: alt(1.2 if m == "A" else 1.0, s))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    st = cwsc.compute(df, focal_model="A")
    assert st["perm"]["verdict"] == "not-significant"
    assert np.isclose(st["perm"]["perm_p"], 1.0)


def test_perm_skipped_when_focal_never_behind():
    """焦点全面领先 → 最差片无正差距 → perm 置 null、原因进 note。"""
    st = cwsc.compute(_df(), focal_model="B")
    assert st["perm"] is None
    assert "perm 未做" in st["note"]


def test_perm_disabled_flag():
    st = cwsc.compute(_df_perm(), focal_model="A", n_perm=0)
    assert st["perm"] is None
    assert "n_perm=0" in st["note"]
