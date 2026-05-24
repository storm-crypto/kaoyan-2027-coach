# Kaoyan 2027 Coach 开发维护说明

这份文档面向维护者，而不是最终使用者。  
如果你只是想安装和使用这个 skill，请回到 `README.md` 或直接阅读 `docs/USAGE.md`。

## 维护目标

维护这个仓库时，最重要的不是“多写几段说明”，而是保持下面三件事一致：

- `SKILL.md` 里的行为规则
- `scripts/` 和 `templates/` 的真实能力
- 用户文档里的承诺

一旦三者脱节，就会出现：

- README 写得很好看，但实际不会触发
- 指令名或参数在文档里和真实行为不一致
- 模板结构改了，脚本和测试却没跟上

## 建议修改顺序

推荐按这个顺序做改动：

1. 先改 `SKILL.md`
2. 再改 `scripts/` 或 `templates/`
3. 再补 `tests/`
4. 最后改 `README.md` 和 `docs/USAGE.md`

原因如下：

- `SKILL.md` 决定 agent 的行为边界和调用规则
- `scripts/` 决定真正的落盘与计算逻辑
- `templates/` 决定生成出来的 Markdown 结构
- `tests/` 用来兜住回归
- 文档应该描述真实能力，而不是领先于实现

## 仓库重点目录

- `SKILL.md`
  触发条件、工作流、硬约束和指令语义
- `scripts/`
  Python 脚本实现，负责建档、归档、复习、复盘、模考分析等
- `templates/`
  所有 Markdown 模板
- `references/`
  数学一和 408 的专项答疑参考
- `tests/`
  回归测试
- `README.md`
  仓库首页，保持简洁
- `docs/USAGE.md`
  最终用户的完整使用手册

## 常见改动应该怎么改

### 新增一个指令

至少同步检查这些位置：

- `SKILL.md` 的指令说明
- 对应 `scripts/` 实现
- `README.md` 的功能概览或 quickstart
- `docs/USAGE.md` 的指令详解和示例
- 必要的 `tests/`

### 修改某个指令的参数或行为

重点检查：

- 文档中的命令示例是否还正确
- 旧参数名是否还残留在 README 或使用文档里
- 测试是否覆盖新旧分支

### 调整 Markdown 落盘结构

重点检查：

- `templates/` 是否更新
- 解析模板的脚本是否同步
- 依赖字段名的测试是否同步
- `docs/USAGE.md` 的“文件会写到哪里”是否还准确

### 新增学科支持

至少补齐这些部分：

- 知识地图模板
- 脚本中的学科分支
- `SKILL.md` 的学科说明

### 笔记追踪相关改动

涉及「今日新增笔记」「知识沉淀」「知识地图覆盖」的改动，重点关注：

- `scripts/note_scan.py`：扫描 `知识笔记/`，按 frontmatter `created` 分组的核心模块。`extract_chapter_num` 是打通 知识笔记 / 错题本 / 知识地图 三处不同章节命名的唯一归一化函数，其他需要做跨表对照的逻辑都应复用它
- `scripts/knowledge_map_parser.py`：解析 `知识地图/{科目}.md` 的章节表头，返回 `{科目: [ChapterEntry(subgroup, chapter_num, chapter_name)]}`。月复盘的覆盖度统计依赖它
- `scripts/log_progress.py`：`main` 开头会跑 `auto_fill_created_frontmatter`（幂等），日志段「今日新增笔记」每次重跑都重生成，**不走 `merge_with_existing`**——这是因为该段由文件系统派生，不存在"用户手写后被脚本覆盖"的风险
- `scripts/build_recap.py`：`collect_note_stats / collect_wrong_exposure / collect_cross_signals` 周/月通用；`collect_coverage` 仅月复盘调用，依赖 `knowledge_map_parser`

### 周/月复盘渲染相关改动

涉及"产出聚类/教材进度/wikilink/智能建议"的改动，重点关注：

- `scripts/log_bullet.py`：把日志的每条 bullet 解析成结构化 `LogBullet(day, kind, content, subject, subgroup_canonical, chapter_num, extras)`。新增功能必须复用此模块，避免对原始字符串做正则
- `PLACEHOLDER_BULLETS` 集合：`log_progress.py:bullet_list` 写入的兜底文案集合，`extract_log_bullets` 自动过滤；新增兜底文案需同步加进这个集合
- `group_by_chapter` / `collect_textbook_progress`：聚合工具。周复盘的"学习产出"按章节聚类、教材进度区间合并都依赖它们
- `build_recap.py:_format_chapter_key(key, chapter_activity)`：渲染章节 wikilink 的统一入口。传入 `chapter_activity` 时会用 `first_card_path` 生成 obsidian 双链；不传则降级为纯文本
- `build_recap.py:build_next_actions`：智能建议生成器。新增建议条件时优先级清晰：only-drilling > only-theory > 顽固卡集中 > 章节积压主线 > blocker > 复习节奏 > 覆盖度

### 改 `bullet_list` 的兜底文案

`log_progress.py:bullet_list` 在用户没传字段时写的占位符（"今天没有显式记录卡点。"等）必须**不是** `- ` 形态，避免被 `extract_log_bullets` 误抓。当前实现用 `_（...）_` 斜体非列表项；新增字段保持这个约定。同时把字面文案加入 `log_bullet.PLACEHOLDER_BULLETS` 兜底（历史日志里残留的旧占位符仍要能被过滤）。
- 使用文档里的支持范围
- 回归测试

## 提交前自查清单

提交前建议逐项确认：

1. `README.md` 是否仍然简洁，且只保留功能介绍、quickstart 和文档入口
2. `docs/USAGE.md` 是否已经覆盖新增或变更后的真实用法
3. `SKILL.md` 中的指令名、参数名、行为约束是否和脚本一致
4. `templates/` 的字段名变化是否同步到脚本和测试
5. 是否残留旧路径、旧命令、旧示例
6. 是否新增了未被文档说明的行为变化

## 测试

运行完整测试：

```bash
python3 -m pytest tests/ -v
```

如果只是改某一块，也建议至少运行相关测试文件。

## 文档边界约定

为了避免文档越写越乱，建议保持下面的边界：

- `README.md`
  仓库首页摘要，只放功能概览、quickstart、文档入口、最少量开发信息
- `docs/USAGE.md`
  面向最终用户的完整使用文档
- `docs/MAINTAINING.md`
  面向维护者的工作流和检查清单
- `SKILL.md`
  面向 agent 的真实行为规范，不承担用户教程职责

## 一个实用原则

任何时候只要你新增、删除或改变了某个能力，都问自己两个问题：

1. 这个变化是否已经真实实现并能通过测试
2. 用户从 `README.md` 和 `docs/USAGE.md` 看到的内容，是否和真实行为一致

如果这两个问题都能回答“是”，这次改动通常就比较稳。

