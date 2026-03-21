"""test find_card.py"""
import json
from helpers import run_script


def test_qid_exact_match(sample_card, vault_root):
    rc, out, _ = run_script("find_card.py", [
        str(vault_root), "数学一", "--question-id", "qid-f728c5b18974"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["verdict"] == "found"
    assert data["search_mode"] == "question_id"
    assert data["count"] == 1


def test_keyword_match(sample_card, vault_root):
    rc, out, _ = run_script("find_card.py", [
        str(vault_root), "数学一", "二重积分", "极坐标"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["verdict"] == "found"
    assert data["count"] == 1


def test_no_match(vault_root):
    rc, out, _ = run_script("find_card.py", [
        str(vault_root), "数学一", "--question-id", "qid-000000000000"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["verdict"] == "new"


def test_empty_dir(vault_root):
    rc, out, _ = run_script("find_card.py", [
        str(vault_root), "政治", "马原"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["verdict"] == "new"


def test_env_var(sample_card, vault_root):
    """测试通过环境变量传入 OBSIDIAN_ROOT。"""
    rc, out, _ = run_script("find_card.py", [
        "数学一", "--question-id", "qid-f728c5b18974"
    ], env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})
    assert rc == 0
    data = json.loads(out)
    assert data["verdict"] == "found"


def test_icloud_placeholder(sample_card, vault_root):
    """iCloud 占位符文件应被跳过并报告。"""
    # 创建一个 .icloud 占位符
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    placeholder = card_dir / ".二重积分极坐标-900题-qid-f728c5b18974.md.icloud"
    placeholder.write_text("", encoding="utf-8")

    rc, out, _ = run_script("find_card.py", [
        str(vault_root), "数学一", "--question-id", "qid-f728c5b18974"
    ])
    assert rc == 0
    data = json.loads(out)
    # 文件本身还在，所以还是能找到；但应报告 icloud_placeholders
    assert "icloud_placeholders" in data
