"""worst-points golden：单单元 3 窗口，分别植入 极值点/转折点/高波动点（各配大误差 5，
底噪 0.1）→ top-3 必须是这 3 个点且各自标签命中（标签可叠加，断言成员而非相等）。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_worst_points as cwp  # noqa: E402
from synth import make_long       # noqa: E402


def _df():
    # 三类现象放三个不同单元——标签阈值按单元自身分位数算，
    # 植入点是本单元该统计量的最大值 ⇒ 必然 ≥ q95（分位数 ≤ 最大值恒成立），回收有保证。
    def y_fn(w, u, s):
        if u == "U_ext":
            return 100.0 if s == 30 else 10.0 + 0.05 * s   # 极值尖峰
        if u == "U_ramp":
            return 50.0 if s >= 30 else 10.0               # 30 处陡坡（转折点）
        if 40 <= s <= 50:                                  # U_vol 高波动段
            return 10.0 + (8.0 if s % 2 == 0 else -8.0)
        return 10.0 + 0.05 * s

    def err(m, u, w, s):
        big = (u == "U_ext" and s == 30) or \
              (u == "U_ramp" and s == 30) or \
              (u == "U_vol" and s == 45)
        return 5.0 if big else 0.1

    df = make_long(["A"], ["U_ext", "U_ramp", "U_vol"],
                   ["2024-01-01"], 60, err, y_fn=y_fn)
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_top3_points_and_labels():
    st = cwp.compute(_df(), top_n=3, freq="15min")
    pts = st["models"]["A"]["points"]
    assert len(pts) == 3
    by_key = {(p["unit"], p["step"]): p for p in pts}
    assert ("U_ext", 30) in by_key
    assert "极值" in by_key[("U_ext", 30)]["labels"]
    assert "转折点" in by_key[("U_ramp", 30)]["labels"]
    assert "高波动" in by_key[("U_vol", 45)]["labels"]
    for p in pts:
        assert p["err"] == 5.0
        assert set(p["context"]) == {"abs_dy", "local_std", "y_quantile"}


def test_label_share_sums_to_points():
    st = cwp.compute(_df(), top_n=3, freq="15min")
    share = st["models"]["A"]["label_share"]
    assert all(0 <= v <= 1 for v in share.values())


def test_main_writes_outputs(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    cwp.main(["--pred", str(p), "--out-dir", str(tmp_path), "--top-n", "3"])
    assert (tmp_path / "worst-points.json").exists()
    assert (tmp_path / "worst-points.png").exists()
