"""history_avail_power.py 单测：南网 IN 宽表 DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt 的读取与拼接。

目录约定：{root}/{YYYY-MM-DD}/IN/{plantid}/DQYC_IN_HISTORY_AVAIL_POWER_WIDE.txt
宽表格式：空格分列、utf-8、大小写不敏感；列 = PlantID PDate Tjlx V0000 V0015 ... V2345；
         V0000 即当日 00:00 的取值；数值空列写 "null"。
"""
import os

import numpy as np
import pandas as pd
import pytest

import history_avail_power as hap

VCOLS = [f"V{h:02d}{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]


def write_wide(root, date, plant, rows, header=True, vcols=None):
    """rows = [(tjlx, {vcol: 文本值}), ...]；未给的 vcol 补 "0"。返回写出的文件路径。"""
    vcols = list(VCOLS if vcols is None else vcols)
    d = os.path.join(root, date, "IN", plant)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, hap.WIDE_FILENAME)
    lines = []
    if header:
        lines.append(" ".join(["PlantID", "PDate", "Tjlx"] + vcols))
    for tjlx, vals in rows:
        lines.append(" ".join([plant, date, str(tjlx)] + [str(vals.get(c, "0")) for c in vcols]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ============================================================ 单文件解析
def test_parse_wide_file_expands_to_96_quarter_hour_points(tmp_path):
    """一个文件 = 当日 96 个点，V0000 落在 00:00、V2345 落在 23:45。"""
    p = write_wide(str(tmp_path), "2026-08-13", "1358", [(1, {"V0000": "1.5", "V1045": "42.0", "V2345": "9.0"})])
    s = hap.parse_wide_file(p, tjlx=1)
    assert len(s) == 96
    assert s.index[0] == pd.Timestamp("2026-08-13 00:00")
    assert s.index[-1] == pd.Timestamp("2026-08-13 23:45")
    assert s[pd.Timestamp("2026-08-13 00:00")] == 1.5
    assert s[pd.Timestamp("2026-08-13 10:45")] == 42.0
    assert s[pd.Timestamp("2026-08-13 23:45")] == 9.0


def test_parse_wide_file_null_becomes_zero(tmp_path):
    """数值空列写作 null（大小写不敏感）-> 填 0，而不是 NaN。"""
    p = write_wide(str(tmp_path), "2026-08-13", "1358",
                   [(1, {"V0000": "null", "V0015": "NULL", "V0030": "3.0"})])
    s = hap.parse_wide_file(p, tjlx=1)
    assert s[pd.Timestamp("2026-08-13 00:00")] == 0.0
    assert s[pd.Timestamp("2026-08-13 00:15")] == 0.0
    assert s[pd.Timestamp("2026-08-13 00:30")] == 3.0
    assert np.isfinite(s.to_numpy()).all()


def test_parse_wide_file_missing_column_becomes_zero(tmp_path):
    """文件里根本没有 V1045 这一列 -> 该时刻仍要出现且取 0（96 点一个不少）。"""
    short = [c for c in VCOLS if c != "V1045"]
    p = write_wide(str(tmp_path), "2026-08-13", "1358", [(1, {"V1030": "7.0"})], vcols=short)
    s = hap.parse_wide_file(p, tjlx=1)
    assert len(s) == 96
    assert s[pd.Timestamp("2026-08-13 10:30")] == 7.0
    assert s[pd.Timestamp("2026-08-13 10:45")] == 0.0


def test_parse_wide_file_picks_requested_tjlx(tmp_path):
    """同一 plant+date 可能有多行统计类型：0-调度端 1-场站端 2-agc限电标志位，只取要的那行。"""
    p = write_wide(str(tmp_path), "2026-08-13", "1358",
                   [(0, {"V0000": "10.0"}), (1, {"V0000": "20.0"}), (2, {"V0000": "1"})])
    assert hap.parse_wide_file(p, tjlx=1)[pd.Timestamp("2026-08-13 00:00")] == 20.0
    assert hap.parse_wide_file(p, tjlx=0)[pd.Timestamp("2026-08-13 00:00")] == 10.0


def test_parse_wide_file_absent_tjlx_returns_none(tmp_path):
    """要的统计类型这天没有 -> 返回 None（调用方据此告警并留空洞），不是一整天的 0。"""
    p = write_wide(str(tmp_path), "2026-08-13", "1358", [(0, {"V0000": "10.0"})])
    assert hap.parse_wide_file(p, tjlx=1) is None


def test_parse_wide_file_is_case_insensitive(tmp_path):
    """文档写明所有字符对大小写不敏感：表头小写照样认。"""
    p = write_wide(str(tmp_path), "2026-08-13", "1358", [(1, {"V0000": "5.0"})])
    with open(p, encoding="utf-8") as f:
        text = f.read()
    head, rest = text.split("\n", 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(head.lower() + "\n" + rest)
    assert hap.parse_wide_file(p, tjlx=1)[pd.Timestamp("2026-08-13 00:00")] == 5.0


def test_parse_wide_file_without_header_uses_documented_order(tmp_path):
    """没有表头行时按文档列序 PlantID PDate Tjlx V0000...V2345 解析。"""
    p = write_wide(str(tmp_path), "2026-08-13", "1358",
                   [(1, {"V0000": "5.0", "V0015": "6.0"})], header=False)
    s = hap.parse_wide_file(p, tjlx=1)
    assert len(s) == 96
    assert s[pd.Timestamp("2026-08-13 00:00")] == 5.0
    assert s[pd.Timestamp("2026-08-13 00:15")] == 6.0


# ============================================================ 站名 -> 场站文件夹号
def test_station_to_plant_id_takes_trailing_digits():
    assert hap.station_to_plant_id("plant_guangfu1358") == "1358"
    assert hap.station_to_plant_id("1358") == "1358"


def test_station_to_plant_id_without_digits_falls_back_to_name():
    assert hap.station_to_plant_id("stationA") == "stationA"


# ============================================================ 多日期 / 多场站 拼接与裁剪
def test_load_raw_history_concatenates_days_and_clips_to_span(tmp_path):
    """三天文件拼一条线，再按主表历史线的 [t_start, t_end] 裁剪 —— 这就是两条线对齐的地方。"""
    for day, v in (("2026-08-11", "1.0"), ("2026-08-12", "2.0"), ("2026-08-13", "3.0")):
        write_wide(str(tmp_path), day, "1358", [(1, {c: v for c in VCOLS})])
    got = hap.load_raw_history(str(tmp_path), ["plant_guangfu1358"],
                               pd.Timestamp("2026-08-11 10:15"), pd.Timestamp("2026-08-13 10:00"), tjlx=1)
    s = got["plant_guangfu1358"]
    assert s.index[0] == pd.Timestamp("2026-08-11 10:15")     # 起点被裁到 10:15，不是当日 00:00
    assert s.index[-1] == pd.Timestamp("2026-08-13 10:00")    # 终点收在起报时刻 10:00
    assert s[pd.Timestamp("2026-08-12 00:00")] == 2.0         # 中间那天来自它自己的文件
    assert len(s) == 55 + 96 + 41


def test_load_raw_history_missing_day_leaves_a_gap(tmp_path, capsys):
    """整天文件缺失 -> 留空洞并告警，绝不拿一整天的 0 冒充（那在图上等于假装全天停机）。"""
    for day in ("2026-08-11", "2026-08-13"):
        write_wide(str(tmp_path), day, "1358", [(1, {c: "1.0" for c in VCOLS})])
    got = hap.load_raw_history(str(tmp_path), ["plant_guangfu1358"],
                               pd.Timestamp("2026-08-11 00:00"), pd.Timestamp("2026-08-13 23:45"), tjlx=1)
    s = got["plant_guangfu1358"]
    assert len(s) == 192
    assert pd.Timestamp("2026-08-12 00:00") not in s.index
    assert "2026-08-12" in capsys.readouterr().out


def test_load_raw_history_missing_station_folder_lists_what_exists(tmp_path, capsys):
    """场站文件夹找不到 -> 告警里列出该日期下实际有哪些文件夹，方便用户核对站号规则。"""
    write_wide(str(tmp_path), "2026-08-13", "9999", [(1, {"V0000": "1.0"})])
    got = hap.load_raw_history(str(tmp_path), ["plant_guangfu1358"],
                               pd.Timestamp("2026-08-13 00:00"), pd.Timestamp("2026-08-13 23:45"), tjlx=1)
    out = capsys.readouterr().out
    assert got.get("plant_guangfu1358") is None or got["plant_guangfu1358"].empty
    assert "1358" in out and "9999" in out


def test_load_raw_history_keeps_stations_separate(tmp_path):
    """多场站各读各的文件夹，互不串味。"""
    write_wide(str(tmp_path), "2026-08-13", "1358", [(1, {c: "1.0" for c in VCOLS})])
    write_wide(str(tmp_path), "2026-08-13", "1025", [(1, {c: "2.0" for c in VCOLS})])
    got = hap.load_raw_history(str(tmp_path), ["plant_guangfu1358", "plant_guangfu1025"],
                               pd.Timestamp("2026-08-13 00:00"), pd.Timestamp("2026-08-13 23:45"), tjlx=1)
    assert set(got["plant_guangfu1358"]) == {1.0}
    assert set(got["plant_guangfu1025"]) == {2.0}


def test_load_raw_history_only_reads_days_inside_the_span(tmp_path):
    """跨度外的日期文件夹存在也不读 —— 7 天窗别把整个数据盘扫一遍。"""
    for day in ("2026-08-10", "2026-08-11", "2026-08-12"):
        write_wide(str(tmp_path), day, "1358", [(1, {c: "1.0" for c in VCOLS})])
    got = hap.load_raw_history(str(tmp_path), ["plant_guangfu1358"],
                               pd.Timestamp("2026-08-11 00:00"), pd.Timestamp("2026-08-11 23:45"), tjlx=1)
    s = got["plant_guangfu1358"]
    assert s.index.min() == pd.Timestamp("2026-08-11 00:00")
    assert s.index.max() == pd.Timestamp("2026-08-11 23:45")


def test_load_raw_history_missing_root_is_a_hard_error(tmp_path):
    """--hist-root 指错了要立刻炸，而不是安静地画不出线。"""
    with pytest.raises(SystemExit):
        hap.load_raw_history(str(tmp_path / "nope"), ["plant_guangfu1358"],
                             pd.Timestamp("2026-08-13 00:00"), pd.Timestamp("2026-08-13 23:45"), tjlx=1)
