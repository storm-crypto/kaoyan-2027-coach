# 整卷记录与突破单数据契约

Muse 负责判定错误类型、选疗程和解释趋势；脚本只关联结构化记录、计算与读写。

## `/wrong` → `/score` 自动关联

- 新卡归档时传 `--question-number`；数学卡片可保存 1–23（容纳旧制），408 为 1–47。写成绩时统一调用 `_question_limit(subject, paper, paper_type, section)`：整卷模拟上限 22，真题明确年份 ≤2020 时上限 23，其他真题上限 22；选填旧制上限 14，其他上限 16；408 整卷上限 47。手动错题、考点参数与自动关联使用相同规则。
- `--error-type` 可选：`没思路 / 遗忘 / 计算失误 / 思路偏差 / 时间不够`。由 Muse 根据实际作答选择，省略时不猜。
- `/score --paper "2010 数学一真题" --date YYYY-MM-DD` 关联同科、同卷且该练习日期有错误事件的卡。卷名允许空白/全角字符差异；来源可为完整卷名或“卷名第N题”，不做子串匹配。
- 题号优先看 `question_number`，再看明确来源后缀或题面/locator 开头的编号。多个来源冲突、缺失题号或同题号对应多个 qid 时跳过并返回 `link_warnings`；qid 哈希不能反推题号。
- 成绩文件的 `## 卷子错题` JSON 每项含 `question_number / error_description / record_date`，关联成功时另含 `topic / chapter_id / question_id / card_path / error_type`。
- `--wrong-questions` 是手动覆盖：只写所列题号，空字符串清空。省略时自动关联；没有可关联项时保留已有记录。`--question-topics` 只供手动记录明确考点，不从错误自述推断。
- `--issues` 可选，用户只给分数时不强制补写自由文本。自动关联只读卡片，支持来源末尾的“选填”，如 `2010 数学一真题选填`。

## 选填专项

```sh
python3 scripts/record_paper_score.py "$OBSIDIAN_ROOT" 数学一 \
  --section 选填 --paper 2010真题 --paper-type 真题 --total 40 \
  --wrong-questions "3:不会"
```

- `--section` 为 `整卷`（默认）或 `选填`，选填仅支持数学一。
- 选填的 `total_score` 与 `score_objective` 同值，不存 `score_big`；frontmatter 保存 `section: 选填` 和 `max_score`。旧制真题满分 56，2021 年起、年份不明的真题及模拟卷满分 80。
- 成绩文件采用 `日期-选填-卷型-卷名.md`，与同日同卷的整卷记录分别保存。同一范围重复记录覆盖原文件。
- 档案写入 `## 数学一选填专项成绩追踪` 的七列表：日期、卷型、卷子、选填得分、满分、主要问题、备注。不会修改或迁移整卷成绩表。
- `collect_score_records` 默认只读整卷；传 `section='选填'` 读专项，`section=None` 读取两类。`analyze_paper.py` 和既有总分趋势默认只读整卷；需要专项序列时显式传 `--section 选填`。
- 触发检查读取两类成绩，同卷同日同题的重复摘要合并；模块低得分率信号包含 `section`。Sheets 同步由 Muse 按该字段路由。

## 触发证据

`check_breakthrough_triggers.py --days 3` 使用含今天的 3 个自然日窗口：

- `triggered`：错误事件按同科 `chapter_id` 聚合；缺少 id 的旧卡按明确 `topic` 聚合，≥3 次才输出。题号/日期明确关联的成绩错题和卡片首次事件合并，首次归档及完全相同的历史行去重。
- `strong_signals`：`reason=module_accuracy` 表示窗口内某模块得分率 <0.6；`reason=consecutive_failures` 表示单卡当前连续复习“不会”≥3次，包含 qid、路径、考点和次数，不受 3 天窗口限制。没有信号时该字段省略。
- `unmapped`：错误事件缺少 `chapter_id` 和 `topic`。不能靠 `error_description`、知识地图词汇或历史累计 `wrong_count` 补猜。
- 新卡 `consecutive_failures=0`；每次复习“不会”+1，“半会/会”清零。旧卡缺少字段时先从复习历史计算，排除首次归档；首次更新后写入缓存。SRS 仍采用整数天、最短 1 天。

开单由 Muse 决定，脚本不自动开单。

## 疗程对口验收

开单时重复传 `--topic-id`，值采用错题卡的规范 `chapter_id`：

```sh
python3 scripts/manage_breakthrough.py create "$OBSIDIAN_ROOT" \
  --goal "二重积分验收" --source "2010 数学一真题" \
  --plan "Day1：重做;Day2：变式;Day3：验收" --criteria "5题对4题" \
  --topic-id math1:gaoshu:10:02
python3 scripts/build_knowledge_test.py "$OBSIDIAN_ROOT" 数学一 \
  --breakthrough-id 突破单-20261012-01 --count 5
```

- 突破单的 `- 考点IDs：[...]` 保存 JSON 字符串列表，解析为 `topic_ids`；旧单缺省 `[]`。延期、推进和关闭保留此列表。
- Muse 在验收时传 `--breakthrough-id`，脚本优先抽对应叶子（包含已标“会”的点），不足题量再补普通弱项。
- 缺 id 或全部不匹配时返回错误；部分不匹配时通过 `unmatched_topic_ids` 提示。普通 `/test` 的弱项选择规则不变。

## 纵向序列

```sh
python3 scripts/analyze_paper.py "$OBSIDIAN_ROOT" --subject 数学一 \
  --start-date 2026-10-01 --end-date 2026-10-12
```

`--paper` 可重复，精确筛选卷名；不传筛选条件返回该科整卷全序列。`--section 选填` 单独选择专项序列。日期边界均包含，排序为练习日期、卷型、卷名。

- `papers`：每套的 `date / paper / paper_type / total_score / modules / topic_wrong_counts / record_path`。
- 数学整卷 `modules.objective / big` 使用现有 `score_objective / score_big`。真题明确年份 ≤2020 时满分 56 / 94；2021 年起、年份不明的真题及模拟卷为 80 / 70。选填专项只输出 `objective`，同样按卷型/年份取满分 56 或 80。分析和低得分率触发共用此口径，`accuracy=score/max_score`。
- 408 `modules.DS / CO / OS / CN` 保留四科各自的 `choice / big` 原始分数；两部分齐全时求 `score` 和 `accuracy`，满分依次 45 / 45 / 35 / 25。[考试结构来源](https://www.tup.tsinghua.edu.cn/bookscenter/bookpreface?id=08987801)
- 未提供的细分得分字段省略；缺少 408 任一部分时不计算该科总得分率。旧记录不迁移、不补写。
- `topic_wrong_count_series`：每个明确 topic 的逐卷错题数序列，零值表示已记录的该考点错题数为 0；不推断未记录的作答。不计算 topic 正确率。
- 旧记录缺少卷面错题时可以只读关联同卷同日期的卡；显式手动清空的记录保留空列表。缺题号/考点等信息通过 `warnings` 提示。
- 输出仅数据，不写 vault、不做趋势解读、不生成图表。
