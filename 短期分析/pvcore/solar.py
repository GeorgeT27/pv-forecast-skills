"""晴空辐照 GHI_cs 与晴空指数 K_t —— 给 K_t 乘性反事实提供「这一时刻这一地点天最亮能亮到多少」。

GHI_cs 只由 纬度/经度/时刻 决定，跟任何实测或预报辐照无关：太阳几何 + 一个大气衰减经验式。
用 Haurwitz(1945)：GHI_cs = 1098 · cosθz · exp(−0.059 / cosθz)，θz 为天顶角。
选它是因为只需要 cosθz，不吃气溶胶/水汽/气压这些本地观测 —— 站点侧只有经纬度时它是唯一诚实的选择。
太阳位置用 Spencer(1971) 的赤纬与时差近似（全年误差 < 0.5°，对 15min 网格绰绰有余）。

K_t = GHI / GHI_cs 是「这一刻实际有多少晴空的量」：≈1 晴、0.3 阴、>1 是云增强（云边缘反射叠加直射）。
夜间 GHI_cs = 0，K_t 无定义 —— 所有函数在那里返回 0 / NaN 而不是让它变 inf。

时区：times 是「墙上时间」，tz_offset 是它相对 UTC 的小时数（北京时间 = 8）。传错会让整条晴空曲线
平移 tz_offset 小时，check_alignment 就是用来当场看出这件事的。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HAURWITZ_A = 1098.0        # W/m^2
HAURWITZ_B = 0.059
KT_MAX_DEFAULT = 1.2       # 云增强的经验上限：晴空的 1.2 倍，再高就不是地表辐照该有的样子
CHINA_LON = (73.0, 135.5)  # 坐标体检用的国境粗框
CHINA_LAT = (3.5, 53.6)


def _spencer(times: pd.DatetimeIndex):
    """Spencer(1971): -> (赤纬 rad, 时差 min)。day angle 用 dayofyear，不区分闰年（差值 < 0.2°）。"""
    B = 2.0 * np.pi * (times.dayofyear.to_numpy(float) - 1.0) / 365.0
    decl = (0.006918 - 0.399912 * np.cos(B) + 0.070257 * np.sin(B)
            - 0.006758 * np.cos(2 * B) + 0.000907 * np.sin(2 * B)
            - 0.002697 * np.cos(3 * B) + 0.001480 * np.sin(3 * B))
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(B) - 0.032077 * np.sin(B)
                    - 0.014615 * np.cos(2 * B) - 0.040849 * np.sin(2 * B))
    return decl, eot


def cos_zenith(times, lat, lon, tz_offset: float = 8.0) -> np.ndarray:
    """cos(天顶角)，太阳在地平线下时为负。真太阳时 = 墙上时间 + 4·(经度 − 15·tz_offset) 分钟 + 时差。
    那个 4 分钟/度就是地球每转 1° 花的时间：北京时间基准经线 120°E，站点每偏西 1° 正午就晚 4 分钟。"""
    times = pd.DatetimeIndex(times)
    decl, eot = _spencer(times)
    phi = np.deg2rad(float(lat))
    clock_h = times.hour.to_numpy(float) + times.minute.to_numpy(float) / 60.0 \
        + times.second.to_numpy(float) / 3600.0
    solar_h = clock_h + (4.0 * (float(lon) - 15.0 * tz_offset) + eot) / 60.0
    omega = np.deg2rad(15.0 * (solar_h - 12.0))
    return np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(omega)


def clear_sky_ghi(times, lat, lon, tz_offset: float = 8.0) -> np.ndarray:
    """晴空水平面总辐照 W/m^2（Haurwitz）。太阳在地平线下 -> 0（不是 NaN：0 才是夜间的物理真值）。"""
    cz = cos_zenith(times, lat, lon, tz_offset)
    out = np.zeros(len(cz), dtype=float)
    day = cz > 0
    out[day] = HAURWITZ_A * cz[day] * np.exp(-HAURWITZ_B / cz[day])
    return out


def clearness_index(ghi, ghi_cs) -> np.ndarray:
    """K_t = GHI / GHI_cs；GHI_cs<=0（夜间）处返回 NaN —— 那里 K_t 无定义，用 0 冒充会把夜间
    算成「全阴」，分箱统计立刻被一半的点污染。"""
    ghi = np.asarray(ghi, dtype=float)
    cs = np.asarray(ghi_cs, dtype=float)
    out = np.full(cs.shape, np.nan)
    day = cs > 0
    out[day] = ghi[day] / cs[day]
    return out


def scale_in_kt(ghi, ghi_cs, k: float, kt_max: float = KT_MAX_DEFAULT):
    """K_t 空间里的乘性缩放，返回 (新 GHI, 被天花板拦下的点数, 白天点数)。

        GHI' = clip(K_t · k, 0, kt_max) · GHI_cs        （白天，GHI_cs > 0）
             = max(GHI · k, 0)                          （夜间，天花板无定义就不设）

    白天那条等价于 clip(GHI·k, 0, kt_max·GHI_cs) —— 也就是「先按 k 缩放，再拦在当时晴空的
    kt_max 倍」。天花板是护栏：平时不响，只在 k 把某点顶出物理边界（也顶出模型见过的分布）时拦一下。
    夜间不设上限是刻意的：那里 GHI_cs=0，一设就等于把夜间预报强行归零 —— 那是偷偷做了一次
    夜间 oracle，会污染这个实验只想测「乘性缩放」的干净因果。"""
    ghi = np.asarray(ghi, dtype=float)
    cs = np.asarray(ghi_cs, dtype=float)
    scaled = np.maximum(ghi * float(k), 0.0)
    day = cs > 0
    ceiling = kt_max * cs
    clipped = day & (scaled > ceiling)
    out = np.where(clipped, ceiling, scaled)
    return out, int(clipped.sum()), int(day.sum())


# ---------------------------------------------------------------- 体检
def solar_noon_hour(day, lon, tz_offset: float = 8.0) -> float:
    """该日真太阳正午对应的墙上时钟小时（108.3°E 北京时间下约 12.8 = 12:48）。"""
    _, eot = _spencer(pd.DatetimeIndex([pd.Timestamp(day).normalize()]))
    return 12.0 - (4.0 * (float(lon) - 15.0 * tz_offset) + float(eot[0])) / 60.0


def check_coords(lat, lon, station="", verbose=True) -> bool:
    """坐标可用性体检。落在国境粗框外就告警 —— info.csv 里经纬度串行/错列是真发生过的事，
    而错了的坐标不会报错，只会安静地把晴空曲线算到别的地方去。"""
    if lat is None or lon is None or not (np.isfinite(lat) and np.isfinite(lon)):
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        if verbose:
            print(f"  [warn] station {station}: coordinates out of range (lat={lat}, lon={lon}) -> skipped")
        return False
    if not (CHINA_LON[0] <= lon <= CHINA_LON[1] and CHINA_LAT[0] <= lat <= CHINA_LAT[1]) and verbose:
        print(f"  [warn] station {station}: (lat={lat:g}, lon={lon:g}) falls outside China "
              f"(lon {CHINA_LON[0]}-{CHINA_LON[1]}, lat {CHINA_LAT[0]}-{CHINA_LAT[1]}) -- "
              f"check --info-csv for shifted/mismatched coordinate columns; GHI_cs will be computed anyway")
    return True


def check_alignment(times, ghi, lat, lon, tz_offset: float = 8.0, station="", verbose=True):
    """把实测/预报 GHI 的日峰值时刻和模型算出的真太阳正午比一比 -> (中位偏差小时, 天数)。

    时区假设错 8 小时、经纬度串了行，都会在这里表现成几小时量级的偏差；对了则通常在 ±1h 内
    （日内云况会把峰值推开一点，但不会推几个小时）。无法判定时返回 (None, 0)。"""
    s = pd.Series(np.asarray(ghi, dtype=float), index=pd.DatetimeIndex(times)).dropna()
    s = s[s > 0]
    if s.empty:
        return None, 0
    offs = []
    for day, g in s.groupby(s.index.normalize()):
        if g.max() <= 0 or len(g) < 4:
            continue
        peak = g.idxmax()
        peak_h = peak.hour + peak.minute / 60.0
        offs.append(peak_h - solar_noon_hour(day, lon, tz_offset))
    if not offs:
        return None, 0
    med = float(np.median(offs))
    if verbose:
        noon = solar_noon_hour(s.index[0], lon, tz_offset)
        verdict = ("looks right" if abs(med) <= 1.5 else
                   "SUSPECT -- check --cf-kt-tz-offset and the info-csv lat/lon columns")
        print(f"  [kt] {station or 'geometry'} check: observed GHI peaks at solar noon "
              f"{med:+.2f} h (median over {len(offs)} day(s)); modelled solar noon "
              f"{int(noon):02d}:{int(round((noon % 1) * 60)):02d} at lon {lon:g}, tz UTC+{tz_offset:g} -> {verdict}")
    return med, len(offs)
