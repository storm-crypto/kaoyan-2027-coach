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


# --- 隐式章节推断 ---


def test_parse_bullet_infers_subject_from_textbook_name():
    """没显式 (科目·...) 标签，但 bullet 内提到「李林高数」应能反推数学一·高数。"""
    b = parse_log_bullet("李林高数辅导讲义推进到 p50", date(2026, 5, 19))
    assert b.subject == "数学一"
    assert b.subgroup_canonical == "高等数学"
    # 没章节关键词 → chapter_num = None，落入逐日分组
    assert b.chapter_num is None
    assert b.chapter_key is None


def test_parse_bullet_infers_chapter_from_keyword():
    """文本里出现「可导性」「导数与微分」等关键词时反推第 2 章。"""
    b = parse_log_bullet("在 Gemini 老师帮助下，明显加深了对可导性常用结论的理解", date(2026, 5, 20))
    # 关键词 "可导性" → 高数 ch2，但 subject 还得先被定位到
    # 这里没出现"高数"关键词，所以推断不出 subject → chapter_num 也为 None
    assert b.subject == ""

    b2 = parse_log_bullet("完成若干导数与微分相关卡点的归档与修正（数学一·高数）", date(2026, 5, 19))
    # 显式标签给出 subject+subgroup，缺章节号 → 关键词推断补 ch2
    assert b2.subject == "数学一"
    assert b2.subgroup_canonical == "高等数学"
    assert b2.chapter_num == 2

    b3 = parse_log_bullet("李林高数辅导讲义 ch2 可导性的常用结论", date(2026, 5, 24))
    # 主题词「李林高数」推 subject；内嵌 chN 直接给出章节号
    assert b3.subject == "数学一"
    assert b3.subgroup_canonical == "高等数学"
    assert b3.chapter_num == 2


def test_parse_bullet_explicit_tag_overrides_inference():
    """显式 (科目·subgroup·chN) 永远优先，不被关键词推断覆盖。"""
    b = parse_log_bullet("学习::中值定理 (数学一·线代·ch1)", date(2026, 5, 20))
    # 文本里有「中值定理」会推到高数 ch3，但显式标签把它定位到线代 ch1
    assert b.subgroup == "线代"
    assert b.subgroup_canonical == "线性代数"
    assert b.chapter_num == 1


def test_parse_bullet_inline_chapter_zh():
    b = parse_log_bullet("教材::李林高数辅导讲义 第三章 微分中值定理", date(2026, 5, 20))
    assert b.subject == "数学一"
    assert b.chapter_num == 3


def test_parse_bullet_inference_skips_when_no_keyword():
    """完全自由文本 → 无 subject 推断，bullet 落入未归章节。"""
    b = parse_log_bullet("反函数二阶求导题型识别不稳", date(2026, 5, 22))
    # "反函数二阶求导" 在 ch2 关键词列表里，但没有 subject 关键词 → 整体不推断
    assert b.subject == ""
    assert b.chapter_key is None
