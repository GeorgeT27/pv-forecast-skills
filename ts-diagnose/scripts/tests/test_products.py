"""produces/upstream 分层机制测试：索引、校验、环检测、问题去重、产物状态、DSL、orient。
全部在 tmp 沙箱 playbooks 目录里跑（monkeypatch ec.PLAYBOOKS_DIR / 子进程用
TSD_PLAYBOOKS_DIR），不依赖真实 playbook 的 produces 声明落地顺序。"""
import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)
import engine_common as ec  # noqa: E402

PRODUCER = """\
---
id: prod-a
name: 生产者A
goal: 产 setup 供测试
produces:
  id: setup
  manifest: setup_manifest.json
  marker_files: [predictions.csv]
stages:
  - id: 0
    name: 做事
    done_when: {artifacts: ["predictions.csv"]}
questions:
  - id: freq
    stage: 0
    ask: 步长?
    why: w
    default: null
---
正文
"""

CONSUMER = """\
---
id: cons-b
name: 消费者B
goal: 消费 setup
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 分析
    done_when: {artifacts: ["out.json"]}
---
正文
"""


def _write_pb(root, pid, text):
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "playbook.md").write_text(text, encoding="utf-8")
    return str(d / "playbook.md")


@pytest.fixture
def pbdir(tmp_path, monkeypatch):
    d = tmp_path / "playbooks"
    _write_pb(d, "prod-a", PRODUCER)
    _write_pb(d, "cons-b", CONSUMER)
    monkeypatch.setattr(ec, "PLAYBOOKS_DIR", str(d))
    monkeypatch.chdir(tmp_path)
    return d


# ------------------------------------------------------------ products_index
def test_products_index_scans_produces(pbdir):
    idx = ec.products_index()
    assert idx["setup"] == {"playbook": "prod-a", "manifest": "setup_manifest.json",
                            "marker_files": ["predictions.csv"]}


def test_products_index_rejects_duplicate_id(pbdir):
    _write_pb(pbdir, "prod-dup", PRODUCER.replace("id: prod-a", "id: prod-dup"))
    with pytest.raises(ValueError, match="重复声明"):
        ec.products_index()


def test_produces_missing_key_rejected(pbdir):
    bad = PRODUCER.replace("  manifest: setup_manifest.json\n", "")
    p = _write_pb(pbdir, "prod-bad", bad.replace("id: prod-a", "id: prod-bad")
                  .replace("id: setup", "id: setup2"))
    with pytest.raises(ValueError, match="produces 缺 manifest"):
        ec.load_frontmatter(p)


# ------------------------------------------------------------ upstream 校验
def test_upstream_unknown_product_rejected(pbdir):
    p = _write_pb(pbdir, "cons-x", CONSUMER.replace("id: cons-b", "id: cons-x")
                  .replace("product: setup", "product: no-such"))
    with pytest.raises(ValueError, match="未声明的产物"):
        ec.load_frontmatter(p)


def test_upstream_self_reference_rejected(pbdir):
    text = PRODUCER.replace("id: prod-a", "id: prod-self").replace(
        "id: setup", "id: selfp")
    text = text.replace("---\n正文", "upstream:\n  - product: selfp\n"
                        "    required: true\n---\n正文")
    p = _write_pb(pbdir, "prod-self", text)
    with pytest.raises(ValueError, match="自引用"):
        ec.load_frontmatter(p)


def test_upstream_cycle_rejected(pbdir):
    a = ("---\nid: cyc-a\nname: a\ngoal: g\n"
         "produces: {id: pa, manifest: m.json, marker_files: [x]}\n"
         "upstream:\n  - {product: pb, required: true}\n"
         "stages:\n  - id: 0\n    name: s\n    done_when: {manual: true}\n---\n正文\n")
    b = ("---\nid: cyc-b\nname: b\ngoal: g\n"
         "produces: {id: pb, manifest: m.json, marker_files: [x]}\n"
         "upstream:\n  - {product: pa, required: true}\n"
         "stages:\n  - id: 0\n    name: s\n    done_when: {manual: true}\n---\n正文\n")
    _write_pb(pbdir, "cyc-a", a)
    pb = _write_pb(pbdir, "cyc-b", b)
    with pytest.raises(ValueError, match="成环"):
        ec.load_frontmatter(pb)


def test_upstream_question_dedupe(pbdir):
    text = CONSUMER.replace("id: cons-b", "id: cons-dupq").replace(
        "---\n正文",
        "questions:\n  - id: freq\n    stage: 0\n    ask: 步长?\n    why: w\n"
        "    default: null\n---\n正文")
    p = _write_pb(pbdir, "cons-dupq", text)
    with pytest.raises(ValueError, match="重复声明了生产者"):
        ec.load_frontmatter(p)


def test_playbook_without_layering_keys_unaffected(pbdir):
    plain = ("---\nid: plain\nname: p\ngoal: g\nstages:\n"
             "  - id: 0\n    name: s\n    done_when: {manual: true}\n---\n正文\n")
    p = _write_pb(pbdir, "plain", plain)
    fm = ec.load_frontmatter(p)
    assert fm["id"] == "plain"


# ------------------------------------------------------------ product_status
def _seed_setup_product(tmp_path, manifest=None):
    d = tmp_path / "setup"
    d.mkdir(exist_ok=True)
    (d / "predictions.csv").write_text("x", encoding="utf-8")
    (d / "setup_manifest.json").write_text(
        json.dumps(manifest if manifest is not None else {"inputs": {}}),
        encoding="utf-8")
    return d


def test_product_status_lifecycle(pbdir, tmp_path):
    assert ec.product_status({}, "setup")["status"] == "absent"
    with pytest.raises(ValueError, match="未知产物"):
        ec.product_status({}, "no-such")
    cfg = {"products": {"setup": {"workdir": "setup", "status": "built"}}}
    # 登记了但目录里没 marker → invalid
    (tmp_path / "setup").mkdir()
    assert ec.product_status(cfg, "setup")["status"] == "invalid"
    _seed_setup_product(tmp_path)
    assert ec.product_status(cfg, "setup")["status"] == "built"
    cfg2 = {"products": {"setup": {"status": "declined"}}}
    assert ec.product_status(cfg2, "setup")["status"] == "declined"


def test_product_status_staleness(pbdir, tmp_path):
    raw = tmp_path / "raw_predict.parquet"
    raw.write_text("v1", encoding="utf-8")
    fp = ec.file_fingerprint(str(raw))
    _seed_setup_product(tmp_path, {"inputs": {"predict": {"path": str(raw),
                                                          "fingerprint": fp}}})
    cfg = {"products": {"setup": {"workdir": "setup", "status": "built"}}}
    assert ec.product_status(cfg, "setup")["status"] == "built"
    raw.write_text("v2-changed", encoding="utf-8")       # 输入变了
    s = ec.product_status(cfg, "setup")
    assert s["status"] == "stale" and s["stale_inputs"] == ["predict"]
    cfg["products"]["setup"]["accept_stale"] = True      # 用户确认沿用
    assert ec.product_status(cfg, "setup")["status"] == "built"


def test_file_fingerprint_changes_with_content(tmp_path):
    p = tmp_path / "f.bin"
    p.write_text("aaa", encoding="utf-8")
    f1 = ec.file_fingerprint(str(p))
    p.write_text("bbb", encoding="utf-8")
    assert ec.file_fingerprint(str(p)) != f1
    assert f1.startswith("v1:full:")


def test_file_fingerprint_head_tail_detects_footer_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "FULL_HASH_MAX_BYTES", 8)   # 压小阈值走 头+尾 采样路径
    p = tmp_path / "big.parquet"
    p.write_bytes(b"HEAD" + b"x" * 100 + b"FOOT")
    f1 = ec.file_fingerprint(str(p))
    assert f1.startswith("v1:ht:")
    p.write_bytes(b"HEAD" + b"x" * 100 + b"F00T")       # 只改尾部（parquet footer 场景）
    assert ec.file_fingerprint(str(p)) != f1


def test_product_status_missing_input_is_stale(pbdir, tmp_path):
    raw = tmp_path / "raw.parquet"
    raw.write_text("v1", encoding="utf-8")
    fp = ec.file_fingerprint(str(raw))
    _seed_setup_product(tmp_path, {"inputs": {"predict": {"path": str(raw),
                                                          "fingerprint": fp}}})
    cfg = {"products": {"setup": {"workdir": "setup", "status": "built"}}}
    raw.unlink()                                  # 输入文件消失（redo 教训）
    s = ec.product_status(cfg, "setup")
    assert s["status"] == "stale" and s["stale_inputs"] == ["predict"]


def test_check_product_dsl(pbdir, tmp_path):
    fm = ec.load_frontmatter(str(pbdir / "cons-b" / "playbook.md"))
    ctx = {"cfg": {}, "fm": fm, "state": {}}
    assert not ec.check("product:setup", ctx)
    _seed_setup_product(tmp_path)
    ctx["cfg"] = {"products": {"setup": {"workdir": "setup", "status": "built"}}}
    assert ec.check("product:setup", ctx)
    with pytest.raises(ValueError, match="未知产物"):
        ec.check("product:no-such", ctx)
