"""解释环收口：算未解释的 real 切片、对账 verdict_summary、追加写 harvest.json。

回归点（fullchain-weather r1）：4 条假设 → 1 confirmed、2 undecided、1 skipped，
14 个 real 切片没被任何干预推动，主 agent 直奔 Stage 4 写结论，没人问「还剩什么没解释」。
"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(SCRIPTS_DIR, "harvest_check.py")
sys.path.insert(0, SCRIPTS_DIR)
import harvest_check as hc  # noqa: E402


def zc(**slices):
    return {"slices": {k: {"verdict": v[0], "z": v[1], "mean_diff": v[2]}
                       for k, v in slices.items()}}


REAL3 = zc(**{"channel:a": ("real", 8.0, 0.02), "month:2020-10": ("real", 9.0, 0.04),
              "horizon:far": ("real", 11.0, -0.05), "channel:b": ("~noise", 0.4, 0.001)})


def vs(interventions, unexplained, **extra):
    d = {"interventions": interventions, "unexplained_real_slices": unexplained}
    d.update(extra)
    return d


def full_ledger(zcheck):
    """认领核对走完的最小账本：每个 real 切片都登记过（这里一律记为 uncovered）。"""
    return {"uncovered": [{"slice": s, "note": "无假设认领"}
                          for s in sorted(hc.real_slices(zcheck))]}


def run(tmp_path, zcheck, verdicts, ledger="auto", write_ledger=True):
    (tmp_path / "slice_zcheck.json").write_text(json.dumps(zcheck), encoding="utf-8")
    (tmp_path / "verdict_summary.json").write_text(json.dumps(verdicts), encoding="utf-8")
    if write_ledger:
        led = full_ledger(zcheck) if ledger == "auto" else ledger
        (tmp_path / "hypothesis_ledger.json").write_text(json.dumps(led), encoding="utf-8")
    return subprocess.run([sys.executable, SCRIPT], cwd=tmp_path,
                          capture_output=True, text=True, timeout=60)


def test_missing_ledger_fails_loudly(tmp_path):
    r = run(tmp_path, REAL3, vs([], []), write_ledger=False)
    assert r.returncode == 1 and "hypothesis_ledger.json" in r.stdout


# ------------------------------------------------------------------ 计算
def test_unexplained_is_real_minus_moved():
    h = hc.compute_harvest(REAL3, None, vs(
        [{"hypothesis_id": "H1", "verdict": "confirmed"}], [],
        slice_recompute={"H1": {"beyond_noise_floor": [["horizon:far", -0.01, "归零"]]}}))
    assert h["n_real_slices"] == 3 and h["n_moved"] == 1
    assert [u["slice"] for u in h["unexplained"]] == ["channel:a", "month:2020-10"]
    assert h["harvest"] == "partial" and h["next_round_required"] is True


def test_harvest_none_when_nothing_confirmed_and_nothing_moved():
    h = hc.compute_harvest(REAL3, None, vs(
        [{"hypothesis_id": "H1", "verdict": "undecided"}], []))
    assert h["harvest"] == "none" and h["n_confirmed"] == 0
    assert len(h["unexplained"]) == 3


def test_harvest_full_when_every_real_slice_moved():
    h = hc.compute_harvest(REAL3, None, vs(
        [{"hypothesis_id": "H1", "verdict": "confirmed"}], [],
        slice_recompute={"H1": {"beyond_noise_floor": [
            ["channel:a", 0.1, "归零"], ["month:2020-10", 0.1, "反转"],
            ["horizon:far", 0.1, "残留"]]}}))
    assert h["harvest"] == "full" and h["unexplained"] == []
    assert h["next_round_required"] is False


def test_dimension_comes_from_slice_name_not_ledger():
    """账本 slice_map 的 dimension 是自由填写的：r1 里 month:2020-12 被标成 time，
    照它分组会把同一批残留拆成两堆。维度只认切片名前缀。"""
    led = {"slice_map": [{"slice": "month:2020-10", "dimension": "time",
                          "claimed_by": ["H1"]}]}
    h = hc.compute_harvest(REAL3, led, vs([], []))
    assert h["residual_by_dimension"] == {"channel": 1, "horizon": 1, "month": 1}
    row = [u for u in h["unexplained"] if u["slice"] == "month:2020-10"][0]
    assert row["dimension"] == "month" and row["claimed_by"] == ["H1"]


def test_claim_state_separates_uncovered_from_unregistered():
    """「账本登记为无人认领」和「压根没登记」是两回事：前者是 Stage 1 认领核对走完的
    合法出口，后者是那道硬规则没走完。真实回归：r1 的账本 slice_map 只有 29 行、
    slice_zcheck 有 31 个切片，month:2020-10/11 与 time_half:first 三条从没登记过，
    此前被印成同一句「无人认领」。"""
    led = {"slice_map": [{"slice": "channel:a", "claimed_by": ["H1"]},
                         {"slice": "month:2020-10", "claimed_by": []}]}
    h = hc.compute_harvest(REAL3, led, vs([], []))
    state = {u["slice"]: u["claim_state"] for u in h["unexplained"]}
    assert state == {"channel:a": "claimed", "month:2020-10": "uncovered",
                     "horizon:far": "unregistered"}
    assert h["unregistered_real_slices"] == ["horizon:far"]
    assert h["never_claimed"] == ["horizon:far", "month:2020-10"]


def test_uncovered_list_counts_as_registered():
    led = {"slice_map": [{"slice": "channel:a", "claimed_by": ["H1"]}],
           "uncovered": [{"slice": "month:2020-10", "note": "无假设认领"},
                         {"slice": "horizon:far", "note": "无假设认领"}]}
    h = hc.compute_harvest(REAL3, led, vs([], []))
    assert h["unregistered_real_slices"] == []
    assert hc.validate(h, vs([], [u["slice"] for u in h["unexplained"]])) == []


def test_unregistered_real_slice_blocks(tmp_path):
    led = {"slice_map": [{"slice": "channel:a", "claimed_by": ["H1"]}]}
    r = run(tmp_path, REAL3, vs([], ["channel:a", "horizon:far", "month:2020-10"]), ledger=led)
    assert r.returncode == 1
    assert "既没进 slice_map 也没进 uncovered" in r.stdout
    assert "horizon:far" in r.stdout and "month:2020-10" in r.stdout
    assert not (tmp_path / "harvest.json").exists()


def test_moved_slice_outside_real_set_is_ignored():
    """干预推动了一个 ~noise 切片不算解释——分母只有 real 切片。"""
    h = hc.compute_harvest(REAL3, None, vs([], [],
        slice_recompute={"H1": {"beyond_noise_floor": [["channel:b", 0.1, "归零"]]}}))
    assert h["n_moved"] == 0 and len(h["unexplained"]) == 3


# ------------------------------------------------------------------ 对账
def test_missing_unexplained_field_is_rejected(tmp_path):
    r = run(tmp_path, REAL3, {"interventions": []})
    assert r.returncode == 1 and "unexplained_real_slices" in r.stdout
    assert not (tmp_path / "harvest.json").exists()


def test_unexplained_list_must_match_computation(tmp_path):
    r = run(tmp_path, REAL3, vs([], ["channel:a"]))
    assert r.returncode == 1 and "漏列" in r.stdout


def test_declared_counts_must_match_interventions(tmp_path):
    r = run(tmp_path, REAL3, vs([{"hypothesis_id": "H1", "verdict": "undecided"}],
                                ["channel:a", "horizon:far", "month:2020-10"],
                                n_confirmed=2))
    assert r.returncode == 1 and "n_confirmed=2" in r.stdout


def test_zero_confirmed_with_nothing_unexplained_is_contradiction():
    h = hc.compute_harvest(zc(**{"channel:a": ("real", 8.0, 0.02)}), None,
                           vs([], [], slice_recompute={
                               "H1": {"beyond_noise_floor": [["channel:a", 0.1, "归零"]]}}))
    errs = hc.validate(h, vs([], []))
    assert any("自相矛盾" in e for e in errs)


def test_missing_zcheck_fails_loudly(tmp_path):
    (tmp_path / "verdict_summary.json").write_text(json.dumps(vs([], [])), encoding="utf-8")
    r = subprocess.run([sys.executable, SCRIPT], cwd=tmp_path,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "slice_zcheck.json" in r.stdout


# ------------------------------------------------------------------ 落盘与汇报
def test_writes_append_array_and_reports_three_options(tmp_path):
    r = run(tmp_path, REAL3, vs([{"hypothesis_id": "H1", "verdict": "undecided"}],
                                ["channel:a", "horizon:far", "month:2020-10"]))
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.load(open(tmp_path / "harvest.json", encoding="utf-8"))
    assert isinstance(doc, list) and len(doc) == 1 and doc[0]["verdict_summary_sha256"]
    for opt in ("①", "②", "③"):
        assert opt in r.stdout
    assert "不许自己替用户选" in r.stdout
    assert "本轮未能归因到任何组件" in r.stdout  # confirmed=0 时把闸的原话给出来
    r2 = run(tmp_path, REAL3, vs([{"hypothesis_id": "H1", "verdict": "undecided"}],
                                 ["channel:a", "horizon:far", "month:2020-10"]))
    assert r2.returncode == 0
    assert len(json.load(open(tmp_path / "harvest.json", encoding="utf-8"))) == 2


def test_round_counts_prior_harvests(tmp_path):
    """轮次自己数：解释环没人写 state.round（那是改进环的字段），第 N 次收口 = 第 N 轮。"""
    args = (REAL3, vs([], ["channel:a", "horizon:far", "month:2020-10"]))
    run(tmp_path, *args)
    run(tmp_path, *args)
    doc = json.load(open(tmp_path / "harvest.json", encoding="utf-8"))
    assert [d["round"] for d in doc] == [1, 2]
