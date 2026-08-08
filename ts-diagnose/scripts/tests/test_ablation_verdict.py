"""干预判定测试：delta 与噪声底 3σ 比较 + 预测方向核对 → 确认/否证/未决。
CLI 部分额外验证 receipt 行格式与 conclusion_gate.RECEIPT_LINE_RE 对齐（Task 1 契约）。"""
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import ablation_verdict as av  # noqa: E402
import conclusion_gate as cg  # noqa: E402


def test_confirmed_when_delta_exceeds_floor_and_direction_matches():
    assert av.verdict(delta=0.031, noise_floor_3sigma=0.0102, pred_direction="increase") == "confirmed"


def test_undecided_when_within_noise_floor():
    assert av.verdict(delta=0.004, noise_floor_3sigma=0.0102, pred_direction="increase") == "undecided"


def test_refuted_when_direction_wrong():
    assert av.verdict(delta=-0.031, noise_floor_3sigma=0.0102, pred_direction="increase") == "refuted"


def test_cli_receipt_line_matches_gate_regex():
    """CLI 打印的 receipt 行必须能被 Task 1 的 conclusion_gate.RECEIPT_LINE_RE 命中——
    这是「## 消融证据」节直接抄录该行就能过闸的契约保证。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "ablation_verdict.py"),
         "--hypothesis-id", "H3", "--switch=--itrans_no_attn",
         "--delta", "0.031", "--noise-floor", "0.0102",
         "--direction", "increase", "--seeds", "3"],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    line = proc.stdout.strip()
    assert cg.RECEIPT_LINE_RE.search(line), f"receipt 行未命中 RECEIPT_LINE_RE：{line}"
    assert "confirmed" in line
    assert "switch=--itrans_no_attn" in line
    assert "seeds=3" in line


def test_cli_undecided_and_refuted_lines_also_match_gate_regex():
    for delta, direction, want in (("0.004", "increase", "undecided"),
                                    ("-0.031", "increase", "refuted")):
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "ablation_verdict.py"),
             "--hypothesis-id", "H1", "--switch=--n_heads=1",
             "--delta", delta, "--noise-floor", "0.0102",
             "--direction", direction, "--seeds", "3"],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        line = proc.stdout.strip()
        assert want in line
        assert cg.RECEIPT_LINE_RE.search(line), f"receipt 行未命中 RECEIPT_LINE_RE：{line}"
