"""现场写图的样板（chartbook 未覆盖某个疑问时，拷这份改，别从零写）。

用法：cp <ENGINE>/chartbook/adhoc-template.py analysis_scripts/<名字>.py，改
RECIPE_ID / compute / verify / render 四处，然后：
    python3 analysis_scripts/<名字>.py --pred <setup>/predictions.csv \
        --out-dir charts/ --engine <ENGINE> --verify
`--verify` 必跑：对账两关不过不许用数字。JSON 顶层的 verification.tier 决定这张图的
数字能不能进结论（三档见 engine-core「现场写的图按三档验证」），build_index 按它归组。
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

RECIPE_ID = "my-adhoc-chart"          # 改成本图的名字（连字符），产物按它命名
VERIFICATION_TIER = "reconcile-2"     # reconcile-2 / chartbook-fn / exploratory


def _load_cc(engine_dir):
    """引 chartbook 公共设施：中文字体、长表加载、口径函数、双落盘。
    现场脚本别自己写这些——字体没设中文标题会缺字，口径自己写会与主口径脱钩。"""
    sys.path.insert(0, os.path.join(engine_dir, "chartbook", "scripts"))
    import chart_common as cc
    return cc


def compute(df, cc, metric="rmse"):
    """算本图的统计量。df 是 cc.load_predictions() 的长表，已带 err 列。
    口径一律走 cc.metric_fn / cc.row_metric，别自己写平方根。"""
    fn = cc.metric_fn(metric)
    per_model = df.groupby("model")["err"].apply(fn)
    return {"recipe": RECIPE_ID, "metric": metric,
            "per_model": {m: round(float(v), 6) for m, v in per_model.items()},
            "n_rows": int(len(df)),
            "note": f"口径={cc.metric_label(metric)}；<一句话说清这张图怎么读>。"}


def verify(df, stats):
    """对账两关（reconcile-2 档位的证据）。→ (ok, 报告行)。
    关 1 行数守恒：聚合前后的行数对得上；关 2 抽 3 个单位逐值手算复核。
    关 2 的手算**故意不调 cc 的口径函数**——用同一份代码复核同一份代码，等于没查。
    口径按 stats["metric"] 自己分支写，这样 compute 用错聚合函数时这里会 FAIL。"""
    lines, ok = [], True
    n = int(len(df))
    c1 = stats["n_rows"] == n
    ok &= c1
    lines.append(f"[关1 行数守恒] 表内 {stats['n_rows']} == 长表 {n} → "
                 f"{'ok' if c1 else 'FAIL'}")
    for m in sorted(df["model"].unique())[:3]:
        e = df[df["model"] == m]["err"].to_numpy()
        ms = float(np.mean(np.square(e)))
        manual = ms if stats["metric"] == "mse" else float(np.sqrt(ms))
        got = stats["per_model"][m]
        agree = abs(manual - got) < 1e-6
        ok &= agree
        lines.append(f"[关2 逐值] {m}: 手算 {manual:.8f} vs 表内 {got:.8f} → "
                     f"{'ok' if agree else 'FAIL'}")
    return ok, lines


def render(stats, cc):
    import matplotlib.pyplot as plt
    cc.setup_font()                    # 不调这句中文标题会缺字
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ms = list(stats["per_model"])
    ax.bar(ms, [stats["per_model"][m] for m in ms])
    ax.set_ylabel(cc.metric_label(stats["metric"]))
    ax.set_title(f"{RECIPE_ID} [chartbook 未覆盖·现场脚本]")
    fig.tight_layout()
    return fig


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--engine", required=True, help="<ENGINE>：ts-diagnose 包目录")
    ap.add_argument("--metric", choices=("rmse", "mse"), default="rmse",
                    help="须与分析主口径同源")
    ap.add_argument("--verify", action="store_true", help="跑对账两关")
    a = ap.parse_args(argv)
    cc = _load_cc(a.engine)
    df = cc.load_predictions(a.pred)
    stats = compute(df, cc, a.metric)
    if a.verify:
        ok, lines = verify(df, stats)
        print("\n".join(lines))
        stats["verification"] = {"tier": VERIFICATION_TIER, "passed": bool(ok),
                                 "checks": lines}
        if not ok:
            raise SystemExit("对账两关未通过——数字不许用")
    else:
        print("⚠ 未跑 --verify：这张图的数字不许进 FINDINGS 与 CONCLUSION")
    os.makedirs(a.out_dir, exist_ok=True)
    cc.save_outputs(render(stats, cc), a.out_dir, RECIPE_ID, stats)
    print(f"✓ {RECIPE_ID} 落盘（验证档位 {VERIFICATION_TIER}）")


if __name__ == "__main__":
    main()
