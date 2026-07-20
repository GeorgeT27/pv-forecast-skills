"""ε 分解构件单测 + 合成小样端到端（Task 2 追加）。全部确定性零随机。"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fb_common as fb  # noqa: E402


def test_harmonic_basis_wraps_midnight():
    b0 = fb.harmonic_basis(np.array([0.0]), 24.0, 3)
    b24 = fb.harmonic_basis(np.array([24.0]), 24.0, 3)
    assert b0.shape == (1, 6)
    assert np.allclose(b0, b24, atol=1e-9)          # cyclic：午夜无边界跳变


def test_hinge_basis_shape_and_constant_guard():
    x = np.linspace(-3, 7, 100)
    b = fb.hinge_basis(x, n_knots=4)
    assert b.shape == (100, 5)                       # df = 1 + 4 knots = 5 ≤ 6
    c = fb.hinge_basis(np.full(50, 3.0), n_knots=4)
    assert c.shape[0] == 50 and np.all(c == 0.0)     # 常量列：零基不装样子


def test_huber_ridge_recovers_slope_despite_outliers():
    x = np.linspace(0, 10, 400)
    y = 2.0 * x + 1.0
    y[::20] += 80.0                                  # 5% 确定性大离群
    X = np.column_stack([np.ones_like(x), x])
    coef = fb.huber_ridge(X, y)
    assert coef is not None
    assert abs(coef[1] - 2.0) < 0.1                  # 稳健：离群不拉歪斜率
    assert fb.huber_ridge(X[:5], y[:5]) is None      # 样本不足 → None（保守不剥）


def test_temporal_split_embargo():
    ts = pd.date_range("2025-01-01", periods=40, freq="6h")   # 跨 10 天
    front, back = fb.temporal_split(ts, embargo="48h")
    assert len(front) == 20
    cutoff = ts[front].max() + pd.Timedelta("48h")
    assert all(ts[i] >= cutoff for i in back)        # 后段与前段末行至少隔 48h
    assert len(back) > 0
    dense = pd.date_range("2025-01-01", periods=40, freq="15min")  # 只跨 10h
    _, back2 = fb.temporal_split(dense, embargo="48h")
    assert len(back2) == 0                           # 数据太短 → 后段空（调用方 λ=0）


def test_lag1_reducibility():
    n = np.arange(192)
    smooth = np.sin(2 * np.pi * n / 16.0)            # period-16：ρ1=cos(2π/16)≈0.92
    E = np.tile(smooth, (10, 1))
    assert fb.lag1_reducibility(E) > 0.5
    nyq = np.sin(np.pi * n / 2.0 + 0.7)              # period-4 近奈奎斯特：ρ1≈0
    assert fb.lag1_reducibility(np.tile(nyq, (10, 1))) < 0.05
    assert fb.lag1_reducibility(np.zeros((5, 192))) == 0.0   # 常量 → 0
