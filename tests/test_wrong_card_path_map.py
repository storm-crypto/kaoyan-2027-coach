"""单测 wrong_card_path_map：章节解析、别名碰撞守卫、历史卡反解展示名。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wrong_card_path_map import (  # noqa: E402
    WRONG_CARD_PATH_MAP,
    _build_alias_map,
    canonical_chapter_display,
    resolve_wrong_card_chapter,
)


def test_real_map_builds_alias_table_without_collision():
    """真实目录表必须能无碰撞地构建别名表，否则解析会静默路由到错误章节。"""
    for subject_map in WRONG_CARD_PATH_MAP.values():
        assert _build_alias_map(subject_map)


def test_build_alias_map_raises_on_conflicting_collision():
    """同一归一化别名指向两个不同目录时必须报错，而不是 setdefault 静默选第一个。"""
    bad_map = {
        "甲": "子科目/01 第一章 甲乙/01 第一节 同名",
        "乙": "子科目/02 第二章 丙丁/01 第一节 同名",
    }
    with pytest.raises(ValueError, match="章节别名碰撞"):
        _build_alias_map(bad_map)


def test_build_alias_map_allows_duplicate_keys_pointing_to_same_dir():
    """多个 key 指向同一目录是良性的（如幂级数两条），不应误报碰撞。"""
    ok_map = {
        "幂级数的收敛域与求和": "高等数学/12 第十二章 无穷级数/02 第二节 幂级数",
        "函数展开为幂级数": "高等数学/12 第十二章 无穷级数/02 第二节 幂级数",
    }
    assert _build_alias_map(ok_map)


def test_canonical_chapter_display_reverses_materialized_dir():
    """历史卡的落盘路径（sanitize 后无空格）能反解出与新卡一致的展示名。"""
    display = canonical_chapter_display(
        "数学一", "高等数学/05第五章不定积分/02第二节不定积分的计算"
    )
    assert display == "05.02 第二节 不定积分的计算"


def test_canonical_chapter_display_empty_for_unknown_or_unmapped_subject():
    """未配置章节、或没有目录表的科目，反解失败返回空串，交由调用方退化处理。"""
    assert canonical_chapter_display("数学一", "未配置章节") == ""
    assert canonical_chapter_display("408", "数据结构") == ""


def test_math1_first_kind_line_integral_resolves_to_13_02():
    """第一型曲线积分必须进入 ch13.02，不能误挂到三重积分或第二型曲线积分。"""
    resolution = resolve_wrong_card_chapter(
        "数学一", "13.02 第二节 第一型曲线积分"
    )
    assert resolution.chapter_display == "13.02 第二节 第一型曲线积分"
    assert resolution.chapter_id == "math1:gaoshu:13:02"


@pytest.mark.parametrize(
    ("chapter", "display", "chapter_id"),
    [
        (
            "14.03 第三节 第二型曲线、曲面积分的奇偶对称性",
            "14.03 第三节 第二型曲线、曲面积分的奇偶对称性",
            "math1:gaoshu:14:03",
        ),
        (
            "14.04 第四节 场论简介",
            "14.04 第四节 场论简介",
            "math1:gaoshu:14:04",
        ),
    ],
)
def test_math1_late_chapter_14_sections_resolve_to_canonical_dirs(
    chapter, display, chapter_id
):
    """ch14.03/14.04 必须与知识地图一致，不得退化挂靠到 14.01/14.02。"""
    resolution = resolve_wrong_card_chapter("数学一", chapter)
    assert resolution.chapter_display == display
    assert resolution.chapter_id == chapter_id
