#!/usr/bin/env python3
"""评测模式段边界探针（Claude Code PostToolUse hook）。

每次工具调用后被唤起，补齐转录里看不见的三个洞：段边界的实时记录（agent 忘跑
orient 也有）、闸回执归段、脚本内部写出的产物。

SKILL_EVOLVE_TRAJECTORY_AGENT 未设置时立刻退出——日常使用零行为改变。设置时：
  1. 定位工作目录（最新 diagnose_config.json，与 gate_guard 同法）；
  2. 拼标志性文件指纹（diagnose_state/diagnose_config + gate_reports/receipts/
     analysis_scripts 三个小目录 + 工作目录根的 json/md 文件），与上次相同直接
     退出——C1 一场约 150 次工具调用，短路是常态；
  3. 有变化才发事件（追加到 SKILL_EVOLVE_TRAJECTORY_AGENT 指向的日志）：
       segment_enter / segment_exit   current_stage 变化 → 带命名空间 segment_id
       gate_report                    gate_reports/ 新增或改写 → 归到当前段
       config_changed                 diagnose_config 顶层键变化（确认/答案落盘，
                                      供 paused 判定：停顿段出口后有无确认动作）
       artifact_write                 受访小目录/根部文件新增或改写 → 归到当前段

纪律：只读 diagnose_state.json 绝不写（单写者是 orient）；自身状态存工作目录的
.stage_probe_last.json；任何异常静默退出（exit 0），不打扰 agent、不产生 stdout。

自检：python3 stage_probe.py --selftest
"""
from __future__ import annotations
import sys, os, json, glob, datetime

ENV_VAR = "SKILL_EVOLVE_TRAJECTORY_AGENT"
PROBE_STATE = ".stage_probe_last.json"
WATCH_DIRS = ("gate_reports", "receipts", "analysis_scripts")
ROOT_SUFFIXES = (".json", ".md", ".csv", ".jsonl")


def find_workdir(cwd):
    cfgs = glob.glob(os.path.join(cwd, "**", "diagnose_config.json"), recursive=True)
    return os.path.dirname(max(cfgs, key=os.path.getmtime)) if cfgs else None


def _traj_log_real():
    """轨迹日志自身的真实路径(未设 env 时 None)。"""
    p = os.environ.get(ENV_VAR)
    try:
        return os.path.realpath(p) if p else None
    except OSError:
        return None


def fingerprint(workdir):
    """relpath → [mtime_ns, size]，只 stat 标志性小文件，不碰训练产物目录。

    轨迹日志若落在 workdir 内必须排除:否则每写一条事件就改变指纹,下次调用又报
    一条 artifact_write 指向日志自己 → 永不短路、事件无限自增,真实段边界被淹没。
    """
    fp = {}
    traj = _traj_log_real()

    def _is_traj(full):
        if not traj:
            return False
        try:
            return os.path.realpath(full) == traj
        except OSError:
            return False

    def _stat(rel):
        full = os.path.join(workdir, rel)
        if _is_traj(full):
            return
        try:
            st = os.stat(full)
            fp[rel] = [st.st_mtime_ns, st.st_size]
        except OSError:
            pass

    for rel in ("diagnose_state.json", "diagnose_config.json"):
        _stat(rel)
    for d in WATCH_DIRS:
        try:
            names = os.listdir(os.path.join(workdir, d))
        except OSError:
            continue
        for n in names:
            if not n.startswith("."):
                _stat(os.path.join(d, n))
    try:
        for e in os.scandir(workdir):
            if e.is_file() and e.name.endswith(ROOT_SUFFIXES) \
                    and not e.name.startswith(".") and e.name != "diagnose_state.json" \
                    and e.name != "diagnose_config.json" and not _is_traj(e.path):
                fp[e.name] = [e.stat().st_mtime_ns, e.stat().st_size]
    except OSError:
        pass
    return fp


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _event(type_, playbook, segment_id, **kw):
    ev = {"schema_version": 2, "timestamp": _now(), "source": "orient",
          "type": type_, "playbook": playbook,
          "summary": kw.pop("summary", ""),
          "artifact_refs": kw.pop("artifact_refs", [])}
    if segment_id:
        ev["segment_id"] = segment_id
    ev.update(kw)
    return ev


def diff_events(prev, workdir):
    """核心纯逻辑：旧探针状态 + 当前文件系统 → (事件列表, 新探针状态)。可单测。"""
    prev = prev or {}
    events = []
    fp = fingerprint(workdir)
    old_fp = prev.get("fingerprint") or {}

    # 1) 段边界：current_stage / playbook 变化
    state, cur_seg = None, prev.get("current") or {}
    try:
        state = json.load(open(os.path.join(workdir, "diagnose_state.json"),
                               encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    counter = prev.get("counter", 0)
    if state:
        pb = state.get("playbook", "")
        stage = str(state.get("current_stage"))
        if pb != cur_seg.get("playbook") or stage != cur_seg.get("stage"):
            if cur_seg.get("segment_id"):
                events.append(_event("segment_exit", cur_seg.get("playbook", ""),
                                     cur_seg["segment_id"],
                                     stage=cur_seg.get("stage")))
            counter += 1
            seg_id = f"{counter:02d}-{pb}-stage-{stage}"
            events.append(_event("segment_enter", pb, seg_id, stage=stage))
            cur_seg = {"segment_id": seg_id, "playbook": pb, "stage": stage}
    seg_id = cur_seg.get("segment_id")
    pb = cur_seg.get("playbook", "")

    # 2) 文件层变化：新增/改写(状态与配置本身不当产物报)
    for rel, sig in fp.items():
        if rel in ("diagnose_state.json", "diagnose_config.json"):
            continue
        old = old_fp.get(rel)
        if old == sig:
            continue
        if rel.startswith("gate_reports" + os.sep):
            passed = None
            try:
                passed = bool(json.load(open(os.path.join(workdir, rel),
                                             encoding="utf-8")).get("passed"))
            except (OSError, json.JSONDecodeError, ValueError):
                pass
            events.append(_event("gate_report", pb, seg_id, artifact_refs=[rel],
                                 passed=passed,
                                 rewrite=old is not None,
                                 summary=f"gate {os.path.basename(rel)}"
                                         f" passed={passed}"))
        else:
            events.append(_event("artifact_write", pb, seg_id,
                                 artifact_refs=[rel], rewrite=old is not None,
                                 summary=("改写 " if old is not None else "产出 ")
                                 + rel))

    # 3) 配置顶层键变化(确认/答案落盘) → paused 判定的原料
    cfg_keys = None
    try:
        cfg = json.load(open(os.path.join(workdir, "diagnose_config.json"),
                             encoding="utf-8"))
        if isinstance(cfg, dict):
            cfg_keys = sorted(cfg.keys())
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    old_keys = prev.get("config_keys")
    if cfg_keys is not None and old_keys is not None and cfg_keys != old_keys \
            and fp.get("diagnose_config.json") != old_fp.get("diagnose_config.json"):
        added = sorted(set(cfg_keys) - set(old_keys))
        events.append(_event("config_changed", pb, seg_id,
                             artifact_refs=["diagnose_config.json"],
                             added_keys=added,
                             summary=f"config 键变化 +{added}"))

    new_state = {"fingerprint": fp, "counter": counter, "current": cur_seg,
                 "config_keys": cfg_keys}
    return events, new_state


def run_hook():
    log_path = os.environ.get(ENV_VAR)
    if not log_path:
        sys.exit(0)
    try:
        inp = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        inp = {}
    cwd = inp.get("cwd") or os.getcwd()
    workdir = find_workdir(cwd)
    if not workdir:
        sys.exit(0)
    probe_path = os.path.join(workdir, PROBE_STATE)
    prev = None
    try:
        prev = json.load(open(probe_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    # 短路:指纹没变直接退(常态路径,一次 fingerprint 的 stat 成本)
    if prev and prev.get("fingerprint") == fingerprint(workdir):
        sys.exit(0)
    events, new_state = diff_events(prev, workdir)
    if events:
        with open(log_path, "a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    tmp = probe_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False)
    os.replace(tmp, probe_path)
    sys.exit(0)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "gate_reports"))
        json.dump({"playbook": "pb-a"},
                  open(os.path.join(td, "diagnose_config.json"), "w"))
        json.dump({"playbook": "pb-a", "current_stage": 0, "stages": {}},
                  open(os.path.join(td, "diagnose_state.json"), "w"))
        evs, st = diff_events(None, td)
        assert [e["type"] for e in evs] == ["segment_enter"], evs
        assert evs[0]["segment_id"] == "01-pb-a-stage-0"
        # 无变化 → 零事件
        evs2, st2 = diff_events(st, td)
        assert evs2 == [], evs2
        # 换 stage + 落一张闸报告 + 产一个根部产物
        json.dump({"playbook": "pb-a", "current_stage": 1, "stages": {}},
                  open(os.path.join(td, "diagnose_state.json"), "w"))
        json.dump({"passed": True},
                  open(os.path.join(td, "gate_reports", "g.json"), "w"))
        open(os.path.join(td, "facts.json"), "w").write("{}")
        evs3, st3 = diff_events(st2, td)
        types = sorted(e["type"] for e in evs3)
        assert types == ["artifact_write", "gate_report",
                         "segment_enter", "segment_exit"], types
        enter = next(e for e in evs3 if e["type"] == "segment_enter")
        assert enter["segment_id"] == "02-pb-a-stage-1"
        gate = next(e for e in evs3 if e["type"] == "gate_report")
        assert gate["passed"] is True
        # 事件全部过轨迹校验(与 skill-evolve 的 validate_event 同规则的最小核对)
        for e in evs3:
            assert e["schema_version"] == 2 and e["timestamp"] and e["source"]
        # config 加键 → config_changed
        json.dump({"playbook": "pb-a", "intervention-budget-confirmed": True},
                  open(os.path.join(td, "diagnose_config.json"), "w"))
        evs4, _ = diff_events(st3, td)
        assert any(e["type"] == "config_changed"
                   and "intervention-budget-confirmed" in e["added_keys"]
                   for e in evs4), evs4
    _selftest_traj_log_excluded()
    print("stage_probe selftest ok")


def _selftest_traj_log_excluded():
    """回归:轨迹日志落在 workdir 内不许进指纹,否则事件无限自增(2026-08-24)。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "trajectory.jsonl")
        old = os.environ.get(ENV_VAR)
        os.environ[ENV_VAR] = log
        try:
            json.dump({"playbook": "pb"},
                      open(os.path.join(td, "diagnose_config.json"), "w"))
            json.dump({"playbook": "pb", "current_stage": 0, "stages": {}},
                      open(os.path.join(td, "diagnose_state.json"), "w"))
            evs, st = diff_events(None, td)
            assert [e["type"] for e in evs] == ["segment_enter"], evs
            # 模拟 hook 把事件写进 workdir 内的日志,再跑一轮:必须零事件
            with open(log, "a", encoding="utf-8") as f:
                for e in evs:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            evs2, _ = diff_events(st, td)
            assert evs2 == [], f"轨迹日志自触发未修复:{evs2}"
            assert "trajectory.jsonl" not in st["fingerprint"], st["fingerprint"]
        finally:
            if old is None:
                os.environ.pop(ENV_VAR, None)
            else:
                os.environ[ENV_VAR] = old


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try:
            run_hook()
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001 —— 探针任何故障都不许打扰 agent
            sys.exit(0)
