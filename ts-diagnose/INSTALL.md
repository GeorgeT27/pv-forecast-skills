# 安装 ts-diagnose（Claude Code）

## 前置

- python3 ≥ 3.9，`pip install -r <仓库根>/requirements.txt`（pyyaml、numpy 1.26.4、shap 0.44.1 等）
- Claude Code CLI 已登录

## 安装

    git clone <仓库> && cd <仓库>/ts-diagnose
    bash install.sh
    bash install.sh --check     # 期望最后一行 ALL OK

`install.sh` 做五件事：`~/.claude/skills/ts-diagnose` → 本目录；`~/.claude/agents/` 下逐张链接
`agents/*-compute.md` `*-worker.md`；`~/.claude/workflows/` 下链接 `workflows/*.js`（如有）；
删除旧的 `~/.claude/skills/ts-diagnose-v2` 链接（v2 已退役）；
把 `hooks/hooks.json` 三条钩子合并进 `~/.claude/settings.json`（幂等，可重复跑）。

Claude Code 若不跟随 agents 目录下的 symlink（新会话里 Agent 工具的可用类型没有
`model-comparison-compute`），改跑 `bash install.sh --copy`，以后每次更新包后重跑一次。

## 确认卡片已注册

开一个新的 `claude` 会话，让它列出可用 subagent 类型；应出现 13 个名字：
`data-setup-compute` `metric-eval-compute` `model-audit-compute` `training-sufficiency-compute`
`robustness-compute` `feature-importance-compute` `model-comparison-compute`
`deployment-drift-compute` `fact-scan-compute` `result-eval-compute` `subset-influence-compute`
`architecture-attribution-compute` `architecture-attribution-worker`。

## 钩子说明

| 事件 | 脚本 | 作用 |
|---|---|---|
| PostToolUse | `hooks/stage_probe.py` | 评测轨迹埋点；环境变量 `SKILL_EVOLVE_TRAJECTORY_AGENT` 未设时零行为 |
| Stop | `hooks/gate_guard.py` | 结论闸守卫：cwd 下有诊断在跑且 receipt 不合法时打回；连续 3 次后放行 |
| UserPromptSubmit | `hooks/orient_reminder.py` | 每回合注入「先跑 orient」提醒 |

工程会话里不想被 Stop 钩子打回：`python3 hooks/install_hooks.py --uninstall`，用完 `bash install.sh` 装回。

## 卸载

    bash install.sh --uninstall

## 附录：非 Claude Code 宿主（自研 SDK / DeepSeek）

- 只需 `SKILL.md` + `references/` + `playbooks/` + `scripts/` + `chartbook/` + `agents/`；钩子不装。
- 卡片按 `agents[name]` 查表加载：name = 文件名去 `.md`，frontmatter `tools/model` 是该 agent 的工具白名单与模型；
  正文整份作为 system prompt。宿主必须保证卡片没有向用户提问的工具。
- 派发时主 agent 把「输入」节的 `<ENGINE>`/`<workdir>` 替换为绝对路径，final message 按「输出契约」解析 JSON。
- 所有强制（入口闸 / 阶段闸 / 结论闸）都在 `scripts/` 的 Python 里，与宿主无关。
