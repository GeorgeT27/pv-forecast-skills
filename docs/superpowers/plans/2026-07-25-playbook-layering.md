# Playbook 分层（produces/upstream）实施计划 —— Phase 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 ts-diagnose 的两层 playbook 机制：`produces:`/`upstream:` frontmatter + orient 机器裁决 + 新 data-setup 必需前置 playbook + model-audit/fact-scan 升格生产者 + model-comparison 试点瘦身。

**Architecture:** 泛化现有 `contexts:` 机制——生产者 playbook 声明 `produces:`（产物 id + manifest + marker 文件），消费者声明 `upstream:`（required 缺→orient 打自动内联生产指令并阻塞开工；optional 缺→三分支问）。产物注册在消费者 `diagnose_config.json` 的 `products` 块；过期检测靠 manifest 里的输入文件指纹。全程向后兼容：无 `upstream:` 的 playbook 行为不变。

**Tech Stack:** Python 3.11 + pyyaml + pandas + pytest（既有栈，零新依赖）。

**Scope:** 本计划 = spec §8 迁移步骤 1–3。步骤 4（其余 6 个 playbook 批量改造）与步骤 5（contexts: 退役）在试点验证后另出 Phase 2 计划。

**Spec:** `docs/superpowers/specs/2026-07-25-playbook-layering-design.md`

## Global Constraints

- 引擎目录 = `ts-diagnose/`（仓库根相对）；所有命令在仓库根跑，pytest 命令为 `python3 -m pytest ts-diagnose/scripts/tests/ -q`。
- SKILL.md ≤60 行 / ~6000 token（test_layering 预算闸）；SKILL.md 禁出现方法词汇：`Stage`、`done_when`、`pause_after`、`evidence_lines`、`findings_marker`、`Spearman` 等（METHOD_VOCAB 全表见 test_layering.py）。
- golden 零随机：make_golden.py 禁 random/Date；期望值来自 reference 实跑留容差。
- 每个 task 结束时全部 pytest 必须绿（向后兼容纪律）；每个 task 一次 commit。
- playbook 正文八节结构见 `ts-diagnose/playbooks/_playbook-spec.md` §4；FINDINGS 状态只用保留字（现象/假设/已证实/被推翻）。
- 新增 DSL/校验的报错信息必须带"哪里错了 + 合法集/规范出处"（既有风格）。

---

### Task 1: Spec 文档 —— produces/upstream/product-DSL 写进 _playbook-spec.md

**Files:**
- Modify: `ts-diagnose/playbooks/_playbook-spec.md`

**Interfaces:**
- Produces: spec 文本契约，后续所有 task 的 YAML 键名/语义以此为准：`produces.{id,manifest,marker_files}`、`upstream[].{product,required}`、DSL `product:<id>`、config `products.<id>.{workdir,status,accept_stale}`，status 枚举 `built|linked|declined`（`absent` = 无记录）。

- [ ] **Step 1: 在 §1 Frontmatter schema 的 yaml 代码块中、`materials:` 块之前插入两个新块**

```yaml
produces:                         # 可选。声明本 playbook 是生产者（level-1）
  id: setup                       #   产物 id，引擎内唯一（products_index 加载期查重）
  manifest: setup_manifest.json   #   机器契约文件名（产物工作目录内）；含 inputs 指纹则启用过期检测
  marker_files: [predictions.csv] #   有效性核验：产物工作目录下这些文件必须存在
upstream:                         # 可选。声明本 playbook 消费的上游产物（level-2）
  - product: setup                #   引用某 playbook 的 produces.id（未声明的 id 加载期报错）
    required: true                #   true：缺 → orient 打「立即内联生产」指令并阻塞开工（不问用户）
  - product: model_profile        #   false：缺 → 三分支问（现跑 / 链接已有 / declined 并声明代价）
    required: false
```

- [ ] **Step 2: 在 §2 check-DSL 表格追加一行，并在表格下方追加 products 注册说明**

表格追加行：

```markdown
| `product:<id>` | 该产物已就绪：config.products 登记 status ∈ {built, linked} 且 marker_files 核验通过、无未确认过期（id 必须是某 playbook 的 produces.id，拼错报错） |
```

表格下方（"不追求图灵完备"段落之前）追加：

```markdown
产物注册在消费者 `diagnose_config.json` 的 `products` 块：
`products.<id> = {"workdir": "<产物目录>", "status": "built|linked|declined", "accept_stale": bool?}`
——`built` = 本会话内联生产；`linked` = 用户链接已有目录；`declined` = 用户放弃（仅 optional 允许，结论须声明）。
生产者在**产物 id 命名的子目录**跑（`./setup/`、`./model_profile/`……），有自己的 diagnose_config.json；
内联生产时把父 config 的 materials/questions 块拷入子 config（沿用已答，不重复问用户）。
过期检测：manifest 的 `inputs.{材料id: {path, fingerprint}}` 与当前材料文件指纹对账。
指纹（`engine_common.file_fingerprint`）：≤64MB 全量 sha256（权威）；更大用 大小+头 1MB+尾 1MB
sha256——尾部覆盖 parquet footer 的 EOF 元数据（imohash 模式；头部单独哈希不安全，无任何构建/数据
工具拿它当新鲜度权威）；指纹带算法版本前缀 `v1:`，未来换算法不至于全体产物 stale 或不可解析；
**输入文件消失同样算 stale**（redo 教训）。同尺寸且只改中段的超大文件改动检测不到——显式接受的
残余风险（要更强改 FULL_HASH_MAX_BYTES 走全量）。不一致 → status=stale，须用户确认重建或写
`accept_stale: true` 留痕。**代码也是依赖**（Snakemake 7.8 教训）：setup manifest 把适配器脚本
指纹一并记入 inputs——适配逻辑变了，产物即过期。
纪律：frontmatter 声明 = 意图，orient 解析出的状态 = 观测事实——agent 只写 config.products 的登记
字段（workdir/status/accept_stale），绝不手改判定结果。
上游产物拥有的问题（如 setup 的 freq/align-keys）**下游不得重复声明**（加载期查重报错）；
生产者自己也可声明 upstream（fact-scan 依赖 setup），加载期做环检测。
```

- [ ] **Step 3: 在 `contexts:` 的 schema 注释里加一行弃用说明**

在 §1 yaml 块 `contexts:` 行的注释后补：`# ⚠ 弃用中：新 playbook 一律用 upstream:；contexts 仅为迁移期兼容保留（Phase 2 退役）`

- [ ] **Step 4: Commit**

```bash
git add ts-diagnose/playbooks/_playbook-spec.md
git commit -m "docs(ts-diagnose): spec 增补 produces/upstream/product-DSL 契约——分层机制 Phase 1 起点

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: engine_common —— products_index + produces/upstream 加载期校验

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`
- Test: `ts-diagnose/scripts/tests/test_products.py`（新建）

**Interfaces:**
- Produces: `ec.products_index() -> {pid: {"playbook": str, "manifest": str, "marker_files": [str]}}`；`ec._raw_frontmatter(md_path) -> dict|None`；`ec.validate_upstream(fm, md_path)`（`load_frontmatter` 内部调用，外部一般不直呼）；`PLAYBOOKS_DIR` 支持环境变量 `TSD_PLAYBOOKS_DIR` 覆盖（供子进程测试沙箱）。
- Consumes: 既有 `load_frontmatter/_validate_frontmatter/find_playbook`。

- [ ] **Step 1: 写失败测试 —— 新建 `ts-diagnose/scripts/tests/test_products.py`**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -q`
Expected: FAIL / ERROR —— `AttributeError: module 'engine_common' has no attribute 'products_index'`。

- [ ] **Step 3: 实现 —— engine_common.py 修改**

3a. 第 24 行 `PLAYBOOKS_DIR` 改为支持环境变量覆盖：

```python
PLAYBOOKS_DIR = os.environ.get("TSD_PLAYBOOKS_DIR") \
    or os.path.join(ENGINE_DIR, "playbooks")
```

3b. 在 `load_frontmatter` 之前加原始读取器（防校验递归——索引扫描只做轻解析）：

```python
def _raw_frontmatter(md_path):
    """轻解析：只切 YAML，不做校验（products_index/validate_upstream 内部用，
    避免 load_frontmatter ↔ 全目录扫描的递归）。解析不动 → None。"""
    text = _read_text(md_path)
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    fm = yaml.safe_load(text[3:end])
    return fm if isinstance(fm, dict) else None
```

3c. 在 `find_playbook` 附近（`list_playbooks` 之后）加产物索引与 upstream 校验：

```python
# ---------------------------------------------------------------- products（分层）
def products_index():
    """全引擎 produces 声明扫描 → {产物id: {playbook, manifest, marker_files}}。
    产物 id 冲突（两个 playbook 声明同一 id）→ ValueError。"""
    out = {}
    for p in sorted(glob.glob(os.path.join(PLAYBOOKS_DIR, "*", "playbook.md"))):
        fm = _raw_frontmatter(p)
        if not fm or not fm.get("produces"):
            continue
        pr = fm["produces"]
        pid = pr.get("id")
        if pid in out:
            raise ValueError(f"产物 id '{pid}' 重复声明：{out[pid]['playbook']} 与 "
                             f"{fm.get('id')}（produces.id 引擎内唯一）")
        out[pid] = {"playbook": fm.get("id"), "manifest": pr.get("manifest"),
                    "marker_files": list(pr.get("marker_files") or [])}
    return out


def validate_upstream(fm, md_path):
    """upstream 声明的加载期校验：引用存在、不自引用、问题不与生产者重复、依赖不成环。"""
    idx = products_index()
    my_product = (fm.get("produces") or {}).get("id")
    qids_own = {q["id"] for q in fm.get("questions") or []}
    for u in fm.get("upstream") or []:
        if not isinstance(u, dict) or not u.get("product"):
            raise ValueError(f"{md_path} upstream 条目缺 product 键（_playbook-spec §upstream）")
        pid = u["product"]
        if pid not in idx:
            raise ValueError(f"{md_path} upstream 引用未声明的产物 '{pid}'"
                             f"（已声明：{sorted(idx)}）")
        if pid == my_product:
            raise ValueError(f"{md_path} 自引用：既 produces 又 upstream '{pid}'")
        prod_fm = _raw_frontmatter(find_playbook(idx[pid]["playbook"])) or {}
        dup = qids_own & {q["id"] for q in prod_fm.get("questions") or []}
        if dup:
            raise ValueError(f"{md_path} 重复声明了生产者 {idx[pid]['playbook']} "
                             f"拥有的问题 {sorted(dup)}——上游产物的问题只在生产者处问一次")
    _upstream_cycle_check(fm, idx, [fm.get("id")])


def _upstream_cycle_check(fm, idx, seen):
    for u in fm.get("upstream") or []:
        producer = idx[u["product"]]["playbook"]
        if producer in seen:
            raise ValueError(f"upstream 依赖成环：{' → '.join(seen + [producer])}")
        pfm = _raw_frontmatter(find_playbook(producer))
        if pfm:
            _upstream_cycle_check(pfm, idx, seen + [producer])
```

3d. `_validate_frontmatter` 末尾（contexts 校验循环之后）追加：

```python
    pr = fm.get("produces")
    if pr is not None:
        if not isinstance(pr, dict):
            raise ValueError(f"{md_path} produces 须为 dict（_playbook-spec §produces）")
        for key in ("id", "manifest", "marker_files"):
            if not pr.get(key):
                raise ValueError(f"{md_path} produces 缺 {key}（_playbook-spec §produces）")
        if not isinstance(pr["marker_files"], list):
            raise ValueError(f"{md_path} produces.marker_files 须为 list")
    ups = fm.get("upstream")
    if ups is not None:
        if not isinstance(ups, list):
            raise ValueError(f"{md_path} upstream 须为 list（_playbook-spec §upstream）")
        validate_upstream(fm, md_path)
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -q` → PASS（8 项）。
Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿（真实 playbook 都无 produces/upstream，行为不变）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): products_index + produces/upstream 加载期校验——环检测与问题去重

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: engine_common —— file_fingerprint + product_status + `product:` DSL

**Files:**
- Modify: `ts-diagnose/scripts/engine_common.py`
- Test: `ts-diagnose/scripts/tests/test_products.py`（追加）

**Interfaces:**
- Produces: `ec.file_fingerprint(path) -> "size:sha256前1MB"`；`ec.product_status(cfg, pid) -> {"status": "built|linked|declined|absent|invalid|stale", "workdir"?, "missing_markers"?, "stale_inputs"?}`；`ec.upstream_report(fm, cfg) -> [(entry, statusdict)]`；DSL `product:<id>`（built/linked 才为真）。
- Consumes: Task 2 的 `products_index`。

- [ ] **Step 1: 追加失败测试到 test_products.py**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -q`
Expected: 新 4 项 FAIL（`no attribute 'product_status'` / DSL "未知 DSL 表达式"）。

- [ ] **Step 3: 实现**

3a. engine_common.py 头部 import 区加 `import hashlib`。

3b. Task 2 的 products 节末尾追加：

```python
FULL_HASH_MAX_BYTES = 64 << 20   # ≤64MB 全量哈希（权威）；更大走 头+尾 采样（imohash 模式）
SAMPLE_BYTES = 1 << 20           # 采样块：头 1MB + 尾 1MB（尾部覆盖 parquet footer 的 EOF 元数据）
FINGERPRINT_ALGO = "v1"          # 算法版本前缀——未来换算法不至于全体产物 stale


def file_fingerprint(path):
    """产物过期检测用指纹。≤FULL_HASH_MAX_BYTES 全量 sha256；更大取 头+尾 各 1MB
    ——头部单独哈希对列式格式不安全（footer 在 EOF）。同尺寸只改中段的超大文件
    检测不到：显式接受的残余风险（spec §2）。"""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if size <= FULL_HASH_MAX_BYTES:
            for chunk in iter(lambda: f.read(SAMPLE_BYTES), b""):
                h.update(chunk)
            mode = "full"
        else:
            h.update(f.read(SAMPLE_BYTES))
            f.seek(max(size - SAMPLE_BYTES, 0))
            h.update(f.read(SAMPLE_BYTES))
            mode = "ht"
    return f"{FINGERPRINT_ALGO}:{mode}:{size}:{h.hexdigest()}"


def product_status(cfg, pid):
    """产物状态（真相以产物为准）：config.products 登记 + marker 核验 + 指纹对账。
    → {status: built|linked|declined|absent|invalid|stale, ...}"""
    idx = products_index()
    if pid not in idx:
        raise ValueError(f"未知产物 id '{pid}'（已声明：{sorted(idx)}）")
    rec = ((cfg or {}).get("products") or {}).get(pid) or {}
    status, workdir = rec.get("status"), rec.get("workdir") or ""
    if status == "declined":
        return {"status": "declined"}
    if status not in ("built", "linked") or not workdir:
        return {"status": "absent"}
    missing = [m for m in idx[pid]["marker_files"]
               if not os.path.exists(os.path.join(workdir, m))]
    manifest = read_json(os.path.join(workdir, idx[pid]["manifest"]))
    if missing or manifest is None:
        return {"status": "invalid", "workdir": workdir,
                "missing_markers": missing + ([idx[pid]["manifest"]]
                                              if manifest is None else [])}
    stale = []
    for mid, fp in (manifest.get("inputs") or {}).items():
        path = (fp or {}).get("path")
        if not path:
            continue
        if not os.path.exists(path):
            stale.append(mid)      # 输入文件消失也算过期（redo/apenwarr 教训）
        elif file_fingerprint(path) != fp.get("fingerprint"):
            stale.append(mid)
    if stale and not rec.get("accept_stale"):
        return {"status": "stale", "workdir": workdir, "stale_inputs": sorted(stale)}
    return {"status": status, "workdir": workdir, "missing_markers": [],
            "stale_inputs": sorted(stale)}


def upstream_report(fm, cfg):
    """orient 打印素材：[(upstream 条目, product_status 结果)]。"""
    return [(u, product_status(cfg, u["product"])) for u in fm.get("upstream") or []]
```

3c. `check()` 里 `material:` 分支之后、`raise ValueError` 之前加：

```python
    if expr.startswith("product:"):
        pid = expr[len("product:"):]
        return product_status(ctx["cfg"], pid)["status"] in ("built", "linked")
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -q` → PASS（14 项）。
Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/engine_common.py ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): product_status 六态 + 指纹过期检测 + product: DSL

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: orient —— 上游产物解析块（required 自动内联指令 / optional 三分支 / stale 警告）

**Files:**
- Modify: `ts-diagnose/scripts/orient.py`
- Modify: `ts-diagnose/scripts/tests/test_layering.py`（provider 豁免扩展）
- Test: `ts-diagnose/scripts/tests/test_products.py`（追加子进程测试）

**Interfaces:**
- Produces: orient 输出新增「上游产物」区块；required 未就绪进目标阶段前置 ✗ 清单并阻塞开工。文案锚点（测试断言用）：`⛔ 必需上游产物「` / `[✗] 必需上游产物未就绪` / `三分支` / `[stale]` / `accept_stale`。
- Consumes: Task 3 的 `upstream_report/products_index`。

- [ ] **Step 1: 追加失败的子进程测试到 test_products.py**

```python
# ------------------------------------------------------------ orient e2e
ORIENT = os.path.join(SCRIPTS_DIR, "orient.py")
FIVE_OK = {mid: {"status": "absent-confirmed", "source": "user"}
           for mid in ("training_log", "truth", "train_y", "checkpoint", "model_code")}

OPT_CONSUMER = CONSUMER.replace("id: cons-b", "id: cons-opt").replace(
    "required: true", "required: false")


def run_orient_env(cwd, pbroot, *args):
    env = dict(os.environ, TSD_PLAYBOOKS_DIR=str(pbroot))
    return subprocess.run([sys.executable, ORIENT, *args], cwd=cwd,
                          capture_output=True, text=True, timeout=60, env=env)


def _cfg(playbook, extra=None):
    cfg = {"playbook": playbook, "materials": dict(FIVE_OK)}
    cfg.update(extra or {})
    return cfg


def test_orient_required_upstream_missing_blocks(pbdir, tmp_path):
    (tmp_path / "diagnose_config.json").write_text(
        json.dumps(_cfg("cons-b")), encoding="utf-8")
    r = run_orient_env(tmp_path, pbdir)
    assert r.returncode == 0, r.stderr
    assert "⛔ 必需上游产物「setup」缺失" in r.stdout
    assert "prod-a" in r.stdout                      # 指令点名生产者 playbook
    assert "[✗] 必需上游产物未就绪：setup" in r.stdout
    assert "可开工" not in r.stdout


def test_orient_required_upstream_built_unblocks(pbdir, tmp_path):
    _seed_setup_product(tmp_path, {"inputs": {}, "models": ["A", "B"],
                                   "n_rows": 3, "freq": "1h"})
    (tmp_path / "diagnose_config.json").write_text(json.dumps(_cfg(
        "cons-b", {"products": {"setup": {"workdir": "setup", "status": "built"}}})),
        encoding="utf-8")
    r = run_orient_env(tmp_path, pbdir)
    assert "上游产物「setup」[built]" in r.stdout
    # CrewAI 教训：注入摘要而非指针——下游不再自行摸文件
    assert "manifest 摘要" in r.stdout and '"models": ["A", "B"]' in r.stdout
    assert "可开工 Stage 0" in r.stdout


def test_orient_optional_upstream_asks_three_branch(pbdir, tmp_path):
    _write_pb(pbdir, "cons-opt", OPT_CONSUMER)
    (tmp_path / "diagnose_config.json").write_text(
        json.dumps(_cfg("cons-opt")), encoding="utf-8")
    r = run_orient_env(tmp_path, pbdir)
    assert "三分支" in r.stdout and "declined" in r.stdout
    assert "⛔ 必需上游产物" not in r.stdout
    assert "可开工 Stage 0" in r.stdout               # optional 缺不阻塞


def test_orient_stale_upstream_warns_and_blocks(pbdir, tmp_path):
    raw = tmp_path / "raw.parquet"
    raw.write_text("v1", encoding="utf-8")
    fp = ec.file_fingerprint(str(raw))
    _seed_setup_product(tmp_path, {"inputs": {"predict": {"path": str(raw),
                                                          "fingerprint": fp}}})
    raw.write_text("v2", encoding="utf-8")
    (tmp_path / "diagnose_config.json").write_text(json.dumps(_cfg(
        "cons-b", {"products": {"setup": {"workdir": "setup", "status": "built"}}})),
        encoding="utf-8")
    r = run_orient_env(tmp_path, pbdir)
    assert "[stale]" in r.stdout and "accept_stale" in r.stdout
    assert "可开工" not in r.stdout
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -q`
Expected: 新 4 项 FAIL（orient 输出无上游区块）。

- [ ] **Step 3: 实现 —— orient.py 两处修改**

3a. orient.py 头部 import 区加 `import json`；然后在 contexts 循环（`for cx in fm.get("contexts") or []:`，约 188 行）**之前**插入上游产物区块：

```python
    ups = ec.upstream_report(fm, cfg)
    up_blocked = []
    idx = ec.products_index() if ups else {}
    for u, s in ups:
        pid, req = u["product"], bool(u.get("required"))
        prod_pb = idx[pid]["playbook"]
        print("-" * 62)
        if s["status"] in ("built", "linked"):
            note = (f" ⚠ 输入已变但用户确认沿用（accept_stale）：{s['stale_inputs']}"
                    if s.get("stale_inputs") else "")
            print(f"  上游产物「{pid}」[{s['status']}]: {s['workdir']}{note}")
            man = ec.read_json(os.path.join(s["workdir"], idx[pid]["manifest"])) or {}
            digest = {k: man[k] for k in ("tables", "models", "freq", "n_rows",
                                          "window_range") if k in man}
            if digest:
                print(f"    manifest 摘要：{json.dumps(digest, ensure_ascii=False)}"
                      "（下游直接用，不再自行摸文件）")
        elif s["status"] == "declined":
            print(f"  上游产物「{pid}」[declined]：用户已放弃——结论须声明缺此产物。")
        elif s["status"] == "stale":
            print(f"  ⚠ 上游产物「{pid}」[stale]：输入材料已变 {s['stale_inputs']}——"
                  f"AskUserQuestion 二选一：回 {prod_pb} 重建，或用户确认沿用后写 "
                  f"config.products.{pid}.accept_stale=true（结论须声明）。")
            up_blocked.append((u, s))
        elif s["status"] == "invalid":
            print(f"  ⚠ 上游产物「{pid}」[invalid]：登记了但核验失败"
                  f"（缺 {s.get('missing_markers')}）——修复或回 {prod_pb} 重建后再消费。")
            up_blocked.append((u, s))
        elif req:  # absent + required → 自动内联生产，不问用户
            print(f"  ⛔ 必需上游产物「{pid}」缺失——主 agent 立即内联生产（不问用户）：")
            print(f"     1. mkdir -p {pid}，把本 config 的 materials/questions 块拷入 "
                  f"{pid}/diagnose_config.json（沿用已答，不重复问）；")
            print(f"     2. 在 {pid}/ 内跑 orient --playbook {prod_pb} 并按其菜谱完成；")
            print(f"     3. 回本目录写 config.products.{pid}="
                  f"{{workdir:'{pid}',status:'built'}} 后重跑 orient。")
            up_blocked.append((u, s))
        else:      # absent + optional → 三分支问
            print(f"  ⚠ 上游产物「{pid}」[absent]（可选）：AskUserQuestion 三分支——"
                  f"现在内联生产（{prod_pb}）/ 链接已有目录（写 workdir+status=linked）/ "
                  f"放弃（status=declined，结论须声明缺此产物与代价）。")
```

3b. 目标阶段前置区（`mm = ec.modelmap_blocker(cfg, fm)` 打印之后）追加，并把开工判定条件扩一项：

```python
        for u, s in up_blocked:
            print(f"  [✗] 必需上游产物未就绪：{u['product']}（{s['status']}）")
```

开工判定行改为：

```python
        if ec.prereqs_ok(pr) and not blocked_qs and not mat_blocked and not mm \
                and not up_blocked:
```

（注意：`up_blocked` 在 3a 中定义于 contexts 循环前、目标阶段区之前，作用域可达；`ups` 为空时 `up_blocked=[]`，无 upstream 的 playbook 行为不变。）

3c. test_layering.py 的 `_declared_providers` 扩展——upstream 声明的生产者同样是合法跨引用（消费者正文可点名生产者）：

```python
def _declared_providers(playbook_path):
    """读取 playbook 的合法跨引用集合：contexts[].provider_playbook（迁移期）
    ∪ upstream[] 各产物的生产者 playbook（分层机制）。"""
    fm = ec.load_frontmatter(playbook_path)
    provs = {ctx["provider_playbook"] for ctx in (fm.get("contexts") or [])
             if isinstance(ctx, dict) and ctx.get("provider_playbook")}
    idx = ec.products_index()
    provs |= {idx[u["product"]]["playbook"] for u in (fm.get("upstream") or [])
              if isinstance(u, dict) and u.get("product") in idx}
    return frozenset(provs)
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py ts-diagnose/scripts/tests/test_layering.py -q` → PASS。
Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/orient.py ts-diagnose/scripts/tests/test_products.py \
        ts-diagnose/scripts/tests/test_layering.py
git commit -m "feat(ts-diagnose): orient 上游产物解析——required 自动内联指令/optional 三分支/stale 阻塞

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: manifest 落盘器 —— setup_manifest.py + product_manifest.py

**Files:**
- Create: `ts-diagnose/scripts/setup_manifest.py`
- Create: `ts-diagnose/scripts/product_manifest.py`
- Test: `ts-diagnose/scripts/tests/test_product_manifest.py`（新建）

**Interfaces:**
- Produces: CLI `python3 <ENGINE>/scripts/setup_manifest.py --pred predictions.csv --alignment alignment_report.json --config diagnose_config.json --out setup_manifest.json`（manifest 键：product/tables/models/freq/n_rows/window_range/materials/inputs）；CLI `python3 <ENGINE>/scripts/product_manifest.py --product <id> --out <file>`（键：product/inputs）。`inputs.{mid}={path,fingerprint}` 与 Task 3 的 `product_status` 过期检测约定一致。
- Consumes: `ec.file_fingerprint / ec.read_json / ec.dump_json`。

- [ ] **Step 1: 写失败测试 —— 新建 test_product_manifest.py**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_product_manifest.py -q`
Expected: FAIL —— 脚本文件不存在。

- [ ] **Step 3: 实现两个脚本**

`ts-diagnose/scripts/setup_manifest.py`：

```python
#!/usr/bin/env python3
"""setup 产物 manifest 落盘器（引擎机制脚本——pytest 单测覆盖，不走 gen_gate；
gen_gate 只闸运行时生成的分析脚本）。读规范长表 + 对齐报告 + config.materials，
写 setup_manifest.json：表/模型/freq/行数/窗口范围/完整材料清单（含训练日志与实验
配置的位置——下游 playbook 由此获知，不再各自问）/输入指纹（product_status 过期
检测的对账对象）。"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402


def _inputs_of(cfg):
    inputs = {}
    for mid, rec in ((cfg or {}).get("materials") or {}).items():
        if not isinstance(rec, dict) or rec.get("status") != "present":
            continue
        for p in rec.get("paths") or []:
            if os.path.exists(p):
                inputs.setdefault(mid, {"path": p,
                                        "fingerprint": ec.file_fingerprint(p)})
    return inputs


def build_manifest(pred_path, alignment_path, cfg):
    df = pd.read_csv(pred_path)
    align = ec.read_json(alignment_path) or {}
    tables = {"predictions": pred_path}
    for extra in ("features.csv", "train_y.csv"):
        if os.path.exists(extra):
            tables[extra.split(".")[0]] = extra
    inputs = _inputs_of(cfg)
    # 代码也是依赖（Snakemake 7.8 教训）：适配逻辑变了 → setup 产物即过期
    if os.path.exists("analysis_scripts/adapter.py"):
        inputs["_adapter_code"] = {
            "path": "analysis_scripts/adapter.py",
            "fingerprint": ec.file_fingerprint("analysis_scripts/adapter.py")}
    return {
        "product": "setup",
        "tables": tables,
        "models": sorted(df["model"].astype(str).unique().tolist()),
        "freq": align.get("freq"),
        "n_rows": int(len(df)),
        "window_range": [str(df["window_ts"].min()), str(df["window_ts"].max())],
        "materials": (cfg or {}).get("materials") or {},
        "inputs": inputs,
    }


def main():
    ap = argparse.ArgumentParser(description="setup 产物 manifest 落盘")
    ap.add_argument("--pred", default="predictions.csv")
    ap.add_argument("--alignment", default="alignment_report.json")
    ap.add_argument("--config", default=ec.CONFIG_PATH)
    ap.add_argument("--out", default="setup_manifest.json")
    a = ap.parse_args()
    man = build_manifest(a.pred, a.alignment, ec.read_json(a.config))
    ec.dump_json(man, a.out)
    print(f"setup_manifest → {a.out}：models={man['models']} "
          f"n_rows={man['n_rows']} freq={man['freq']} inputs={sorted(man['inputs'])}")


if __name__ == "__main__":
    main()
```

`ts-diagnose/scripts/product_manifest.py`：

```python
#!/usr/bin/env python3
"""通用产物 manifest 落盘器（setup 有专用 setup_manifest.py，域字段更全；
其余产物——chart_sweep 等——用本脚本）。只记产物 id + 来源材料指纹，
供 product_status 过期检测。引擎机制脚本，pytest 单测覆盖，不走 gen_gate。"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="通用产物 manifest 落盘")
    ap.add_argument("--product", required=True)
    ap.add_argument("--config", default=ec.CONFIG_PATH)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    inputs = {}
    for mid, rec in ((ec.read_json(a.config) or {}).get("materials") or {}).items():
        if isinstance(rec, dict) and rec.get("status") == "present":
            for p in rec.get("paths") or []:
                if os.path.exists(p):
                    inputs.setdefault(mid, {"path": p,
                                            "fingerprint": ec.file_fingerprint(p)})
    ec.dump_json({"product": a.product, "inputs": inputs}, a.out)
    print(f"{a.product} manifest → {a.out}（inputs={sorted(inputs)}）")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_product_manifest.py -q` → PASS（2 项）。
Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/scripts/setup_manifest.py ts-diagnose/scripts/product_manifest.py \
        ts-diagnose/scripts/tests/test_product_manifest.py
git commit -m "feat(ts-diagnose): setup/product manifest 落盘器——产物契约与指纹入档

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: data-setup playbook + golden + SKILL.md 路由

**Files:**
- Create: `ts-diagnose/playbooks/data-setup/playbook.md`
- Create: `ts-diagnose/playbooks/data-setup/golden/{make_golden.py,manifest.json,reference/stage0_adapter.py,wide.csv}`
- Modify: `ts-diagnose/SKILL.md`
- Modify: `ts-diagnose/scripts/tests/test_routing.py`

**Interfaces:**
- Produces: 产物 `setup`（manifest `setup_manifest.json`，markers `predictions.csv`+`alignment_report.json`）；问题 `freq`/`align-keys` 归 data-setup 所有（下游不得重声明）。
- Consumes: Task 5 的 setup_manifest.py CLI。

- [ ] **Step 1: 写 playbook 全文 —— `ts-diagnose/playbooks/data-setup/playbook.md`**

````markdown
---
id: data-setup
name: 数据就位（普适前置）
goal: 把用户原始预测/真值材料规范成长表并对齐，产 setup 产物供全部分析 playbook 复用
produces:
  id: setup
  manifest: setup_manifest.json
  marker_files: [predictions.csv, alignment_report.json]
stages:
  - id: 0
    name: 适配与对齐
    done_when:
      artifacts: [predictions.csv, alignment_report.json, adapter_report.json]
    prereqs:
      - desc: 步长已确认
        check: "question:freq"
      - desc: 对齐键已确认
        check: "question:align-keys"
  - id: 1
    name: 产物清单落盘
    done_when:
      artifacts: [setup_manifest.json]
    prereqs:
      - desc: 长表与对齐就绪
        check: "stage:0"
materials:
  required: [predict, truth]
  optional: [features, train_y, training_log, experiment_config]
questions:
  - id: freq
    stage: 0
    ask: "horizon 步长（freq）是多少？（如 15min / 1h——hour/tod 维度全靠它）"
    why: "freq 错则时段维度全错，污染全部下游图与结论"
    default: null
  - id: align-keys
    stage: 0
    ask: "各模型/各文件按什么键对齐？缺窗如何处理？（默认 window_ts+unit_id 内连接）"
    why: "对齐错位会把数据覆盖差异误判成模型差异"
    options: ["window_ts+unit_id 内连接（默认）", "其他"]
    default: "window_ts+unit_id 内连接"
---

# data-setup：数据就位（全部分析 playbook 的必需上游）

## 1. 问题框定与首要陷阱

本 playbook 只做一件事：用户的原始材料 → 规范长表 + 对齐报告 + setup 产物 manifest。
**不画图、不算指标、不下任何结论**——那些是下游 playbook 的活。首要陷阱：适配器
顺手"清洗"数据（去重/填缺/截断）——薄适配器只做重排不做清洗，任何数据问题如实
进 alignment_report 的 note，让下游看得见。第二陷阱：多模型缺窗不对称时静默取
交集不留痕——dropped 统计必须逐模型入报告，否则下游把覆盖差异当模型差异。

## 2. 逐阶段菜谱

### Stage 0 适配与对齐
输入：materials 盘点后的 predict/truth 原始数据（有 features/train_y 材料时一并处理）。
菜谱：现场写薄适配器 `analysis_scripts/adapter.py`（用户格式 → 规范长表
predictions.csv，列：window_ts/unit_id/model/horizon_step/y_true/y_pred，见
chartbook/_recipe-spec.md §2；features/train_y 同步产 features.csv / train_y.csv），
CLI 契约固定：
`--in <用户文件> --n-steps <N> --freq <freq答案> --out predictions.csv --alignment alignment_report.json --report adapter_report.json`。
过**对账两关**（行数守恒 + 抽 3 窗数值核对，样例 chartbook/golden/example_adapter/），
按 align-keys 答案对齐各模型，落 `alignment_report.json`（schema：`{"models":[...],
"n_rows_per_model":{}, "n_aligned":int, "n_dropped_per_model":{}, "freq":str,
"note":"dropped 不对称时的说明"}`）与 `adapter_report.json`（`{"rows_wide":int,
"rows_long":int, "spot_checks":[...], "ok":bool}`）。
**生成闸（硬规则）**：真实数据前先过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/adapter.py --playbook data-setup --stage 0`。
验证步：gen_gate 金标准（golden/ 植入不对称覆盖难例）全 expect 通过，对账记录写 PROGRESS.md。
done：三个产物落盘。

### Stage 1 产物清单落盘
菜谱：跑引擎机制脚本（预写，禁现场重写）：
`python3 <ENGINE>/scripts/setup_manifest.py --pred predictions.csv --alignment alignment_report.json --out setup_manifest.json`。
manifest 记录表路径/模型清单/freq/行数/窗口范围/**完整材料清单（含 training_log 与
experiment_config 的位置与格式——下游训练类 playbook 由此获知日志在哪，不再另问）**/
输入文件指纹（过期检测）/适配器脚本指纹（代码也是依赖——适配逻辑变了 setup 即过期）。
done：setup_manifest.json 落盘。随后主 agent 回父工作目录写
`config.products.setup = {workdir, status: "built"}`。

## 3. 证据升级规则

无。本 playbook 不产结论——产物即全部输出（这是它与诊断类 playbook 的边界）。

## 4. 停顿点与汇报

无 pause_after 阶段。产物就绪后一句话汇报：模型清单/行数/窗口范围/dropped 是否
对称/哪些可选材料缺席，然后把控制权还给发起的下游 playbook（或用户）。

## 5. subagent 拆分建议

不拆。两个阶段都轻且串行（适配器要过闸、manifest 要读适配产物）。

## 6. 结论模板与反驳门

不适用（无结论阶段）。唯一自查：adapter_report.ok=false 或对账任一关不过 →
不许落 predictions.csv，回头修适配器。

## 7. 材料降级说明

- predict / truth 缺（absent-confirmed）：本 playbook 不可做——没有降级路径，
  全部依赖 setup 的下游 playbook 同样不可做，向用户说明后终止；
- features / train_y 缺：对应长表不产，manifest.tables 里没有该键，下游按各自
  材料降级规则跳过相关图；
- training_log / experiment_config 缺：不影响本 playbook 主线，manifest.materials
  如实记 absent，下游训练类 playbook 自行按缺席处理。

## 8. chartbook 覆盖声明

本 playbook 不声明任何 charts（产数据产物，不画图）：全部 28 个 recipe 跳过，
理由统一为「结构性不适用——本 playbook 无分析阶段，图属于下游消费者」。下游
playbook 各自声明目标核心图；大而全体检走 fact-scan（chart_sweep 产物）。
````

- [ ] **Step 2: 写 golden —— 四个文件**

`ts-diagnose/playbooks/data-setup/golden/make_golden.py`：

```python
#!/usr/bin/env python3
"""data-setup 金标准：确定性宽表（零随机）。难例植入：B 缺第 3 窗（不对称覆盖）
——对齐后 n_aligned=2、dropped 不对称，适配器必须如实入报告而非静默取交集。"""
import pandas as pd


def main():
    rows = []
    for m, bias, n_win in (("A", 0.0, 3), ("B", 0.5, 2)):
        for w in range(n_win):
            row = {"ts": f"2024-01-0{w + 1}T00:00:00", "station": "S1", "model": m}
            for s in range(4):
                row[f"y_{s}"] = float(w + s)
                row[f"p_{s}"] = float(w + s) + bias
            rows.append(row)
    pd.DataFrame(rows).to_csv("wide.csv", index=False)


if __name__ == "__main__":
    main()
```

在 golden/ 目录下跑 `python3 make_golden.py` 生成 `wide.csv`（提交进仓库）。

`ts-diagnose/playbooks/data-setup/golden/reference/stage0_adapter.py`：

```python
#!/usr/bin/env python3
"""data-setup Stage 0 参考实现：薄适配器 + 对账两关 + 对齐报告。
CLI 契约 = playbook 菜谱声明；现场 adapter.py 照此契约写，gen_gate 用金标准闸它。"""
import argparse
import json

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--n-steps", type=int, required=True)
    ap.add_argument("--freq", required=True)
    ap.add_argument("--out", default="predictions.csv")
    ap.add_argument("--alignment", default="alignment_report.json")
    ap.add_argument("--report", default="adapter_report.json")
    a = ap.parse_args()
    wide = pd.read_csv(a.inp)
    rows = []
    for r in wide.itertuples():
        for s in range(a.n_steps):
            rows.append({"window_ts": r.ts, "unit_id": r.station, "model": r.model,
                         "horizon_step": s, "y_true": getattr(r, f"y_{s}"),
                         "y_pred": getattr(r, f"p_{s}")})
    long = pd.DataFrame(rows)
    assert len(long) == len(wide) * a.n_steps, "对账关1：行数守恒破产"
    spot = []
    for r in wide.head(3).itertuples():
        sub = long[(long.window_ts == r.ts) & (long.model == r.model)]
        for s in range(a.n_steps):
            assert sub[sub.horizon_step == s].iloc[0]["y_pred"] == \
                getattr(r, f"p_{s}"), "对账关2：抽查数值不符"
        spot.append({"ts": str(r.ts), "model": str(r.model), "ok": True})
    long.to_csv(a.out, index=False)
    models = sorted(long.model.astype(str).unique())
    per_model = {m: set(long[long.model == m].window_ts) for m in models}
    aligned = set.intersection(*per_model.values()) if models else set()
    with open(a.alignment, "w", encoding="utf-8") as f:
        json.dump({"models": models,
                   "n_rows_per_model": {m: len(v) for m, v in per_model.items()},
                   "n_aligned": len(aligned),
                   "n_dropped_per_model": {m: len(v) - len(aligned)
                                           for m, v in per_model.items()},
                   "freq": a.freq,
                   "note": "dropped 不对称时下游只在对齐子集上比较"},
                  f, ensure_ascii=False, indent=2)
    with open(a.report, "w", encoding="utf-8") as f:
        json.dump({"rows_wide": len(wide), "rows_long": len(long),
                   "spot_checks": spot, "ok": True}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

`ts-diagnose/playbooks/data-setup/golden/manifest.json`：

```json
{
  "playbook": "data-setup",
  "note": "适配器金标准：B 缺第 3 窗（不对称覆盖难例）——n_aligned=2 且 dropped 不对称必须如实入对齐报告，静默取交集会被 n_dropped 断言抓住。Stage 1 的 setup_manifest.py 是引擎机制脚本，pytest（test_product_manifest.py）单测覆盖，不进 gen_gate——gen_gate 只闸运行时生成脚本。改期望先改 make_golden.py 并重跑 pytest。",
  "planted": {"n_aligned": 2, "b_missing_windows": 1, "rows_long": 20},
  "stages": {
    "0": {
      "desc": "宽转长 + 对账两关 + 不对称覆盖如实入对齐报告",
      "inputs": ["wide.csv"],
      "args": ["--in", "wide.csv", "--n-steps", "4", "--freq", "1h",
               "--out", "predictions.csv", "--alignment", "alignment_report.json",
               "--report", "adapter_report.json"],
      "expect": [
        {"file": "adapter_report.json", "path": "rows_long", "op": "eq", "value": 20},
        {"file": "adapter_report.json", "path": "ok", "op": "eq", "value": true},
        {"file": "alignment_report.json", "path": "n_aligned", "op": "eq", "value": 2},
        {"file": "alignment_report.json", "path": "models", "op": "contains", "value": "B"},
        {"file": "alignment_report.json", "path": "n_dropped_per_model.A", "op": "eq", "value": 1},
        {"file": "alignment_report.json", "path": "n_dropped_per_model.B", "op": "eq", "value": 0}
      ],
      "reference": "reference/stage0_adapter.py"
    }
  }
}
```

- [ ] **Step 3: SKILL.md 更新（守住 60 行/词汇预算）**

3a. frontmatter description：`含 9 个可插拔 playbook` → `含 10 个可插拔 playbook`；在 `"评估预测结果/算指标/月度或时段归因"（result-eval）、` 之后插入 `"把原始预测/真值先规范成长表与对齐报告（各分析目标的必需前置，通常由引擎自动先跑）"（data-setup）、`。

3b. 路由表末尾（subset-influence 行之后）加一行：

```markdown
| 只想先把原始数据规范成长表/对齐报告（其他目标的必需前置，一般自动先跑） | `data-setup` |
```

3c. 正文第 14 行 `其余诊断与评估目标一律由下方 9 个 playbook 覆盖` → `其余诊断与评估目标一律由下方 10 个 playbook 覆盖`。

- [ ] **Step 4: test_routing.py 更新**

`ALL_PLAYBOOK_IDS` 元组追加 `"data-setup"`；函数 `test_engine_description_enumerates_all_nine_playbooks` 更名 `test_engine_description_enumerates_all_playbooks`，其 docstring 改为 `"""单入口化后 description 必须正面枚举全部 playbook id（Phase1 起含 data-setup 共 10 个）。"""`。

- [ ] **Step 5: 跑金标准闸自检 + 全量回归**

Run（在 golden/ 临时验证 reference 自洽，test_gen_gate 也会动态收集）:
`python3 -m pytest ts-diagnose/scripts/tests/test_gen_gate.py ts-diagnose/scripts/tests/test_routing.py ts-diagnose/scripts/tests/test_layering.py -q` → PASS（data-setup 进 test_every_playbook_has_golden 与动态过闸收集）。
Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/playbooks/data-setup/ ts-diagnose/SKILL.md \
        ts-diagnose/scripts/tests/test_routing.py
git commit -m "feat(ts-diagnose): data-setup 前置 playbook——setup 产物+金标准+路由，问题 freq/align-keys 归一

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: model-audit 升格生产者（produces: model_profile）+ modelmap_blocker 接产物

**Files:**
- Modify: `ts-diagnose/playbooks/model-audit/playbook.md`（仅 frontmatter + 正文一句）
- Modify: `ts-diagnose/scripts/engine_common.py`（modelmap_blocker）
- Test: `ts-diagnose/scripts/tests/test_products.py`（追加）

**Interfaces:**
- Produces: 产物 `model_profile`（manifest `MODELMAP_RECEIPT.json`，marker `MODELMAP_RECEIPT.json`）。注意：receipt 无 `inputs` 键 → 过期检测自然空转（可接受，正文注明）。
- Consumes: Task 3 `product_status`。

- [ ] **Step 1: 追加失败测试**

```python
# ------------------------------------------------------------ modelmap 接产物
def test_modelmap_blocker_accepts_product(pbdir, tmp_path, monkeypatch):
    # 在沙箱里造一个 model_profile 生产者声明，让 product_status 可解析
    _write_pb(pbdir, "audit-x",
              PRODUCER.replace("id: prod-a", "id: audit-x")
              .replace("id: setup", "id: model_profile")
              .replace("manifest: setup_manifest.json",
                       "manifest: MODELMAP_RECEIPT.json")
              .replace("marker_files: [predictions.csv]",
                       "marker_files: [MODELMAP_RECEIPT.json]")
              .replace("id: freq", "id: audit-q"))
    fm = {"id": "cons-b"}
    cfg = {"materials": {"model_code": {"status": "present", "paths": ["m/"]}}}
    assert ec.modelmap_blocker(cfg, fm)          # 无 receipt、无产物 → 阻塞
    d = tmp_path / "model_profile"
    d.mkdir()
    (d / "MODELMAP_RECEIPT.json").write_text("{}", encoding="utf-8")
    cfg["products"] = {"model_profile": {"workdir": "model_profile",
                                         "status": "built"}}
    assert ec.modelmap_blocker(cfg, fm) is None  # 产物 built → 放行
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest ts-diagnose/scripts/tests/test_products.py -q`
Expected: 新 1 项 FAIL（blocker 不认产物仍阻塞）。

- [ ] **Step 3: 实现**

3a. `engine_common.modelmap_blocker` 在 `if os.path.exists("MODELMAP_RECEIPT.json"): return None` 之后加：

```python
    try:
        if product_status(cfg, "model_profile")["status"] in ("built", "linked"):
            return None
    except ValueError:
        pass  # model_profile 产物未声明（model-audit 未升格的部署形态）——退回 receipt 判定
```

3b. `playbooks/model-audit/playbook.md` frontmatter 在 `goal:` 行后加：

```yaml
produces:
  id: model_profile
  manifest: MODELMAP_RECEIPT.json
  marker_files: [MODELMAP_RECEIPT.json]
```

3c. 正文开头产物说明段（"产物固定位置"那段）追加一句：
`作为分层机制的生产者，本 playbook 的产物注册名为 model_profile（manifest = 工作目录回执 MODELMAP_RECEIPT.json；回执不含 inputs 指纹，产物过期检测对它空转——代码变更后的重审计时机由用户判断）。`

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿（model-audit 无 upstream，其余 playbook 不受影响；products_index 现含 setup 与 model_profile 两条）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/model-audit/playbook.md ts-diagnose/scripts/engine_common.py \
        ts-diagnose/scripts/tests/test_products.py
git commit -m "feat(ts-diagnose): model-audit 升格生产者 produces:model_profile——modelmap 闸接产物注册

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: fact-scan 改造 —— 消费 setup、产 chart_sweep

**Files:**
- Modify: `ts-diagnose/playbooks/fact-scan/playbook.md`（frontmatter 全换 + 正文改）
- Modify: `ts-diagnose/playbooks/fact-scan/golden/manifest.json`（stage 键 "1"→"0"）

**Interfaces:**
- Produces: 产物 `chart_sweep`（manifest `chart_sweep_manifest.json`，markers `INDEX.md`+`FINDINGS.md`）。
- Consumes: 产物 `setup`（required）；Task 5 `product_manifest.py`。

- [ ] **Step 1: frontmatter 整体替换为**

```yaml
---
id: fact-scan
name: 图谱体检（只看现象不下结论）
goal: 把手头材料能画的标准分析图一次画全，产出现象清单与 chart_sweep 产物——终点即停顿，不进任何归因
produces:
  id: chart_sweep
  manifest: chart_sweep_manifest.json
  marker_files: [INDEX.md, FINDINGS.md]
upstream:
  - product: setup
    required: true
stages:
  - id: 0
    name: 画图与现象清单（终点）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md", "chart_sweep_manifest.json"]
      findings_marker: "现象"
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
    pause_after: true
    charts: [error-breakdown, intraday-profile, worst-points,
             horizon-degradation, rolling-stability, true-vs-pred-scatter,
             model-error-correlation, worst-slice-compare, oracle-gap,
             feature-error-conditional, feature-trend-overlay,
             y-vs-feature-mapping, train-test-drift]
materials:
  required: [predict, truth]
  optional: [features, train_y]
---
```

（删除原 Stage 0「口径与对齐」与 questions 块——freq 归 data-setup 所有；单/多模型不再问，
从 setup manifest 的 models 读。）

- [ ] **Step 2: 正文对应修改**

- §2 删掉「Stage 0 口径与对齐」小节；「Stage 1」标题改「Stage 0 画图与现象清单（终点）」，开头加一句：`输入：setup 产物（config.products.setup.workdir 下的 predictions.csv 等长表与 setup_manifest.json——模型数、freq 从 manifest 读，不再问用户）。图命令的 --pred 一律指向 <setup_workdir>/predictions.csv。`
- 同小节 done 行前加：`画完建索引后跑 python3 <ENGINE>/scripts/product_manifest.py --product chart_sweep --out chart_sweep_manifest.json，随后主 agent 写 config.products.chart_sweep = {workdir: ".", status: "built"}（本 playbook 直接在自己的工作目录产出，产物即工作目录）。`
- §1 末尾追加一句：`本 playbook 的图产物（charts/*.json + INDEX.md + 现象清单）就是 chart_sweep 产物——下游 playbook 声明它为可选上游时，重叠图直接复用判读、不重画。`
- §7 材料降级说明保持，首句改为 `predict/truth 缺 → setup 产物本身不可建，本 playbook 连带不可做；`。

- [ ] **Step 3: golden manifest stage 键改名**

`playbooks/fact-scan/golden/manifest.json` 的 `"stages"` 键 `"1"` 改 `"0"`（纯查找键改名，
expect/args/reference 全部不动，desc 不变）。

- [ ] **Step 4: 全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。
特别看：test_gen_gate（fact-scan golden 键改名后动态收集仍过）、test_layering
（fact-scan 若正文提及 data-setup——本 task 未提及，upstream 豁免也已在 Task 4 就位）。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/playbooks/fact-scan/
git commit -m "feat(ts-diagnose): fact-scan 分层改造——消费 setup、产 chart_sweep，口径问题归 data-setup

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: model-comparison 试点瘦身 —— upstream 依赖 + 图 14→5 + 阶段 5→4

**Files:**
- Modify: `ts-diagnose/playbooks/model-comparison/playbook.md`
- Modify: `ts-diagnose/playbooks/model-comparison/golden/manifest.json`（stage 键平移）

**Interfaces:**
- Consumes: 产物 `setup`（required）、`model_profile`（optional）。
- Produces: 无新产物；阶段号映射 旧→新：1→0（总差距）、2→1（分解）、3→2（机制变体）、4→3（结论）；golden stage 键 `"1"→"0"`、`"2"→"1"`、`"2-crossdim"→"1-crossdim"`。

- [ ] **Step 1: frontmatter 整体替换为**

```yaml
---
id: model-comparison
name: 多模型对比归因
goal: 量化「模型 A 为什么比 B 好/差」，把差距分解到片段/时效/输入并归因到机制
upstream:
  - product: setup
    required: true
  - product: model_profile
    required: false
stages:
  - id: 0
    name: 总差距事实
    done_when:
      artifacts: ["gap_summary.json"]
    prereqs:
      - desc: setup 产物就绪
        check: "product:setup"
      - desc: 考核口径已定
        check: "question:metric-caliber"
      - desc: 对比模型集已定
        check: "question:model-set"
  - id: 1
    name: 差距分解（事实）
    done_when:
      artifacts: ["charts/*.json", "INDEX.md"]
      findings_marker: "现象"
    prereqs:
      - desc: 总差距已知
        check: "stage:0"
    pause_after: true
    charts: [worst-slice-compare, model-error-correlation, oracle-gap,
             horizon-degradation, cross-dim-stability]
  - id: 2
    name: 机制归因（变体）
    done_when:
      findings_marker: "假设"
    prereqs:
      - desc: 模型档案产物已解决（built/linked 或 declined）
        check: "config:products.model_profile.status"
  - id: 3
    name: 结论
    done_when:
      artifacts: ["CONCLUSION.md", "gate_reports/conclusion_gate.json"]
    subagent_ok: false
    prereqs:
      - desc: 现象清单已停顿汇报
        check: "stage:1"
materials:
  required: [predict, truth]
  optional: [model_code, training_log, experiment_config, features, train_y]
variants:
  - id: mechanism
    when: "material:model_code"
    unlocks_stages: [2]
questions:
  - id: metric-caliber
    stage: 0
    ask: "考核口径是什么？（默认 rmse_192=每行全部 horizon 点的 RMSE；也可指定子段或自定义）"
    why: "口径不同结论可反转——horizon 交叉存在时尤甚"
    options: ["rmse_192（默认）", "指定 horizon 子段", "自定义公式"]
    default: "rmse_192"
  - id: model-set
    stage: 0
    ask: "这次对比哪些模型？多于 2 个时，最关注哪一对（如 A vs B）？"
    why: "全集对比与定向配对的分解深度不同；配对决定 Stage 0 的差距检验对象"
    default: null
evidence_lines:
  - id: total-gap
    stage: 0
    output: gap_summary.json
  - id: slice-gap
    stage: 1
    output: charts/worst-slice-compare.json
  - id: cross-dim
    stage: 1
    output: charts/cross-dim-stability.json
upgrade_rule: "总差距方向与主导切片方向一致（slice-gap 仅在 worst-slice perm.verdict=significant 时计入）且 cross-dim time_split 两半同向，才把差距结论从「现象」升「假设」"
---
```

（相对旧版的删除项：旧 Stage 0「口径与对齐」整段、`align-keys` 问题、`contexts:` 块——
model_profile 走 upstream；`metric-caliber` 的对齐部分由 setup 产物承接。）

- [ ] **Step 2: 正文 §2 逐阶段菜谱替换为**

````markdown
## 2. 逐阶段菜谱

（长表与对齐由 setup 产物提供：`<setup>` = config.products.setup.workdir，
alignment_report.json 与各长表都在其中；本 playbook 不再写适配器。）

### Stage 0 总差距事实
输入：`<setup>/predictions.csv` + `<setup>/alignment_report.json`（先读 dropped
统计——不对称时后续结论必须声明对齐子集）。
菜谱：写 `analysis_scripts/gap_metrics.py`，CLI 契约固定：
`--pred <setup>/predictions.csv --pair A,B --out gap_summary.json`。
计算（口径=rmse_192 时）：每 (model,unit,window) 行 RMSE → 每模型均值与排名；
配对差 d_i = rmse_focal_i − rmse_other_i（对齐行内逐样本）→ mean_diff、
win_rate（d<0 占比）、符号检验正态近似 z=(wins−n/2)/sqrt(n/4) 与双侧 p。
落 `gap_summary.json`（schema：`{"caliber":str, "per_model":{m:mean},
"ranking":[...], "pair":[A,B], "n":int, "mean_diff":float, "win_rate":float,
"sign_z":float, "sign_p":float, "note":"差距是真的还是噪声：|z|<2 时只写现象
不写方向"}`）。
**生成闸（硬规则）**：真实数据前先过
`python3 <ENGINE>/scripts/gen_gate.py --script analysis_scripts/gap_metrics.py \
  --playbook model-comparison --stage 0`。
验证步：gen_gate 金标准（golden/ 植入已知差距结构）全 expect 通过。
done：gap_summary.json 落盘。

### Stage 1 差距分解（事实）
**不写图代码**——frontmatter charts 声明的 5 张对比核心图全部用 chartbook 预写
脚本（engine-core chartbook 豁免），orient 已按材料标好可画/跳过；命令模板：

    python3 <ENGINE>/chartbook/scripts/chart_<蛇形id>.py \
      --pred <setup>/predictions.csv --out-dir charts/ [各图特有参数]

（worst-slice-compare 与 cross-dim-stability 传 `--focal-model` = model-set
答案里的关注模型；worst-slice 置换基线默认开——`--n-perm 200 --perm-seed 0`，
改种子=改期望须连 golden 一起改。）
广谱图（error-breakdown/intraday-profile 等）不在默认集：已有 chart_sweep 产物
（fact-scan 跑过）→ 直接复用其图 JSON 判读；没有 → 需要时经图表选择门从可加画
池加画，或先跑 fact-scan。
判读读各图 JSON 的描述符（recipe 判读节），产出 FINDINGS.md 现象清单——只写
「现象」；因缺材料跳过的图逐条注明「因缺 <材料> 未画」。
done：charts/*.json 至少一个 + INDEX.md + FINDINGS.md 含「现象」→ **pause_after 停顿**。

### Stage 2 机制归因（变体，material:model_code 解锁）
输入：model_profile 产物（upstream 机制：built/linked 的工作目录下 models.md 的
桥接假设 H-ID；declined → 本阶段虽解锁也只能停在现象，结论声明缺档案）+
Stage 1 图 JSON。
菜谱：逐条桥接假设 → 找它预言的图形态（bridge_hooks）→ 对照实际描述符；
升级按 §3 三条腿判定。产出写回 FINDINGS.md（状态用保留字）。
done：FINDINGS.md 出现「假设」。

### Stage 3 结论
主 agent 亲自做（subagent_ok: false）。三道门（references/mechanisms.md）+
本 playbook 反驳门（§6）逐条过 → 跑 `scripts/provenance.py` 归因闸 → 写
CONCLUSION.md（末尾附 Provenance 块）→ 跑 conclusion_gate.py 拿 receipt。
````

- [ ] **Step 3: 正文其余节点状修改**

- §1 问题框定：第二句「（口径换了可反转……先回 Stage 0 确认口径再比）」中
  「必须先回 Stage 0」保留（新 Stage 0 就是口径所在）；「②在**对齐样本**上好
  （缺窗不对称时……先看 alignment_report 的 dropped 统计）」改为
  「先看 `<setup>/alignment_report.json` 的 dropped 统计」；「Stage 1/2 全部是
  事实阶段」改「Stage 0/1 全部是事实阶段」；「机制只能在 Stage 3」改「Stage 2」。
- §3 证据升级规则：数字不变，仅「cross-dim」证据线所在阶段口径改（文内无阶段号则不动）。
- §4 停顿点：「Stage 2 完成即停」改「Stage 1 完成即停」。
- §5 subagent：「Stage 2 各图独立可并发」改「Stage 1 各图独立可并发」；
  「Stage 0/1/4 不拆」改「Stage 0/3 不拆」。
- §7 材料降级：predict/truth 条改为「predict / truth 缺：setup 产物不可建，本
  playbook 连带不可做——向用户说明后终止」；model_code 条的「Stage 3 锁死」改
  「Stage 2 锁死」。
- 正文末尾新增 §8：

```markdown
## 8. chartbook 覆盖声明

已声明（frontmatter Stage 1，对比核心 5 张）：worst-slice-compare /
model-error-correlation / oracle-gap / horizon-degradation / cross-dim-stability。
跳过（默认不画，可经图表选择门加画或复用 chart_sweep 产物；逐条理由）：
error-breakdown、intraday-profile、worst-points、rolling-stability、
true-vs-pred-scatter——单模型广谱体检图，对比结论非必需，chart_sweep 覆盖；
feature-error-conditional、feature-trend-overlay、y-vs-feature-mapping、
feature-regime-error——输入侧关联图，需 features 材料，对比主线可选加画；
train-test-drift、lookback-decay——需 train_y／训练侧材料，属训练类目标默认集；
bad-window-clustering、good-bad-contrast、error-acf、horizon-error-quantiles、
theil-decomposition、time-shift-diagnosis、pp-calibration、baseline-skill、
revision-stability——误差结构细察图，深挖阶段按需加画；
model-rank-significance——与 Stage 0 sign_z 判定重叠，需要更细排名显著性时加画；
global-attribution、local-waterfall——归因组图，需 serving_api 反事实通道，
本目标默认不开；
worst-slice-compare 等 5 张已声明图不重复列出。
```

- [ ] **Step 4: golden manifest stage 键平移**

`playbooks/model-comparison/golden/manifest.json`：`"stages"` 下键 `"1"` 改 `"0"`、
`"2"` 改 `"1"`、`"2-crossdim"` 改 `"1-crossdim"`；note 里「伪 stage 键 2-crossdim」
改「伪 stage 键 1-crossdim」。expect/args/reference（reference/stage1_gap.py 等
文件名照旧）全部不动。

- [ ] **Step 5: 全量回归 + 试点端到端冒烟**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。
冒烟（临时目录，不入库）：

```bash
cd "$(mktemp -d)" && cat > diagnose_config.json <<'EOF'
{"playbook": "model-comparison",
 "materials": {"predict": {"status": "present", "paths": ["p.parquet"],
                            "schema": {"y_col": "y", "time_col": "ts"}},
               "truth": {"status": "present", "paths": ["t.parquet"],
                          "schema": {"y_col": "y", "time_col": "ts"}},
               "training_log": {"status": "absent-confirmed", "source": "user"},
               "train_y": {"status": "absent-confirmed", "source": "user"},
               "checkpoint": {"status": "absent-confirmed", "source": "user"},
               "model_code": {"status": "absent-confirmed", "source": "user"}}}
EOF
python3 <仓库根>/ts-diagnose/scripts/orient.py
```

Expected 输出包含：`⛔ 必需上游产物「setup」缺失`、`orient --playbook data-setup`、
`上游产物「model_profile」[absent]（可选）`、`[✗] 必需上游产物未就绪：setup`，
且无 `可开工`。

- [ ] **Step 6: Commit**

```bash
git add ts-diagnose/playbooks/model-comparison/
git commit -m "feat(ts-diagnose): model-comparison 试点瘦身——upstream 依赖 setup/model_profile，图 14→5，阶段 5→4

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: 收尾 —— CHANGELOG + 端到端产物链冒烟 + Phase 2 交接清单

**Files:**
- Modify: `ts-diagnose/CHANGELOG.md`（追加条目）
- Create: `docs/superpowers/plans/2026-07-25-playbook-layering-phase2-TODO.md`

**Interfaces:**
- Produces: Phase 2 待办清单（批量改造 + contexts 退役的输入）。

- [ ] **Step 1: 端到端产物链冒烟（golden 数据全程走一遍，临时目录）**

```bash
T=$(mktemp -d) && cd "$T" && mkdir setup && cd setup
cp <仓库根>/ts-diagnose/playbooks/data-setup/golden/wide.csv .
python3 <仓库根>/ts-diagnose/playbooks/data-setup/golden/reference/stage0_adapter.py \
  --in wide.csv --n-steps 4 --freq 1h
cat > diagnose_config.json <<'EOF'
{"playbook": "data-setup", "materials": {"predict": {"status": "present",
 "paths": ["wide.csv"], "schema": {"y_col": "y", "time_col": "ts"}}}}
EOF
python3 <仓库根>/ts-diagnose/scripts/setup_manifest.py
cd "$T" && cat > diagnose_config.json <<'EOF'
{"playbook": "model-comparison",
 "products": {"setup": {"workdir": "setup", "status": "built"}},
 "materials": {"predict": {"status": "present", "paths": ["setup/wide.csv"],
                            "schema": {"y_col": "y", "time_col": "ts"}},
               "truth": {"status": "present", "paths": ["setup/wide.csv"],
                          "schema": {"y_col": "y", "time_col": "ts"}},
               "training_log": {"status": "absent-confirmed", "source": "user"},
               "train_y": {"status": "absent-confirmed", "source": "user"},
               "checkpoint": {"status": "absent-confirmed", "source": "user"},
               "model_code": {"status": "absent-confirmed", "source": "user"}}}
EOF
python3 <仓库根>/ts-diagnose/scripts/orient.py
```

Expected：`上游产物「setup」[built]: setup`，目标阶段为 Stage 0 总差距，
前置清单里 `[✓] setup 产物就绪`，`可开工 Stage 0`（metric-caliber 有默认、
model-set 未答会标 ✗——输出里出现 `model-set` 未答即为预期，不影响本冒烟判定
产物链通了）。把冒烟结论（跑通/输出要点）记入 commit message。

- [ ] **Step 2: CHANGELOG 追加**

在 `ts-diagnose/CHANGELOG.md` 顶部追加：

```markdown
## 2026-07-25 分层机制 Phase 1（produces/upstream）

- 新机制：playbook 可声明 produces（产物）与 upstream（依赖）；orient 机器裁决——
  required 缺 → 自动内联生产指令并阻塞开工；optional 缺 → 三分支问；输入指纹过期
  检测（stale 须用户确认）。加载期校验：产物 id 唯一、引用存在、依赖无环、问题去重。
- 新 playbook data-setup（必需前置）：适配器+对齐+setup manifest（含材料清单与
  训练日志位置，全下游复用）；golden 植入不对称覆盖难例。
- model-audit 升格生产者（model_profile）；fact-scan 消费 setup、产 chart_sweep。
- 试点 model-comparison：图 14→5（对比核心集），阶段 5→4，contexts 改 upstream。
- 向后兼容：无 upstream 声明的 playbook 行为不变；contexts: 迁移期保留，Phase 2 退役。
```

- [ ] **Step 3: 写 Phase 2 待办清单**

`docs/superpowers/plans/2026-07-25-playbook-layering-phase2-TODO.md`：

```markdown
# Playbook 分层 Phase 2 待办（试点验证后另出实施计划）

前置：Phase 1 已合入且 model-comparison 试点在真实数据上至少跑通一次。

1. 批量改造剩余 6 个 playbook（逐个 task，模式照 model-comparison 试点）：
   - result-eval / deployment-drift / robustness：upstream setup(required)，
     删各自适配对齐阶段，charts 收窄到目标核心集（result-eval 保留月度归因组；
     deployment-drift 保留时序稳定组；robustness 保留切分稳定组），
     chart_sweep 设为 optional 上游供广谱复用；
   - feature-importance：upstream setup(required)；feature_true 对照与反事实
     材料线不动；
   - subset-influence：upstream setup(required) + model_profile(optional)；
   - training-sufficiency：不依赖 setup（记录源是训练日志不是预测长表）——
     改为读 setup manifest 的 training_log 位置作可选加速（optional），
     Stage 0 探测记录源保留。
2. 各 playbook golden manifest 的 stage 键随阶段重编号平移；正文阶段号与
   gen_gate --stage 参数同步。
3. contexts: 机制退役：spec 删 §contexts、engine_common 删 context_status/
   context_embed_hint、orient 删 contexts 循环、test_engine 删对应用例——
   前提：grep 确认全部 playbook 无 contexts 声明。
4. modelmap_blocker 评估是否降级为普通 upstream 声明（model_code present 时
   model_profile 自动升 required 的规则能否用 variants 表达）。
5. 固化（crystallize）与 profile 机制对 products 的兼容：profile 是否允许携带
   products 登记（倾向不允许——产物是每次运行的现场事实，如 degraded_ok 同理）。
6. 提问纪律文档（question-discipline.md）补「上游产物拥有的问题」一节。
```

- [ ] **Step 4: 最终全量回归**

Run: `python3 -m pytest ts-diagnose/scripts/tests/ -q` → 全绿。
Run: `python3 -m pytest ts-diagnose/chartbook/tests/ -q`（若存在）→ 全绿。

- [ ] **Step 5: Commit**

```bash
git add ts-diagnose/CHANGELOG.md docs/superpowers/plans/2026-07-25-playbook-layering-phase2-TODO.md
git commit -m "docs(ts-diagnose): 分层 Phase 1 收尾——CHANGELOG + 端到端产物链冒烟 + Phase 2 待办

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
