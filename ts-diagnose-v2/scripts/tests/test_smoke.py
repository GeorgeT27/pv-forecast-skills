import os, sys, subprocess, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
V2 = os.path.dirname(SCRIPTS_DIR)
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")

import pytest

@pytest.mark.parametrize("pid", ["model-comparison", "training-sufficiency"])
def test_orient_steps_on_copy(pid):
    with tempfile.TemporaryDirectory() as wd:
        r = subprocess.run([sys.executable, ORIENT, "--playbook", pid],
                           cwd=wd, capture_output=True, text=True)
        assert r.returncode == 0, f"orient --playbook {pid} 失败：{r.stderr[-800:]}"
        assert pid in (r.stdout + r.stderr), "orient 输出未提及该 playbook"

@pytest.mark.parametrize("pid", ["model-comparison", "training-sufficiency"])
def test_golden_regenerates(pid):
    gdir = os.path.join(V2, "playbooks", pid, "golden")
    mk = os.path.join(gdir, "make_golden.py")
    assert os.path.exists(mk), f"{pid} 缺 golden/make_golden.py"
    r = subprocess.run([sys.executable, mk], cwd=gdir, capture_output=True, text=True)
    assert r.returncode == 0, f"{pid} make_golden 失败：{r.stderr[-800:]}"
