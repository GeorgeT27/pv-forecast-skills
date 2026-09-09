"""口径开关与 freq 解析（全链路联调 F6/F7）。

F7：证据线三图过去写死逐行 RMSE，分析主口径是逐行 MSE 时，升级规则的输入与主口径脱钩。
F6：--freq 默认 15min 且不读 setup_manifest，10min 数据的日内聚合会整体错位且不报错。
"""
import json
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import chart_common as cc
import chart_cross_dim_stability as cds
import chart_model_rank_significance as mrs
import chart_worst_slice_compare as wsc
from synth import make_long

WINDOWS = [f"2024-01-{d:02d}" for d in range(1, 9)]


def _df_rank_flips():
    """A 每行误差恒定 2.0；B 一半行 0.5、一半行 3.0。
    逐行 RMSE 均值：A=2.0 < B=1.75 为假——B 更小；逐行 MSE 均值：A=4.0 < B=4.625。
    即两个口径下的排名相反。"""
    def err(m, u, w, s):
        if m == "A":
            return cc_alt(2.0, s)
        return cc_alt(0.5 if WINDOWS.index(w) < 4 else 3.0, s)
    return make_long(["A", "B"], ["u1"], WINDOWS, 4, err)


def cc_alt(amp, s):
    return amp * (1.0 if s % 2 == 0 else -1.0)


def test_row_metric_rmse_and_mse_differ():
    d = _df_rank_flips()
    d["err"] = d["y_pred"] - d["y_true"]
    rr = cc.row_metric(d, "rmse").groupby("model")["rmse"].mean()
    mm = cc.row_metric(d, "mse").groupby("model")["rmse"].mean()
    assert rr["A"] > rr["B"]      # 逐行 RMSE：B 更好
    assert mm["A"] < mm["B"]      # 逐行 MSE：A 更好 → 排名反转
    assert cc.row_metric(d, "rmse").equals(cc.row_rmse(d))


def test_row_metric_rejects_unknown():
    d = _df_rank_flips()
    d["err"] = d["y_pred"] - d["y_true"]
    with pytest.raises(ValueError):
        cc.row_metric(d, "mae")


def _write(tmp_path, df, manifest_freq=None):
    p = tmp_path / "predictions.csv"
    df.to_csv(p, index=False)
    if manifest_freq:
        (tmp_path / "setup_manifest.json").write_text(
            json.dumps({"freq": manifest_freq}), encoding="utf-8")
    return p


def test_cross_dim_cli_metric_switch(tmp_path):
    pred = _write(tmp_path, _df_rank_flips())
    out = tmp_path / "charts"
    cds.main(["--pred", str(pred), "--out-dir", str(out), "--focal-model", "A",
              "--metric", "mse"])
    stats = json.loads((out / "cross-dim-stability.json").read_text(encoding="utf-8"))
    assert stats["metric"] == "mse"
    # 口径切成 mse 后，A 相对 B 的行均值差为负（A 更好），与 rmse 口径反号
    cds.main(["--pred", str(pred), "--out-dir", str(out), "--focal-model", "A"])
    rmse_stats = json.loads((out / "cross-dim-stability.json").read_text(encoding="utf-8"))
    assert rmse_stats["metric"] == "rmse"
    assert (stats["pairs"]["B"]["caliber_switch"]["row_diff"]
            * rmse_stats["pairs"]["B"]["caliber_switch"]["row_diff"]) < 0


def test_worst_slice_and_rank_record_metric(tmp_path):
    pred = _write(tmp_path, _df_rank_flips())
    out = tmp_path / "charts"
    wsc.main(["--pred", str(pred), "--out-dir", str(out), "--focal-model", "A",
              "--n-perm", "0", "--metric", "mse"])
    assert json.loads((out / "worst-slice-compare.json").read_text(encoding="utf-8"))["metric"] == "mse"
    mrs.main(["--pred", str(pred), "--out-dir", str(out), "--metric", "mse"])
    rank = json.loads((out / "model-rank-significance.json").read_text(encoding="utf-8"))
    assert rank["metric"] == "mse" and "逐行 mse" in rank["note"]


def test_resolve_freq_priority(tmp_path):
    pred = _write(tmp_path, _df_rank_flips(), manifest_freq="10min")
    assert cc.resolve_freq(pred) == "10min"                 # 读 manifest
    assert cc.resolve_freq(pred, "5min") == "5min"          # CLI 优先
    bare = tmp_path / "bare"
    bare.mkdir()
    p2 = _write(bare, _df_rank_flips())
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert cc.resolve_freq(p2) == "15min"               # 回落并告警
        assert len(w) == 1


def test_intraday_profile_uses_manifest_freq(tmp_path):
    import chart_intraday_profile as ip
    pred = _write(tmp_path, _df_rank_flips(), manifest_freq="10min")
    out = tmp_path / "charts"
    ip.main(["--pred", str(pred), "--out-dir", str(out)])
    assert json.loads((out / "intraday-profile.json").read_text(encoding="utf-8"))["freq"] == "10min"


# ---------------------------------------------------------------- 口径守卫（F7 全覆盖）
def _chart_scripts():
    d = Path(__file__).resolve().parents[1] / "scripts"
    return sorted(p for p in d.glob("chart_*.py") if p.name != "chart_common.py")


@pytest.mark.parametrize("path", _chart_scripts(), ids=lambda p: p.name)
def test_every_row_level_chart_exposes_metric_flag(path):
    """凡是按逐行指标聚合的图，都必须能跟着主口径切 --metric 并把口径写进 JSON。
    新图漏了这条 = 又一次「图用另一个口径答题且不报错」（F7 的原始故障）。"""
    src = path.read_text(encoding="utf-8")
    if "row_metric" not in src and "row_rmse" not in src:
        pytest.skip("非逐行指标图")
    assert '"--metric"' in src, f"{path.name} 用逐行指标却没有 --metric，口径被写死"
    assert "row_rmse(" not in src, f"{path.name} 仍直接调 row_rmse，应改 row_metric(df, metric)"
    assert '"metric"' in src, f"{path.name} 没把口径写进 JSON，判读端看不出用的哪个口径"


def test_metric_flag_coverage_not_shrunk():
    """下限断言：能切口径的逐行图只许增不许减。"""
    n = sum(1 for p in _chart_scripts()
            if '"--metric"' in p.read_text(encoding="utf-8"))
    assert n >= 11, f"能切口径的图只剩 {n} 张——有人删了 --metric？"


# ---------------------------------- R2-4：文案跟着 --metric 走，不许写死 RMSE
# 回归点：11 张图接了 --metric 之后，JSON 的 metric 字段说 mse、note 与轴标签却仍写
# RMSE。数字对、决策也对（剧本读 JSON 数字），但人看图会读成另一个口径。
def _metric_capable_scripts():
    import re
    root = Path(__file__).resolve().parents[1] / "scripts"
    out = []
    for p in sorted(root.glob("chart_*.py")):
        src = p.read_text(encoding="utf-8")
        if re.search(r'add_argument\(\s*"--metric"', src):
            out.append((p.name, src))
    return out


def test_metric_capable_charts_exist():
    assert len(_metric_capable_scripts()) >= 11


@pytest.mark.parametrize("name,src", _metric_capable_scripts(),
                         ids=[n for n, _ in _metric_capable_scripts()])
def test_rendered_labels_go_through_metric_label(name, src):
    """能切口径的图，凡是会画到 PNG 上或写进 note 的口径名，都必须来自 cc.metric_label()。

    不管三类：①`--metric` 自己的 help 文本（那是在解释这个开关，写死才对）；
    ②模块 docstring（静态文本，插不进运行时口径，只要求别把默认说成唯一）；
    ③列名/键名（rr["rmse"]、"rmse_by_step"、rmse_actual——固定契约，口径以 metric 字段为准）。"""
    import re
    bad = []
    for i, line in enumerate(src.split("\n"), 1):
        if not re.search(r"\b(RMSE|MSE)\b", line):
            continue
        if "metric_label" in line or "help=" in line:
            continue
        if re.search(r"set_ylabel\(|set_xlabel\(|set_title\(|\.bar\(|label\s*=|"
                     r'"note"|note\s*(\+)?=', line):
            bad.append(f"{i}: {line.strip()[:100]}")
    assert not bad, (f"{name}: 这些会被人读到的文案把口径名写死了，"
                     "应改成 cc.metric_label(...)：\n  " + "\n  ".join(bad))


def test_module_docstrings_do_not_claim_rmse_is_the_only_caliber():
    """docstring 插不进运行时口径，但也不许把默认口径说成唯一口径。"""
    import re
    offenders = []
    for name, src in _metric_capable_scripts():
        doc = src.split('"""')[1] if src.count('"""') >= 2 else ""
        if re.search(r"\b(RMSE|MSE)\b", doc) and "--metric" not in doc and "默认" not in doc:
            offenders.append(name)
    assert not offenders, ("这些图的 docstring 提了具体口径却没说它只是默认值："
                           f"{offenders}——补一句「口径由 --metric 定，默认 RMSE」")
