"""cf_logic 单测——合成模型直接喂纯函数，无网络。selfcheck 覆盖判定数学的主干，
这里补：确定性重放（resume 根基）、候选池、旧 CSV 兼容、版本漂移、行 verdict 聚合。"""
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cf_logic as cf  # noqa: E402


def recorder(err_of):
    calls = []

    def wrapped(S):
        calls.append(cf.subset_id(S))
        return err_of(S)
    return wrapped, calls


def test_selfcheck_all_pass():
    res = cf.selfcheck()
    assert res["passed"], res["checks"]


def test_subset_id_roundtrip_and_separator_guard():
    assert cf.subset_id(["b", "a"]) == "a|b"
    assert cf.parse_subset_id("a|b") == frozenset({"a", "b"})
    assert cf.parse_subset_id("") == frozenset()
    with pytest.raises(ValueError):
        cf.subset_id(["bad|name"])
    with pytest.raises(ValueError):
        cf.subset_id(["bad+name"])                       # '+' 已被 v1 all-blamed 占用


def test_legacy_subset_id_derivation():
    assert cf.legacy_subset_id("__baseline__", "per-feature") == ""
    assert cf.legacy_subset_id("ghi", "per-feature") == "ghi"
    assert cf.legacy_subset_id("b+a", "all-blamed") == "a|b"


def test_gap_gate_reasons():
    assert cf.gap_gate(10.0, 1.0, eps=0.01)["ok"]
    assert cf.gap_gate(10.0, 9.5, eps=0.01)["reason"] == "not_feature_problem"
    assert cf.gap_gate(10.0, 9.99, eps=0.01)["reason"] == "gap_within_noise"
    assert cf.gap_gate(0.0, 0.0, eps=0.01)["reason"] == "zero_baseline"
    assert cf.gap_gate(float("nan"), 1.0, eps=0.01)["reason"] == "invalid_errors"
    assert cf.gap_gate(10.0, None, eps=0.01)["reason"] == "invalid_errors"


def test_predicate_three_states_and_noise_margin():
    v = cf.make_predicate(base=10.0, G=10.0, tau=0.8, eps=1.0)   # 阈 = 0.8 + 0.1
    assert v(0.5) == "pass"                                       # R=0.95
    assert v(1.5) == "fail"                                       # R=0.85 < 0.9
    assert v(None) == "invalid" and v(float("nan")) == "invalid"


def test_greedy_deterministic_replay():
    """同输入两次运行请求完全相同的 subset 序列——max-calls 截断 + 缓存重放的根基。"""
    err = cf._synthetic({"a": 6.0, "b": 3.0, "c": 1.0}, redundant=("d", "e", 5.0))
    base, oracle = err(frozenset()), err(frozenset("abcde"))
    seqs = []
    for _ in range(2):
        wrapped, calls = recorder(err)
        r = cf.greedy_minimal_set(["c", "b", "a", "d", "e"], wrapped, base, base - oracle)
        seqs.append(calls)
        assert r["status"] == "ok"
    assert seqs[0] == seqs[1]


def test_greedy_pool_insufficient():
    err = cf._synthetic({"a": 2.0, "hidden": 8.0})
    base = err(frozenset())
    r = cf.greedy_minimal_set(["a"], err, base, G=10.0)          # hidden 不在池里
    assert r["status"] == "pool_insufficient"
    assert r["recovery_full"] < 0.8


def test_shapley_rejects_k_gt_5():
    with pytest.raises(ValueError):
        cf.shapley_lattice(list("abcdef"), lambda S: 0.0, 1.0)


def test_shapley_invalid_subset_voids_row():
    err = cf._synthetic({"a": 1.0, "b": 1.0})
    def flaky(S):
        return None if S == frozenset(["a"]) else err(S)
    out = cf.shapley_lattice(["a", "b"], flaky, err(frozenset()))
    assert out["status"] == "invalid" and out["at_subset"] == "a"


def test_shapley_linear_matches_weights():
    w = {"a": 4.0, "b": 1.0}
    err = cf._synthetic(w)
    out = cf.shapley_lattice(["a", "b"], err, err(frozenset()))
    assert out["shapley"]["a"] == pytest.approx(4.0)
    assert out["shapley"]["b"] == pytest.approx(1.0)
    assert out["interaction"]["a|b"] == pytest.approx(0.0)        # 可加 = 零交互


def test_candidate_pool_blamed_cluster_relax_cap():
    stats = {f"f{i}": {"z": float(9 - i), "blamed": i == 0} for i in range(10)}
    pool = cf.candidate_pool(stats, clusters=[["f0", "f9"]], z_relax=1.0, cap=8)
    assert pool[0] == "f0"                                        # 被点名优先
    assert "f9" in pool                                           # 共线簇成员拉入（z=0 也进）
    assert len(pool) == 8                                         # cap 生效
    assert "f8" not in pool                                       # z=1 挤不进（被点名+簇+高 z 占满）


def test_version_drift():
    assert not cf.version_drift(10.0, 11.0)                       # 10% 以内
    assert cf.version_drift(10.0, 13.0)                           # 30% 漂移
    assert cf.version_drift(None, 10.0)                           # 缺值 = 不可信


def test_classify_row_verdicts():
    # 单特征可修
    out = cf.classify_row(base=10.0, oracle=0.5, eps=0.01, g_min=0.2,
                          per_feature={"a": 0.6, "b": 9.8}, minimal=None, tau=0.8)
    assert out["verdict"] == "单特征可修" and out["features"] == ["a"]
    # 需联合修复（单换都不行，消解给出对子）
    out = cf.classify_row(10.0, 0.5, 0.01, 0.2, {"a": 10.0, "b": 10.0},
                          {"status": "ok", "set": ["a", "b"]}, 0.8)
    assert out["verdict"] == "需联合修复" and out["features"] == ["a", "b"]
    # 非特征问题（oracle 修不动）
    out = cf.classify_row(10.0, 9.5, 0.01, 0.2, {}, None, 0.8)
    assert out["verdict"] == "非特征问题"
    # 候选池不足
    out = cf.classify_row(10.0, 0.5, 0.01, 0.2, {"a": 9.0},
                          {"status": "pool_insufficient", "set": ["a"],
                           "recovery_full": 0.4}, 0.8)
    assert "候选池不足" in out["verdict"]


def test_greedy_calls_bounded():
    """k 个候选的消解 ≤ 1 + k + 2|S| 次**不同** subset 请求（cache-first 下即 API 调用数）。"""
    k = 8
    err = cf._synthetic({f"f{i}": float(i) for i in range(k)})
    base, oracle = err(frozenset()), err(frozenset(f"f{i}" for i in range(k)))
    seen = set()
    def counting(S):
        seen.add(cf.subset_id(S))
        return err(S)
    r = cf.greedy_minimal_set([f"f{i}" for i in range(k)], counting, base, base - oracle)
    assert r["status"] == "ok"
    assert len(seen) <= 1 + k + 2 * max(1, len(r["set"]))
