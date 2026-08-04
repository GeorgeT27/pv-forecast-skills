"""Stage 1 参考实现：总差距事实。CLI 契约即菜谱契约（gen_gate 钉死）。"""
import argparse
import json
import math

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--pair", required=True)      # 如 A,B
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    df = pd.read_csv(a.pred)
    df["err"] = df["y_pred"] - df["y_true"]
    rr = (df.groupby(["model", "unit_id", "window_ts"])["err"]
          .apply(lambda e: float(np.sqrt(np.mean(np.square(e)))))
          .rename("rmse").reset_index())
    per_model = rr.groupby("model")["rmse"].mean()
    focal, other = a.pair.split(",")
    piv = rr.pivot_table(index=["unit_id", "window_ts"], columns="model",
                         values="rmse").dropna()
    d = (piv[focal] - piv[other]).to_numpy()
    n = len(d)
    wins = int((d < 0).sum())
    z = (wins - n / 2) / math.sqrt(n / 4)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    json.dump({
        "caliber": "rmse_192",
        "per_model": {m: round(float(v), 4) for m, v in per_model.items()},
        "ranking": list(per_model.sort_values().index),
        "pair": [focal, other], "n": n,
        "mean_diff": round(float(d.mean()), 4),
        "win_rate": round(wins / n, 4),
        "sign_z": round(float(z), 4), "sign_p": round(float(p), 4),
        "note": "|z|<2 → 差距未过噪声线，只写现象不写方向",
    }, open(a.out, "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
