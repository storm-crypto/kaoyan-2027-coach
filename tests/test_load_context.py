"""test load_context.py"""
import json
import textwrap

from helpers import run_script


def _write_log(vault_root, day, blocker):
    log_path = vault_root / "学习日志" / f"{day}.md"
    log_path.write_text(textwrap.dedent(f"""\
        # Session: {day}

        ## 今日概览
        - **主题**: 数学 + 408
        - **时长**: 4
        - **模式**: 错题解析 / 复习

        ## 学到了什么
        - 数学二重积分区域判断更清楚了

        ## 卡壳与挣扎
        - {blocker}

        ## 下次需要复习
        - OS 调度和积分区域都要回看
    """), encoding="utf-8")


def _write_week_report(vault_root):
    report_path = vault_root / "复盘报告" / "2026-W12-周复盘.md"
    report_path.write_text(textwrap.dedent("""\
        # 周复盘：2026-W12

        ## 本周卡点
        - 408 进程调度题还是容易算乱

        ## 下周建议
        - 先拆 OS 调度专题
    """), encoding="utf-8")


def _write_mock_report(vault_root):
    report_path = vault_root / "复盘报告" / "2026-10-10-模考分析.md"
    report_path.write_text(textwrap.dedent("""\
        # 模考分析：2026-10-10

        ## 关键问题
        - 数学一 距目标还差 12 分，需要优先补。

        ## 下一步动作
        - 优先复盘 数学一：把失分点拆成 2-3 个小专题。
    """), encoding="utf-8")


def _write_due_card(vault_root, subject, filename, next_review, interval=2):
    card_dir = vault_root / "错题本" / subject / "专题"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / filename
    card.write_text(textwrap.dedent(f"""\
        ---
        source: test
        question_id: qid-load-{filename.replace('.md', '')}
        topic: {filename}
        first_wrong_at: 2026-03-01
        last_review_at: 2026-03-10
        wrong_count: 1
        status: 半会
        next_review: {next_review}
        review_interval: {interval}
        ease_factor: 2.50
        ---

        test
    """), encoding="utf-8")


def test_load_context_happy_path(sample_archive, vault_root):
    text = sample_archive.read_text(encoding="utf-8").replace("2026-12-20", "2026-12-25", 1)
    sample_archive.write_text(text, encoding="utf-8")
    _write_log(vault_root, "2026-10-12", "积分上下限一紧张还是会写反")
    _write_week_report(vault_root)
    _write_mock_report(vault_root)
    for index in range(11):
        _write_due_card(vault_root, "数学一", f"math-{index}.md", "2026-10-14", interval=1)

    rc, out, _ = run_script("load_context.py", [str(vault_root), "--today", "2026-10-16"])

    assert rc == 0
    data = json.loads(out)
    assert data["show_countdown"] is True
    assert data["days_until_exam"] == 70
    assert data["due_total"] == 11
    assert len(data["priorities"]) == 3
    assert "最早到期的 3-5 道旧题" in data["first_step"]
    assert "到期复习积压 11 道" in "\n".join(data["warnings"])
    assert data["latest_log_path"].endswith("2026-10-12.md")
    assert data["latest_report_path"].endswith("2026-10-10-模考分析.md")
    assert "考试倒计时" in data["markdown"]


def test_load_context_missing_fields(vault_root):
    archive = vault_root / "我的学习者档案.md"
    archive.write_text(textwrap.dedent("""\
        # 我的学习者档案

        ## 基本信息
        - **目标院校/专业**：计算机科学与技术
        - **当前目标总分**：
        - **考试日期**：（以当年公告为准）
        - **每日可投入时长**：
        - **最近更新日期**：2026-03-20
        - **当前阶段关键词**：

        ## 各科当前状态
        | 科目 | 当前水平 | 目标 | 差距 | 当前判断 |
        |------|----------|------|------|----------|
        | 政治 | 55 | 70 | 15 | 选择题基础薄 |
        | 数学一 | 105 | | | 计算和方法都要提速 |
        | 英语一 | 72 | | | 阅读速度偏慢 |
        | 408 | 92 | | | OS 和计网容易失分 |

        ## 模考成绩追踪
        | 日期 | 政治 | 数学一 | 英语一 | 408 | 总分 | 备注 |
        |------|------|--------|--------|-----|------|------|
        | 初始 | | | | | | 基准分 |

        ## 最近聚焦问题（只保留 3-5 条）
        - 数学专题推进

        ## 短板雷达
        | 短板 | 科目 | 严重度 | 证据 | 当前状态 | 下一步 |
        |------|------|--------|------|----------|--------|
        | | | | | | |

        ## 高频错误模式统计
        | 错误模式 | 科目 | 出现频率 | 最近一次出现 | 备注 |
        |----------|------|----------|--------------|------|
        | | | | | |

        ## 下一步建议（只保留 3 条）
        1. 先把数学专题打穿
    """), encoding="utf-8")

    rc, out, _ = run_script("load_context.py", [str(vault_root), "--today", "2026-10-16"])

    assert rc == 0
    data = json.loads(out)
    assert "考试日期" in data["missing_fields"]
    assert "每日可投入时长" in data["missing_fields"]
    assert "当前目标总分" in data["missing_fields"]
    assert "数学一目标分" in data["missing_fields"]
    assert any("还没有学习日志" in item for item in data["warnings"])
    assert any("还没有复盘或模考报告" in item for item in data["warnings"])
