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
