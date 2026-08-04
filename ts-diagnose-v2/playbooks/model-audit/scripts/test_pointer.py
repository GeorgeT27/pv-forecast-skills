import json
import os
from pointer import write_pointer, read_pointer, is_stale

def test_roundtrip(tmp_path):
    p = tmp_path / "sub" / "model-ref.pointer"
    write_pointer(
        str(p),
        docs_path="/repo/.modelmap",
        repo="/repo",
        commit="abc123",
        models=["M1", "M2", "ensemble"],
        date="2026-07-13",
    )
    got = read_pointer(str(p))
    assert got["path"] == "/repo/.modelmap"
    assert got["repo"] == "/repo"
    assert got["commit"] == "abc123"
    assert got["date"] == "2026-07-13"
    assert got["models"] == ["M1", "M2", "ensemble"]

def test_is_stale_commit_mismatch():
    assert is_stale({"commit": "abc123"}, "def456") is True
    assert is_stale({"commit": "abc123"}, "abc123") is False

def test_is_stale_no_git_never_stale():
    assert is_stale({"commit": "no-git"}, "anything") is False
    assert is_stale({"commit": ""}, "anything") is False

def test_write_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import pointer
    pointer.write_receipt(modelmap_dir=str(tmp_path / "repo/.modelmap"),
                          commit="abc1234")
    rec = json.load(open("MODELMAP_RECEIPT.json", encoding="utf-8"))
    assert rec["modelmap_dir"].endswith(".modelmap")
    assert rec["commit"] == "abc1234" and rec["date"]
