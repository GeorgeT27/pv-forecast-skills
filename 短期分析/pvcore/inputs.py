"""命令行 spec 与 info.csv 的解析，外加按模板正反解析站点列名。

load_station_info 原先在短期与超短期两个脚本里各有一份逐字相同的拷贝，现在只此一处。
"""
from __future__ import annotations

import pandas as pd

DEFAULT_FEATURE_PAIRS = [("GHI_SOLARGIS_predict", "GHI_real_future", "GHI")]


def parse_feature_pairs(spec):
    if not spec:
        return list(DEFAULT_FEATURE_PAIRS)
    out = []
    for item in spec.split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) == 2:
            parts.append(parts[0])
        if len(parts) != 3 or not all(parts[:2]):
            raise SystemExit(f"--feature-pairs item format should be pred:true[:label], got '{item}'")
        out.append(tuple(parts))
    return out


def parse_capacity(spec):
    if not spec:
        return {}
    out = {}
    for item in spec.split(","):
        k, _, v = item.partition(":")
        out[k.strip()] = float(v)
    return out


LAT_NAMES = ("LATITUDE", "LAT")            # info.csv 里纬度/经度列的常见拼法，大小写不敏感
LON_NAMES = ("LONGITUDE", "LON", "LNG", "LONG")


def load_station_info(path, station_col, stations):
    """info_csv -> {str(station): {"gccap": float|None, "city": str|None, "lat": float|None, "lon": float|None}}.
    Capacity column: GCCAPCITY or GCCAPACITY (case-insensitive). Join column: station_col when present,
    otherwise auto-detected as the info_csv column whose values (str-compared) match the most stations;
    zero matches anywhere -> SystemExit. city 与 LATITUDE/LONGITUDE 列都可选（都是大小写不敏感匹配）：
    没有经纬度只是让 --cf-kt-scale 无法开工，其余功能照跑。"""
    df = pd.read_csv(path)
    cap_col = next((c for c in df.columns if str(c).upper() in ("GCCAPCITY", "GCCAPACITY")), None)
    if cap_col is None:
        raise SystemExit(f"--info-csv has no GCCAPCITY/GCCAPACITY column; actual columns: {list(df.columns)[:30]}")
    city_col = next((c for c in df.columns if str(c).lower() == "city"), None)
    lat_col = next((c for c in df.columns if str(c).upper() in LAT_NAMES), None)
    lon_col = next((c for c in df.columns if str(c).upper() in LON_NAMES), None)
    want = {str(s) for s in stations}
    if station_col in df.columns:
        join_col = station_col
    else:
        join_col, hits = None, 0
        for c in df.columns:
            n = int(df[c].astype(str).isin(want).sum())
            if n > hits:
                join_col, hits = c, n
        if join_col is None:
            raise SystemExit(f"--info-csv: no column matches any station value (stations look like "
                             f"{sorted(want)[:3]}; columns: {list(df.columns)[:30]})")
        print(f"  [info-csv] join column auto-detected: '{join_col}' (matches {hits}/{len(want)} stations); "
              f"capacity column: '{cap_col}'")
    def _num(r, c):
        if c is None or pd.isna(r[c]):
            return None
        try:
            return float(r[c])
        except (TypeError, ValueError):     # 经纬度列里混进 '' / 'N/A' 之类：当没有，别让整表读不进来
            return None

    out = {}
    for _, r in df.iterrows():
        v = r[cap_col]
        out[str(r[join_col])] = {
            "gccap": float(v) if pd.notna(v) else None,
            "city": str(r[city_col]) if city_col is not None and pd.notna(r[city_col]) else None,
            "lat": _num(r, lat_col), "lon": _num(r, lon_col)}
    return out


def resolve_pred_col(st, pred, template):
    """站点 -> 预测表列名 template.format(station=st)；列不存在返回 None（调用方 warn + skip）。"""
    col = template.format(station=st)
    return col if col in pred.columns else None


def stations_from_columns(cols, template: str, skip=("dtime",)) -> list:
    """按模板反解列名里的站名；template 需含 {station} 占位。"""
    pre, _, suf = template.partition("{station}")
    out = []
    for c in cols:
        c = str(c)
        if c in skip:
            continue
        if c.startswith(pre) and c.endswith(suf) and len(c) > len(pre) + len(suf):
            out.append(c[len(pre):len(c) - len(suf)] if suf else c[len(pre):])
    return out
