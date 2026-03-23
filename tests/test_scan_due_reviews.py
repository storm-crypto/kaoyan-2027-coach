"""test scan_due_reviews.py"""
import json
from datetime import date, timedelta
from helpers import run_script

TODAY = "2026-06-15"
TODAY_DATE = date.fromisoformat(TODAY)


def _make_card(vault_root, name, next_review, interval, status="半会", question_lines=None, option_lines=None):
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / name
    question_block = "### 题目\n- 设二重积分区域 D 为单位圆与第一象限的交集，求积分值。\n"
    if question_lines is not None:
        question_block = "### 题目\n" + "\n".join(question_lines) + "\n"

    option_block = ""
    if option_lines is not None:
        option_block = "### 选项（如有）\n" + "\n".join(option_lines) + "\n"

    content = (
        "---\n"
        "source: test\n"
        "question_id: qid-000000000001\n"
        "topic: test topic\n"
        "first_wrong_at: 2026-01-01\n"
        "last_review_at: 2026-01-01\n"
        "wrong_count: 1\n"
        f"status: {status}\n"
        f"next_review: {next_review}\n"
        f"review_interval: {interval}\n"
        "ease_factor: 2.50\n"
        "---\n\n"
        "## Test card\n\n"
        f"{question_block}\n"
        f"{option_block}"
        "### 错误原因\n"
        "- 计算时把上下限写反了\n"
    )
    card.write_text(content, encoding="utf-8")
    return card


def test_due_today(vault_root):
    _make_card(vault_root, "due-today.md", TODAY, 2)
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 1
    assert data["due"][0]["filename"] == "due-today"
    assert "单位圆与第一象限" in data["due"][0]["question_text"]
    assert "单位圆与第一象限" in data["due"][0]["question_preview"]


def test_due_card_includes_options(vault_root):
    _make_card(
        vault_root,
        "with-options.md",
        TODAY,
        2,
        question_lines=["- 下列关于进程调度的说法，正确的是："],
        option_lines=[
            "- A. FCFS 一定优于短作业优先",
            "- B. 带权周转时间越小越好",
            "- C. 时间片轮转不会发生上下文切换",
            "- D. 周转时间与服务时间总是相等",
        ],
    )
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    item = next(card for card in data["due"] if card["filename"] == "with-options")
    assert "进程调度" in item["question_text"]
    assert "A. FCFS" in item["options_text"]
    assert "B. 带权周转时间越小越好" in item["options_text"]


def test_not_yet_due(vault_root):
    tomorrow = (TODAY_DATE + timedelta(days=1)).isoformat()
    _make_card(vault_root, "future.md", tomorrow, 2)
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 0


def test_overdue_degradation(vault_root):
    overdue = (TODAY_DATE - timedelta(days=10)).isoformat()
    card = _make_card(vault_root, "overdue.md", overdue, 8)
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert data["degraded"] == 1
    assert len(data["due"]) == 1
    assert data["due"][0]["review_interval"] == 1


def test_graduated_excluded(vault_root):
    """interval >= 90 的卡不出现在到期列表中。"""
    _make_card(vault_root, "graduated.md", TODAY, 90, status="会")
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 0


def test_empty_dir(vault_root):
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert data["due"] == []
    assert data["degraded"] == 0


def test_env_var(vault_root):
    _make_card(vault_root, "env-test.md", TODAY, 2)
    rc, out, _ = run_script("scan_due_reviews.py", ["--today", TODAY],
                            env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault_root)})
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 1
