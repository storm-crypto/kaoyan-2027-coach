# 周上下文数据契约

worker 负责预算、优先级和计划正文；skill 只汇总事实，不生成计划、不写 vault。

```sh
python3 scripts/get_weekly_context.py "$OBSIDIAN_ROOT" --week-start 2026-10-12
```

`--week-start` 必须为周一，范围包含该周一至周日，事件按北京时间归周。省略 vault 路径时使用现有环境变量解析规则。

## JSON 字段与缺失值

| 字段 | 口径 |
| --- | --- |
| `week_start / week_end` | 包含边界的日期范围 |
| `daily_completion_rates` | 7 个日期键，值为归档任务完成率 0–1；无归档为 null，有归档但无任务为 0；不读取尚未归档的今日计划 |
| `papers` | 本周成绩列表，每项含 `subject / paper / paper_type / section / total_score / modules / date / record_path`；同时包含整卷和选填，调用方按 section 分开统计趋势 |
| `subject_hours` | 数学一、408、英语一、政治的明确分科小时数；有总时长但没有分科记录的部分不分配给任何科目 |
| `unallocated_hours` | 日志总时长减去已归科时长的周内合计；数据冲突时保留负差值并提示，不裁成 0 |
| `breakthroughs` | 每项为 `id / goal / events`，events 只含本周明确发生的变化；有完整事件记录但本周无事件的单不列出；旧单无事件记录时列出 `events: null`，不能理解为本周没有变化 |
| `breakthrough_snapshots` | 当前突破单字段快照，供定位；不是周末历史状态，不用来推断本周变化 |
| `new_cards` | 本周 first_wrong_at 的错题卡数，按 question_id 去重，缺 id 时按路径 |
| `reviewed_cards` | 本周实际复习过的不同卡片数，多次复习只计一张；首次归档不计复习；无本周历史记录时可用明确的 last_review_at，创建当天无法区分则不计 |
| `data_gaps` | 存在时列出缺失或冲突的来源、日期/单号和原因 |

分科时长支持日志的 `## 分科时长` 两列表格（科目、时长）、`- 数学一: 2h` 列表，或 frontmatter 的单行 JSON `subject_hours: {"数学一": 2, "408": 1}`。数字按小时，明确的 h/小时/min/分钟按单位换算，不从主题或示例代码块猜时长。同日新旧日志共存时只读新布局版本。

无日志，或任一已有日志没有明确全天总时长时，`subject_hours` 和 `unallocated_hours` 均为 null，并提示已有日志缺口。没有日志的日期不补 0，也不推断当天没学习；有日志的 0h 是明确零值。只有三天日志时，时长是这三天的合计，不代表其余四天投入为零。

数学模块满分沿用成绩口径：旧制真题选填/大题 56/94，2021 年起或模拟卷 80/70；选填专项只有 objective 模块。408 保留四科模块及题型得分。未记录的模块不补猜。

## 突破单事件

`manage_breakthrough.py` 在档案的每个突破单下保存 `- 事件记录：[...]` JSON。每个事件含 `timestamp / type / status / day / total_days`，按需带 `note / result`。

| type | 触发操作 | result |
| --- | --- | --- |
| `created` | create 新建 | 无 |
| `advanced` | update-status 实际推进 DayN | 无 |
| `extended` | close --result 延期，追加两天 | 无 |
| `closed` | close --result 已攻克/未通过/长期关注 | 通过/未通过/转长期关注 |
| `cancelled` | close --result 取消或原有放弃 | 无 |

默认 timestamp 为操作发生时的带时区北京时间。补记可以显式传 `--timestamp 2026-10-13T09:00:00+08:00`；只传 `--today YYYY-MM-DD` 则保留日期精度，不编造时分。两者同传须在北京时间属于同一天。幂等重试与单纯修改关闭备注不产生新的状态变化事件。

旧单只从今后的真实操作开始记录，不补造 created 或其他过去事件。无历史记录在周上下文中为 null；旧单新增了部分事件则输出本周已知事件，并通过 data_gaps 标明之前历史未知。

`build_weekly_plan.py` 已 deprecated：周计划决策已上移至 worker，本脚本仅保留作历史参考。保留文件和旧接口以兼容历史引用，新工作流调用只读聚合脚本。
