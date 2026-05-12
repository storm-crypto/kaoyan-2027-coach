"""test update_knowledge_map.py"""
import json
import textwrap
import pytest
from helpers import run_script


def test_single_match(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "二重积分", "半会", "极坐标不熟"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["updated"] == "05.5 二重积分"
    assert data["mastery"] == "半会"
    # 验证文件已更新
    content = (knowledge_map / "数学一.md").read_text()
    assert "半会" in content


def test_no_match(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "不存在的考点", "会"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_ambiguous_match(knowledge_map, vault_root):
    """多行匹配应报错并列出候选。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "积分", "会"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "candidates" in data


def test_chapter_header_skipped(knowledge_map, vault_root):
    """章节标题（含 **）不应被匹配。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "多元函数微积分", "会"
    ])
    assert rc == 1  # 章节标题被跳过，所以找不到叶子行


def test_unknown_subject(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "物理", "力学", "会"
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_env_var(knowledge_map, vault_root):
    rc, out, _ = run_script("update_knowledge_map.py", [
        "数学一", "三重积分", "不会"
    ], env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})
    assert rc == 0
    data = json.loads(out)
    assert data["mastery"] == "不会"


@pytest.fixture
def lilang_knowledge_map(vault_root):
    """李林结构的数学一知识地图，覆盖 alias 命中所需的几个章节。"""
    km_dir = vault_root / "知识地图"
    content = textwrap.dedent("""\
        ## 高等数学 (约 56%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **01 第一章 函数、极限、连续** | | | |
        | 01.01 第一节 函数 | | | |
        | 01.02 第二节 函数极限 | | | |
        | 01.03 第三节 数列极限 | | | |
        | 01.04 第四节 函数的连续性 | | | |
        | **10 第十章 二重积分** | | | |
        | 10.02 第二节 二重积分的计算 | | | |

        ## 线性代数 (约 22%)
        | 考点 | 掌握度 | 信心 | 备注 |
        |------|--------|------|------|
        | **04 第四章 线性方程组** | | | |
        | 04.01 第一节 齐次线性方程组 | | | |
        | 04.02 第二节 非齐次线性方程组 | | | |
        | 04.03 第三节 线性方程组的综合应用 | | | |
    """)
    (km_dir / "数学一.md").write_text(content, encoding="utf-8")
    return km_dir


def test_alias_old_bucket_resolves_to_new_leaf(lilang_knowledge_map, vault_root):
    """传入旧通用桶名应通过 alias 命中新李林叶子行。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "函数的性质与图形", "不会", "周期性不稳"
    ])
    assert rc == 0, out
    data = json.loads(out)
    assert data["updated"] == "01.01 第一节 函数"
    assert data["mastery"] == "不会"
    content = (lilang_knowledge_map / "数学一.md").read_text()
    assert "周期性不稳" in content


def test_alias_new_leaf_name_still_works(lilang_knowledge_map, vault_root):
    """传入新李林叶子精确名应直接命中（alias 不命中时透传）。"""
    rc, out, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "01.03 第三节 数列极限", "半会"
    ])
    assert rc == 0, out
    data = json.loads(out)
    assert data["updated"] == "01.03 第三节 数列极限"
    assert data["mastery"] == "半会"


def test_alias_split_linear_equations_three_leaves(lilang_knowledge_map, vault_root):
    """线代第四章 alias 拆分后，齐次/非齐次/综合应用三条都能命中各自叶子。"""
    rc1, out1, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "齐次方程组", "不会"
    ])
    rc2, out2, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "非齐次方程组", "半会"
    ])
    rc3, out3, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "方程组综合应用", "会"
    ])
    assert (rc1, rc2, rc3) == (0, 0, 0)
    assert json.loads(out1)["updated"] == "04.01 第一节 齐次线性方程组"
    assert json.loads(out2)["updated"] == "04.02 第二节 非齐次线性方程组"
    assert json.loads(out3)["updated"] == "04.03 第三节 线性方程组的综合应用"


def test_write_back_keeps_clean_pipe_spacing(lilang_knowledge_map, vault_root):
    """写回后表格行应保持 `| cell | cell | cell | cell |` 干净格式，
    不能产生 `|topic| 不会 ||  note |` 这种连续 pipe 或缺失两侧空格的行。"""
    rc, _, _ = run_script("update_knowledge_map.py", [
        str(vault_root), "数学一", "数列极限", "半会", "测试备注"
    ])
    assert rc == 0
    content = (lilang_knowledge_map / "数学一.md").read_text(encoding="utf-8")
    target_line = next(line for line in content.splitlines() if "01.03 第三节 数列极限" in line)
    assert target_line == "| 01.03 第三节 数列极限 | 半会 |  | 测试备注 |"
