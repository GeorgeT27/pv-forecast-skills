import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hypothesis_ledger as hl

# slice_map 行的规格：slice + claimed_by 必填（此前无人写过 schema，夹具停在只有
# dim/bucket 的旧形态，与真跑产物和下游消费者键的字段都对不上）。
VALID = {"slice_map": [{"slice": "lead_time:far", "claimed_by": ["H1"],
                        "dimension": "lead_time", "z": 10.2, "winner": "iTransformer"}],
         "hypotheses": [{"id": "H1", "claim": "跨变量注意力带来近端优势",
                         "component": "itransformer.attention",
                         "falsifiable_pred": "置零后近端优势消失",
                         "discriminating_power": 3,
                         "intervention": {"switch": "--itrans_no_attn", "seeds": 3},
                         "status": "pending", "kill_receipt": None,
                         "provenance": "pre-registered"}]}

def test_valid_ledger_passes():
    assert hl.validate_ledger(VALID) == []

def test_missing_component_rejected():
    bad = {"slice_map": [], "hypotheses": [dict(VALID["hypotheses"][0], component="")]}
    errs = hl.validate_ledger(bad)
    assert any("component" in e for e in errs)

def test_posthoc_requires_new_intervention_flag():
    h = dict(VALID["hypotheses"][0], provenance="post-hoc", status="confirmed", kill_receipt=None)
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("post-hoc" in e for e in errs)

def test_refuted_requires_kill_receipt():
    h = dict(VALID["hypotheses"][0], status="refuted", kill_receipt=None)
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("kill_receipt" in e for e in errs)

def test_no_candidate_is_undecided_only():
    h = dict(VALID["hypotheses"][0], provenance="no_candidate", status="confirmed")
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("no_candidate" in e for e in errs)


def test_empty_object_rejected():
    """畸形账本：顶层无 hypotheses 键，不得静默视为合法（原 bug：{}.get(...) == [] → 无错误）。"""
    errs = hl.validate_ledger({})
    assert errs != []


def test_object_missing_hypotheses_key_rejected():
    errs = hl.validate_ledger({"foo": 1})
    assert errs != []


def test_non_list_hypotheses_rejected():
    errs = hl.validate_ledger({"hypotheses": "x"})
    assert errs != []


def test_non_dict_hypothesis_entry_rejected_without_crash():
    errs = hl.validate_ledger({"hypotheses": [1]})
    assert errs != []


IMPROVE = {"id": "F1", "kind": "improvement", "derived_from": "H1",
           "claim": "关闭通道混合能降 val_mse", "component": "tsmixer.channel_mix",
           "falsifiable_pred": "关闭后 val_mse 下降超噪声底且 far 不退化",
           "fix": {"target_model": "TSMixer", "config_diff": {"tsmixer_no_channel_mix": True},
                   "predicted_gain": "val_mse 下降 ≥ 0.0154", "guard_slices": ["horizon:far"]},
           "status": "pending", "provenance": "pre-registered", "kill_receipt": None, "receipt": None}


def test_improvement_entry_valid():
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [IMPROVE]}) == []


def test_kind_default_mechanism_and_illegal_kind_rejected():
    assert hl.validate_ledger(VALID) == []                      # 无 kind = mechanism
    h = dict(VALID["hypotheses"][0], kind="magic")
    assert any("kind" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h]}))


def test_improvement_allows_empty_guard_slices():
    """守护切片可以一个都没有：空 list 是合法取值，不是「缺字段」。"""
    h = dict(IMPROVE, fix=dict(IMPROVE["fix"], guard_slices=[]))
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [h]}) == []


def test_improvement_requires_fix_fields():
    h = dict(IMPROVE, fix={"target_model": "TSMixer"})
    errs = hl.validate_ledger({"slice_map": [], "hypotheses": [h]})
    assert any("config_diff" in e for e in errs) and any("guard_slices" in e for e in errs)
    h2 = dict(IMPROVE); del h2["fix"]
    assert any("fix" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h2]}))
    h3 = dict(IMPROVE, fix=dict(IMPROVE["fix"], config_diff="--flag"))
    assert any("config_diff" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h3]}))


def test_untested_requires_reason():
    h = dict(IMPROVE, status="untested")
    assert any("untested_reason" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h]}))
    ok = dict(IMPROVE, status="untested", untested_reason="seed 1337 crash: NaN loss")
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [ok]}) == []


def test_improvement_confirmed_requires_receipt():
    h = dict(IMPROVE, status="confirmed")
    assert any("receipt" in e for e in hl.validate_ledger({"slice_map": [], "hypotheses": [h]}))
    ok = dict(IMPROVE, status="confirmed", receipt="receipts/E003.json")
    assert hl.validate_ledger({"slice_map": [], "hypotheses": [ok]}) == []


# ---------------------------------------- R2-6：slice_map 结构与认领覆盖（Stage 1 机检）
# 回归点：r1 的账本 slice_map 只有 29 行、slice_zcheck 有 31 个切片，month:2020-10/11
# 与 time_half:first 三条从没登记过，一路带到 Stage 3 才被收口脚本抓出来。
ZC = {"slices": {"channel:a": {"verdict": "real", "z": 8.0},
                 "month:2020-10": {"verdict": "real", "z": 9.0},
                 "horizon:far": {"verdict": "real", "z": 11.0},
                 "channel:b": {"verdict": "~noise", "z": 0.4}}}
REAL = {k for k, v in ZC["slices"].items() if v["verdict"] == "real"}


def _led(slice_map, uncovered=None, hyps=None):
    d = {"slice_map": slice_map, "hypotheses": hyps if hyps is not None else []}
    if uncovered is not None:
        d["uncovered"] = uncovered
    return d


def test_unregistered_real_slice_is_rejected():
    led = _led([{"slice": "channel:a", "claimed_by": ["H1"]}])
    errs = hl.validate_ledger(led, REAL, ZC["slices"])
    assert any("既没进 slice_map 也没进 uncovered" in e for e in errs)
    assert any("month:2020-10" in e and "horizon:far" in e for e in errs)


def test_uncovered_covers_the_rest():
    led = _led([{"slice": "channel:a", "claimed_by": ["H1"]}],
               uncovered=[{"slice": "month:2020-10", "note": "无假设认领"}, "horizon:far"])
    assert hl.validate_ledger(led, REAL, ZC["slices"]) == []


def test_noise_slices_need_no_registration():
    """分母只有 real 切片——~noise 的不登记不算漏。"""
    led = _led([{"slice": s, "claimed_by": []} for s in sorted(REAL)])
    assert hl.validate_ledger(led, REAL, ZC["slices"]) == []


def test_claimed_and_uncovered_are_mutually_exclusive():
    led = _led([{"slice": s, "claimed_by": ["H1"]} for s in sorted(REAL)],
               uncovered=["channel:a"])
    errs = hl.validate_ledger(led, REAL, ZC["slices"])
    assert any("同时被假设认领又列进 uncovered" in e and "channel:a" in e for e in errs)


def test_duplicate_slice_row_is_rejected():
    led = _led([{"slice": "channel:a", "claimed_by": []},
                {"slice": "channel:a", "claimed_by": ["H1"]}],
               uncovered=["month:2020-10", "horizon:far"])
    assert any("重复登记切片 channel:a" in e for e in hl.validate_ledger(led, REAL, ZC["slices"]))


def test_embedded_zcheck_copy_must_match_source():
    """slice_map 里内嵌的 zcheck 是权威产物的副本——副本漂了比没有更危险。"""
    led = _led([{"slice": s, "claimed_by": [], "zcheck": {"verdict": "real"}}
                for s in sorted(REAL)])
    assert hl.validate_ledger(led, REAL, ZC["slices"]) == []
    led["slice_map"][0]["zcheck"] = {"verdict": "~noise"}
    assert any("副本已漂" in e for e in hl.validate_ledger(led, REAL, ZC["slices"]))


def test_claimed_by_must_be_list():
    led = _led([{"slice": s, "claimed_by": []} for s in sorted(REAL)])
    led["slice_map"][0]["claimed_by"] = "H1"
    assert any("claimed_by 须为 list" in e for e in hl.validate_ledger(led, REAL, ZC["slices"]))


def test_ledger_without_slice_map_is_untouched():
    """改进环的账本没有 slice_map——不许因此报错（零破坏）。"""
    assert hl.validate_ledger({"hypotheses": []}, REAL, ZC["slices"]) == []


def test_coverage_check_skipped_when_no_zcheck():
    """model-comparison 的工作目录没有 slice_zcheck（切片版图产在别处）——跳过覆盖检查。"""
    led = _led([{"slice": "channel:a", "claimed_by": ["H1"]}])
    assert hl.validate_ledger(led) == []


def test_slice_row_missing_claimed_by_is_rejected():
    """省略 claimed_by ≠ 写 []：下游按「有没有这个键」区分「没登记」与「登记为无人认领」。"""
    led = _led([{"slice": s} for s in sorted(REAL)])
    errs = hl.validate_ledger(led, REAL, ZC["slices"])
    assert any("缺 claimed_by" in e for e in errs)


def test_slice_row_missing_slice_name_names_the_row():
    """旧形态 {dim, bucket} 键不上 slice——报错要把整行打出来，不然没法定位。"""
    errs = hl.validate_ledger(_led([{"dim": "lead_time", "bucket": "far"}]))
    assert any("缺 slice 名" in e and "lead_time" in e for e in errs)
