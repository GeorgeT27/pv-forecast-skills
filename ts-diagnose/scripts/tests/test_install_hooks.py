import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ENGINE_DIR, "hooks"))
import install_hooks as ih  # noqa: E402

SCRIPTS = ("stage_probe.py", "gate_guard.py", "orient_reminder.py")


def _cmds(settings):
    return [h["command"] for ev in settings.get("hooks", {}).values()
            for e in ev for h in e["hooks"]]


def test_hooks_json_resolves_pkg_and_scripts_exist():
    ours = ih.load_hooks_json()
    assert set(ours) == {"PostToolUse", "Stop", "UserPromptSubmit"}
    for ev in ours.values():
        for e in ev:
            for h in e["hooks"]:
                assert "<PKG>" not in h["command"]
                path = h["command"].split('"')[1]
                assert os.path.isfile(path), path


def test_merge_into_empty_then_idempotent(tmp_path):
    s = tmp_path / "settings.json"
    ih.main(["--settings", str(s)])
    first = json.loads(s.read_text(encoding="utf-8"))
    assert sorted(os.path.basename(c.split('"')[1]) for c in _cmds(first)) == sorted(SCRIPTS)
    ih.main(["--settings", str(s)])
    second = json.loads(s.read_text(encoding="utf-8"))
    assert first == second


def test_merge_preserves_foreign_entries_and_uninstall_removes_only_ours(tmp_path):
    s = tmp_path / "settings.json"
    foreign = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "echo foreign"}]}]}, "permissions": {"allow": ["x"]}}
    s.write_text(json.dumps(foreign), encoding="utf-8")
    ih.main(["--settings", str(s)])
    merged = json.loads(s.read_text(encoding="utf-8"))
    assert "echo foreign" in _cmds(merged)
    assert merged["permissions"] == {"allow": ["x"]}
    ih.main(["--settings", str(s), "--uninstall"])
    after = json.loads(s.read_text(encoding="utf-8"))
    assert _cmds(after) == ["echo foreign"]
    assert "Stop" not in after["hooks"]


def test_dry_run_writes_nothing(tmp_path, capsys):
    s = tmp_path / "settings.json"
    ih.main(["--settings", str(s), "--dry-run"])
    assert not s.exists()
    assert "gate_guard.py" in capsys.readouterr().out
