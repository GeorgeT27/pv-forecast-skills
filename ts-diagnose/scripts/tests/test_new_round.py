"""解释环开新一轮：归档上一轮产物、腾空入口、账本补轮次。

回归点：model-comparison 与 architecture-attribution 的阶段产物都是扁平命名的，
第一轮跑完文件全在盘上，orient 判每个阶段都 done → 用户选①「换角度再取一轮」时
根本拿不到 Stage 0/1 的入口；硬做又会盖掉上一轮「问了什么、取了什么证」的记录，
账本也分不清哪条假设是哪轮提的。
"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(SCRIPTS_DIR, "new_round.py")
LEDGER = os.path.join(SCRIPTS_DIR, "hypothesis_ledger.py")
sys.path.insert(0, SCRIPTS_DIR)
import new_round as nr            # noqa: E402
import hypothesis_ledger as hl    # noqa: E402

HARVEST = [{"round": 1, "harvest": "none", "n_confirmed": 0,
            "unexplained": [{"slice": "channel:a"}, {"slice": "month:2020-10"}]}]
LED = {"slice_map": [{"slice": "channel:a", "claimed_by": ["H1"]}],
       "hypotheses": [{"id": "H1", "claim": "c", "component": "m.x",
                       "falsifiable_pred": "p", "status": "undecided",
                       "provenance": "pre-registered"}]}


def world(tmp_path, *, state=None, harvest=HARVEST, ledger=LED, artifacts=True):
    (tmp_path / "diagnose_state.json").write_text(
        json.dumps(state if state is not None else {"round": 1}), encoding="utf-8")
    if harvest is not None:
        (tmp_path / "harvest.json").write_text(json.dumps(harvest), encoding="utf-8")
    if ledger is not None:
        (tmp_path / "hypothesis_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    if artifacts:
        for n in ("slice_zcheck.json", "verdict_summary.json", "intervention_plan.json"):
            (tmp_path / n).write_text("{}", encoding="utf-8")
        (tmp_path / "charts").mkdir()
        (tmp_path / "charts" / "x.json").write_text("{}", encoding="utf-8")
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts" / "H1.json").write_text("[]", encoding="utf-8")
    return tmp_path


def run(wd, *args):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=wd,
                          capture_output=True, text=True, timeout=60)


# ------------------------------------------------------------------ 归档
def test_archives_round_artifacts_and_bumps_round(tmp_path):
    wd = world(tmp_path)
    r = run(wd, "--note", "改按波动强度切")
    assert r.returncode == 0, r.stdout + r.stderr
    for n in ("slice_zcheck.json", "verdict_summary.json", "intervention_plan.json", "charts"):
        assert not (wd / n).exists(), f"{n} 还在原地——入口就回不来"
        assert (wd / "rounds" / "round_1" / n).exists(), f"{n} 没归档——上一轮记录丢了"
    assert json.load(open(wd / "diagnose_state.json", encoding="utf-8"))["round"] == 2


def test_cumulative_artifacts_stay_put(tmp_path):
    """账本跨轮累积、receipt 防摘樱桃、收成追加——三样都不许归档。"""
    wd = world(tmp_path)
    assert run(wd).returncode == 0
    for n in ("hypothesis_ledger.json", "harvest.json", "receipts/H1.json"):
        assert (wd / n).exists(), f"{n} 被归档了"


def test_existing_hypotheses_get_tagged_with_their_round(tmp_path):
    wd = world(tmp_path)
    assert run(wd).returncode == 0
    led = json.load(open(wd / "hypothesis_ledger.json", encoding="utf-8"))
    assert [h["round"] for h in led["hypotheses"]] == [1]


def test_manifest_records_what_each_round_left_behind(tmp_path):
    wd = world(tmp_path)
    assert run(wd, "--note", "按波动强度").returncode == 0
    m = json.load(open(wd / "rounds" / "manifest.json", encoding="utf-8"))
    assert len(m) == 1 and m[0]["round"] == 1 and m[0]["harvest"] == "none"
    assert m[0]["note"] == "按波动强度"
    assert m[0]["unexplained"] == ["channel:a", "month:2020-10"]


def test_dry_run_touches_nothing(tmp_path):
    wd = world(tmp_path)
    r = run(wd, "--dry-run")
    assert r.returncode == 0 and "没动盘" in r.stdout
    assert (wd / "slice_zcheck.json").exists() and not (wd / "rounds").exists()
    assert json.load(open(wd / "diagnose_state.json", encoding="utf-8"))["round"] == 1


# ------------------------------------------------------------------ 拒绝的情形
def test_refuses_without_harvest(tmp_path):
    """没收口就开新一轮 = 不知道这轮解释了多少就换角度，等于瞎换。"""
    wd = world(tmp_path, harvest=None)
    r = run(wd)
    assert r.returncode == 1 and "harvest_check" in r.stdout


def test_refuses_without_state(tmp_path):
    wd = world(tmp_path)
    os.remove(wd / "diagnose_state.json")
    assert run(wd).returncode == 1


def test_refuses_when_nothing_to_archive(tmp_path):
    wd = world(tmp_path, artifacts=False)
    r = run(wd)
    assert r.returncode == 1 and "一个都不在盘上" in r.stdout


def test_refuses_to_overwrite_an_existing_archive(tmp_path):
    wd = world(tmp_path)
    (wd / "rounds" / "round_1").mkdir(parents=True)
    r = run(wd)
    assert r.returncode == 1 and "已存在" in r.stdout
    assert (wd / "slice_zcheck.json").exists()   # 拒绝时不许动盘


# ------------------------------------------------------------------ 按轮盖章
def test_round_receipt_needs_a_hypothesis_from_this_round(tmp_path):
    """账本在盘上说明不了「这一轮登记过假设」——章是按轮盖的。"""
    wd = world(tmp_path)
    assert run(wd).returncode == 0            # → round 2
    r = subprocess.run([sys.executable, LEDGER, "hypothesis_ledger.json"],
                       cwd=wd, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "第 2 轮还没登记任何假设" in r.stdout
    assert not (wd / "gate_reports" / "ledger_round_2.json").exists()

    led = json.load(open(wd / "hypothesis_ledger.json", encoding="utf-8"))
    led["hypotheses"].append(dict(led["hypotheses"][0], id="H2", round=2, status="pending"))
    (wd / "hypothesis_ledger.json").write_text(json.dumps(led), encoding="utf-8")
    r2 = subprocess.run([sys.executable, LEDGER, "hypothesis_ledger.json"],
                        cwd=wd, capture_output=True, text=True, timeout=60)
    assert r2.returncode == 0, r2.stdout
    rec = json.load(open(wd / "gate_reports" / "ledger_round_2.json", encoding="utf-8"))
    assert rec["round"] == 2 and rec["hypotheses_this_round"] == ["H2"]
    assert rec["n_hypotheses_total"] == 2 and rec["ledger_sha256"]


def test_missing_round_field_counts_as_round_one():
    assert hl.hypotheses_in_round(LED, 1) == ["H1"]
    assert hl.hypotheses_in_round(LED, 2) == []


def test_round_field_must_be_a_positive_int():
    bad = {"hypotheses": [dict(LED["hypotheses"][0], round=0)]}
    assert any("round 须为" in e for e in hl.validate_ledger(bad))
    bad2 = {"hypotheses": [dict(LED["hypotheses"][0], round="2")]}
    assert any("round 须为" in e for e in hl.validate_ledger(bad2))
    ok = {"hypotheses": [dict(LED["hypotheses"][0], round=3)]}
    assert hl.validate_ledger(ok) == []


def test_tag_ledger_rounds_leaves_existing_tags_alone():
    led = {"hypotheses": [{"id": "A", "round": 1}, {"id": "B"}]}
    out, n = nr.tag_ledger_rounds(led, 2)
    assert n == 1
    assert [h["round"] for h in out["hypotheses"]] == [1, 2]
