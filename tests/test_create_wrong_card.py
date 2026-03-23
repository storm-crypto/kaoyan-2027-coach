"""test create_wrong_card.py"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from archive_ops import extract_heading_block
from helpers import run_script


def test_create_wrong_card_preserves_all_explicit_options(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "操作系统",
        "--topic", "进程调度",
        "--source", "王道",
        "--question-id", "qid-aabbccddeeff",
        "--question", "以下关于进程调度的说法，正确的是：",
        "--option", "A. FCFS 总能让平均周转时间最小",
        "--option", "B. 时间片轮转适合交互式系统",
        "--option", "C. SJF 一定不会饥饿",
        "--option", "D. 高响应比优先综合考虑等待时间和服务时间",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 4
    assert data["options_source"] == "explicit"
    card_path = Path(data["path"])
    content = card_path.read_text(encoding="utf-8")
    options_block = extract_heading_block(content, "选项（如有）", level=3)
    assert "A. FCFS 总能让平均周转时间最小" in options_block
    assert "B. 时间片轮转适合交互式系统" in options_block
    assert "C. SJF 一定不会饥饿" in options_block
    assert "D. 高响应比优先综合考虑等待时间和服务时间" in options_block


def test_create_wrong_card_detects_options_inside_question_text(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "408",
        "--chapter", "数据结构",
        "--topic", "二叉树遍历",
        "--source", "王道",
        "--question-id", "qid-112233445566",
        "--question",
        "下列关于二叉树遍历的说法，正确的是：\nA. 先序遍历一定有序\nB. 中序遍历二叉搜索树可得有序序列\nC. 后序遍历总能唯一还原二叉树\nD. 层序遍历不需要队列",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 4
    assert data["options_source"] == "detected"
    card_path = Path(data["path"])
    content = card_path.read_text(encoding="utf-8")
    question_block = extract_heading_block(content, "题目", level=3)
    options_block = extract_heading_block(content, "选项（如有）", level=3)
    assert "下列关于二叉树遍历的说法，正确的是：" in question_block
    assert "A. 先序遍历一定有序" not in question_block
    assert "A. 先序遍历一定有序" in options_block
    assert "D. 层序遍历不需要队列" in options_block


def test_create_wrong_card_writes_none_for_non_choice_question(vault_root):
    rc, out, _ = run_script("create_wrong_card.py", [
        str(vault_root),
        "数学一",
        "--chapter", "高等数学",
        "--topic", "二重积分",
        "--source", "900题",
        "--question-id", "qid-f728c5b18974",
        "--question", "设 D 为单位圆与第一象限的交集，求二重积分。",
        "--today", "2026-03-23",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["option_count"] == 0
    assert data["options_source"] == "none"
    card_path = Path(data["path"])
    content = card_path.read_text(encoding="utf-8")
    options_block = extract_heading_block(content, "选项（如有）", level=3)
    assert options_block == "- 无"
