#!/usr/bin/env python3
"""Step 0：Orient —— 每次进入 ts-diagnose 先跑：定位 playbook 与阶段 + 报问题清单与前置。

与两个专用技能的 run_orient.py 同一哲学：**真相以产物为准**（每次重扫工作目录，
不信任可能过期的 state），当前阶段 = 第一个未完成且未被变体跳过的阶段。
差异：阶段/前置/问题/变体不再写死在脚本里，全部由 playbook frontmatter 声明
（见 playbooks/_playbook-spec.md），本脚本只是通用求值器。

用法（在工作目录下）：
  python3 <ENGINE>/scripts/orient.py                                # 已有 diagnose_config.json：报阶段+问题+前置
  python3 <ENGINE>/scripts/orient.py --playbook training-sufficiency  # 首次进入：绑定 playbook
  python3 <ENGINE>/scripts/orient.py --profile <skill>/profile.yaml   # 固化技能入口：合并 profile
  python3 <ENGINE>/scripts/orient.py --goto 3                        # 直达校验

单写者纪律：diagnose_state.json / PROGRESS.md 只由本脚本（主 agent 调用）写；
diagnose_config.json 由主 agent 写（本脚本仅在 --playbook/--profile 合并时代写）。
subagent 不跑 orient、不碰这三个文件。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_common as ec


def print_no_config_guidance():
    print("=" * 62)
    print("未找到 diagnose_config.json —— 此前没跑过。引导主 agent：")
    print("1) 选 playbook（--playbook <id>），可选目标：")
    for pid, name, goal in ec.list_playbooks():
        print(f"   - {pid}：{name} —— {goal}")
    pc = ec.detect_project_context()
    if pc:
        exps = ec.list_experiments(pc)
        print(f"2) 发现 project-context：{pc}")
        if exps:
            print("   可用实验线（AskUserQuestion 问用户是否用某条预填 config）：")
            for name, path in exps:
                print(f"   - {name}  ({path})")
    else:
        print("2) 未发现 project-context（不阻塞——纯路径/schema 走提问收集）。")
    print("3) 绑定后重跑 orient；✗ 的必答问题用 AskUserQuestion 收集（同阶段合并一次问），")
    print("   答案写进 diagnose_config.json 的 questions 块（格式见 SKILL.md「提问纪律」）。")
    print("=" * 62)


def stage_tag(st, fm, ctx, cur, actives):
    if ec.stage_skipped(st, fm, ctx, actives):
        vids = [v["id"] for v in fm.get("variants") or []
                if st["id"] in (v.get("unlocks_stages") or []) and not actives.get(v["id"])]
        return f"变体 {','.join(vids)} 未激活（跳过，不阻塞）"
    if ec.stage_done(st, ctx):
        return "已完成"
    if cur is not None and st["id"] == cur["id"]:
        return "← 当前"
    return "待做"


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose Step 0 Orient")
    ap.add_argument("--playbook", default=None, help="playbook id（首次进入绑定）")
    ap.add_argument("--profile", default=None, help="固化技能 profile.yaml 路径")
    ap.add_argument("--goto", type=int, default=None, help="直达目标阶段 id：校验前置")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    cfg = ec.load_config()
    notes = []

    if args.profile:
        prof = ec.load_profile(args.profile)
        cfg = cfg or {}
        res = ec.merge_profile(cfg, prof, today)
        if not res["version_ok"]:
            notes.append(f"⚠ profile_version ≠ {ec.PROFILE_VERSION}：已忽略其已答问题，"
                         "降级为按 playbook 现问（config_defaults 仍合并）。建议重新固化。")
        else:
            notes.append(f"profile 合并：config +{len(res['merged_keys'])} 键，"
                         f"固化问答 +{len(res['merged_questions'])} 条。")
        if res.get("experiment_line_placeholder"):
            notes.append("⚠ profile 的 experiment_line 接口为 v0-draft：占位不生效，"
                         "不合并实验线，相关问题照常问（project-context 定稿轮统一 v0→v1）。")
        ec.save_config(cfg)
    if args.playbook:
        cfg = cfg or {}
        cfg.setdefault("playbook", args.playbook)
        ec.save_config(cfg)

    if not cfg or not cfg.get("playbook"):
        print_no_config_guidance()
        return

    if ec._filled(cfg.get("experiment_line")) and os.path.exists(cfg["experiment_line"]):
        merged = ec.merge_experiment_line(cfg, cfg["experiment_line"])
        if merged:
            notes.append(f"实验线补缺：{', '.join(merged)}")
            ec.save_config(cfg)

    fm = ec.load_frontmatter(ec.find_playbook(cfg["playbook"]))
    state = ec.read_json(ec.STATE_PATH) or {}
    ctx = {"cfg": cfg, "fm": fm, "state": state}
    actives = ec.variant_active(fm, ctx)
    cur = ec.current_stage(fm, ctx)

    print("=" * 62)
    print(f"playbook: {fm['id']}（{fm['name']}）    工作目录: {os.getcwd()}")
    print(f"目标: {fm['goal']}")
    for n in notes:
        print(f"  {n}")
    print("-" * 62)
    for st in fm["stages"]:
        pause = " ⏸" if st.get("pause_after") else ""
        print(f"  Stage {st['id']} {st['name']}{pause}  [{stage_tag(st, fm, ctx, cur, actives)}]")
        if st.get("charts"):
            for (_sid, rid, missing) in ec.charts_report(fm, cfg):
                if _sid != st["id"]:
                    continue
                if missing:
                    print(f"    📊 {rid} ✗缺材料:{','.join(missing)}"
                          "（自动跳过，不阻塞）")
                else:
                    print(f"    📊 {rid} ✓可画")
    if ec.has_chart_stage(fm):
        addable = ec.addable_recipes(fm, cfg)
        print("-" * 62)
        print("  图表选择门（画图前 AskUserQuestion 多选，engine-core「图表选择门」）：")
        print("    默认全选上方 ✓可画 图；用户可取消勾选删图（删了记 PROGRESS+CONCLUSION"
              "声明覆盖缺口），或从下方「可加画」勾选加图。")
        if addable:
            print("    ➕ 可加画（未声明、材料已满足，可跨 playbook 任取）：")
            for rid, needs, min_models in addable:
                mnote = f"，需 ≥{min_models} 模型（单模型勿加）" if min_models >= 2 else ""
                print(f"       {rid}（需 {','.join(needs) or '无'}{mnote}）")
        else:
            print("    ➕ 可加画：无（未声明的 recipe 材料都不满足，或已全声明）。")

    if cur is None:
        print("  全部阶段完成——可写/刷新 CONCLUSION.md，或 --goto 复核，或按"
              " references/crystallize.md 提议固化。")

    for cx in fm.get("contexts") or []:
        cs = ec.context_status(cx, ctx)
        print("-" * 62)
        if cs["status"] == "linked":
            miss = cs.get("missing_markers")
            flag = f" ⚠ 缺核验文件 {miss}（有效性存疑，先复核再消费）" if miss else ""
            print(f"  上下文「{cx['name']}」[linked]: {cs['workdir']}{flag}")
        elif cs["status"] == "declined":
            print(f"  上下文「{cx['name']}」[declined]：用户已拒绝——结论须注明缺此上下文。")
        else:
            print(f"  ⚠ 上下文「{cx['name']}」[absent]：主 agent 必须先 AskUserQuestion"
                  f"（要不要先建立该上下文？做法见 playbook 正文），"
                  f"答案回填 config.{cx['status_key']}（+{cx['workdir_key']}）。")
            hint = ec.context_embed_hint(cx, cfg)
            if hint:
                print(f"    {hint}")

    mat_rows = ec.materials_report(fm, cfg)
    mat_blocked = ec.blocking_materials(fm, cfg)
    if mat_rows:
        print("-" * 62)
        print("  材料盘点（追问模板与 status 写法见 references/intake.md；"
              "答案落 config.materials）：")
        for mid, kind, st in mat_rows:
            rec = ((cfg.get("materials") or {}).get(mid)) or {}
            if st == "present":
                label = "✓present"
            elif st == "absent-confirmed":
                label = "−absent"
                kind = f"{kind}, 已确认降级" if rec.get("degraded_ok") else kind
            else:
                label = "✗未盘点·阻塞" if (mid, "unknown") in mat_blocked else "○未盘点"
            print(f"  [{label}] {mid} ({kind})")
        if mat_blocked:
            print("  ⚠ 必需材料未就绪：" + ", ".join(m for m, _ in mat_blocked)
                  + " —— 开工前先按 references/intake.md 盘点：")
            print("    一次多选 AskUserQuestion 列全该 playbook 的材料 checklist"
                  "（末尾带『还有别的吗』开放项），")
            print("    再按每类的追问模板批量补齐 路径/格式/schema（y列/时间列/id列）；")
            print("    absent-confirmed 的必需材料要走降级须经用户确认后写 degraded_ok。")

    qs = fm.get("questions") or []
    if qs:
        print("-" * 62)
        print("  问题清单（✗ 在其 stage 开工前必须 AskUserQuestion，同阶段合并一次问）：")
        for q in qs:
            code, label = ec.question_status(q, ctx)
            block = f" ·阻塞 Stage {q['stage']}" if code == "unanswered" else ""
            print(f"  [{label}]{block} {q['id']}：{q['ask']}")

    target = None
    if args.goto is not None:
        target = ec._stage_by_id(fm, args.goto)
        if target is None:
            print(f"→ 无 Stage {args.goto}（本 playbook 阶段：{[s['id'] for s in fm['stages']]}）")
    elif cur is not None:
        target = cur
    if target is not None:
        print("-" * 62)
        print(f"进入 Stage {target['id']} 的前置：")
        pr = ec.prereqs_of(target, ctx)
        for desc, ok in pr:
            print(f"  [{'✓' if ok else '✗'}] {desc}")
        blocked_qs = ec.blocking_questions(fm, ctx, stage_id=target["id"])
        for q in blocked_qs:
            print(f"  [✗] 必答问题未答：{q['id']}（{q['why']}）")
        for mid, reason in mat_blocked:
            print(f"  [✗] 必需材料未就绪：{mid}（{reason}）")
        if ec.prereqs_ok(pr) and not blocked_qs and not mat_blocked:
            print(f"→ 前置齐，可开工 Stage {target['id']}。")
        elif args.goto is not None and cur is not None and args.goto != cur["id"]:
            print(f"→ 前置不齐，不能直达 Stage {args.goto}。正确入口 = Stage {cur['id']}（{cur['name']}）。")
        else:
            print("→ 有 ✗ 先补：缺答案 AskUserQuestion；缺产物回上一阶段；缺路径问用户后写 config。")
    print("=" * 62)

    # state + PROGRESS（保留 manual_done——manual 阶段的完成标记只有主 agent 会写）
    new_state = {
        "playbook": fm["id"],
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
        "current_stage": (cur["id"] if cur is not None else "done"),
        "stages": {str(st["id"]): ("skipped" if ec.stage_skipped(st, fm, ctx, actives)
                                   else "done" if ec.stage_done(st, ctx) else "todo")
                   for st in fm["stages"]},
        "manual_done": state.get("manual_done") or [],
        "variants": actives,
    }
    ec.dump_json(new_state, ec.STATE_PATH)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    is_new = not os.path.exists(ec.PROGRESS_PATH)
    with open(ec.PROGRESS_PATH, "a", encoding="utf-8") as f:
        if is_new:
            f.write("# PROGRESS —— ts-diagnose 进度叙事日志\n\n每行：时间 | 动作。"
                    "脚本验证记录也追加在此（crystallize 只快照有验证记录的脚本）。\n\n")
        f.write(f"- {stamp} | orient：playbook={fm['id']}，当前 Stage "
                f"{cur['id'] if cur is not None else '收尾'}"
                f"{f'（--goto {args.goto}）' if args.goto is not None else ''}\n")


if __name__ == "__main__":
    main()
