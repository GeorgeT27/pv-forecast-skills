"""chart_common 单测：长表校验 / row_rmse / 形状描述符 / 落盘双产物。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chart_common as cc          # noqa: E402
from synth import make_long        # noqa: E402


def _write_csv(tmp_path, df):
    p = tmp_path / "pred.csv"
    df.to_csv(p, index=False)
    return p


def test_load_predictions_missing_col_raises(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 4,
                   lambda m, u, w, s: 1.0).drop(columns=["y_pred"])
    with pytest.raises(ValueError, match="y_pred"):
        cc.load_predictions(_write_csv(tmp_path, df))


def test_load_predictions_adds_err_and_datetime(tmp_path):
    df = make_long(["A"], ["U1"], ["2024-01-01"], 4, lambda m, u, w, s: 2.0)
    out = cc.load_predictions(_write_csv(tmp_path, df))
    assert np.allclose(out["err"], 2.0)
    assert pd.api.types.is_datetime64_any_dtype(out["window_ts"])


def test_row_rmse_exact():
    # err = ±3 交替 ⇒ 每行 RMSE 恰为 3
    df = make_long(["A"], ["U1"], ["2024-01-01", "2024-01-02"], 8,
                   lambda m, u, w, s: 3.0 * (1 if s % 2 == 0 else -1))
    df["window_ts"] = pd.to_datetime(df["window_ts"])
    df["err"] = df["y_pred"] - df["y_true"]
    rr = cc.row_rmse(df)
    assert len(rr) == 2
    assert np.allclose(rr["rmse"], 3.0)
    assert set(rr.columns) == {"model", "unit_id", "window_ts", "rmse"}


def test_curve_stats_fields_and_values():
    st = cc.curve_stats([1.0, 1.0, 4.0, 2.0])
    assert st["trend"] == "上升"
    assert st["monotonic"] is False
    assert st["max_jump_idx"] == "1" and st["max_jump"] == 3.0
    assert st["argmax"] == "2" and st["argmin"] == "0"
    assert set(st) == {"curve", "trend", "monotonic", "max_jump_idx",
                       "max_jump", "roughness", "argmax", "argmin"}


def test_downsample_keeps_ends_and_bound():
    d = {str(i): i for i in range(2000)}
    out = cc.downsample(d, max_points=100)
    assert len(out) <= 100
    assert "0" in out and "1999" in out


def test_save_outputs_writes_json_and_png(tmp_path):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    stats = cc.save_outputs(fig, tmp_path, "demo-recipe", {"a": 1})
    assert stats == {"a": 1}
    assert (tmp_path / "demo-recipe.png").exists()
    loaded = json.loads((tmp_path / "demo-recipe.json").read_text())
    assert loaded == {"a": 1}


def test_curve_stats_degenerate_single_point():
    st = cc.curve_stats([5.0], index=["only"])
    assert st["max_jump_idx"] is None and st["max_jump"] == 0.0
    assert st["argmax"] == "only" and st["argmin"] == "only"


def test_setup_font_returns_hits_and_renders_cjk(tmp_path):
    """setup_font 返回命中字体列表;命中时渲染中文+负号必须无 missing-glyph 警告。"""
    import warnings
    import matplotlib.pyplot as plt
    hits = cc.setup_font()
    assert isinstance(hits, list)
    if not hits:
        pytest.skip("环境无 CJK 字体")
    assert plt.rcParams["font.family"] == ["sans-serif"]
    assert plt.rcParams["font.sans-serif"][:len(hits)] == hits
    fig, ax = plt.subplots()
    ax.set_title("中文标题")
    ax.plot([0, 1], [-1.5, 1.0])
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        fig.savefig(tmp_path / "cjk.png")
    plt.close(fig)
    bad = [w for w in rec if "Glyph" in str(w.message) or "findfont" in str(w.message)]
    assert not bad, f"渲染出缺字形警告: {[str(w.message) for w in bad]}"


def test_detect_period_steps_sine():
    x = 10 + 5 * np.sin(2 * np.pi * np.arange(96) / 24)
    assert cc.detect_period_steps(x, max_lag=48) == 24


def test_detect_period_steps_aperiodic_returns_none():
    x = np.arange(50, dtype=float)  # 纯趋势,无周期
    assert cc.detect_period_steps(x, max_lag=20) is None


def test_detect_period_steps_period_at_max_lag_boundary():
    # 3 个完整周期(72 点),period=24=max_lag → 真峰恰好落在 rho 数组末位(无右邻)。
    # 注:用 2 个周期(48 点)会让线性去趋势后 lag=24 处 rho 跌破默认 threshold=0.5
    # (仅约 0.37,边界处单周期重叠样本太少),故取 3 周期保证边界峰能稳健地过阈值。
    x = 10 + 5 * np.sin(2 * np.pi * np.arange(72) / 24)
    assert cc.detect_period_steps(x, max_lag=24) == 24


def test_metric_fn_switches_caliber():
    """按 row/model 之外的维度池化的图共用这个聚合函数，别各写各的平方根。"""
    e = np.array([1.0, 2.0, 3.0])
    assert cc.metric_fn("mse")(e) == pytest.approx(14 / 3)
    assert cc.metric_fn("rmse")(e) == pytest.approx(np.sqrt(14 / 3))
    with pytest.raises(ValueError, match="只支持"):
        cc.metric_fn("bogus")


def test_metric_label_for_figures():
    assert cc.metric_label("mse") == "MSE"
    assert cc.metric_label("rmse") == "RMSE"


def test_row_and_pooled_metric_agree_with_metric_fn():
    """三个入口必须同源——row/pooled 改实现时这条会红。"""
    df = pd.DataFrame({
        "model": ["A"] * 4, "unit_id": ["u"] * 4,
        "window_ts": ["t"] * 4, "horizon_step": [0, 1, 2, 3],
        "err": [1.0, -2.0, 3.0, -4.0]})
    fn = cc.metric_fn("mse")
    assert cc.row_metric(df, "mse")["rmse"].iloc[0] == pytest.approx(fn(df["err"]))
    assert cc.pooled_metric(df, "mse")["A"] == pytest.approx(fn(df["err"]))
