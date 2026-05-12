"""test build_knowledge_test.py"""
import json
import textwrap

from helpers import run_script


def _write_map(vault_root, subject, filename, body):
    path = vault_root / "知识地图" / filename
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_build_knowledge_test_prioritizes_unmastered_topics(vault_root):
    _write_map(vault_root, "数学一", "数学一.md", """\
        # 数学一 知识地图

        ## 高等数学
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **05 多元函数微积分** | | | |
        |  05.2 偏导数与全微分 | 半会 | 中 | 复合函数时容易漏项 |
        |  05.5 二重积分 | 不会 | 低 | 极坐标切换总乱 |
        |  05.6 三重积分 |  |  |  |
        |  05.7 曲线积分 | 会 | 高 |  |
    """)

    rc, out, _ = run_script("build_knowledge_test.py", [
        str(vault_root), "数学一", "--chapter", "多元函数微积分", "--count", "3"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["subject"] == "数学一"
    assert data["question_count"] == 3
    assert [item["topic"] for item in data["questions"]] == [
        "05.5 二重积分",
        "05.6 三重积分",
        "05.2 偏导数与全微分",
    ]
    assert "知识测试：数学一" in data["markdown"]
    assert "极坐标切换总乱" in data["markdown"]


def test_build_knowledge_test_supports_alias_and_env_var(vault_root):
    _write_map(vault_root, "408", "408.md", """\
        # 408 知识地图

        ## 数据结构
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **02 栈、队列和数组** | | | |
        |  02.1 栈的应用 | 不会 | 低 | 表达式求值总混 |
        |  02.2 队列的应用 | 半会 | 中 |  |
        | **04 图** | | | |
        |  04.2 图的遍历 | 不会 | 低 | BFS/DFS 容易混 |
    """)

    rc, out, _ = run_script("build_knowledge_test.py", [
        "408", "--chapter", "图", "--count", "3"
    ], env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})
    assert rc == 0
    data = json.loads(out)
    assert data["subject"] == "408"
    assert data["question_count"] == 1
    assert data["questions"][0]["topic"] == "04.2 图的遍历"


def test_build_knowledge_test_errors_when_no_weak_topics(vault_root):
    _write_map(vault_root, "政治", "政治.md", """\
        # 政治 知识地图

        ## 马原
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 哲学基础** | | | |
        |  01.1 实践与认识 | 会 | 高 |  |
        |  01.2 矛盾分析法 | 会 | 高 |  |
    """)

    rc, out, _ = run_script("build_knowledge_test.py", [
        str(vault_root), "政治", "--chapter", "哲学基础", "--count", "3"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "未找到" in data["message"]


def test_build_knowledge_test_math1_chapter_alias_resolves_to_lilang_leaf(vault_root):
    """数学一 --chapter 旧通用桶名应通过 alias 命中新李林叶子。"""
    _write_map(vault_root, "数学一", "数学一.md", """\
        ## 高等数学 (约 56%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 第一章 函数、极限、连续** | | | |
        | 01.01 第一节 函数 | 不会 | | 周期性不稳 |
        | 01.02 第二节 函数极限 | 半会 | | 左右极限 |
        | 01.03 第三节 数列极限 | 不会 | | 递推数列 |
        | 01.04 第四节 函数的连续性 | | | |
    """)

    # 传入旧桶名 "函数的性质与图形" → alias → "01.01 第一节 函数"，应只命中 01.01。
    rc, out, _ = run_script("build_knowledge_test.py", [
        str(vault_root), "数学一", "--chapter", "函数的性质与图形", "--count", "3"
    ])
    assert rc == 0, out
    data = json.loads(out)
    topics = [item["topic"] for item in data["questions"]]
    assert topics == ["01.01 第一节 函数"]
    assert data["chapter_filter"] == "函数的性质与图形"
    assert data["chapter_filter_resolved"] == "01.01 第一节 函数"


def test_build_knowledge_test_math1_new_leaf_name_passthrough(vault_root):
    """数学一 --chapter 直接传新李林叶子名应正常命中。"""
    _write_map(vault_root, "数学一", "数学一.md", """\
        ## 高等数学 (约 56%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 第一章 函数、极限、连续** | | | |
        | 01.03 第三节 数列极限 | 不会 | | 递推 |
    """)

    rc, out, _ = run_script("build_knowledge_test.py", [
        str(vault_root), "数学一", "--chapter", "01.03 第三节 数列极限", "--count", "3"
    ])
    assert rc == 0, out
    data = json.loads(out)
    assert [item["topic"] for item in data["questions"]] == ["01.03 第三节 数列极限"]


def test_build_knowledge_test_math1_fallback_keeps_legacy_map_working(vault_root):
    """数学一旧结构知识地图 + 旧桶名输入,alias 命中为 0 时回退到原始关键词。"""
    _write_map(vault_root, "数学一", "数学一.md", """\
        ## 高等数学
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **05 多元函数微积分** | | | |
        |  05.5 二重积分 | 不会 | 低 | 极坐标 |
    """)

    # alias 把 "二重积分" 翻成 "10.02 第二节 二重积分的计算"，
    # 新名在旧结构中找不到 → 回退到 "二重积分" → 命中 05.5。
    rc, out, _ = run_script("build_knowledge_test.py", [
        str(vault_root), "数学一", "--chapter", "二重积分", "--count", "3"
    ])
    assert rc == 0, out
    data = json.loads(out)
    assert [item["topic"] for item in data["questions"]] == ["05.5 二重积分"]
    assert data["chapter_filter_resolved"] == "二重积分"
