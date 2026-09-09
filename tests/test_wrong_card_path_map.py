"""单测 wrong_card_path_map：章节解析、别名碰撞守卫、历史卡反解展示名。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from wrong_card_path_map import (  # noqa: E402
    WRONG_CARD_PATH_MAP,
    _build_alias_map,
    canonical_chapter_display,
    iter_408_knowledge_map_rows,
    resolve_knowledge_map_keyword,
    resolve_wrong_card_chapter,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent


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
    # 408 已配目录表，但旧式扁平目录「数据结构」不是叶子节 → 仍返回空串，让聚合方退化到目录名
    assert canonical_chapter_display("408", "数据结构") == ""
    assert canonical_chapter_display("政治", "马原") == ""


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


# --------------------------- 408：老汤大纲 ---------------------------


def _template_408_rows():
    """从模板里抽出 知识地图/408.md 代码块的 (模块, 章节行, 叶子行) 序列。"""
    import re
    import textwrap

    text = (SKILL_ROOT / "templates" / "学习者档案与知识地图模板.md").read_text(encoding="utf-8")
    anchor = "### `知识地图/408.md`"
    start = text.index("```markdown", text.index(anchor)) + len("```markdown\n")
    block = text[start:text.index("```", start)]
    rows = []
    module = chapter = ""
    for line in textwrap.dedent(block).splitlines():
        heading = re.match(r"^##\s+(.+?)\s*(?:\(.*\))?\s*$", line)
        if heading:
            module = heading.group(1).strip()
            continue
        chapter_match = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|", line)
        if chapter_match:
            chapter = chapter_match.group(1).strip()
            continue
        leaf_match = re.match(r"^\|\s*(\d{2}\.\d{2}\s+[^|]+?)\s*\|", line)
        if leaf_match:
            rows.append((module, chapter, leaf_match.group(1).strip()))
    return rows


def test_408_template_matches_path_map_outline():
    """知识地图模板的 408 块必须与 _408_OUTLINE 逐行一致：叶子行 == chapter_display。

    两处不同步的后果：/wrong 建卡的 chapter_display 找不到知识地图行，
    update_knowledge_map --finding-add 直接报「未找到叶子考点行」。
    """
    assert _template_408_rows() == iter_408_knowledge_map_rows()


def test_408_outline_has_four_modules_and_unique_leaves():
    rows = iter_408_knowledge_map_rows()
    modules = list(dict.fromkeys(module for module, _, _ in rows))
    assert modules == ["数据结构", "计算机组成原理", "操作系统", "计算机网络"]
    leaves = [leaf for _, _, leaf in rows]
    assert len(leaves) == len(set(leaves)), "叶子节名跨模块重复会让别名表碰撞"
    assert all("/" not in leaf for leaf in leaves), "叶子名含 / 会被 Path 拆成两级目录"
    # 老汤特有章序的抽样锚点
    displays = set(leaves)
    assert "03.03 Cache 基本原理与映射方式" in displays  # 计组 ch3 是主存储器（含 Cache）
    assert "02.01 空闲盘块管理" in displays  # 操作系统 ch2 是文件系统
    assert "07.01 KMP 算法与 next 数组" in displays  # KMP 单独成章
    assert "04.05 堆及其应用" in displays  # 2025 新增考点挂在树这一章


@pytest.mark.parametrize(
    ("chapter", "display", "chapter_id", "chapter_path"),
    [
        ("银行家算法", "08.02 死锁", "408:os:08:02", "操作系统/08第八章互斥和同步/02死锁"),
        ("cache基本原理与映射方式", "03.03 Cache 基本原理与映射方式", "408:co:03:03",
         "计算机组成原理/03第三章主存储器/03Cache基本原理与映射方式"),
        ("CSMA/CD", "03.04 随机接入协议与 CSMA-CD", "408:cn:03:04",
         "计算机网络/03第三章数据链路层/04随机接入协议与CSMA-CD"),
        ("I/O 接口", "07.02 IO 接口", "408:co:07:02", "计算机组成原理/07第七章输入输出系统/02IO接口"),
        ("三次握手", "05.07 TCP 连接管理", "408:cn:05:07", "计算机网络/05第五章运输层/07TCP连接管理"),
        ("07.01 KMP 算法与 next 数组", "07.01 KMP 算法与 next 数组", "408:ds:07:01",
         "数据结构/07第七章KMP字符串匹配/01KMP算法与next数组"),
    ],
)
def test_408_aliases_resolve_to_laotang_leaf(chapter, display, chapter_id, chapter_path):
    """节名、别名、带序号写法、大小写差异都要落到同一个老汤叶子节。"""
    resolution = resolve_wrong_card_chapter("408", chapter)
    assert resolution.is_canonical
    assert resolution.chapter_display == display
    assert resolution.chapter_id == chapter_id
    assert resolution.chapter_path == chapter_path


def test_408_module_or_chapter_level_input_is_rejected_with_leaf_candidates():
    """传模块名/章名/多义词不能落盘，报错里要给出可直接重试的叶子候选。"""
    with pytest.raises(ValueError, match="无法识别 408 章节 '流水线'") as excinfo:
        resolve_wrong_card_chapter("408", "流水线")
    message = str(excinfo.value)
    assert "06.04 流水线基本原理与吞吐量" in message
    assert "06.05 流水线冒险与解决方法" in message


def test_408_materialized_dir_reverses_to_display():
    """历史卡按 sanitize 后的目录路径也能反解出与新卡一致的展示名。"""
    assert canonical_chapter_display(
        "408", "计算机网络/03第三章数据链路层/04随机接入协议与CSMA-CD"
    ) == "03.04 随机接入协议与 CSMA-CD"


def test_resolve_knowledge_map_keyword_per_subject():
    """数学一走旧桶名 alias，408 走老汤别名表，其他科目原样透传。"""
    assert resolve_knowledge_map_keyword("数学一", "函数的性质与图形") == "01.01 第一节 函数"
    assert resolve_knowledge_map_keyword("408", "页面置换") == "05.03 页面置换算法"
    assert resolve_knowledge_map_keyword("408", "Cache") == "Cache"  # 多义词不猜，交给调用方报候选
    assert resolve_knowledge_map_keyword("政治", "唯物论") == "唯物论"
