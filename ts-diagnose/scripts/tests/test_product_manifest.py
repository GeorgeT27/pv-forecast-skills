"""setup_manifest.py / product_manifest.py 单测：引擎机制脚本（非运行时分析脚本，
不走 gen_gate），manifest 的 inputs 指纹契约必须与 product_status 咬合。"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402


def _seed(tmp_path):
    (tmp_path / "predictions.csv").write_text(
        "window_ts,unit_id,model,horizon_step,y_true,y_pred\n"
        "2024-01-01,S1,A,0,1.0,1.1\n2024-01-01,S1,B,0,1.0,1.2\n"
        "2024-01-02,S1,A,0,2.0,2.1\n", encoding="utf-8")
    (tmp_path / "alignment_report.json").write_text(
        json.dumps({"models": ["A", "B"], "n_aligned": 1, "freq": "1h"}),
        encoding="utf-8")
    raw = tmp_path / "raw_predict.parquet"
    raw.write_text("rawdata", encoding="utf-8")
    (tmp_path / "analysis_scripts").mkdir()
    (tmp_path / "analysis_scripts" / "adapter.py").write_text(
        "# adapter v1", encoding="utf-8")
    (tmp_path / "diagnose_config.json").write_text(json.dumps({
        "materials": {"predict": {"status": "present", "paths": [str(raw)],
                                  "schema": {"y_col": "y", "time_col": "ts"}},
                      "training_log": {"status": "present",
                                       "paths": [str(raw)]},
                      "truth": {"status": "absent-confirmed", "source": "user"}}}),
        encoding="utf-8")
    return raw


def test_setup_manifest_contract(tmp_path):
    raw = _seed(tmp_path)
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS_DIR, "setup_manifest.py")],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    man = json.loads((tmp_path / "setup_manifest.json").read_text(encoding="utf-8"))
    assert man["product"] == "setup"
    assert man["models"] == ["A", "B"]
    assert man["n_rows"] == 3 and man["freq"] == "1h"
    assert man["window_range"] == ["2024-01-01", "2024-01-02"]
    # 材料清单原样入 manifest（训练日志位置由此传给全下游）
    assert man["materials"]["training_log"]["paths"] == [str(raw)]
    # inputs 指纹与 product_status 契约咬合
    assert man["inputs"]["predict"]["fingerprint"] == ec.file_fingerprint(str(raw))
    # absent 材料不产指纹
    assert "truth" not in man["inputs"]
    # 代码也是依赖（Snakemake 7.8 教训）：适配器脚本指纹入 inputs
    assert man["inputs"]["_adapter_code"]["path"] == "analysis_scripts/adapter.py"


def test_product_manifest_generic(tmp_path):
    _seed(tmp_path)
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS_DIR, "product_manifest.py"),
                        "--product", "chart_sweep",
                        "--out", "chart_sweep_manifest.json"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    man = json.loads((tmp_path / "chart_sweep_manifest.json")
                     .read_text(encoding="utf-8"))
    assert man["product"] == "chart_sweep"
    assert set(man["inputs"]) == {"predict", "training_log"}


def _seed_multipath(tmp_path):
    """predict 材料声明两条真实存在的路径——终审抓到的 bug：只有第一条被指纹，
    第 2..N 条文件变了，过期检测对它失明。"""
    raw = _seed(tmp_path)
    raw2 = tmp_path / "raw_predict_part2.parquet"
    raw2.write_text("rawdata-part2", encoding="utf-8")
    cfg = json.loads((tmp_path / "diagnose_config.json").read_text(encoding="utf-8"))
    cfg["materials"]["predict"]["paths"] = [str(raw), str(raw2)]
    (tmp_path / "diagnose_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return raw, raw2


def test_setup_manifest_multi_path_material_all_fingerprinted(tmp_path):
    raw, raw2 = _seed_multipath(tmp_path)
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS_DIR, "setup_manifest.py")],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    man = json.loads((tmp_path / "setup_manifest.json").read_text(encoding="utf-8"))
    # 第一条路径仍用裸键（向后兼容）
    assert man["inputs"]["predict"]["path"] == str(raw)
    assert man["inputs"]["predict"]["fingerprint"] == ec.file_fingerprint(str(raw))
    # 第二条路径不能被 setdefault 吞掉——必须以 predict#1 入指纹
    assert man["inputs"]["predict#1"]["path"] == str(raw2)
    assert man["inputs"]["predict#1"]["fingerprint"] == ec.file_fingerprint(str(raw2))
    # 单路径材料（training_log）仍只用裸键，不产生 #0 后缀
    assert "training_log#0" not in man["inputs"]
    assert man["inputs"]["training_log"]["path"] == str(raw)


def test_product_manifest_generic_multi_path_material_all_fingerprinted(tmp_path):
    raw, raw2 = _seed_multipath(tmp_path)
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS_DIR, "product_manifest.py"),
                        "--product", "chart_sweep",
                        "--out", "chart_sweep_manifest.json"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    man = json.loads((tmp_path / "chart_sweep_manifest.json")
                     .read_text(encoding="utf-8"))
    assert man["inputs"]["predict"]["path"] == str(raw)
    assert man["inputs"]["predict#1"]["path"] == str(raw2)
    assert man["inputs"]["predict#1"]["fingerprint"] == ec.file_fingerprint(str(raw2))
