"""probe_schema / fb_common 单测（内存构造小 DataFrame，不依赖 golden 大文件）。"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fb_common as fb  # noqa: E402
import probe_schema as ps  # noqa: E402

du = fb.require_du()


# ---------------------------------------------------------------- 配对启发式
def test_normalize_col_strips_multiple_markers():
    assert ps.normalize_col("f_blame_pred") == ("f_blame", {"pred"})
    assert ps.normalize_col("ghi_obs") == ("ghi", {"label"})
    assert ps.normalize_col("nwp_ghi_fc") == ("ghi", {"pred"})     # 前后缀双层剥离
    assert ps.normalize_col("mystery_x")[1] == set()               # 无记号


def test_discover_pairs_suffix_prefix_and_unmapped():
    cols = ["a_pred", "a_true", "b_predict", "b_label", "nwp_c_fc", "c_obs", "mystery_x"]
    pairs, unmapped = ps.discover_pairs(cols)
    assert {p["feature"] for p in pairs} == {"a", "b", "c"}
    assert {p["pred_col"] for p in pairs} == {"a_pred", "b_predict", "nwp_c_fc"}
    assert unmapped == ["mystery_x"]


def test_discover_pairs_ambiguous_goes_unmapped():
    # 同词干两个预测列 → 不硬配，全部进 unmapped 由用户裁决
    pairs, unmapped = ps.discover_pairs(["x_pred", "x_forecast", "x_true"])
    assert pairs == []
    assert set(unmapped) == {"x_pred", "x_forecast", "x_true"}


# ---------------------------------------------------------------- 时间戳侦测
def test_detect_ts_col_named_and_index(tmp_path):
    ts = pd.date_range("2025-01-01", periods=4, freq="15min")
    p1 = tmp_path / "win.parquet"
    pd.DataFrame({"timestamp_win": ts, "v": [[1.0] * 192] * 4}).to_parquet(p1)
    assert fb.detect_ts_col(str(p1)) == "timestamp_win"
    df, orig = fb.load_any(str(p1))
    assert orig == "timestamp_win" and du.TIMESTAMP_COL in df.columns

    p2 = tmp_path / "idx.parquet"
    pd.DataFrame({"v": [[1.0] * 192] * 4}, index=ts).to_parquet(p2)
    assert fb.detect_ts_col(str(p2)) == "<index>"


# ---------------------------------------------------------------- 模型列发现
def test_discover_models_only_horizon_lists():
    lists = {"pred_M1": 192, "observe_power": 672, "pred_ensemble": 192, "junk": 5}
    assert ps.discover_models(lists, 192) == ["pred_M1", "pred_ensemble"]
    assert ps.discover_models({"only": 192}, 192) == ["only"]      # 单模型也成立


# ---------------------------------------------------------------- 坏行判定与口径
def test_bad_mask_top_pct_above_mean():
    err = np.array([0.0] * 9 + [10.0])
    m = fb.bad_mask(err, top_pct=10)
    assert m.sum() == 1 and m[9]
    assert fb.bad_mask(np.ones(10), top_pct=10).sum() == 0         # 全相等：无人高于均值


def test_row_errors_definitions_from_data_utils():
    ts = pd.Series(pd.to_datetime(["2025-01-01 08:45", "2025-01-01 09:00", "2025-01-01 09:15"]))
    Y = np.zeros((3, du.HORIZON))
    P = np.zeros((3, du.HORIZON))
    P[1, du.ULTRA_SHORT_IDX] = 4.0                                 # 只碰考核点
    P[1, du.SHORT_SLICE] = 3.0
    sel, err = fb.row_errors(ts, P, Y, "ultra_short")
    assert list(sel) == [0, 1, 2] and err[1] == pytest.approx(4.0)
    sel, err = fb.row_errors(ts, P, Y, "short")
    assert list(sel) == [1]                                        # 仅 09:00 行
    assert err[0] == pytest.approx(3.0)                            # [59:155] 上恒 3.0 → RMSE=3.0


def test_metric_slices_import_not_rederive():
    s = fb.metric_slices()
    assert s["ultra_short"] == slice(0, du.ULTRA_SHORT_IDX + 1)
    assert s["short"] == du.SHORT_SLICE
    assert du.ULTRA_SHORT_IDX == 16 and du.SHORT_SLICE == slice(59, 155)


# ---------------------------------------------------------------- 窗一致性闸只闸真值列
def test_wc_targets_excludes_predict_and_pred_features():
    """predict 模型列/预报特征列绝不进闸——逐行重新起报下行间不一致是预期物理
    （翻新信号，归 feature_revision.py），不是窗口构造 bug。"""
    pairs = [{"feature": "ghi", "pred_col": "ghi_pred", "label_col": "ghi_true"}]
    t = ps.wc_targets({du.LABEL_COL: du.HORIZON, "ghi": 864}, pairs)
    assert t["test"] == [du.LABEL_COL]                             # 只有功率真值列
    assert t["feature_true"] == ["ghi_true"]                       # 只有 label 列
    flat = [c for cols in t.values() for c in cols]
    assert "ghi_pred" not in flat and "ghi" not in flat
    assert "predict" not in t                                      # predict 文件整体不进闸


def test_lead_dependent_predictions_dont_trip_gate():
    """lead-time 依赖的预测列（相邻行对同一物理时刻预测不同）不再触发坏率——
    直接对真值列跑 check_window_consistency 验证闸本身仍有牙。"""
    n = 20
    ts = pd.date_range("2025-01-01", periods=n, freq="15min")
    t0 = ts[0]
    truth = [[float(((t0 - t0) + (t - t0)).total_seconds() / 900 + k) for k in range(du.HORIZON)]
             for t in ts]                                          # 纯物理时间函数 → 一致
    jumpy = [[truth[i][k] + (10.0 if i % 2 else 0.0) for k in range(du.HORIZON)]
             for i in range(n)]                                    # parity 交替偏置 → 行间跳变
    df = pd.DataFrame({du.TIMESTAMP_COL: ts, du.LABEL_COL: truth, "pred_M1": jumpy})
    assert du.check_window_consistency(df, du.LABEL_COL, n_checks=100) == 0.0
    assert du.check_window_consistency(df, "pred_M1", n_checks=100) > 0.0  # 闸对跳变列仍敏感
    # 但 wc_targets 不会把 pred_M1 交给闸：
    assert "pred_M1" not in ps.wc_targets({du.LABEL_COL: du.HORIZON, "pred_M1": du.HORIZON}, [])["test"]


# ---------------------------------------------------------------- 对齐偏移
def test_alignment_offset_detected():
    base = pd.date_range("2025-01-01", periods=50, freq="15min")
    shifted = base - 672 * du.FREQ                                 # feature_true 用了另一种起点口径
    a = ps.alignment(base, base, shifted, du.FREQ)
    assert a["align_offset_steps"] == 672 and a["n_common"] == 50
    a0 = ps.alignment(base, base, base, du.FREQ)
    assert a0["align_offset_steps"] == 0 and a0["n_common"] == 50


# ---------------------------------------------------------------- 统计工具
def test_spearman_and_zscore_guards():
    assert fb.spearman(np.ones(10), np.arange(10)) == 0.0          # 常量向量不产 NaN
    x = np.arange(10.0)
    assert fb.spearman(x, x) == pytest.approx(1.0)
    assert np.allclose(fb.zscores(np.zeros(5)), 0.0)               # 完美特征全零误差 → z=0
