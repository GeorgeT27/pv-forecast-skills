#!/usr/bin/env python3
"""Stage 4（门控·可选）：反事实确认——预算阶梯版。决策数学全在 cf_logic.py（已过金标准闸），
本文件只做 IO / HTTP / 缓存 / 断点续跑。这是把归因从「假设」升「已证实」的唯一通道。

## 阶梯（--mode，各层可单独调起、共享缓存，跨层去重不重打）

  oracle        每坏行 2 调（基线 + 全特征换真值）→ 可解释缺口 G 闸：G 不显著 =「非特征
                问题」（模型/label 的锅），防冤枉。**用全部坏行**（不限被点名的——零点名
                坏行恰是非特征问题候选）。
  per-feature   v1 语义：被点名特征逐个换真值，边际充分性 Δ_f。
  all-blamed    v1 语义：被点名特征一次全换。
  minimal-set   oracle 可修但单换修不动的行：候选池（点名∪共线簇∪z≥1，cap 8）反向贪心
                消解 → 最小修复集（冗余结构「两个都换才修好」在这里现形）。
  lattice       每口径×模型最差 --lattice-rows 行（候选 ≤5）：全子集精确 Shapley + 交互。
  neighbor-swap 翻新致不稳反事实：把行 r+1 的特征未来段换成行 r 的同 valid-time 预报
                （r+1 的 0..190 ← r 的 1..191，第 191 点保留原值），churn 消失 = 已证实。
                **须 config.api.neighbor_swap_confirmed=true**——拼接序列行间不连续，
                服务端若做输入连续性校验会 4xx，先 --dry-run 给用户看 payload。

## 安全与稳健

  - 首跑必须 --dry-run：打印按层调用计划表 + 首个 payload，用户确认才许打真实 API。
  - 确定性探针：开跑对首行基线重复 2 调实测 ε（重复调用误差上界），进 G 闸与修复谓词。
  - 版本漂移闸：API 基线 vs 离线 parquet 行误差漂移 >20% 的行标 version_mismatch，
    占比 > --drift-stop(0.3) 硬停（API 后面的模型版本可能不对，先核再归因）。
  - NaN 防御：替换序列非有限 → skipped_nan 不发（裸 json.dumps 会产非标 NaN token，
    FastAPI 422）；考核点真值 NaN 的行计划期剔除。
  - resume：CSV 按 (口径,模型,行,subset_id) 去重（subset_id="|"排序特征串，""=基线），
    跨 mode 复用；旧版 CSV（无 subset_id 列）自动派生兼容，不迁移文件。

用法（在工作目录下；前置见 run_orient.py Stage 4）：
  python3 <SKILL>/scripts/counterfactual_api.py --dry-run [--mode ...]
  python3 <SKILL>/scripts/counterfactual_api.py --mode oracle|per-feature|all-blamed|
      minimal-set|lattice|neighbor-swap [--metric ...] [--model ...] [--rows ts1,ts2|all-bad]
      [--max-calls 400] [--lattice-rows 3] [--pairs-top 5] [--monthly]

产物：counterfactual_results.csv（每调用一行）+ neighbor_swap_results.csv（swap 模式）
      + counterfactual_summary.json（modes/ladder/version_drift/neighbor_swap 分节合并更新）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fb_common as fb  # noqa: E402
import cf_logic as cf  # noqa: E402


class Budget(Exception):
    pass


def load_adapter():
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        import adapter  # type: ignore  用户在工作目录放的 adapter.py
    except ImportError as e:
        raise SystemExit("未找到工作目录下的 adapter.py —— 复制 scripts/api_adapter_template.py "
                         "到工作目录改名 adapter.py，填入你 FastAPI 的 payload/响应契约。") from e
    return adapter


def post_json(endpoint: str, payload: dict, timeout: float) -> dict:
    import urllib.request                     # Stage 4 天生要网络，不过 gen_gate（决策逻辑在 cf_logic 过闸）
    req = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    # 预测服务通常在内网/本机——绕开系统代理（否则 http_proxy 环境变量会 502 劫持）
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def row_error_of(pred: np.ndarray, truth: np.ndarray, metric: str) -> float:
    d = fb.require_du()
    if metric == "ultra_short":
        return float(abs(pred[d.ULTRA_SHORT_IDX] - truth[d.ULTRA_SHORT_IDX]))
    sl = fb.metric_slices()[metric]           # rmse_192 / short：切片 RMSE，与 fb.row_errors 同口径
    diff = pred[sl] - truth[sl]
    return float(np.sqrt(np.nanmean(diff ** 2)))


CSV_COLS = ["metric", "model", "timestamp", "feature", "mode", "subset_id", "repl_mode",
            "status", "api_row_error"]


class Runner:
    def __init__(self, args, cfg):
        self.args, self.cfg = args, cfg
        self.d = fb.require_du()
        self.adapter = load_adapter()
        self.calls = 0
        rep = pd.read_csv(args.blame_report, parse_dates=["timestamp_win"])
        if args.metric:
            rep = rep[rep["metric"].isin(args.metric.split(","))]
        if args.model:
            rep = rep[rep["model"].isin(args.model.split(","))]
        if args.rows not in ("from-blame-topk", "all-bad"):
            rep = rep[rep["timestamp_win"].isin(pd.to_datetime(args.rows.split(",")))]
        self.rep = rep
        ft, _ = fb.load_any(cfg["feature_true"])
        test_df, _ = fb.load_any(cfg["test_label"])
        self.pcols = {p["feature"]: p
                      for p in (fb.read_json("feature_pairs.json") or {}).get("pairs") or []}
        self.ft = ft
        self.ft_idx = {t: i for i, t in enumerate(pd.DatetimeIndex(ft[self.d.TIMESTAMP_COL]))}
        self.y_idx = {t: i for i, t in enumerate(pd.DatetimeIndex(test_df[self.d.TIMESTAMP_COL]))}
        self.Y = self.d.to_matrix(test_df, self.d.LABEL_COL)
        self.blame_sum = fb.read_json("blame_summary.json") or {}
        self.cache = self._load_cache(args.out)
        self.summary = fb.read_json(args.summary) or {}
        self._csv_header = not os.path.exists(args.out)
        # residual 模式：Stage 1.5 分解产物在 → 边际/minimal/lattice 层用 pred−ε_res（label+ε_sys）
        # 替换（留系统偏差、只去波动，避开 ε_sys 方向 OOD），Δ 才可信。oracle 的 G 闸仍整换真值。
        dec = fb.read_json("feature_decomp.json")
        self.eps_res, self.residual_on = {}, False
        if dec and (cfg.get("decompose", {}).get("enabled", True)) \
                and int(dec.get("n_rows", -1)) == len(self.ft):
            try:
                self.eps_res = {f: np.load(f"eps_res_{fb.sanitize(f)}.npy")
                                for f in self.pcols}
                self.residual_on = True
            except OSError:
                self.eps_res = {}
        self.summary["counterfactual_mode"] = "residual" if self.residual_on else "full"

    # ---------------------------------------------------------- 缓存与落盘
    @staticmethod
    def _load_cache(path):
        cache = {}
        if not os.path.exists(path):
            return cache
        prev = pd.read_csv(path, parse_dates=["timestamp"])
        if "subset_id" not in prev.columns:                       # 旧版 CSV：一次性迁移 schema
            prev["subset_id"] = [cf.legacy_subset_id(str(f), str(m))
                                 for f, m in zip(prev["feature"], prev["mode"])]
            prev["status"] = "ok"
            prev.to_csv(path + ".v1bak", index=False)             # 原样备份
            prev.reindex(columns=CSV_COLS).to_csv(path, index=False)
            print(f"  ℹ 旧版 CSV 已迁移到新 schema（原文件备份为 {path}.v1bak）")
        if "status" not in prev.columns:
            prev["status"] = "ok"
        prev["subset_id"] = prev["subset_id"].fillna("")
        if "repl_mode" not in prev.columns:                       # 旧 CSV 全是整换真值 → "full"
            prev["repl_mode"] = "full"
        prev["repl_mode"] = prev["repl_mode"].fillna("full")
        for r in prev.itertuples():
            if r.status == "ok" and np.isfinite(r.api_row_error):
                cache[(r.metric, r.model, pd.Timestamp(r.timestamp),
                       str(r.subset_id), str(r.repl_mode))] = float(r.api_row_error)
        return cache

    def _record(self, metric, model, ts, sid, status, err, repl_mode="full"):
        row = {"metric": metric, "model": model, "timestamp": ts,
               "feature": sid or "__baseline__", "mode": self.args.mode,
               "subset_id": sid, "repl_mode": repl_mode, "status": status,
               "api_row_error": round(err, 6) if err is not None and np.isfinite(err) else ""}
        pd.DataFrame([row])[CSV_COLS].to_csv(self.args.out, mode="a",
                                             header=self._csv_header, index=False)
        self._csv_header = False

    # ---------------------------------------------------------- 一次真实调用
    def _predict(self, ts, replaced: dict, model: str | None = None) -> np.ndarray:
        if self.calls >= self.args.max_calls:
            raise Budget()
        rd = self._row_dict(ts)
        rd["model"] = model                                       # 多模型 API 用；单模型可忽略
        for f, arr in replaced.items():
            if not np.all(np.isfinite(arr)):
                raise ValueError("nan_in_replacement")
        payload = self.adapter.build_payload(rd, replaced)
        self.calls += 1
        pred = np.asarray(self.adapter.parse_response(
            post_json(self.args.endpoint, payload, self.args.timeout)), float)
        return pred

    def _row_dict(self, ts):
        i = self.ft_idx[ts]
        feats = {f: {"pred": np.asarray(self.ft.iloc[i][p["pred_col"]], float),
                     "label": np.asarray(self.ft.iloc[i][p["label_col"]], float)}
                 for f, p in self.pcols.items()}
        return {"timestamp": str(ts), "features": feats}

    def err_of_factory(self, metric, model, ts, residual: bool = False):
        """cf_logic 的 err_of 回调：cache-first，未命中才打 API，落 CSV。None=invalid。
        residual=True 且分解产物在 → 替换向量用 pred−ε_res（label+ε_sys，只去波动、留系统偏差），
        否则整换真值（label）。repl_mode 进 cache key 与 CSV：同 subset 的 res/full 是两个键，
        不会串用（full 缓存值绝不冒充 residual 结果，反之亦然）。"""
        use_res = bool(residual and self.residual_on)
        repl = "res" if use_res else "full"

        def err_of(subset: frozenset):
            sid = cf.subset_id(subset)
            key = (metric, model, ts, sid, repl)
            if key in self.cache:
                return self.cache[key]
            rd = self._row_dict(ts)
            if use_res:
                i = self.ft_idx[ts]
                replaced = {f: cf.residual_replacement(rd["features"][f]["pred"],
                                                       self.eps_res[f][i]) for f in subset}
            else:
                replaced = {f: rd["features"][f]["label"] for f in subset}
            try:
                pred = self._predict(ts, replaced, model)
                err = row_error_of(pred, self.Y[self.y_idx[ts]], metric)
            except Budget:
                raise
            except ValueError:
                self._record(metric, model, ts, sid, "skipped_nan", None, repl)
                return None
            except Exception as e:                                # 网络/服务错 → invalid
                self._record(metric, model, ts, sid, f"failed:{type(e).__name__}", None, repl)
                return None
            if not np.isfinite(err):
                self._record(metric, model, ts, sid, "nan_error", None, repl)
                return None
            self._record(metric, model, ts, sid, "ok", err, repl)
            self.cache[key] = err
            return err
        return err_of

    # ---------------------------------------------------------- 行集与元数据
    def rows_of(self, only_blamed: bool):
        rep = self.rep if not only_blamed else self.rep[self.rep["blamed_topk"]]
        out = []
        for (metric, model, ts), grp in rep.groupby(["metric", "model", "timestamp_win"]):
            if ts not in self.ft_idx or ts not in self.y_idx:
                continue
            truth = self.Y[self.y_idx[ts]]
            sl = fb.metric_slices()[metric]
            ok = (np.isfinite(truth[self.d.ULTRA_SHORT_IDX]) if metric == "ultra_short"
                  else np.isfinite(truth[sl]).any())
            if not ok:
                continue                                          # 考核点真值 NaN → 剔除
            out.append((metric, model, ts, grp))
        return out

    def pool_of(self, metric, model, grp):
        stats = {r.feature: {"z": float(r.feature_err_z), "blamed": bool(r.blamed_topk)}
                 for r in grp.itertuples()}
        clusters = ((self.blame_sum.get(metric) or {}).get(model) or {}) \
            .get("collinearity_clusters") or []
        blame_cfg = self.cfg.get("blame") or {}
        return cf.candidate_pool(stats, clusters,
                                 z_relax=blame_cfg.get("z_relax", 1.0),
                                 cap=blame_cfg.get("pool_cap", 8))

    def probe_eps(self):
        """确定性探针：首行基线重复 2 调。已有 eps 且非 --reprobe 则复用。"""
        if self.summary.get("eps") is not None and not self.args.reprobe:
            return float(self.summary["eps"])
        rows = self.rows_of(only_blamed=False)
        if not rows:
            raise SystemExit("blame_report 里没有可用坏行（或全被过滤/真值 NaN）。")
        metric, model, ts, _ = rows[0]
        e = [row_error_of(self._predict(ts, {}, model), self.Y[self.y_idx[ts]], metric)
             for _ in range(2)]
        eps = abs(e[0] - e[1])
        self.summary["eps"] = round(eps, 8)
        if eps > 0:
            print(f"  ⚠ API 非确定（ε={eps:.4g}）——谓词已带噪声边际；ε 大时建议重复取均值")
        return eps

    # ---------------------------------------------------------- 各层
    def run_oracle(self, eps):
        lad = self.summary.setdefault("ladder", {})
        drift_bad = drift_n = 0
        cfg_b = self.cfg.get("blame") or {}
        for metric, model, ts, grp in self.rows_of(only_blamed=False):
            err_of = self.err_of_factory(metric, model, ts, residual=False)  # G 闸整换真值（spec §7）
            base = err_of(frozenset())
            oracle = err_of(frozenset(self.pcols))
            offline = float(grp["row_error"].iloc[0])
            drift_n += 1
            drift_bad += cf.version_drift(offline, base, self.args.drift_tol)
            gate = cf.gap_gate(base, oracle, eps, cfg_b.get("g_min", 0.2))
            ent = lad.setdefault(metric, {}).setdefault(model, {}).setdefault(str(ts), {})
            ent.update({"base": _r(base), "oracle": _r(oracle), "offline": _r(offline),
                        "G": _r(gate["G"]), "gate": gate["reason"],
                        "version_mismatch": bool(cf.version_drift(offline, base,
                                                                  self.args.drift_tol))})
            if "verdict" not in ent and not gate["ok"]:
                ent["verdict"] = "非特征问题" if gate["reason"] in (
                    "not_feature_problem", "gap_within_noise") else "无法判定"
        share = drift_bad / drift_n if drift_n else 0.0
        self.summary["version_drift"] = {"share": round(share, 4), "n": drift_n,
                                         "tol": self.args.drift_tol}
        if share > self.args.drift_stop:
            fb.dump_json(self.args.summary, self.summary)
            raise SystemExit(f"版本漂移行占比 {share:.0%} > {self.args.drift_stop:.0%} —— "
                             "API 后面的模型可能不是产出 predict.parquet 的版本，先核对再归因。")

    def run_marginal(self, all_blamed: bool):
        """per-feature / all-blamed（v1 语义，经 subset 机制跨层去重）。"""
        for metric, model, ts, grp in self.rows_of(only_blamed=True):
            err_of = self.err_of_factory(metric, model, ts, residual=True)
            err_of(frozenset())
            feats = sorted(grp.loc[grp["blamed_topk"], "feature"])
            if all_blamed:
                err_of(frozenset(feats))
            else:
                for f in feats:
                    err_of(frozenset([f]))

    def run_minimal(self, eps):
        cfg_b = self.cfg.get("blame") or {}
        tau, g_min = cfg_b.get("tau", 0.8), cfg_b.get("g_min", 0.2)
        lad = self.summary.setdefault("ladder", {})
        freq = {}
        for metric, model, ts, grp in self.rows_of(only_blamed=False):
            # residual 模式：base/oracle/子集全在 pred−ε_res 尺度，recovery=(base−err_S)/G 同尺一致；
            # 权威的整换真值 G 闸由 oracle 模式那一趟落盘（spec §7）。
            err_of = self.err_of_factory(metric, model, ts, residual=True)
            base, oracle = err_of(frozenset()), err_of(frozenset(self.pcols))
            gate = cf.gap_gate(base, oracle, eps, g_min)
            ent = lad.setdefault(metric, {}).setdefault(model, {}).setdefault(str(ts), {})
            if not gate["ok"]:
                ent["verdict"] = ("非特征问题" if gate["reason"] in
                                  ("not_feature_problem", "gap_within_noise") else "无法判定")
                ent["gate"] = gate["reason"]
                continue
            pool = self.pool_of(metric, model, grp)
            per_feat = {f: err_of(frozenset([f])) for f in pool}
            minimal = cf.greedy_minimal_set(pool[::-1], err_of, base, gate["G"], tau, eps)
            if minimal["status"] == "pool_insufficient" and set(pool) != set(self.pcols):
                rest = [f for f in sorted(self.pcols) if f not in pool]
                minimal = cf.greedy_minimal_set(rest + pool[::-1], err_of, base,
                                                gate["G"], tau, eps)
                minimal["pool_expanded"] = True
            out = cf.classify_row(base, oracle, eps, g_min, per_feat, minimal, tau)
            ent.update({"verdict": out["verdict"], "features": out.get("features"),
                        "G": _r(gate["G"]), "gate": "ok",
                        "minimal_status": minimal.get("status"),
                        "n_invalid": minimal.get("n_invalid", 0)})
            for f in out.get("features") or []:
                freq[f] = freq.get(f, 0) + 1
        ms = self.summary.setdefault("minimal_sets", {})
        for f, n in freq.items():
            ms[f] = max(ms.get(f, 0), n)

    def run_lattice(self, eps):
        cfg_b = self.cfg.get("blame") or {}
        lad = self.summary.setdefault("ladder", {})
        rows = self.rows_of(only_blamed=False)
        by_mm = {}
        for metric, model, ts, grp in rows:
            by_mm.setdefault((metric, model), []).append(
                (float(grp["row_error"].iloc[0]), ts, grp))
        for (metric, model), lst in by_mm.items():
            for _, ts, grp in sorted(lst, key=lambda x: -x[0])[: self.args.lattice_rows]:
                err_of = self.err_of_factory(metric, model, ts, residual=True)
                base, oracle = err_of(frozenset()), err_of(frozenset(self.pcols))
                gate = cf.gap_gate(base, oracle, eps, cfg_b.get("g_min", 0.2))
                if not gate["ok"]:
                    continue
                cands = self.pool_of(metric, model, grp)[:5]
                res = cf.shapley_lattice(cands, err_of, base)
                ent = lad.setdefault(metric, {}).setdefault(model, {}).setdefault(str(ts), {})
                ent["lattice"] = res

    def run_neighbor_swap(self):
        api = self.cfg.get("api") or {}
        if not self.args.dry_run and api.get("neighbor_swap_confirmed") is not True:
            raise SystemExit("neighbor-swap 需要 config.api.neighbor_swap_confirmed=true ——"
                             "拼接序列行间不连续，服务端可能拒收；先 --dry-run 给用户确认 payload。")
        rev = fb.read_json("revision_summary.json") or {}
        pred_df, _ = fb.load_any(self.cfg["predict"])
        d = self.d
        pidx = pd.DatetimeIndex(pred_df[d.TIMESTAMP_COL])
        done = set()
        out_path = "neighbor_swap_results.csv"
        if os.path.exists(out_path):
            prev = pd.read_csv(out_path, parse_dates=["ts_r"])
            done = {(r.model, pd.Timestamp(r.ts_r), r.feature) for r in prev.itertuples()}
        rows_out = []
        models = self.args.model.split(",") if self.args.model else \
            [m for m in pred_df.columns
             if m != d.TIMESTAMP_COL and fb.list_columns(pred_df).get(m) == d.HORIZON]
        for model in models:
            named = sorted({f for met in (rev.get("metrics") or {}).values()
                            for f in ((met.get(model) or {}).get("named") or [])})
            if self.args.features:
                named = self.args.features.split(",")
            if not named:
                continue
            P = d.to_matrix(pred_df, model)
            churn = []
            for i in range(len(pidx) - 1):
                if pidx[i + 1] - pidx[i] != d.FREQ:
                    continue
                if pidx[i] not in self.ft_idx or pidx[i + 1] not in self.ft_idx:
                    continue
                j = np.arange(17)                                # ultra_short 前导段选高 churn 对
                c = float(np.sqrt(np.nanmean((P[i + 1, j] - P[i, j + 1]) ** 2)))
                churn.append((c, pidx[i], pidx[i + 1]))
            for c_off, tr, tr1 in sorted(churn, key=lambda x: -x[0])[: self.args.pairs_top]:
                base_r = self._predict(tr, {}, model)
                base_r1 = self._predict(tr1, {}, model)
                for feat in ["__baseline__"] + named:
                    if (model, tr, feat) in done:
                        continue
                    if feat == "__baseline__":
                        pred_swap = base_r1
                    else:
                        arr_r = np.asarray(self.ft.iloc[self.ft_idx[tr]]
                                           [self.pcols[feat]["pred_col"]], float)
                        arr_r1 = np.asarray(self.ft.iloc[self.ft_idx[tr1]]
                                            [self.pcols[feat]["pred_col"]], float).copy()
                        arr_r1[:191] = arr_r[1:]                 # r+1 的 0..190 ← r 的 1..191
                        pred_swap = self._predict(tr1, {feat: arr_r1}, model)
                    for metric, sl in fb.metric_slices().items():
                        j = np.arange(192)[sl]
                        j = j[j <= 190]
                        churn_api = float(np.sqrt(np.nanmean(
                            (pred_swap[j] - base_r[j + 1]) ** 2)))
                        err1 = row_error_of(pred_swap, self.Y[self.y_idx[tr1]], metric) \
                            if tr1 in self.y_idx else None
                        rows_out.append({"model": model, "ts_r": tr, "ts_r1": tr1,
                                         "feature": feat, "metric": metric,
                                         "churn_offline_us": round(c_off, 6),
                                         "churn_api": round(churn_api, 6),
                                         "row_error_r1": _r(err1)})
        if rows_out:
            hdr = not os.path.exists(out_path)
            pd.DataFrame(rows_out).to_csv(out_path, mode="a", header=hdr, index=False)
        # 汇总：per model×feature churn 消减占比（对比 __baseline__）
        if os.path.exists(out_path):
            allr = pd.read_csv(out_path, parse_dates=["ts_r"])
            base = allr[allr["feature"] == "__baseline__"] \
                .set_index(["model", "ts_r", "metric"])["churn_api"]
            ns = {}
            for (model, feat, metric), grp in allr[allr["feature"] != "__baseline__"] \
                    .groupby(["model", "feature", "metric"]):
                b = base.reindex([(model, t, metric) for t in grp["ts_r"]]).to_numpy()
                red = 1.0 - grp["churn_api"].to_numpy() / np.where(b > 0, b, np.nan)
                ns.setdefault(model, {}).setdefault(feat, {})[metric] = {
                    "n_pairs": int(np.isfinite(red).sum()),
                    "churn_reduction_mean": _r(float(np.nanmean(red))),
                    "reduced_share": _r(float(np.nanmean(red > 0.5)))}
            self.summary["neighbor_swap"] = ns

    # ---------------------------------------------------------- 汇总（真值替换类）
    def rebuild_modes_summary(self):
        if not os.path.exists(self.args.out):
            return
        allr = pd.read_csv(self.args.out, parse_dates=["timestamp"])
        if "subset_id" not in allr.columns:
            return
        allr["subset_id"] = allr["subset_id"].fillna("")
        ok = allr[allr["status"] == "ok"].drop_duplicates(
            subset=["metric", "model", "timestamp", "subset_id"], keep="last")
        base = ok[ok["subset_id"] == ""].set_index(["metric", "model", "timestamp"])
        singles = ok[(ok["subset_id"] != "") & ~ok["subset_id"].str.contains(r"\|")]
        per = {}
        for (metric, model, feat), grp in singles.groupby(["metric", "model", "subset_id"]):
            b = base.reindex([(metric, model, t) for t in grp["timestamp"]])["api_row_error"] \
                .to_numpy()
            r = grp["api_row_error"].to_numpy(float)
            fin = np.isfinite(b) & np.isfinite(r)
            if not fin.any():
                continue
            delta = r[fin] - b[fin]
            per.setdefault(metric, {}).setdefault(model, {})[feat] = {
                "n": int(fin.sum()), "baseline_mean": _r(float(np.mean(b[fin]))),
                "replaced_mean": _r(float(np.mean(r[fin]))),
                "delta_mean": _r(float(np.mean(delta))),
                "improved_share": round(float((delta < 0).mean()), 4)}
        self.summary.setdefault("modes", {})["per_feature_effects"] = per


def _r(x):
    return round(float(x), 6) if x is not None and np.isfinite(x) else None


def plan_table(runner, args):
    """--dry-run 的按层调用计划表（估计值，cache 命中会更少）。"""
    rows_all = runner.rows_of(only_blamed=False)
    rows_bl = runner.rows_of(only_blamed=True)
    k = int(np.mean([grp["blamed_topk"].sum() for *_, grp in rows_bl])) if rows_bl else 0
    p = min(8, len(runner.pcols))
    mm = len({(m, mo) for m, mo, *_ in rows_all})
    est = {"oracle": 2 * len(rows_all) + 2,
           "per-feature": len(rows_bl) * (1 + k),
           "all-blamed": len(rows_bl) * 2,
           "minimal-set": len(rows_all) * (2 + p + 4),
           "lattice": mm * args.lattice_rows * (2 ** min(5, p)),
           "neighbor-swap": mm and args.pairs_top * (2 + max(1, 1))}
    repl = runner.summary.get("counterfactual_mode", "full")
    print(f"  替换口径 = {repl}"
          + ("（边际/minimal/lattice 用 pred−ε_res=label+ε_sys；oracle G 闸整换真值）"
             if repl == "residual" else "（分解产物缺/关，全整换真值）"))
    print(f"  调用计划（坏行全集 {len(rows_all)}，被点名行 {len(rows_bl)}，特征对 {len(runner.pcols)}，"
          f"缓存命中 {len(runner.cache)} 条已扣除不了——估上限）:")
    for m, n in est.items():
        mark = "←" if m == args.mode else " "
        print(f"   {mark} {m:13s} ≈ {n:5d} 调   (--max-calls {args.max_calls}/次运行)")


def main():
    cfg = fb.config_or_empty()
    api = cfg.get("api") or {}
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="oracle",
                    choices=("oracle", "per-feature", "all-blamed", "minimal-set",
                             "lattice", "neighbor-swap"))
    ap.add_argument("--metric", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--rows", default="all-bad")
    ap.add_argument("--features", default=None, help="neighbor-swap 指定特征（缺省用 revision 点名）")
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--lattice-rows", type=int, default=3)
    ap.add_argument("--pairs-top", type=int, default=5)
    ap.add_argument("--drift-tol", type=float, default=0.2)
    ap.add_argument("--drift-stop", type=float, default=0.3)
    ap.add_argument("--endpoint", default=api.get("endpoint"))
    ap.add_argument("--timeout", type=float, default=api.get("timeout_s", 30))
    ap.add_argument("--blame-report", default="blame_report.csv")
    ap.add_argument("--out", default="counterfactual_results.csv")
    ap.add_argument("--summary", default="counterfactual_summary.json")
    ap.add_argument("--monthly", action="store_true")
    ap.add_argument("--reprobe", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    runner = Runner(args, cfg)
    if args.dry_run:
        plan_table(runner, args)
        rows = runner.rows_of(only_blamed=False)
        if rows:
            metric, model, ts, grp = rows[0]
            rd = runner._row_dict(ts)
            rd["model"] = model
            feats = sorted(grp.loc[grp["blamed_topk"], "feature"]) or list(runner.pcols)[:1]
            payload = runner.adapter.build_payload(
                rd, {f: rd["features"][f]["label"] for f in feats[:1]})
            txt = json.dumps(payload, ensure_ascii=False, default=str)
            print(f"  首个 payload（{metric}×{model}×{ts} 替换 {feats[:1]}，截断 800 字）:")
            print(f"  {txt[:800]}")
        print("  ↑ 把计划表和 payload 给用户确认无误，再去掉 --dry-run 打真实 API。")
        return

    if not args.endpoint or "待补" in str(args.endpoint):
        raise SystemExit("config.api.endpoint 未填——先跟用户确认 FastAPI 地址与契约。")
    if hasattr(runner.adapter, "healthcheck") and not runner.adapter.healthcheck():
        raise SystemExit("adapter.healthcheck() 未通过——服务不可用。")

    stopped = ""
    try:
        if args.mode == "neighbor-swap":
            runner.run_neighbor_swap()
        else:
            eps = runner.probe_eps()
            if args.mode == "oracle":
                runner.run_oracle(eps)
            elif args.mode == "per-feature":
                runner.run_marginal(all_blamed=False)
            elif args.mode == "all-blamed":
                runner.run_marginal(all_blamed=True)
            elif args.mode == "minimal-set":
                runner.run_minimal(eps)
            elif args.mode == "lattice":
                runner.run_lattice(eps)
    except Budget:
        stopped = f"（--max-calls {args.max_calls} 用尽，中断点已落盘：重跑同命令续跑）"

    runner.rebuild_modes_summary()
    if args.monthly and hasattr(runner.adapter, "monthly_metric"):
        runner.summary["monthly"] = runner.adapter.monthly_metric([])
    fb.dump_json(args.summary, runner.summary)

    lad = runner.summary.get("ladder") or {}
    verdicts = [ent.get("verdict") for by_mo in lad.values() for by_ts in by_mo.values()
                for ent in by_ts.values() if ent.get("verdict")]
    print(f"[counterfactual] mode={args.mode}  替换口径={runner.summary.get('counterfactual_mode', 'full')}"
          f"  本次 API 调用 {runner.calls} {stopped}")
    if verdicts:
        from collections import Counter
        print("  行判定: " + "  ".join(f"{k}×{v}" for k, v in Counter(verdicts).items()))
    if runner.summary.get("minimal_sets"):
        print(f"  最小修复集频次: {runner.summary['minimal_sets']}")
    if runner.summary.get("version_drift"):
        vd = runner.summary["version_drift"]
        print(f"  版本漂移: {vd['share']:.0%} (n={vd['n']}, tol={vd['tol']})")
    if runner.summary.get("neighbor_swap"):
        for model, by_f in runner.summary["neighbor_swap"].items():
            for f, by_m in by_f.items():
                us = by_m.get("ultra_short") or {}
                print(f"  swap {model}×{f}: churn 消减 {us.get('churn_reduction_mean')}"
                      f" (消减>50% 对占比 {us.get('reduced_share')})")
    print(f"  产物: {args.out} + {args.summary}   升「已证实」判据见 references/blame-discipline.md")


if __name__ == "__main__":
    main()
