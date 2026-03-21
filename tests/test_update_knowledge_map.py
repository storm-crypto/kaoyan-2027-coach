"""test update_knowledge_map.py"""
import json
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
