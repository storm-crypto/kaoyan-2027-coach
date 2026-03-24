# Kaoyan 2027 Coach（考研 2027 全科答疑教练）

面向 2027 考研的 Obsidian 驱动型 AI 学习教练。这个 skill 把建档、答疑、错题归档、间隔复习、今日/周计划、学习日志、周月复盘和模考校准串成一个可持续使用的闭环。

## 功能概览

- 支持数学一、408、政治、英语一四科
- 首次 `/load` 自动初始化 Obsidian 学习档案
- `/wrong` 负责讲题并把错题归档到本地 Markdown
- `/review` 按 SRS 扫描到期卡片并更新掌握度
- `/plan_today`、`/plan_week` 负责学习节奏安排
- `/progress`、`/recap`、`/recalibrate` 负责日志、复盘和策略校准
- 所有学习状态都外置到本地文件，跨 AI 工具可恢复

## 适合谁

- 想把“和 AI 聊题”变成“可持续沉淀的学习系统”的考研用户
- 已经在用 Obsidian，想把错题、日志、计划和复盘统一起来的人
- 希望在 Codex、Claude Code、Gemini CLI、Antigravity 等支持 skills 的工具里复用同一套学习状态的人

## Quick Start

### 1. 安装 skill

```bash
bash setup.sh
```

这个脚本会检查 `python3`，并为 `~/.claude/skills/` 和 `~/.codex/skills/` 创建软链接。

### 2. 配置 Obsidian 路径

把下面这行加入 `~/.zshrc` 或 `~/.bashrc`：

```bash
export KAOYAN_OBSIDIAN_ROOT="/path/to/your/obsidian/vault/Kaoyan_2027_Prep"
```

然后重新加载 shell：

```bash
source ~/.zshrc
```

### 3. 开始使用

进入支持 skills 的 AI 工具后，直接发送：

```text
/load
```

如果是第一次建档，也可以把基础信息一起发出去：

```text
/load 我准备考某大学计算机，目标总分 360，考试日期 2026-12-20，每天可投入 6 小时，现在处于 408 重构期。
```

接下来常见的日常动作是：

```text
/plan_today 6h
/wrong 数学一 这道题我卡在第一步
/progress 今天做了哪些内容...
```

普通使用者不需要手动运行 `scripts/` 里的 Python 脚本；正常情况下直接通过对话指令使用即可。

## 文档

- [完整使用文档](docs/USAGE.md)
- [开发维护说明](docs/MAINTAINING.md)

如果你是第一次接触这个 skill，建议先看 `完整使用文档`。  
如果你准备继续迭代脚本、模板或 `SKILL.md`，再看 `开发维护说明`。

## 仓库结构

- `SKILL.md`：skill 触发与行为规则
- `scripts/`：建档、归档、复习、复盘等确定性脚本
- `templates/`：Obsidian Markdown 模板
- `references/`：数学一和 408 的专项答疑参考
- `tests/`：主要脚本的回归测试

## 开发验证

```bash
python3 -m pytest tests/ -v
```

