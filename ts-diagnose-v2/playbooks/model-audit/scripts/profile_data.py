#!/usr/bin/env python3
"""Profile a real data file so the skill can ground its "why this architecture" analysis
in MEASURED facts (shapes, ranges, missingness, cardinality, periodicity) instead of
generic textbook reasoning.

Self-contained, offline, READ-ONLY. Prefers pyarrow for .parquet (reads metadata + a row
SAMPLE, so it stays cheap on huge files); falls back to pandas; numpy for .npy/.npz. If a
needed library is missing, it prints an install hint and exits non-zero — the skill then
asks the user to install it or export a small sample. It NEVER invents statistics: every
number printed was computed from the file.

Usage:
    python profile_data.py data/x_ts.parquet                # profile (samples ~50k rows)
    python profile_data.py data/x_ts.parquet --rows 200000  # bigger sample
    python profile_data.py data/x_ts.parquet --time ts --value load   # periodicity hint

Supported: .parquet, .csv/.tsv, .npy, .npz. Output is plain text with stable headers
(===== ... =====) so the skill can quote it and anchor to `data: <file>`.
"""
import argparse
import sys


def _fail(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def _need(lib, extra=""):
    _fail(
        f"'{lib}' not installed. `pip install {lib}`{extra}\n"
        "Or export a small sample (e.g. first 10k rows) to CSV and pass that instead. "
        "Do NOT guess data statistics.",
        code=2,
    )


def profile_parquet(path, rows):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return profile_with_pandas(path, rows)  # pandas may still have an engine
    pf = pq.ParquetFile(path)
    meta = pf.metadata
    print("===== file =====")
    print(f"path: {path}")
    print(f"rows (total): {meta.num_rows}")
    print(f"columns: {meta.num_columns}")
    print(f"row_groups: {meta.num_row_groups}")
    print("\n===== schema =====")
    for i in range(meta.num_columns):
        col = meta.schema.column(i)
        print(f"{col.name}: {col.physical_type} (logical: {col.logical_type})")
    # read a bounded sample for stats
    try:
        import pyarrow as pa  # noqa: F401
        batch = next(pf.iter_batches(batch_size=min(rows, meta.num_rows or rows)))
        import pandas as pd
        df = batch.to_pandas()
        _describe(df, sampled=len(df), total=meta.num_rows)
    except Exception as e:  # noqa: BLE001
        print(f"\n[stats skipped: {e} — schema above is still exact]")


def profile_with_pandas(path, rows, sep=None):
    try:
        import pandas as pd
    except ImportError:
        _need("pandas")
    if path.endswith((".csv", ".tsv")):
        df = pd.read_csv(path, nrows=rows, sep=sep or ("\t" if path.endswith(".tsv") else ","))
        total = "unknown (CSV not counted; sample only)"
    else:
        df = pd.read_parquet(path)  # needs pyarrow or fastparquet
        total = len(df)
        if rows and len(df) > rows:
            df = df.head(rows)
    print("===== file =====")
    print(f"path: {path}")
    print(f"rows (total): {total}")
    print(f"columns: {df.shape[1]}")
    _describe(df, sampled=len(df), total=total)


def profile_npy(path):
    try:
        import numpy as np
    except ImportError:
        _need("numpy")
    print("===== file =====")
    print(f"path: {path}")
    if path.endswith(".npz"):
        z = np.load(path)
        for k in z.files:
            a = z[k]
            print(f"array '{k}': shape={a.shape} dtype={a.dtype} "
                  f"min={_num(a.min())} max={_num(a.max())} mean={_num(a.mean())} "
                  f"nan={int(np.isnan(a).sum()) if a.dtype.kind=='f' else 0}")
    else:
        a = np.load(path, mmap_mode="r")
        print(f"shape={a.shape} dtype={a.dtype}")
        a = np.asarray(a[: min(len(a), 100000)]) if a.ndim else a
        if a.dtype.kind in "fiu":
            print(f"min={_num(a.min())} max={_num(a.max())} mean={_num(a.mean())} "
                  f"std={_num(a.std())} nan={int(np.isnan(a).sum()) if a.dtype.kind=='f' else 0}")


def _num(x):
    try:
        return f"{float(x):.4g}"
    except Exception:  # noqa: BLE001
        return str(x)


def _describe(df, sampled, total):
    print(f"\n===== stats (sampled {sampled} rows of {total}) =====")
    for c in df.columns:
        s = df[c]
        nulls = int(s.isna().sum())
        kind = s.dtype.kind
        base = f"{c}: dtype={s.dtype} nulls={nulls}/{len(s)} unique={s.nunique(dropna=True)}"
        if kind in "iuf":
            print(base + f" min={_num(s.min())} max={_num(s.max())} "
                        f"mean={_num(s.mean())} std={_num(s.std())}")
        elif kind == "M":  # datetime
            print(base + f" span={s.min()} → {s.max()}")
        else:
            top = s.value_counts(dropna=True).head(3).to_dict()
            print(base + f" top={top}")
    print("\n===== head (first 5 rows) =====")
    with_opt = df.head(5).to_string(max_cols=20)
    print(with_opt)


def periodicity_hint(path, time_col, value_col, rows):
    """Autocorrelation at a few lags to hint seasonality — a MEASURED periodicity signal."""
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        _need("pandas")
    df = (pd.read_parquet(path) if path.endswith(".parquet")
          else pd.read_csv(path, nrows=rows))
    if value_col not in df.columns:
        _fail(f"--value column '{value_col}' not in {list(df.columns)}")
    if time_col and time_col in df.columns:
        df = df.sort_values(time_col)
    x = pd.to_numeric(df[value_col], errors="coerce").dropna().to_numpy()
    x = x[: min(len(x), rows)]
    if len(x) < 10:
        _fail("not enough numeric points for a periodicity estimate")
    x = x - x.mean()
    print(f"\n===== periodicity of '{value_col}' (autocorrelation, {len(x)} pts) =====")
    n = len(x)
    denom = np.dot(x, x) or 1.0
    lags = [1, 2, 3, 6, 12, 24, 48, 96, 168, 336, 720]
    acf = []
    for L in lags:
        if L < n:
            r = float(np.dot(x[:-L], x[L:]) / denom)
            acf.append((L, r))
    for L, r in acf:
        bar = "#" * int(max(0, r) * 40)
        print(f"lag {L:>4}: {r:+.3f} {bar}")
    peaks = sorted((r, L) for L, r in acf)
    if peaks:
        r, L = peaks[-1]
        print(f"[strongest positive autocorrelation at lag {L} (r={r:+.3f}) — "
              f"a candidate seasonal period; verify units against the time column]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--rows", type=int, default=50000, help="max rows to sample for stats")
    ap.add_argument("--time", default=None, help="time/index column (sorts before ACF)")
    ap.add_argument("--value", default=None, help="numeric column for periodicity hint")
    args = ap.parse_args()

    p = args.path.lower()
    if p.endswith(".parquet"):
        profile_parquet(args.path, args.rows)
    elif p.endswith((".csv", ".tsv")):
        profile_with_pandas(args.path, args.rows)
    elif p.endswith((".npy", ".npz")):
        profile_npy(args.path)
    else:
        _fail(f"Unsupported extension: {args.path}. Supported: .parquet .csv .tsv .npy .npz")

    if args.value:
        periodicity_hint(args.path, args.time, args.value, args.rows)


if __name__ == "__main__":
    main()
