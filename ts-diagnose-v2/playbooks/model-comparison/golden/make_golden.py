"""model-comparison 金标准：解析式构造双模型规范长表。

植入：A 在 2024-02 崩（幅度 2.5），其余月 0.8；B 恒 1.5。
⇒ A 总体行 RMSE 均值 (0.8*8+2.5*4)/12 = 1.3667 < B 1.5（A 总体更好）；
  A 的最差片 = 2024-02，片内 B（1.5）反超 A（2.5）；
  slice_gaps 仅 2024-02 为正（+1.0）⇒ concentration_ratio = 1.0。
配对差 d=A−B：8 行 −0.7、4 行 +1.0 ⇒ mean_diff=−0.1333、win_rate=8/12、
sign_z=(8−6)/sqrt(3)=1.1547。符号交替（step 奇偶）保证行 RMSE 恰等于幅度。
"""
import csv
import os

MONTHS = {"2024-01": 0.8, "2024-02": 2.5, "2024-03": 0.8}
B_AMP = 1.5
DAYS = (5, 10, 15, 20)
STEPS = 8


def amp(model, month):
    return MONTHS[month] if model == "A" else B_AMP


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "predictions.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["window_ts", "unit_id", "model", "horizon_step",
                    "y_true", "y_pred"])
        for month in MONTHS:
            for d in DAYS:
                for model in ("A", "B"):
                    for s in range(STEPS):
                        e = amp(model, month) * (1.0 if s % 2 == 0 else -1.0)
                        w.writerow([f"{month}-{d:02d}", "U1", model, s,
                                    10.0, 10.0 + e])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
