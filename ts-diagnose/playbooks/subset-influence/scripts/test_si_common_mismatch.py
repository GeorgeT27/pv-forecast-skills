import json

import si_common


def _make_workdir(tmp_path, station):
    wd = tmp_path / "result_analysis_workdir"
    wd.mkdir()
    (wd / "analysis_config.json").write_text(
        json.dumps({"station": station}), encoding="utf-8"
    )
    return str(wd)


def test_station_mismatch_fail_closed_when_test_station_absent(tmp_path):
    """cfg 没有 test_station 字段 → 与空串比较 → 任何已链接目录都判 mismatch（fail-closed）。"""
    wd = _make_workdir(tmp_path, "somestation")
    cfg = {"result_analysis_workdir": wd}  # 故意不设 test_station
    ev = si_common.detect_result_analysis(cfg)
    assert ev["status"] == "linked"
    assert ev["station_mismatch"] is True


def test_station_mismatch_false_when_test_station_matches(tmp_path):
    """cfg 设了 test_station 且与链接目录 station 一致 → 不 mismatch。"""
    wd = _make_workdir(tmp_path, "somestation")
    cfg = {"result_analysis_workdir": wd, "test_station": "somestation"}
    ev = si_common.detect_result_analysis(cfg)
    assert ev["status"] == "linked"
    assert ev["station_mismatch"] is False
