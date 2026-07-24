import subprocess, sys, os, textwrap

HERE = os.path.dirname(__file__)

def test_profile_data_runs_on_small_csv(tmp_path):
    csv = tmp_path / "sample.csv"
    csv.write_text("t,power\n0,1.0\n1,2.0\n2,3.0\n3,2.0\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "profile_data.py"), str(csv)],
        capture_output=True, text=True,
    )
    # Either it profiles successfully, or it prints a dependency install hint —
    # both are acceptable; a traceback/crash is not.
    assert out.returncode == 0 or "install" in (out.stdout + out.stderr).lower(), out.stderr
