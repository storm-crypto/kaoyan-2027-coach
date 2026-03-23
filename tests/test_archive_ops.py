"""test archive_ops.py"""
import sys
import textwrap
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from archive_ops import (
    extract_heading_block,
    extract_list_items,
    load_template_markdown,
    parse_daily_hours,
    parse_mock_rows,
    parse_score_cell,
    parse_subject_targets,
    replace_heading_block,
    upsert_mock_row,
)


def test_extract_heading_block_supports_level_two_and_three():
    text = textwrap.dedent("""\
        ## 短板雷达
        - 条目 A
        - 条目 B

        ### 子标题
        - 忽略

        ## 下一步建议（只保留 3 条）
        1. 下一步
    """)
    assert extract_heading_block(text, "短板雷达", level=2).startswith("- 条目 A")

    card = textwrap.dedent("""\
        ### 题目
        - 这是题干

        ### 选项（如有）
        - A
        - B
    """)
    assert extract_heading_block(card, "题目", level=3) == "- 这是题干"


def test_extract_heading_block_ignores_indented_code_block_heading():
    text = textwrap.dedent("""\
        ## 正常区块
        - 条目

            ## 代码块里的伪标题
            - 不应命中
    """)
    assert extract_heading_block(text, "代码块里的伪标题", level=2) == ""


def test_replace_heading_block_rewrites_section_body():
    text = textwrap.dedent("""\
        ## 下一步建议（只保留 3 条）
        1. 旧建议

        ## 其他区块
        - 保留
    """)
    updated = replace_heading_block(text, "下一步建议（只保留 3 条）", "1. 新建议", level=2)
    assert "1. 新建议" in updated
    assert "旧建议" not in updated
    assert "## 其他区块" in updated


def test_extract_list_items_and_parse_daily_hours():
    text = textwrap.dedent("""\
        ## 基本信息
        - **每日可投入时长**：6.5

        ## 最近聚焦问题（只保留 3-5 条）
        - 数学提速
        2. 408 补漏
    """)
    assert parse_daily_hours(text) == 6.5
    assert extract_list_items(text, "最近聚焦问题（只保留 3-5 条）") == ["数学提速", "408 补漏"]


def test_parse_subject_targets_and_mock_rows():
    text = textwrap.dedent("""\
        ## 各科当前状态
        | 科目 | 当前水平 | 目标 | 差距 | 当前判断 |
        |------|----------|------|------|----------|
        | 政治 | 55 | 70 | 15 | 选择题基础薄 |
        | 数学一 | 105 | 125 | 20 | 计算和方法都要提速 |

        ## 模考成绩追踪
        | 日期 | 政治 | 数学一 | 英语一 | 408 | 总分 | 备注 |
        |------|------|--------|--------|-----|------|------|
        | 2026-03-01 | 60 | 110 | 76 | 92 | 338 | 阶段基准 |
    """)
    targets = parse_subject_targets(text)
    assert targets["政治"] == 70
    assert targets["数学一"] == 125
    rows = parse_mock_rows(text)
    assert rows[0]["date"] == "2026-03-01"
    assert parse_score_cell(rows[0]["总分"]) == 338


def test_upsert_mock_row_replaces_same_date():
    text = textwrap.dedent("""\
        ## 模考成绩追踪
        | 日期 | 政治 | 数学一 | 英语一 | 408 | 总分 | 备注 |
        |------|------|--------|--------|-----|------|------|
        | 2026-03-01 | 60 | 110 | 76 | 92 | 338 | 阶段基准 |
    """)
    updated = upsert_mock_row(text, {
        "date": "2026-03-01",
        "政治": "61",
        "数学一": "111",
        "英语一": "77",
        "408": "93",
        "总分": "342",
        "备注": "更新后",
    })
    assert updated.count("2026-03-01") == 1
    assert "342" in updated


def test_load_template_markdown_extracts_fenced_markdown(tmp_path, monkeypatch):
    template_dir = tmp_path / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "demo.md").write_text(textwrap.dedent("""\
        # 模板说明

        ```markdown
        # Demo
        body
        ```
    """), encoding="utf-8")
    monkeypatch.setenv("KAOYAN_SKILL_ROOT", str(tmp_path))

    content = load_template_markdown("demo.md")

    assert content == "# Demo\nbody"


def test_load_template_markdown_requires_fenced_markdown(tmp_path, monkeypatch):
    template_dir = tmp_path / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "broken.md").write_text("# 没有 fenced markdown\n", encoding="utf-8")
    monkeypatch.setenv("KAOYAN_SKILL_ROOT", str(tmp_path))

    with pytest.raises(ValueError, match="fenced block"):
        load_template_markdown("broken.md")
