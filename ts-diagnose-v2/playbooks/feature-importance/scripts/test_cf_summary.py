"""回归测试（Fix 1 / Task 8 review finding）：rebuild_modes_summary 的 CSV→summary 核心必须
按 repl_mode 去重，绝不把 full（oracle 整换真值）与 res（marginal/minimal/lattice 的
pred−ε_res）两种替换口径的 Δ 混掺进同一个 per_feature_effects 条目。用 per_feature_effects_
from_csv（counterfactual_api.py 里拆出的纯函数，零网络）直接喂合成 CSV——不需要起 Runner
（那需要 adapter.py + feature_true/test_label parquet + blame_report.csv，网络无关但重且与
本 bug 无关，收窄到最小可复现面）。"""
import os
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cf_logic as cf  # noqa: E402
import counterfactual_api as capi  # noqa: E402


def _write_csv(path, rows):
    cols = ["metric", "model", "timestamp", "feature", "mode", "subset_id", "repl_mode",
            "status", "api_row_error"]
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)


def test_full_and_res_rows_do_not_collide_in_dedup(tmp_path):
    """同一 (metric,model,ts,subset_id) 下 full 与 res 两行必须都存活去重（不是互相覆盖）。"""
    csv_path = str(tmp_path / "counterfactual_results.csv")
    ts = "2026-01-01 00:00:00"
    rows = [
        # baseline（subset_id=""）：full 口径来自 oracle 那趟，res 口径来自 marginal 那趟
        {"metric": "rmse_192", "model": "M1", "timestamp": ts, "feature": "__baseline__",
         "mode": "oracle", "subset_id": "", "repl_mode": "full", "status": "ok",
         "api_row_error": 10.0},
        {"metric": "rmse_192", "model": "M1", "timestamp": ts, "feature": "__baseline__",
         "mode": "per-feature", "subset_id": "", "repl_mode": "res", "status": "ok",
         "api_row_error": 10.0},
        # 单特征 irr 换真值（full，来自某次 all-blamed/oracle 附带跑）——刻意给一个和 res 差很大的值
        {"metric": "rmse_192", "model": "M1", "timestamp": ts, "feature": "irr",
         "mode": "oracle", "subset_id": "irr", "repl_mode": "full", "status": "ok",
         "api_row_error": 1.0},
        # 单特征 irr 换 ε_res（res，来自 per-feature 那趟）——Δ 明显不同于 full 那行
        {"metric": "rmse_192", "model": "M1", "timestamp": ts, "feature": "irr",
         "mode": "per-feature", "subset_id": "irr", "repl_mode": "res", "status": "ok",
         "api_row_error": 8.0},
    ]
    _write_csv(csv_path, rows)

    per = capi.per_feature_effects_from_csv(csv_path)

    assert per is not None
    entry = per["rmse_192"]["M1"]["irr"]
    # 修复后：res 是设计的答案口径（本例中唯一同时有 res baseline+singles 的口径）——
    # delta_mean 必须反映 8.0-10.0=-2.0（res 组），不能被 full 组的 1.0-10.0=-9.0 污染/覆盖。
    assert entry["delta_mean"] == pytest.approx(-2.0), (
        f"per_feature_effects 混掺了 full/res 两种替换口径的 Δ：got {entry}")
    assert entry["replaced_mean"] == pytest.approx(8.0)


def test_repl_mode_participates_in_drop_duplicates_no_row_lost(tmp_path):
    """底层不去掉任何一种 repl_mode 的行——用去重后仍能各自算出 per_feature_effects
    的方式间接验证（而不是直接读内部 DataFrame，保持对实现细节的松耦合）。"""
    csv_path = str(tmp_path / "counterfactual_results.csv")
    ts1, ts2 = "2026-01-01 00:00:00", "2026-01-01 01:00:00"
    rows = [
        {"metric": "rmse_192", "model": "M1", "timestamp": ts1, "feature": "__baseline__",
         "mode": "oracle", "subset_id": "", "repl_mode": "full", "status": "ok",
         "api_row_error": 10.0},
        {"metric": "rmse_192", "model": "M1", "timestamp": ts1, "feature": "irr",
         "mode": "oracle", "subset_id": "irr", "repl_mode": "full", "status": "ok",
         "api_row_error": 1.0},
        {"metric": "rmse_192", "model": "M1", "timestamp": ts2, "feature": "__baseline__",
         "mode": "per-feature", "subset_id": "", "repl_mode": "res", "status": "ok",
         "api_row_error": 12.0},
        {"metric": "rmse_192", "model": "M1", "timestamp": ts2, "feature": "irr",
         "mode": "per-feature", "subset_id": "irr", "repl_mode": "res", "status": "ok",
         "api_row_error": 9.0},
    ]
    _write_csv(csv_path, rows)

    per = capi.per_feature_effects_from_csv(csv_path)

    # 只有 res 口径存在两行（ts2 的一对），full 口径只有 ts1 一对没有配对的 res——
    # 设计选择 res 优先，ts2 的一对是唯一贡献者，n==1。
    entry = per["rmse_192"]["M1"]["irr"]
    assert entry["n"] == 1
    assert entry["delta_mean"] == pytest.approx(-3.0)      # 9.0 - 12.0


def test_full_only_csv_backcompat_unchanged(tmp_path):
    """decomp 关/旧 CSV：全是 full 行 → 行为不变（无 res 行时退回 full）。"""
    csv_path = str(tmp_path / "counterfactual_results.csv")
    ts = "2026-01-01 00:00:00"
    rows = [
        {"metric": "rmse_192", "model": "M1", "timestamp": ts, "feature": "__baseline__",
         "mode": "oracle", "subset_id": "", "repl_mode": "full", "status": "ok",
         "api_row_error": 10.0},
        {"metric": "rmse_192", "model": "M1", "timestamp": ts, "feature": "irr",
         "mode": "oracle", "subset_id": "irr", "repl_mode": "full", "status": "ok",
         "api_row_error": 4.0},
    ]
    _write_csv(csv_path, rows)

    per = capi.per_feature_effects_from_csv(csv_path)

    entry = per["rmse_192"]["M1"]["irr"]
    assert entry["delta_mean"] == pytest.approx(-6.0)


# ---------------------------------------------------------------------------
# Fix 2 regression: run_minimal must not clobber run_oracle's authoritative
# G/gate in the shared ladder[metric][model][ts] dict.
# ---------------------------------------------------------------------------

class _FakeRunner(capi.Runner):
    """Bare Runner built via __new__ (skips __init__'s adapter/parquet/IO load) — only sets
    the attributes run_oracle/run_minimal actually touch. Calls the REAL bound methods
    (not a copy), so the test tracks the source verbatim."""

    def __init__(self, rows, err_table, pool):
        self.summary = {}
        self.cfg = {"blame": {"g_min": 0.2, "tau": 0.8}}
        self.args = _Args()
        self._rows = rows
        self._err_table = err_table          # {(metric, model, ts, subset_id, repl): value}
        self._pool = pool
        self.pcols = {"irr": {}, "temp": {}}  # two synthetic feature-pair columns

    def rows_of(self, only_blamed):
        return self._rows

    def pool_of(self, metric, model, grp):
        return self._pool

    def err_of_factory(self, metric, model, ts, residual=False):
        repl = "res" if residual else "full"

        def err_of(subset):
            sid = cf.subset_id(subset) if subset else ""
            return self._err_table[(metric, model, ts, sid, repl)]
        return err_of


class _Args:
    drift_tol = 0.2
    drift_stop = 0.3


def test_run_minimal_does_not_clobber_run_oracle_G_and_gate():
    """run_oracle 写权威 base/oracle/G/gate（full-swap）；run_minimal 随后跑同一行的残差尺度
    自算缺口，必须写到 minimal_G/minimal_gate ——绝不覆盖 run_oracle 的 G/gate（回归 Fix 2 前
    的 bug：两者共享同一个 ladder[metric][model][ts] dict，run_minimal 用同名键 ent.update()
    会把 run_oracle 的权威值連 gate 原因字符串一起冲掉）。"""
    metric, model, ts = "rmse_192", "M1", "2026-01-01 00:00:00"

    class _Grp(dict):
        def __getitem__(self, key):
            if key == "row_error":
                return _Series([9.0])
            return super().__getitem__(key)

    class _Series(list):
        @property
        def iloc(self):
            return self

    rows = [(metric, model, ts, _Grp())]

    # oracle (full-swap): base=10, oracle=1 -> G=9, big gap, gate ok
    # minimal (residual):  base=10, oracle=6 -> G=4 (different scale/value on purpose,
    #                       proves the two gates are genuinely distinct numbers)
    err_table = {
        (metric, model, ts, "", "full"): 10.0,
        (metric, model, ts, "irr|temp", "full"): 1.0,
        (metric, model, ts, "", "res"): 10.0,
        (metric, model, ts, "irr|temp", "res"): 6.0,
        (metric, model, ts, "irr", "res"): 9.5,
        (metric, model, ts, "temp", "res"): 9.5,
    }
    runner = _FakeRunner(rows, err_table, pool=["irr", "temp"])

    runner.run_oracle(eps=0.01)
    ent_after_oracle = dict(runner.summary["ladder"][metric][model][ts])
    assert ent_after_oracle["G"] == pytest.approx(9.0)
    assert ent_after_oracle["gate"] == "ok"

    runner.run_minimal(eps=0.01)
    ent_after_minimal = runner.summary["ladder"][metric][model][ts]

    # run_oracle's authoritative G/gate must survive run_minimal untouched.
    assert ent_after_minimal["G"] == pytest.approx(9.0), (
        f"run_minimal clobbered run_oracle's G: {ent_after_minimal}")
    assert ent_after_minimal["gate"] == "ok", (
        f"run_minimal clobbered run_oracle's gate: {ent_after_minimal}")
    # run_minimal's own residual-scale gap/gate must land under distinct namespaced keys.
    assert ent_after_minimal["minimal_G"] == pytest.approx(4.0)
    assert ent_after_minimal["minimal_gate"] == "ok"


def test_run_minimal_gate_fail_does_not_clobber_oracle_gate_reason():
    """run_minimal 门未过（残差尺度 G 太小）时也只写 minimal_gate，不碰 run_oracle 的 gate 原因。"""
    metric, model, ts = "rmse_192", "M1", "2026-01-01 00:00:00"

    class _Grp(dict):
        def __getitem__(self, key):
            if key == "row_error":
                return _Series([9.0])
            return super().__getitem__(key)

    class _Series(list):
        @property
        def iloc(self):
            return self

    rows = [(metric, model, ts, _Grp())]
    err_table = {
        (metric, model, ts, "", "full"): 10.0,
        (metric, model, ts, "irr|temp", "full"): 1.0,      # oracle: big gap, gate ok
        (metric, model, ts, "", "res"): 10.0,
        (metric, model, ts, "irr|temp", "res"): 9.9,        # minimal: tiny residual gap, gate fails
    }
    runner = _FakeRunner(rows, err_table, pool=["irr", "temp"])
    runner.run_oracle(eps=0.01)
    oracle_gate = runner.summary["ladder"][metric][model][ts]["gate"]
    assert oracle_gate == "ok"

    runner.run_minimal(eps=0.01)
    ent = runner.summary["ladder"][metric][model][ts]
    assert ent["gate"] == "ok", f"run_oracle's gate reason got clobbered: {ent}"
    assert ent["minimal_gate"] in ("not_feature_problem", "gap_within_noise")
