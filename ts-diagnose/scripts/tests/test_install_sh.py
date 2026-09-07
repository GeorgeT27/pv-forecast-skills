import glob, json, os, subprocess
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SH = os.path.join(ENGINE_DIR, "install.sh")


def _run(args, home):
    return subprocess.run(["bash", SH, *args], env={**os.environ, "CLAUDE_HOME": str(home)},
                          capture_output=True, text=True)


def _cards():
    return sorted(os.path.basename(p) for pat in ("*-compute.md", "*-worker.md", "*-baseline.md")
                  for p in glob.glob(os.path.join(ENGINE_DIR, "agents", pat)))


def test_install_links_everything_then_check_passes(tmp_path):
    home = tmp_path / "claude"
    (home / "skills").mkdir(parents=True)
    (home / "skills" / "ts-diagnose-v2").symlink_to(ENGINE_DIR)
    r = _run([], home)
    assert r.returncode == 0, r.stderr
    assert os.path.realpath(home / "skills" / "ts-diagnose") == os.path.realpath(ENGINE_DIR)
    for c in _cards():
        assert os.path.islink(home / "agents" / c), c
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    assert {"PostToolUse", "Stop", "UserPromptSubmit"} <= set(settings["hooks"])
    assert not (home / "skills" / "ts-diagnose-v2").exists()
    r = _run(["--check"], home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL OK" in r.stdout


def test_install_is_idempotent_and_uninstall_cleans(tmp_path):
    home = tmp_path / "claude"
    assert _run([], home).returncode == 0
    assert _run([], home).returncode == 0
    r = _run(["--uninstall"], home)
    assert r.returncode == 0, r.stderr
    assert not (home / "skills" / "ts-diagnose").exists()
    assert not list((home / "agents").glob("*.md"))
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    assert not settings.get("hooks")


def test_copy_mode_copies_cards(tmp_path):
    home = tmp_path / "claude"
    assert _run(["--copy"], home).returncode == 0
    for c in _cards():
        p = home / "agents" / c
        assert p.is_file() and not p.is_symlink(), c
