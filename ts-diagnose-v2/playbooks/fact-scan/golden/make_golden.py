"""fact-scan 金标准：双模型 mini 长表。A 在 2024-02 崩（幅度 2.0，其余 1.0），
B 恒 1.5 ⇒ error-breakdown argmax=(U1,2024-02)、oracle 均值 = (1.0×4+1.5×4)/8。"""
import csv
import os

AMP = {"A": {"2024-01": 1.0, "2024-02": 2.0}, "B": {"2024-01": 1.5, "2024-02": 1.5}}


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "predictions.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["window_ts", "unit_id", "model", "horizon_step",
                    "y_true", "y_pred"])
        for month in ("2024-01", "2024-02"):
            for d in (5, 10, 15, 20):
                for model in ("A", "B"):
                    for s in range(4):
                        e = AMP[model][month] * (1.0 if s % 2 == 0 else -1.0)
                        w.writerow([f"{month}-{d:02d}", "U1", model, s,
                                    10.0, 10.0 + e])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
