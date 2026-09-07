import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hypothesis_ledger as hl

VALID = {"slice_map": [{"dim": "lead_time", "bucket": "far", "z": 10.2, "winner": "iTransformer"}],
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
