# project-context —— 当前项目实例的全部事实（技能之外的共享外部信息）

本目录是 pv-result-analysis 与 pv-station-influence 两个技能的**共享站点注册表与实验配置**。
技能本体（SKILL.md/scripts/references）不写死任何站点、数量、划分——它们全在这里。
**换新项目 = 整目录替换（或把各技能 references/project-context.pointer 指向别处）**，技能一行不用改。

## 文件

| 文件 | 内容 |
|------|------|
| `stations.md` | **物理站档案**：每站一节（地理/装机/形式/气候/限电），字段带置信标签 ✅确认 /【检索】待核实 /【待补】 |
| `station-entries.md` | **数据条目表**：entry_id 为主键——同一物理站可因数据时间段不同出现多条目 |
| `seasonality.md` | 各站气候季节性（从 pv-result-analysis 迁入，2026-07-14） |
| `event-log.md` | 站点事件台账（同上迁入） |
| `experiments/*.json` | **实验线配置**：训练条目 + 留出站 + 数据路径 + chunk 方案；技能运行时 AskUserQuestion 的答案落盘处 |

## 实验线 JSON schema

```json
{
  "name": "<实验线名（=文件名）>",
  "description": "<一句话>",
  "held_out_station": "<留出/目标测试站名，必填>",
  "held_out_station_slug": "<留出站拼音 slug——figures/<slug>/ 目录名与 config 的 station/test_station 字段统一用它>",
  "training_entries": ["<entry_id，见 station-entries.md，必填>"],
  "chunking": {"n_chunks": 4, "sizes": [5, 5, 5, 2], "epochs_per_chunk": 20},
  "models": ["M1", "M2", "M3", "M4"],
  "data_paths": {"train": "【待补】", "test_label": "【待补】", "metric_py": "【待补】", "predictions": {}},
  "notes": ["<实验线级别的重要事实（分析主线、气候带覆盖等）>"],
  "source": "<谁在什么时候提供>"
}
```

约定：`held_out_station`/`training_entries` 必填；`held_out_station_slug` 是留出站的拼音 slug，
figures 目录名与 analysis_config/influence_config 的 station/test_station 字段统一用它，避免中文站名
散落各处出现拼写不一致；`data_paths` 允许【待补】占位——技能运行到需要处
追问一次并**补写回本文件**；`chunking` 无分块训练时置 null；`models` 按实验线实际。

## 发现机制

各技能 `references/project-context.pointer`（`path:` 行 = 本目录绝对路径）。pointer 缺失时技能会
先探 `<技能目录>/../project-context`（symlink 安装下内核物理解析可达），再不行 AskUserQuestion 问路径。

## 使用纪律

- 已填写的字段才可被分析结论引用；【待补】视为未知——宁写"缺 XX 背景无法归因"也不编造。
- 【检索】字段来自网络检索，用户未核实，引用时注明。
- 同名站点多条目（如 1012 与 runda-b）是**同站不同数据时段**，归因/漂移按条目区分，站点背景共享档案。
