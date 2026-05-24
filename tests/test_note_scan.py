"""test note_scan.py"""
import textwrap
from datetime import date

import pytest

from helpers import SCRIPTS_DIR  # noqa: F401  确保 scripts 路径在 sys.path 中
import sys
sys.path.insert(0, str(SCRIPTS_DIR))

from note_scan import (  # noqa: E402
    NoteEntry,
    auto_fill_created_frontmatter,
    count_missing_created,
    entry_chapter_key,
    extract_chapter_num,
    normalize_subgroup,
    parse_note_path,
    render_recap_notes_block,
    render_today_notes_section,
    scan_all_notes,
    scan_notes_in_range,
)


def test_extract_chapter_num_handles_three_naming_styles():
    assert extract_chapter_num("ch1 函数 极限 连续") == 1
    assert extract_chapter_num("ch10 复杂分析") == 10
    assert extract_chapter_num("03第三章微分中值定理与泰勒公式") == 3
    assert extract_chapter_num("01 第一章 函数、极限、连续") == 1
    assert extract_chapter_num("第十二章 多元函数") == 12
    assert extract_chapter_num("第二十一章 测试") == 21
    assert extract_chapter_num("第一百零五章 极端测试") == 105
    assert extract_chapter_num("") is None
    assert extract_chapter_num("学习方法探索") is None


def test_extract_chapter_num_handles_bare_leading_number():
    """408/政治/英语一 知识地图常用 `NN 章名` 的格式，没有 `第N章` 字样。"""
    assert extract_chapter_num("01 线性表") == 1
    assert extract_chapter_num("03 树与二叉树") == 3
    assert extract_chapter_num("01 马克思主义哲学") == 1
    assert extract_chapter_num("07 输入输出系统") == 7


def test_extract_chapter_num_rejects_dates_and_years():
    """不能把日期或年份误识别成章节号。"""
    assert extract_chapter_num("2026-05-24") is None
    assert extract_chapter_num("2026") is None
    assert extract_chapter_num("2026 年") is None  # 4 位数字


def test_normalize_subgroup_aliases():
    assert normalize_subgroup("数学一", "高数") == "高等数学"
    assert normalize_subgroup("数学一", "线代") == "线性代数"
    assert normalize_subgroup("数学一", "概率") == "概率论与数理统计"
    assert normalize_subgroup("408", "DS") == "数据结构"
    assert normalize_subgroup("408", "OS") == "操作系统"
    # 已是规范名则不变
    assert normalize_subgroup("数学一", "高等数学") == "高等数学"
    # 未知科目原样返回
    assert normalize_subgroup("英语一", "词汇") == "词汇"
    # 空串
    assert normalize_subgroup("数学一", "") == ""


def test_entry_chapter_key_uses_normalized_subgroup():
    entry = NoteEntry(
        path_rel="知识笔记/数学一/高数/ch1/A.md",
        subject="数学一", subgroup="高数",
        chapter_raw="ch1", chapter_num=1,
        title="A", created=date(2026, 5, 20),
    )
    # subgroup 简称应被规范化到全称
    assert entry_chapter_key(entry) == ("数学一", "高等数学", 1)

    entry_no_chapter = NoteEntry(
        path_rel="知识笔记/数学一/学习方法.md",
        subject="数学一", subgroup="",
        chapter_raw="", chapter_num=None,
        title="学习方法", created=date(2026, 5, 20),
    )
    assert entry_chapter_key(entry_no_chapter) is None


def test_parse_note_path_extracts_subject_subgroup_chapter():
    assert parse_note_path("知识笔记/数学一/高数/ch1 函数 极限 连续/Stolz 定理.md") == (
        "数学一", "高数", "ch1 函数 极限 连续", "Stolz 定理",
    )
    assert parse_note_path("知识笔记/数学一/学习方法探索.md") == (
        "数学一", "", "", "学习方法探索",
    )
    assert parse_note_path("知识笔记/英语一/词汇/list 1.md") == (
        "英语一", "", "词汇", "list 1",
    )


def _make_note(root, rel_path, body, mtime=None):
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body, encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(full, (mtime, mtime))
    return full


def test_auto_fill_created_adds_field_when_missing(vault_root):
    note_path = _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch1 函数 极限 连续/Stolz 定理.md",
        "正文内容\n",
    )
    # 第一次跑：应补 created
    result = auto_fill_created_frontmatter(vault_root)
    assert result["filled"] == 1
    text = note_path.read_text(encoding="utf-8")
    assert text.startswith("---\ncreated: ")

    # 第二次跑：幂等，不再补
    result2 = auto_fill_created_frontmatter(vault_root)
    assert result2["filled"] == 0


def test_auto_fill_preserves_existing_frontmatter(vault_root):
    note_path = _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch3/双中值.md",
        textwrap.dedent("""\
            ---
            tags: [中值定理]
            ---
            正文
        """),
    )
    auto_fill_created_frontmatter(vault_root)
    text = note_path.read_text(encoding="utf-8")
    assert "tags: [中值定理]" in text
    assert "created:" in text
    assert text.count("---") >= 2


def test_auto_fill_skips_when_created_present(vault_root):
    note_path = _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch3/已有.md",
        textwrap.dedent("""\
            ---
            created: 2025-09-09
            ---
            正文
        """),
    )
    auto_fill_created_frontmatter(vault_root)
    text = note_path.read_text(encoding="utf-8")
    assert "created: 2025-09-09" in text
    assert text.count("created:") == 1


def test_scan_all_notes_returns_entries_with_chapter_num(vault_root):
    _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch1 函数 极限 连续/Stolz 定理.md",
        "---\ncreated: 2026-05-20\n---\n正文",
    )
    _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch3 微分中值定理与泰勒公式/双中值.md",
        "---\ncreated: 2026-05-22\n---\n正文",
    )

    notes = scan_all_notes(vault_root)
    assert len(notes) == 2
    by_title = {n.title: n for n in notes}
    stolz = by_title["Stolz 定理"]
    assert stolz.subject == "数学一"
    assert stolz.subgroup == "高数"
    assert stolz.chapter_num == 1
    assert stolz.created == date(2026, 5, 20)


def test_scan_notes_in_range_filters_by_created(vault_root):
    _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch1/A.md",
        "---\ncreated: 2026-05-01\n---\n",
    )
    _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch1/B.md",
        "---\ncreated: 2026-05-20\n---\n",
    )
    _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch1/C.md",
        "---\ncreated: 2026-05-24\n---\n",
    )
    notes = scan_notes_in_range(vault_root, date(2026, 5, 20), date(2026, 5, 24))
    titles = sorted(n.title for n in notes)
    assert titles == ["B", "C"]


def test_count_missing_created_after_auto_fill(vault_root):
    _make_note(
        vault_root,
        "知识笔记/数学一/高数/ch1/A.md",
        "正文\n",
    )
    assert count_missing_created(vault_root) == 1
    auto_fill_created_frontmatter(vault_root)
    assert count_missing_created(vault_root) == 0


def test_render_today_notes_section_groups_by_chapter():
    entries = [
        NoteEntry(
            path_rel="知识笔记/数学一/高数/ch1 函数 极限 连续/Stolz 定理.md",
            subject="数学一",
            subgroup="高数",
            chapter_raw="ch1 函数 极限 连续",
            chapter_num=1,
            title="Stolz 定理",
            created=date(2026, 5, 24),
        ),
        NoteEntry(
            path_rel="知识笔记/数学一/高数/ch3 微分中值定理与泰勒公式/双中值.md",
            subject="数学一",
            subgroup="高数",
            chapter_raw="ch3 微分中值定理与泰勒公式",
            chapter_num=3,
            title="双中值",
            created=date(2026, 5, 24),
        ),
    ]
    section = render_today_notes_section(entries, missing_created=0)
    assert "## 今日新增笔记" in section
    assert "**数学一·高数·第1章 函数 极限 连续**" in section
    assert "[[知识笔记/数学一/高数/ch1 函数 极限 连续/Stolz 定理|Stolz 定理]]" in section
    assert "今日合计 2 篇。" in section


def test_render_today_notes_section_empty_with_missing():
    section = render_today_notes_section([], missing_created=3)
    assert "今天没有新增笔记" in section
    assert "3 篇笔记缺 `created`" in section


def test_render_recap_notes_block_with_distribution():
    entries = [
        NoteEntry("知识笔记/数学一/高数/ch1/A.md", "数学一", "高数", "ch1", 1, "A", date(2026, 5, 20)),
        NoteEntry("知识笔记/数学一/高数/ch1/B.md", "数学一", "高数", "ch1", 1, "B", date(2026, 5, 21)),
        NoteEntry("知识笔记/数学一/高数/ch3/C.md", "数学一", "高数", "ch3", 3, "C", date(2026, 5, 22)),
        NoteEntry("知识笔记/408/DS/ch1/D.md", "408", "DS", "ch1", 1, "D", date(2026, 5, 23)),
    ]
    block = render_recap_notes_block(entries, "周")
    assert "本周共新增 4 篇笔记" in block
    assert "数学一 3 篇" in block
    assert "408 1 篇" in block
    assert "高产章节" in block
    assert "数学一·高数·第1章" in block


def test_render_recap_notes_block_empty():
    block = render_recap_notes_block([], "月")
    assert "本月没有新增笔记" in block
