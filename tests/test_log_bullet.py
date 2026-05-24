"""test log_bullet.py"""
import sys
from datetime import date

from helpers import SCRIPTS_DIR  # noqa: F401

sys.path.insert(0, str(SCRIPTS_DIR))

from log_bullet import (  # noqa: E402
    collect_textbook_progress,
    extract_log_bullets,
    group_by_chapter,
    is_placeholder_bullet,
    parse_log_bullet,
    render_bullet_with_date,
    unbucketed_bullets,
)


def test_parse_log_bullet_with_full_structure():
    b = parse_log_bullet("学习::分段函数可导性的 4 种讨论模板 (数学一·高数·ch2) 信心:中高", date(2026, 5, 19))
    assert b.kind == "学习"
    assert b.content == "分段函数可导性的 4 种讨论模板"
    assert b.subject == "数学一"
    assert b.subgroup == "高数"
    assert b.subgroup_canonical == "高等数学"
    assert b.chapter_num == 2
    assert b.extras == "信心:中高"
    assert b.chapter_key == ("数学一", "高等数学", 2)


def test_parse_log_bullet_legacy_form_no_prefix():
    """没有 类型:: 前缀的旧 bullet 也要能解析（视为未分类）。"""
    b = parse_log_bullet("反函数二阶求导题型识别不稳", date(2026, 5, 22))
    assert b.kind == "未分类"
    assert b.content == "反函数二阶求导题型识别不稳"
    assert b.subject == ""
    assert b.chapter_key is None


def test_parse_log_bullet_supports_408_format():
    b = parse_log_bullet("学习::B+ 树的删除流程 (408·DS·ch3)", date(2026, 5, 20))
    assert b.subject == "408"
    assert b.subgroup_canonical == "数据结构"
    assert b.chapter_num == 3


def test_parse_log_bullet_chapter_tag_without_subgroup():
    b = parse_log_bullet("卡点::ch1 极限的换元题 (英语一·ch1)", date(2026, 5, 20))
    assert b.subject == "英语一"
    assert b.chapter_num == 1
    assert b.subgroup == ""


def test_is_placeholder_bullet_matches_known_fallbacks():
    assert is_placeholder_bullet("今天没有显式记录卡点。")
    assert is_placeholder_bullet("暂无明确记录")
    assert is_placeholder_bullet("今天的收获还比较散，建议明天补成更具体的知识点。")
    assert not is_placeholder_bullet("反函数二阶求导题型识别不稳")


def test_extract_log_bullets_filters_placeholders(tmp_path):
    text = """# Session: 2026-05-22

## 学到了什么
- 今天的收获还比较散，建议明天补成更具体的知识点。
- 学习::分段函数可导性 (数学一·高数·ch2)

## 卡壳与挣扎
- 今天没有显式记录卡点。
- 卡点::反函数二阶求导识别 (数学一·高数·ch2)
"""
    learned = extract_log_bullets(text, "学到了什么", date(2026, 5, 22))
    assert len(learned) == 1
    assert learned[0].content == "分段函数可导性"

    blockers = extract_log_bullets(text, "卡壳与挣扎", date(2026, 5, 22))
    assert len(blockers) == 1
    assert blockers[0].content == "反函数二阶求导识别"


def test_render_bullet_with_date_includes_chapter_tag():
    b = parse_log_bullet("学习::分段函数 (数学一·高数·ch2)", date(2026, 5, 19))
    out = render_bullet_with_date(b)
    assert out == "[05-19] 学习: 分段函数 (数学一·高等数学·第2章)"


def test_group_by_chapter_buckets_correctly():
    bullets = [
        parse_log_bullet("学习::A (数学一·高数·ch1)", date(2026, 5, 18)),
        parse_log_bullet("学习::B (数学一·高数·ch1)", date(2026, 5, 19)),
        parse_log_bullet("学习::C (数学一·线代·ch1)", date(2026, 5, 20)),
        parse_log_bullet("学习::D 无章节标签", date(2026, 5, 21)),
    ]
    groups = group_by_chapter(bullets)
    assert ("数学一", "高等数学", 1) in groups
    assert ("数学一", "线性代数", 1) in groups
    assert len(groups[("数学一", "高等数学", 1)]) == 2
    assert len(unbucketed_bullets(bullets)) == 1


def test_collect_textbook_progress_aggregates_range():
    bullets = [
        parse_log_bullet("教材::李林高数辅导讲义 推进到 p48 (数学一·高数·ch2)", date(2026, 5, 18)),
        parse_log_bullet("教材::李林高数辅导讲义 推进到 p50 (数学一·高数·ch2)", date(2026, 5, 19)),
        parse_log_bullet("教材::李林高数辅导讲义 推进到 p56 (数学一·高数·ch2)", date(2026, 5, 22)),
    ]
    progress = collect_textbook_progress(bullets)
    assert len(progress) == 1
    p = progress[0]
    assert p.name == "李林高数辅导讲义"
    assert p.earliest_page == 48
    assert p.latest_page == 56
    assert p.earliest_day == date(2026, 5, 18)
    assert p.latest_day == date(2026, 5, 22)


def test_collect_textbook_progress_supports_range_form():
    bullets = [
        parse_log_bullet("教材::李林高数 p48 → p56", date(2026, 5, 19)),
    ]
    progress = collect_textbook_progress(bullets)
    assert progress[0].earliest_page == 48
    assert progress[0].latest_page == 56


def test_collect_textbook_progress_multiple_books():
    bullets = [
        parse_log_bullet("教材::李林高数 推进到 p50", date(2026, 5, 19)),
        parse_log_bullet("教材::王道数据结构 推进到 p30", date(2026, 5, 20)),
        parse_log_bullet("教材::李林高数 推进到 p56", date(2026, 5, 22)),
    ]
    progress = collect_textbook_progress(bullets)
    names = {p.name for p in progress}
    assert names == {"李林高数", "王道数据结构"}
