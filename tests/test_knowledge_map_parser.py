"""test knowledge_map_parser.py"""
import sys
import textwrap
from pathlib import Path

from helpers import SCRIPTS_DIR  # noqa: F401

sys.path.insert(0, str(SCRIPTS_DIR))

from knowledge_map_parser import (  # noqa: E402
    chapters_index,
    load_all_maps,
    parse_knowledge_map,
    total_chapters,
)


def test_parse_math_style_map(tmp_path):
    p = tmp_path / "数学一.md"
    p.write_text(textwrap.dedent("""\
        ## 高等数学 (约 56%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 第一章 函数、极限、连续** | | | |
        |  01.01 第一节 函数 | | | |
        | **02 第二章 导数与微分** | | | |
        | **03 第三章 微分中值定理与泰勒公式** | | | |

        ## 线性代数 (约 22%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 行列式** | | | |
        | **02 矩阵** | | | |
    """), encoding="utf-8")
    entries = parse_knowledge_map(p)
    assert total_chapters(entries) == 5
    by_sub = {}
    for e in entries:
        by_sub.setdefault(e.subgroup, []).append((e.chapter_num, e.chapter_name))
    assert by_sub["高等数学"] == [
        (1, "第一章 函数、极限、连续"),
        (2, "第二章 导数与微分"),
        (3, "第三章 微分中值定理与泰勒公式"),
    ]
    assert by_sub["线性代数"] == [(1, "行列式"), (2, "矩阵")]


def test_parse_408_style_map(tmp_path):
    p = tmp_path / "408.md"
    p.write_text(textwrap.dedent("""\
        ## 数据结构 (约 45 分)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 线性表** | | | |
        | **02 栈、队列和数组** | | | |
    """), encoding="utf-8")
    entries = parse_knowledge_map(p)
    assert [(e.chapter_num, e.chapter_name) for e in entries] == [
        (1, "线性表"),
        (2, "栈、队列和数组"),
    ]


def test_chapters_index(tmp_path):
    p = tmp_path / "x.md"
    p.write_text(textwrap.dedent("""\
        ## g
        | a |
        |---|
        | **05 五号章** | |
        | **07 七号章** | |
    """), encoding="utf-8")
    idx = chapters_index(parse_knowledge_map(p))
    assert idx[5].chapter_name == "五号章"
    assert idx[7].chapter_name == "七号章"


def test_load_all_maps_returns_dict(vault_root):
    (vault_root / "知识地图" / "数学一.md").write_text(
        "## 高等数学\n| a |\n|---|\n| **01 第一章 函数** | |\n", encoding="utf-8",
    )
    (vault_root / "知识地图" / "408.md").write_text(
        "## 数据结构\n| a |\n|---|\n| **01 线性表** | |\n", encoding="utf-8",
    )
    maps = load_all_maps(vault_root)
    assert set(maps.keys()) == {"数学一", "408"}
    assert maps["数学一"][0].chapter_name == "第一章 函数"
    assert maps["408"][0].chapter_name == "线性表"
