"""金标准端到端：三个阶段脚本必须过 gen_gate（复用 ts-diagnose 的闸，--playbook 给路径形式）。

这同时钉死：CLI 契约、产物 schema、埋点召回（f_blame 被点名）与诱饵拒绝（f_decoy 不被点名）。
另含一个「放水脚本必须 FAIL」用例——谁把诱饵点了名，金标准就拦谁，钉住诱饵断言有牙。

路径说明（2026-07-24 随 feature-blame 方法并入 feature-importance playbook 迁移）：
gen_gate.py 的 golden_run() 硬编码去 <playbook_dir>/golden/manifest.json 找金标准（目录名
写死为 golden，见 ts-diagnose/scripts/gen_gate.py）。本文件的金标准数据迁移后落在同目录的
golden-feature-blame/（改名是为了不与 feature-importance playbook 自己的引擎金标准 golden/
撞名——那是两回事，绝不可合并或互相覆盖）。故不能直接把 --playbook 指向本 playbook 目录；
改为在每个 tmp_path 沙箱里搭一个一次性「锚点」：anchor.md 旁放一份 golden/（= golden-feature-blame
的拷贝），--playbook 指向 anchor.md，gen_gate 就能按约定解析到正确的金标准，而不触碰
playbook.md 的真实 golden/。
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(PLAYBOOK_DIR)))  # scripts→playbook→playbooks→ts-diagnose→repo
GATE = os.path.join(REPO, "ts-diagnose", "scripts", "gen_gate.py")
GOLDEN_SRC = os.path.join(PLAYBOOK_DIR, "golden-feature-blame")

STAGES = [("0", "probe_schema.py"), ("1", "find_bad_rows.py"),
          ("decomp", "feature_decompose.py"), ("2", "feature_blame.py"),
          ("revision", "feature_revision.py"), ("4", "cf_logic.py")]


def _gate_anchor(workdir):
    """在 workdir 下搭 anchor.md + golden/（拷贝自 golden-feature-blame），
    返回 anchor.md 路径供 --playbook 使用。gen_gate 只读 golden/manifest.json，
    不写它——多个测试各自的 tmp_path 互不干扰，无需清理。"""
    anchor = os.path.join(workdir, "_gate_anchor.md")
    if not os.path.exists(anchor):
        open(anchor, "w", encoding="utf-8").close()
        shutil.copytree(GOLDEN_SRC, os.path.join(workdir, "golden"))
    return anchor


def run_gate(workdir, script, stage):
    playbook = _gate_anchor(str(workdir))
    return subprocess.run(
        [sys.executable, GATE, "--script", script, "--playbook", playbook, "--stage", stage],
        cwd=workdir, capture_output=True, text=True)


@pytest.mark.parametrize("stage,script", STAGES)
def test_stage_scripts_pass_gate(tmp_path, stage, script):
    r = run_gate(tmp_path, os.path.join(HERE, script), stage)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.load(open(tmp_path / "gate_reports" / (script[:-3] + ".json"), encoding="utf-8"))
    assert rep["passed"] and rep["static"]["passed"] and rep["golden"]["passed"]
    assert len(rep["script_sha256"]) == 64


BAD_BLAME = r'''
import argparse, json
ap = argparse.ArgumentParser()
ap.add_argument("--feature-true")
a, _ = ap.parse_known_args()
FEATS = ("f_blame", "f_decoy", "f_good", "ghi", "f_jumpy", "f_jumpy_decoy",
         "f_sys_bias", "f_res_culprit", "f_irreducible")
def feats(top):
    out = {}
    for f in FEATS:
        out[f] = {"global_spearman": 0.95 if f == top else 0.1,
                  "feature_err_mean": 2.0 if f in ("f_blame", "f_decoy") else 0.0,
                  "blamed_rows": 1 if f == top else 0, "z_max": 3.0,
                  "global_spearman_raw": 0.1, "feature_err_raw_mean": 1.0,
                  "sys_frac": 0.0, "stability_lambda": 0.0, "reducibility_frac": 1.0}
    return out
summary = {}
for metric in ("ultra_short", "short", "rmse_192"):
    for model in ("pred_M1", "pred_ensemble", "pred_M3", "pred_M4res"):
        summary.setdefault(metric, {})[model] = {
            "n_rows": 40, "n_bad": 1, "features": feats("f_decoy"),   # 放水：点名了诱饵
            "ranking_by_spearman": ["f_decoy"] + [f for f in FEATS if f != "f_decoy"],
            "collinearity_clusters": []}
json.dump({"params": {"decomp": "on"}, **summary}, open("blame_summary.json", "w"))
open("blame_report.csv", "w").write("model,metric\n")
'''


def test_decoy_assertion_has_teeth(tmp_path):
    """CLI 正确、产物 schema 正确、但把误差大的诱饵点了名 → 金标准必须 FAIL。"""
    bad = tmp_path / "bad_blame.py"
    bad.write_text(BAD_BLAME, encoding="utf-8")
    r = run_gate(tmp_path, str(bad), "2")
    assert r.returncode != 0
    assert "不许拿本脚本跑真实数据" in r.stdout


def test_manifest_inputs_exist():
    """manifest 声明的 golden 输入文件必须齐全（防中间产物漏拷/漏提交）。"""
    gdir = GOLDEN_SRC
    man = json.load(open(os.path.join(gdir, "manifest.json"), encoding="utf-8"))
    assert man.get("stages")
    for st, ent in man["stages"].items():
        for rel in ent.get("inputs") or []:
            assert os.path.exists(os.path.join(gdir, rel)), f"golden 缺 {rel}（stage {st}）"
        assert ent.get("args") and ent.get("expect"), f"stage {st} 契约不完整"
