"""error-breakdown golden：植入 (U2, 2024-02) 单元格误差幅度 3（其余 1）→
argmax 单元格、边际曲线、Top-K 必须回收。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_error_breakdown as ceb  # noqa: E402
import chart_common as cc            # noqa: E402
from synth import make_long, alt     # noqa: E402


def _df():
    windows = [f"2024-{mm:02d}-{dd:02d}" for mm in (1, 2, 3)
               for dd in (5, 15, 25)]

    def err(m, u, w, s):
        amp = 3.0 if (u == "U2" and w.startswith("2024-02")) else 1.0
        return alt(amp, s)

    df = make_long(["A"], ["U1", "U2"], windows, 8, err)
    df["window_ts"] = __import__("pandas").to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    return df


def test_argmax_cell_recovered():
    st = ceb.compute(_df(), freq="15min", top_k=3)
    cell = st["models"]["A"]["argmax_cell"]
    assert cell["unit"] == "U2" and cell["month"] == "2024-02"
    assert np.isclose(cell["rmse"], 3.0)


def test_marginals_and_topk():
    st = ceb.compute(_df(), freq="15min", top_k=3)
    a = st["models"]["A"]
    # 单元×月矩阵：非植入格恰为 1
    assert np.isclose(a["unit_month_rmse"]["U1"]["2024-01"], 1.0)
    # per-month 边际（U2 被拉高的月）argmax 落在 2024-02
    assert a["per_month"]["argmax"] == "2024-02"
    top = a["top_worst"]
    assert top[0]["unit"] == "U2" and top[0]["month"] == "2024-02"
    assert len(top) == 3
    # horizon 分带矩阵存在且键完整
    assert set(a["unit_band_rmse"]["U2"]) == {"band0", "band1", "band2", "band3"}


def test_main_writes_json_and_png(tmp_path):
    p = tmp_path / "pred.csv"
    _df().drop(columns=["err"]).to_csv(p, index=False)
    ceb.main(["--pred", str(p), "--out-dir", str(tmp_path)])
    assert (tmp_path / "error-breakdown.json").exists()
    assert (tmp_path / "error-breakdown.png").exists()
