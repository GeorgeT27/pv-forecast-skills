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
import json
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


RECIPE_FAIL_HINT = "⚠ 菜谱抽取失败：{}；本回合直接读 playbook.md 对应 Stage 节"


def _print_preamble(pb_path):
    """菜谱通则（生成闸等硬规则所在）——只有标题、没有正文时不打空表头。"""
    pre = ec.recipe_preamble(pb_path)
    if len([ln for ln in pre.splitlines() if ln.strip()]) <= 1:
        return
    print("📖 菜谱通则（playbook.md 该节开头原文）")
    print(pre)


def _print_recipe(pb_path, stage):
    try:
        secs = ec.recipe_sections(pb_path)
    except ValueError as e:
        print(RECIPE_FAIL_HINT.format(e))
        return
    text = secs.get(stage["id"])
    if not text:
        return
    done = (stage.get("done_when") or {})
    done_s = ", ".join(done.get("artifacts") or []) or ("manual" if done.get("manual") else "")
    if done.get("findings_marker"):
        done_s += f"；FINDINGS 含「{done['findings_marker']}」"
    print("-" * 62)
    _print_preamble(pb_path)
    print(f"📖 本阶段菜谱（playbook.md §Stage {stage['id']} 原文；done：{done_s}）——照此做，"
          "标【硬规则】的步骤不得合并或跳过；整份 playbook 只在需要跨阶段判断时再读：")
    print(text)


def _delivers(fm):
    """生产者/生成器交付的是什么——产物 id 优先，没有 produces 声明就报末阶段产物。"""
    pr = fm.get("produces")
    if pr and pr.get("id"):
        return f"交付产物「{pr['id']}」（manifest: {pr.get('manifest')}）供下游消费"
    last = (fm.get("stages") or [{}])[-1]
    arts = (last.get("done_when") or {}).get("artifacts") or []
    return f"交付 {'、'.join(arts) or '末阶段产物'} 供下游消费"


def main():
    ap = argparse.ArgumentParser(description="ts-diagnose Step 0 Orient")
    ap.add_argument("--playbook", default=None, help="playbook id（首次进入绑定）")
    ap.add_argument("--profile", default=None, help="固化技能 profile.yaml 路径")
    ap.add_argument("--goto", type=int, default=None, help="直达目标阶段 id：校验前置")
    ap.add_argument("--force", action="store_true",
                     help="用户明确要求跳过前置时才可用；PROGRESS 留痕")
    ap.add_argument("--no-recipe", action="store_true", help="不打印当前阶段菜谱原文")
    ap.add_argument("--recipe", type=int, default=None, metavar="N",
                     help="只打印 Stage N 的菜谱原文并退出（复核用，不写 state/PROGRESS）")
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

    pb_path = ec.find_playbook(cfg["playbook"])
    fm = ec.load_frontmatter(pb_path)
    if args.recipe is not None:
        try:
            secs = ec.recipe_sections(pb_path)
        except ValueError as e:
            print(RECIPE_FAIL_HINT.format(e))
            return 0
        if args.recipe not in secs:
            print(f"→ 无 Stage {args.recipe}（本 playbook 阶段：{sorted(secs)}）")
        else:
            _print_preamble(pb_path)
            print(secs[args.recipe])
        return
    state = ec.read_json(ec.STATE_PATH) or {}
    ctx = {"cfg": cfg, "fm": fm, "state": state}
    actives = ec.variant_active(fm, ctx)
    cur = ec.current_stage(fm, ctx)

    blockers = ec.intake_blockers(fm, cfg)
    if blockers:
        print("=" * 62)
        print(f"BLOCKED: 材料盘点未完成（入口闸）    playbook: {fm['id']}")
        print("-" * 62)
        print("以下材料过闸前，orient 不输出任何阶段菜单与菜谱入口"
              "（`--recipe N` 只读复核除外）。")
        print("主 agent 现在只做一件事：AskUserQuestion 盘点（一次多选列 checklist，")
        print("末尾带『还有别的吗』开放项；再按追问模板逐项补齐，答案落")
        print("diagnose_config.json 的 materials 块——格式见 references/intake.md）。")
        reasons = {
            "unknown": "未盘点（从没问过）",
            "absent-not-user": "absent-confirmed 但 source≠user——只有用户亲口说没有才算",
            "absent-need-degraded-ok": "required 材料缺失——须用户确认接受降级后写 degraded_ok: true",
        }
        for mid, reason in blockers:
            desc = reasons.get(reason)
            if desc is None and reason.startswith("present-incomplete:"):
                desc = (f"标了 present 但缺实质字段 {reason.split(':', 1)[1]}"
                        "——schema 没问清不算 present")
            print(f"  ✗ {mid} [{reason}] —— {desc}")
            for ln in ec.intake_ask_lines(mid)[:3]:
                print(f"      {ln}")
        print("=" * 62)
        _write_state_progress(fm, None, args, blocked=[m for m, _ in blockers])
        return

    print("=" * 62)
    print(f"playbook: {fm['id']}（{fm['name']}）    工作目录: {os.getcwd()}")
    print(f"目标: {fm['goal']}")
    for n in notes:
        print(f"  {n}")
    if fm.get("produces"):
        print("  🤝 生产者 playbook：提问/用户裁决只在主 agent；questions 收齐后按名字派")
        print(f"     卡片 agents/{fm['id']}-compute.md，跑到卡片区间终点交回主 agent（名字不可用则")
        print("     卡片全文作 prompt 派 general-purpose）；产物落盘后主 agent 写 config.products")
        print("     回填——主 agent 不要自己埋头执行。")
    print("-" * 62)
    plan_first = ec.chart_gate_mode(fm) == "plan-first"
    plan_ready = ec.chart_plan_ready()
    example = os.path.join(os.path.dirname(pb_path), "EXAMPLE-RUN.md")
    if os.path.exists(example) and not any(ec.stage_done(st, ctx) for st in fm["stages"]):
        print(f"  📎 首次进入：示例轨迹 {example}（golden 数据的完整一遍，读一次即可）")
    for st in fm["stages"]:
        pause = " ⏸" if st.get("pause_after") else ""
        print(f"  Stage {st['id']} {st['name']}{pause}  [{stage_tag(st, fm, ctx, cur, actives)}]")
        if st.get("charts"):
            if plan_first and not plan_ready:
                print("    📊 图池暂不展示——先落 chart_plan.json（见下方图表选择门）。"
                      "先看菜单再想疑问＝从菜单里挑，顺序不能反。")
            else:
                for (_sid, rid, missing) in ec.charts_report(fm, cfg):
                    if _sid != st["id"]:
                        continue
                    cat = ec.recipe_category(rid)
                    if missing:
                        print(f"    📊 {rid} ✗缺材料:{','.join(missing)}"
                              f"（自动跳过，不阻塞）[{cat}]")
                    else:
                        print(f"    📊 {rid} ✓可画 [{cat}]")
    if ec.has_chart_stage(fm) and plan_first and not plan_ready:
        print("-" * 62)
        print("  图表选择门 · 第一步「先想要什么证据」（engine-core「图表选择门」）"
              "——本回合只做这一件事：")
        print("    1. 用人话问用户「这一步你想弄清什么」（AskUserQuestion），"
              "别把 recipe 名字当选项列给用户；")
        print("       上一阶段已有假设/账本时不必问：取证目标就是「验哪条假设」，直接写。")
        print("    2. 每条疑问写清需要什么形态的证据——看什么量、按什么切、跟谁比。")
        print(f"    3. 落盘 {ec.CHART_PLAN_PATH}："
              '{"entries":[{"question","evidence","recipe","source"}]}；'
              "recipe 这步可留空，下一次 orient 才发图池给你匹配。")
        print("    4. 跑 `python3 <ENGINE>/scripts/chart_plan.py` 校验——不过闸不许开画。")
        print("    ⛔ 图池要等计划落盘后的下一次 orient 才打印。不许凭记忆点 recipe 名开画：")
        print("       先看菜单再想疑问，等于从菜单里挑，这一步就白做了。")
    elif ec.has_chart_stage(fm):
        addable = ec.addable_recipes(fm, cfg)
        print("-" * 62)
        if plan_first:
            entries = ec.chart_plan_entries()
            print(f"  图表选择门 · 第二步「拿计划对图池」（{ec.CHART_PLAN_PATH} 已落盘 "
                  f"{len(entries)} 条）——逐条办：")
            print("    1. 每条疑问对上方图池：有现成的 → 直接调 chartbook 脚本"
                  "（豁免仍在：已覆盖的图禁止现场重写）；")
            print("    2. 图池给不了 → 现场写进 analysis_scripts/，回写该条 "
                  "source=ad-hoc + verification（三档见 engine-core）；")
            print("    3. 计划外的图不画。确要加 → 先回写 chart_plan.json 补一条疑问"
                  "（改计划留痕，不静默加图）；没有疑问支撑的图，不画不用声明缺口。")
            print("    4. 画完 → 跑 `chartbook/scripts/build_index.py --charts-dir charts/ "
                  "--out INDEX.md`（每张图登记服务哪条疑问）→ 再进 pause_after 停顿汇报。")
            for e in entries:
                q = str(e.get("question") or "")[:46]
                rid = str(e.get("recipe") or "").strip() or "（待匹配）"
                print(f"    📋 {q} → {rid} [{e.get('source') or '?'}]")
        else:
            print("  图表选择门（画图前必停一次，engine-core「图表选择门」）——按序逐条办：")
            print("    1. 一次 AskUserQuestion 多选；默认全勾上方 ✓可画 图"
                  "（被动接受默认＝画全套，别自作主张少画）；")
            print("    2. 用户取消勾选的删图不静默：记 PROGRESS.md 一行 + CONCLUSION 声明覆盖缺口；")
            print("    3. 可从下方「可加画」勾选加图（跨 playbook，材料满足才在池里）；")
            print("    4. 画最终选定集 → 跑 `chartbook/scripts/build_index.py --charts-dir charts/ "
                  "--out INDEX.md`（阶段闸判的是工作目录根部的 INDEX.md）→ 再进 pause_after 停顿汇报。")
        if addable:
            print("    ➕ 可加画（未声明、材料已满足，可跨 playbook 任取，按类别分组）：")
            by_cat = {}
            for rid, needs, min_models in addable:
                by_cat.setdefault(ec.recipe_category(rid), []).append(
                    (rid, needs, min_models))
            for cat in list(ec.CATEGORY_IDS) + ["uncategorized"]:
                if cat not in by_cat:
                    continue
                print(f"      [{cat}]")
                for rid, needs, min_models in by_cat[cat]:
                    mnote = (f"，需 ≥{min_models} 模型（单模型勿加）"
                             if min_models >= 2 else "")
                    print(f"        {rid}（需 {','.join(needs) or '无'}{mnote}）")
        else:
            print("    ➕ 可加画：无（未声明的 recipe 材料都不满足，或已全声明）。")

    if cur is None:
        # 不产结论的剧本（生产者/生成器）不许被指去写 CONCLUSION.md——Stop 钩子按
        # frontmatter 判定它没有结论阶段，这里再教它写就是自相矛盾（r2 联调 R2-3）。
        if ec.produces_conclusion(fm):
            print("  全部阶段完成——可写/刷新 CONCLUSION.md，或 --goto 复核，或按"
                  " references/crystallize.md 提议固化。")
            print("  🚪 写/改 CONCLUSION.md 后必须跑 python3 <ENGINE>/scripts/"
                  "conclusion_gate.py（不过则结论不算交付，receipt 是结论阶段完成判据）。")
        else:
            print(f"  全部阶段完成——本剧本{_delivers(fm)}，"
                  "**不写 CONCLUSION.md**（结论由下游消费这些产物的剧本在出口产一次）。")
            print("  可 --goto 复核，或按 references/crystallize.md 提议固化；"
                  "交付即停顿汇报，把产物路径与要点交给用户或下游。")

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
                  f"{pid}/diagnose_config.json（沿用已答，不重复问；"
                  f"materials 里的相对路径先改写成绝对路径再拷）；")
            print(f"     2. 在 {pid}/ 内跑 orient --playbook {prod_pb} 并按其菜谱完成；")
            print(f"     3. 回本目录写 config.products.{pid}="
                  f"{{workdir:'{pid}',status:'built'}} 后重跑 orient。")
            up_blocked.append((u, s))
        else:      # absent + optional → 三分支问
            print(f"  ⚠ 上游产物「{pid}」[absent]（可选）：AskUserQuestion 三分支——"
                  f"现在内联生产（{prod_pb}）/ 链接已有目录（写 workdir+status=linked）/ "
                  f"放弃（status=declined，结论须声明缺此产物与代价）。")

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
    force_skipped_prereqs = False
    if args.goto is not None:
        target = ec._stage_by_id(fm, args.goto)
        if target is None:
            print(f"→ 无 Stage {args.goto}（本 playbook 阶段：{[s['id'] for s in fm['stages']]}）")
    elif cur is not None:
        target = cur
    if target is not None:
        pr = ec.prereqs_of(target, ctx)
        blocked_qs = ec.blocking_questions(fm, ctx, stage_id=target["id"])
        goto_jump = (args.goto is not None and cur is not None
                     and target["id"] != cur["id"])
        would_be_refused = goto_jump and not (ec.prereqs_ok(pr) and not blocked_qs)
        if would_be_refused and args.force:
            force_skipped_prereqs = True
        if would_be_refused and not args.force:
            print("-" * 62)
            print(f"⛔ 拒绝直达 Stage {target['id']}：前置不齐。"
                  f"正确入口 = Stage {cur['id']}（{cur['name']}）。")
            print("   确需跳过：须用户明确指示后重跑 orient --goto "
                  f"{target['id']} --force（将记 PROGRESS 留痕，结论须声明缺口）。")
            target = cur          # 回落到当前阶段，按正常流程打印
            pr = ec.prereqs_of(target, ctx)
            blocked_qs = ec.blocking_questions(fm, ctx, stage_id=target["id"])
        print("-" * 62)
        print(f"进入 Stage {target['id']} 的前置：")
        for desc, ok in pr:
            print(f"  [{'✓' if ok else '✗'}] {desc}")
        for q in blocked_qs:
            print(f"  [✗] 必答问题未答：{q['id']}（{q['why']}）")
        for mid, reason in mat_blocked:
            print(f"  [✗] 必需材料未就绪：{mid}（{reason}）")
        mm = ec.modelmap_blocker(cfg, fm)
        if mm:
            print(f"  [✗] {mm}")
        for u, s in up_blocked:
            print(f"  [✗] 必需上游产物未就绪：{u['product']}（{s['status']}）")
        print("  ⚑ 引擎级恒问五类·开工前自检（任务用到且信息不明时必停 AskUserQuestion，"
              "orient 不替你判）：")
        print("    ① schema/单位/口径不明 ② 成功判据未定义 "
              "③ 证据不足以升级（问降级 or 补证据并列成本）")
        print("    ④ 破坏性/昂贵操作（重训/覆盖产物/写外部目录） ⑤ 多候选文件或版本选哪个")
        if (target.get("done_when") or {}).get("manual"):
            print(f"  🖐 本阶段没有产物判据（done_when.manual）——做完必须把 {target['id']} "
                  f"追加进 {ec.STATE_PATH} 的 manual_done 数组，orient 才会判它完成；"
                  "不写就一直停在本阶段，产物齐了也没用。")
        if "CONCLUSION.md" in ((target.get("done_when") or {}).get("artifacts") or []):
            print("  🚪 结论阶段·三道门自检（三门全过才可在 FINDINGS.md 标「已证实」；"
                  "细则 mechanisms.md）——逐条办：")
            print("    门1 稳健性：配对检验过 + 剔除最极端 10% 方向不变；")
            print("    门2 假设登记：先在 playbook 的假设账本写下预测与 provenance，再看数；")
            print("    门3 反驳门：替代解释逐条排除，排不掉就显式降级"
                  "（含 playbook 特有反驳门条目）；")
            print("    另：≥2 证据线按 upgrade_rule 一致才升『假设』；样本<阈值只报排名不报显著；")
            print("    收尾：写 CONCLUSION.md 前跑 provenance.py 附 Provenance 块，"
                  "写完直接呈现给用户不只丢路径。")
            print("    收尾后必须跑：python3 <ENGINE>/scripts/conclusion_gate.py"
                  "（不过则结论不算交付，receipt 是本阶段完成判据）")
        if ec.prereqs_ok(pr) and not blocked_qs and not mat_blocked and not mm \
                and not up_blocked:
            print(f"→ 前置齐，可开工 Stage {target['id']}。")
            if not args.no_recipe:
                _print_recipe(pb_path, target)
        else:
            print("→ 有 ✗ 先补：缺答案 AskUserQuestion；缺产物回上一阶段；缺路径问用户后写 config。")
    print("=" * 62)
    print("↻ 每回合先跑 orient 再动手；本阶段做完重跑一次核对进度——真相以产物为准，"
          "状态已落盘、可断点续跑，别凭记忆推进。")

    # state + PROGRESS（保留 manual_done——manual 阶段的完成标记只有主 agent 会写）
    _write_state_progress(fm, cur, args, ctx=ctx, actives=actives, state=state,
                          force_skipped_prereqs=force_skipped_prereqs)


def _write_state_progress(fm, cur, args, ctx=None, actives=None, state=None, blocked=None,
                          force_skipped_prereqs=False):
    # 评测埋点用:落盘前捕获旧状态(单写者纪律保证此读无竞态)
    old_state = None
    if os.path.exists(ec.STATE_PATH):
        try:
            with open(ec.STATE_PATH, encoding="utf-8") as f:
                old_state = json.load(f)
        except (OSError, json.JSONDecodeError):
            old_state = None
    # round 永不倒退：intake-blocked 分支不传 state，此处退回落盘的 old_state 取真值
    rnd = int(((state or old_state) or {}).get("round") or 1)
    if blocked is not None:
        new_state = {"playbook": fm["id"],
                     "updated": dt.datetime.now().isoformat(timespec="seconds"),
                     "current_stage": "intake-blocked", "stages": {},
                     "manual_done": [], "variants": {},
                     "round": rnd,
                     "produces_conclusion": ec.produces_conclusion(fm)}
        line = f"orient：playbook={fm['id']}，BLOCKED 材料盘点未完成：{','.join(blocked)}"
    else:
        new_state = {
            "playbook": fm["id"],
            "updated": dt.datetime.now().isoformat(timespec="seconds"),
            "current_stage": (cur["id"] if cur is not None else "done"),
            "stages": {str(st["id"]): ("skipped" if ec.stage_skipped(st, fm, ctx, actives)
                                       else "done" if ec.stage_done(st, ctx) else "todo")
                       for st in fm["stages"]},
            "manual_done": (state or {}).get("manual_done") or [],
            "variants": actives,
            "round": rnd,
            # 供 Stop 钩子判「该不该有结论」——钩子不解析 YAML，事实由这里落盘
            "produces_conclusion": ec.produces_conclusion(fm),
        }
        line = (f"orient：playbook={fm['id']}，当前 Stage "
                f"{cur['id'] if cur is not None else '收尾'}"
                f"{f'（--goto {args.goto}）' if args.goto is not None else ''}"
                f"{'（--force：用户要求跳过前置，Stage 前置未齐）' if force_skipped_prereqs else ''}")
    if any("{round}" in a for st in fm["stages"]
           for a in ((st.get("done_when") or {}).get("artifacts") or [])):
        print(f"  改进环：第 {new_state['round']} 轮（产物路径里的 {{round}} 占位按此展开）")
    ec.dump_json(new_state, ec.STATE_PATH)
    # PROGRESS.md 只建头，是 agent 的叙事文档；机器审计线单独进 .orient_audit.jsonl
    # ——此前审计行写进 PROGRESS.md，agent 整篇重写叙事时会把它清掉（C1 实测 5→1 行）
    if not os.path.exists(ec.PROGRESS_PATH):
        with open(ec.PROGRESS_PATH, "w", encoding="utf-8") as f:
            f.write("# PROGRESS —— ts-diagnose 进度叙事日志\n\n每行：时间 | 动作。"
                    "脚本验证记录也追加在此（crystallize 只快照有验证记录的脚本）。\n\n")
    audit = {"timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
             "line": line, "playbook": fm["id"],
             "current_stage": new_state["current_stage"],
             "goto": args.goto, "force_skipped_prereqs": bool(force_skipped_prereqs)}
    with open(ec.ORIENT_AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit, ensure_ascii=False) + "\n")
    # 评测模式轨迹事件(SKILL_EVOLVE_TRAJECTORY_AGENT 未设置时零行为);任何异常不许影响诊断
    try:
        import eval_trajectory
        n_ev = eval_trajectory.maybe_emit(old_state, new_state)
        # 开了埋点就回一行确认:让「轨迹在写」可见。不猜评测语境、不在未设时出声,
        # 日常仍是零行为改变;评测方据此判断埋点是否真的生效(静默失败是 2026-08-24
        # 四场盲跑轨迹全丢的直接原因)。
        traj_path = os.environ.get(eval_trajectory.ENV_VAR)
        if traj_path:
            print(f"  📈 轨迹埋点已开 → {traj_path}(本次 +{n_ev} 事件)")
    except Exception as e:  # noqa: BLE001 —— 埋点故障只降级轨迹完整性,不降级诊断
        print(f"[orient] 评测埋点异常(已忽略):{e}", file=sys.stderr)


if __name__ == "__main__":
    main()
