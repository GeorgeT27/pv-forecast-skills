#!/usr/bin/env python3
"""反事实阶梯的**纯决策逻辑**（零网络导入——HTTP/缓存/CSV 全在 counterfactual_api.py）。

为什么拆出来：gen_gate 禁 urllib，HTTP runner 永远进不了金标准闸；把所有会出错的
决策数学（缺口闸、修复谓词、最小修复集消解、Shapley/交互指数）collect 到本模块，
用合成模型 --selfcheck 过闸 + pytest 单测——Stage 4 的逻辑从此和 Stage 0–2 一样可闸。

## 架构约束：cache-first + 确定性顺序（resume 的根基）

所有搜索算法通过一个回调 `err_of(subset: frozenset) -> float | None` 取"替换 subset
后的行误差"。调用方负责缓存（CSV 已有的 subset 不再打 API）。本模块保证：**给定相同
输入，请求 subset 的顺序完全确定**——于是 --max-calls 中途截断后重跑，前缀全部缓存
命中，搜索沿同一路径继续，不会分叉。err_of 返回 None = 调用失败/NaN（三态谓词的
invalid），算法必须把它当"未知"保守处理（保留该特征），绝不当"没修好"。

## 判定数学

- 可解释缺口 G = base − oracle（oracle = 全特征换真值）。行进入归因需过 **G 闸**：
  G/base ≥ g_min(0.2) 且 G ≥ 5ε（ε = 重复调用误差上界，runner 开跑实测）。
  不过闸 = 「非特征问题」（模型/label 的锅），防冤枉。
- 修复谓词：R(S) = (base − err_S)/G ≥ τ(0.8) + ε/G（噪声边际）。
- 最小修复集：**反向贪心消解**（从候选全集出发按嫌疑升序试删，谓词仍过则永久删，
  固定点后 1-minimal 校验）。比教科书 ddmin 在非单调（换某特征反而更差）下稳，
  且顺序确定可重放。冗余结构（两特征都换才修好）天然被保留成对。
- Shapley（k≤5 全子集）：v(S) = base − err_S，精确 φ_i + 成对交互指数 φ_ij
  （φ_ij > 0 = 协同：一起换的收益超过各自单换之和）。
"""
from __future__ import annotations

import itertools
import math

SEP = "|"


# ---------------------------------------------------------------- subset 标识
def subset_id(feats) -> str:
    feats = sorted(feats)
    for f in feats:
        if SEP in f or "+" in f:
            raise ValueError(f"特征名不得含 '{SEP}' 或 '+'（subset_id 分隔符）：{f}")
    return SEP.join(feats)


def parse_subset_id(sid: str) -> frozenset:
    return frozenset(x for x in sid.split(SEP) if x) if sid else frozenset()


def legacy_subset_id(feature: str, mode: str) -> str:
    """旧版 CSV（无 subset_id 列）派生：baseline→\"\"；per-feature→单特征；
    all-blamed→feature 列是 '+' 连接串。"""
    if feature == "__baseline__":
        return ""
    if mode == "all-blamed":
        return subset_id(feature.split("+"))
    return subset_id([feature])


# ---------------------------------------------------------------- G 闸与谓词
def gap_gate(base: float, oracle: float, eps: float, g_min: float = 0.2) -> dict:
    """行是否有"特征可解释"的缺口。不过闸 = 非特征问题，后续不得对该行归因。"""
    if not _finite(base) or not _finite(oracle):
        return {"G": None, "ok": False, "reason": "invalid_errors"}
    G = base - oracle
    if base <= 0:
        return {"G": G, "ok": False, "reason": "zero_baseline"}
    if G < 5 * eps:
        return {"G": G, "ok": False, "reason": "gap_within_noise"}
    if G / base < g_min:
        return {"G": G, "ok": False, "reason": "not_feature_problem"}
    return {"G": G, "ok": True, "reason": "ok"}


def recovery(base: float, err_s: float, G: float) -> float:
    return (base - err_s) / G


def make_predicate(base: float, G: float, tau: float, eps: float):
    """→ verdict(err_S) ∈ {\"pass\", \"fail\", \"invalid\"}。"""
    thr = tau + (eps / G if G > 0 else 0.0)

    def verdict(err_s):
        if not _finite(err_s):
            return "invalid"
        return "pass" if recovery(base, err_s, G) >= thr else "fail"
    return verdict


def _finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


# ---------------------------------------------------------------- 候选池
def candidate_pool(feature_stats: dict, clusters, z_relax: float = 1.0,
                   cap: int = 8) -> list:
    """一个坏行的消解/lattice 候选池 = 被点名 ∪ 其共线簇成员 ∪ z≥z_relax 放宽集，
    按 (被点名 > 簇成员 > 放宽集，组内 z 降序) 截 cap——簇成员与被点名者统计不可分，
    证据强于只过放宽线的特征，不许被 cap 挤出。feature_stats: {f: {"z", "blamed"}}。"""
    blamed = {f for f, s in feature_stats.items() if s.get("blamed")}
    clustered = set()
    for cl in clusters or []:
        if blamed & set(cl):
            clustered |= set(cl)
    clustered -= blamed
    relaxed = {f for f, s in feature_stats.items()
               if s.get("z") is not None and s["z"] >= z_relax} - blamed - clustered
    def key(f):
        tier = 0 if f in blamed else (1 if f in clustered else 2)
        return (tier, -(feature_stats.get(f, {}).get("z") or 0.0), f)
    return sorted(blamed | clustered | relaxed, key=key)[:cap]


# ---------------------------------------------------------------- 最小修复集
def greedy_minimal_set(candidates: list, err_of, base: float, G: float,
                       tau: float = 0.8, eps: float = 0.0) -> dict:
    """反向贪心消解 + 1-minimal 校验。candidates 按嫌疑**升序**（最不可疑先试删——
    删错代价最小）。err_of 见模块 docstring（None = invalid，保守保留）。"""
    verdict = make_predicate(base, G, tau, eps)
    full = frozenset(candidates)
    n_invalid = 0
    e_full = err_of(full)
    if verdict(e_full) == "invalid":
        return {"status": "invalid_full", "set": sorted(full), "n_invalid": 1}
    if verdict(e_full) == "fail":
        return {"status": "pool_insufficient", "set": sorted(full),
                "recovery_full": recovery(base, e_full, G), "n_invalid": 0}

    keep = set(full)
    for f in candidates:                       # 升序：最不可疑先试删
        if f not in keep:
            continue
        trial = frozenset(keep - {f})
        v = verdict(err_of(trial))
        if v == "pass":
            keep.discard(f)
        elif v == "invalid":
            n_invalid += 1                     # 未知 → 保守保留
    # 1-minimal 校验：留存的每个成员单独去掉都必须破坏谓词（cache-first 下近零成本）
    not_minimal = []
    for f in sorted(keep):
        v = verdict(err_of(frozenset(keep - {f})))
        if v == "pass":
            not_minimal.append(f)
        elif v == "invalid":
            n_invalid += 1
    for f in not_minimal:                      # 二轮兜底（贪心顺序造成的漏删）
        trial = frozenset(keep - {f})
        if verdict(err_of(trial)) == "pass":
            keep.discard(f)
    return {"status": "ok", "set": sorted(keep), "n_invalid": n_invalid,
            "recovery_full": recovery(base, e_full, G)}


# ---------------------------------------------------------------- Shapley 全格
def shapley_lattice(feats: list, err_of, base: float) -> dict:
    """k≤5 全子集精确 Shapley + 成对交互指数。v(S) = base − err(S)。
    任一子集 invalid → 整行 lattice 报废（status=invalid，不出半吊子归因）。"""
    k = len(feats)
    if k > 5:
        raise ValueError(f"lattice 只到 k≤5（2^k 调用），给了 {k} 个候选——先收窄候选池")
    v = {}
    for r in range(k + 1):
        for combo in itertools.combinations(sorted(feats), r):
            e = err_of(frozenset(combo))
            if not _finite(e):
                return {"status": "invalid", "at_subset": subset_id(combo)}
            v[frozenset(combo)] = base - e
    phi = {}
    for f in feats:
        rest = [x for x in feats if x != f]
        total = 0.0
        for r in range(len(rest) + 1):
            w = math.factorial(r) * math.factorial(k - r - 1) / math.factorial(k)
            for combo in itertools.combinations(rest, r):
                s = frozenset(combo)
                total += w * (v[s | {f}] - v[s])
        phi[f] = round(total, 6)
    inter = {}
    for a, b in itertools.combinations(sorted(feats), 2):
        rest = [x for x in feats if x not in (a, b)]
        total = 0.0
        for r in range(len(rest) + 1):
            w = math.factorial(r) * math.factorial(k - r - 2) / math.factorial(k - 1)
            for combo in itertools.combinations(rest, r):
                s = frozenset(combo)
                total += w * (v[s | {a, b}] - v[s | {a}] - v[s | {b}] + v[s])
        inter[f"{a}{SEP}{b}"] = round(total, 6)
    return {"status": "ok", "shapley": phi, "interaction": inter,
            "v_full": round(v[frozenset(feats)], 6)}


# ---------------------------------------------------------------- 行判定聚合
def classify_row(base: float, oracle: float, eps: float, g_min: float,
                 per_feature: dict, minimal: dict | None, tau: float) -> dict:
    """一个坏行的最终 verdict。per_feature: {f: err_f}（单换）。"""
    gate = gap_gate(base, oracle, eps, g_min)
    if not gate["ok"]:
        return {"verdict": "非特征问题" if gate["reason"] in ("not_feature_problem",
                                                              "gap_within_noise")
                else "无法判定", "gate": gate}
    G = gate["G"]
    verdict = make_predicate(base, G, tau, eps)
    solo = sorted((f for f, e in per_feature.items() if verdict(e) == "pass"),
                  key=lambda f: per_feature[f])
    if solo:
        return {"verdict": "单特征可修", "features": solo, "gate": gate}
    if minimal and minimal.get("status") == "ok" and len(minimal["set"]) == 1:
        return {"verdict": "单特征可修", "features": minimal["set"], "gate": gate}
    if minimal and minimal.get("status") == "ok" and len(minimal["set"]) >= 2:
        return {"verdict": "需联合修复", "features": minimal["set"], "gate": gate}
    if minimal and minimal.get("status") == "pool_insufficient":
        return {"verdict": "候选池不足（扩池重试）", "gate": gate,
                "recovery_full": minimal.get("recovery_full")}
    return {"verdict": "未定（缺消解结果）", "gate": gate}


# ---------------------------------------------------------------- 版本漂移
def version_drift(offline_err: float, base_err: float, tol: float = 0.2) -> bool:
    """离线 parquet 行误差 vs API 基线行误差相差 >tol → API 后面的模型版本可能不同。"""
    if not _finite(offline_err) or not _finite(base_err):
        return True
    denom = max(abs(offline_err), 1e-9)
    return abs(base_err - offline_err) / denom > tol


# ---------------------------------------------------------------- selfcheck
def _synthetic(weights: dict, redundant=(), synergy=(), residual: float = 0.0):
    """合成行误差模型：err(S) = Σ_{f∉S} w_f + max 冗余项 + 协同项 + 残差。
    redundant=(f1,f2,c)：两个都没换就 +c（换掉任意一个不减半——都换才消）。
    synergy=(f1,f2,c)：两个都没换才 +c（换掉任一即消）。"""
    def err_of(S: frozenset) -> float:
        e = residual + sum(w for f, w in weights.items() if f not in S)
        if redundant:
            f1, f2, c = redundant
            e += c * max(f1 not in S, f2 not in S)
        if synergy:
            f1, f2, c = synergy
            e += c * ((f1 not in S) and (f2 not in S))
        return e
    return err_of


def selfcheck() -> dict:
    checks = {}
    # 1) 线性可加：贪心找到唯一大头
    err = _synthetic({"a": 10.0, "b": 0.5, "c": 0.5, "d": 0.0})
    base, oracle = err(frozenset()), err(frozenset("abcd"))
    G = gap_gate(base, oracle, eps=0.01)["G"]
    r = greedy_minimal_set(["d", "c", "b", "a"], err, base, G)
    checks["linear_minimal"] = (r["status"] == "ok" and r["set"] == ["a"])
    # 2) 冗余对：单换零改善、贪心保留成对（用户场景「两个坏特征都换才修好」）
    err = _synthetic({}, redundant=("f1", "f2", 10.0))
    base, oracle = err(frozenset()), err(frozenset(["f1", "f2", "x"]))
    G = base - oracle
    checks["redundant_solo_useless"] = (err(frozenset(["f1"])) == base)
    r = greedy_minimal_set(["x", "f1", "f2"], err, base, G)
    checks["redundant_pair_found"] = (r["status"] == "ok" and r["set"] == ["f1", "f2"])
    # 3) 冗余对 Shapley 均分 + 诱饵零分
    s = shapley_lattice(["f1", "f2", "x"], err, base)
    checks["shapley_equal_split"] = (s["status"] == "ok"
                                     and abs(s["shapley"]["f1"] - s["shapley"]["f2"]) < 1e-9
                                     and abs(s["shapley"]["x"]) < 1e-9)
    checks["interaction_flags_pair"] = s["interaction"][f"f1{SEP}f2"] > 1e-9  # 冗余=修复互补
    # 4) 协同对：换任一即修，最小集是单元素
    err = _synthetic({}, synergy=("g1", "g2", 8.0))
    base = err(frozenset())
    r = greedy_minimal_set(["g1", "g2"], err, base, base - err(frozenset(["g1", "g2"])))
    checks["synergy_single_suffices"] = (r["status"] == "ok" and len(r["set"]) == 1)
    # 5) G 闸拦非特征问题
    err = _synthetic({"a": 0.5}, residual=10.0)
    checks["gap_gate_blocks"] = (gap_gate(err(frozenset()), err(frozenset(["a"])),
                                          eps=0.01)["reason"] == "not_feature_problem")
    # 6) invalid 保守保留
    inner = _synthetic({"a": 10.0, "b": 3.0})
    def flaky(S):
        return None if S == frozenset(["a"]) else inner(S)   # 试删 b 时的子集调用失败
    base, oracle = inner(frozenset()), inner(frozenset(["a", "b"]))
    r = greedy_minimal_set(["b", "a"], flaky, base, base - oracle)
    checks["invalid_keeps_feature"] = ("b" in r["set"] and r["n_invalid"] >= 1)
    return {"passed": all(checks.values()), "checks": checks}


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--out", default="cf_logic_selfcheck.json")
    a, _ = ap.parse_known_args()
    if a.selfcheck:
        res = selfcheck()
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"[cf_logic --selfcheck] passed={res['passed']}  "
              + "  ".join(f"{k}={'✓' if v else '✗'}" for k, v in res["checks"].items()))
        raise SystemExit(0 if res["passed"] else 1)
    print("cf_logic 是纯逻辑库：--selfcheck 跑内置合成模型断言；算法由 counterfactual_api.py 调用。")
