"""symlink 安装下 ENGINE_DIR 必须物理解析到真包目录——否则 project-context 探测静默失效。"""
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(SCRIPTS_DIR)


def test_engine_dir_resolves_symlink(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(ENGINE_DIR)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import engine_common as ec; print(ec.ENGINE_DIR)"
            % os.path.join(str(link), "scripts"))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == os.path.realpath(ENGINE_DIR)


def test_project_context_reachable_through_symlink(tmp_path):
    """真仓库里 project-context/ 与引擎同级；经 symlink 导入也必须探到。"""
    if not os.path.isdir(os.path.join(os.path.dirname(ENGINE_DIR), "project-context")):
        import pytest
        pytest.skip("本 checkout 无同级 project-context/")
    link = tmp_path / "link"
    link.symlink_to(ENGINE_DIR)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import engine_common as ec; print(ec.detect_project_context())"
            % os.path.join(str(link), "scripts"))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() not in ("", "None")
