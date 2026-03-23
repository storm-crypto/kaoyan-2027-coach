# Kaoyan 2027 Coach (考研2027全科答疑教练)

考研全科 AI 答疑教练，聚焦三件事：**把题讲明白、把短板记清楚、把明天要干什么排出来。**

深度集成 Obsidian，所有学习状态外置到本地 Markdown 文件，跨 AI 工具可恢复。

## 跨平台设置

此 skill 使用标准 SKILL.md 格式，兼容 Claude Code、Codex、Gemini CLI、Antigravity、Cursor 等工具。

**一键设置：**
```bash
bash setup.sh
```

**手动设置：**
```bash
# 1. 创建 symlink（只需执行一次）
ln -sf ~/.gemini/antigravity/skills/kaoyan-2027-coach ~/.claude/skills/kaoyan-2027-coach
ln -sf ~/.gemini/antigravity/skills/kaoyan-2027-coach ~/.codex/skills/kaoyan-2027-coach

# 2. 设置环境变量（加到 ~/.zshrc 或 ~/.bashrc）
export KAOYAN_OBSIDIAN_ROOT="/path/to/your/obsidian/vault/Kaoyan_2027_Prep"
```

## 前置条件

- Python 3.6+（脚本仅依赖标准库）
- Obsidian vault（首次 `/load` 自动创建目录结构）

## 文件结构

```
kaoyan-2027-coach/
├── SKILL.md                     ← 核心指令与规则
├── setup.sh                     ← 跨平台设置脚本
├── scripts/                     ← 自动化脚本（输出 JSON，支持环境变量）
│   ├── frontmatter.py           ← 共享 YAML frontmatter 解析
│   ├── env_util.py              ← 共享工具函数（环境变量、原子写入、iCloud 检测）
│   ├── archive_ops.py           ← 学习者档案/模板解析辅助
│   ├── init_vault.py            ← 初始化 vault，并可注入首次建档信息
│   ├── generate_question_id.py  ← 生成稳定题卡主键（SHA1）
│   ├── scan_due_reviews.py      ← 扫描到期错题 + 超期降级
│   ├── find_card.py             ← 搜索已有错题卡（判断新旧）
│   ├── update_card.py           ← 更新错题卡（含改进版 SRS + ease_factor）
│   ├── update_knowledge_map.py  ← 更新知识地图掌握度
│   ├── load_context.py          ← 读取档案/最新日志/最新报告，生成 /load 上下文
│   ├── build_daily_plan.py      ← 生成今日计划
│   ├── build_weekly_plan.py     ← 生成周计划
│   ├── build_recap.py           ← 生成周/月复盘
│   ├── log_progress.py          ← 写学习日志并按需回写档案
│   └── analyze_mock_exam.py     ← 记录模考+策略校准
├── references/
│   ├── math-coaching.md         ← 数学答疑参考，保持 SKILL.md 精简
│   └── 408-coaching.md          ← 408 答疑参考，强化概念边界与选项辨析
├── templates/
│   ├── 错题追踪卡模板.md
│   ├── 今日计划模板.md
│   ├── 学习日志模板.md
│   ├── 学习者档案与知识地图模板.md
│   ├── 周计划模板.md
│   ├── 周复盘模板.md
│   ├── 月复盘模板.md
│   └── 模考分析模板.md
└── tests/                       ← pytest 测试
```

## 指令速查

| 指令 | 作用 |
|------|------|
| `/load` | 恢复学习上下文（首次使用走脚本化建档） |
| `/wrong [科目] [题目]` | 全科错题解析（科目可省略，自动判断） |
| `/plan_today [时长]` | 今日学习清单 |
| `/plan_week [本周总时长]` | 生成本周学习计划 |
| `/progress [心得]` | 今日收尾 + 归档 |
| `/review` | 扫描到期错题，逐题复习 |
| `/recap [week\|month]` | 周/月复盘（默认周） |
| `/test [章节]` | 基于知识地图选题测试 |
| `/recalibrate 政治=62 ...` | 记录模考+策略校准 |
| `/mock [科目] [题量]` | 限时训练 |

概念解释、知识串联、解题挑错、Anki 卡片生成等直接用自然语言对话，无需专门指令。

## 设计原则

- **档案是唯一事实源**：个人信息全在 `我的学习者档案.md`，SKILL.md 不硬编码
- **错题驱动**：通过 `/wrong` 自然填充知识地图
- **轻量归档**：单次错题只落错题本，`/progress` 统一收尾
- **初始化收口**：首次建档通过 `init_vault.py` 完成目录、模板和基础档案字段注入
- **周/月复盘闭环**：周计划、周/月复盘、模考分析都有脚本落地
- **防幻觉**：考频定性描述，禁止编造真题题号
- **题卡去重**：`question_id`（SHA1）做主键，防止重复
- **改进版 SRS**：含 ease_factor 的间隔复习算法，上限 90 天

## 运行测试

```bash
python3 -m pytest tests/ -v
```
