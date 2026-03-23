"""test update_card.py"""
import json
import textwrap
from datetime import date

from helpers import run_script

TODAY = "2026-03-23"


def test_status_buhui(sample_card):
    """不会：interval→1, ease×0.8"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "不会", "--comment", "完全忘了", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["interval"] == 1
    assert float(data["ease_factor"]) == 2.0  # 2.5 * 0.8
    assert data["next_review"] == "2026-03-24"


def test_status_banhui(sample_card):
    """半会：interval×1.2(至少+1), ease不变"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "半会", "--comment", "有进步", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    # old_interval=4, 4*1.2=4.8→int=4, max(4, 4+1)=5
    assert data["interval"] == 5
    assert data["ease_factor"] == "2.50"


def test_status_hui(sample_card):
    """会：interval×ease_factor(上限90), ease+0.1"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "会", "--comment", "掌握了", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    # old_interval=4, 4*2.5=10
    assert data["interval"] == 10
    assert float(data["ease_factor"]) == 2.6


def test_ease_floor(sample_card):
    """反复不会，ease 不低于 1.3"""
    for _ in range(5):
        run_script("update_card.py", [str(sample_card), "--status", "不会", "--today", TODAY])
    rc, out, _ = run_script("update_card.py", [str(sample_card), "--status", "不会", "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert float(data["ease_factor"]) >= 1.3


def test_interval_cap(sample_card):
    """会的 interval 上限为 90 天"""
    # 先手动把 interval 设高
    text = sample_card.read_text()
    text = text.replace("review_interval: 4", "review_interval: 80")
    sample_card.write_text(text)

    rc, out, _ = run_script("update_card.py", [str(sample_card), "--status", "会", "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert data["interval"] <= 90


def test_zero_interval_is_treated_as_new_card_baseline(sample_card):
    text = sample_card.read_text(encoding="utf-8").replace("review_interval: 4", "review_interval: 0")
    sample_card.write_text(text, encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [str(sample_card), "--status", "会", "--today", TODAY])

    assert rc == 0
    data = json.loads(out)
    assert data["interval"] == 2


def test_missing_interval_uses_new_card_baseline(sample_card_no_qid):
    text = sample_card_no_qid.read_text(encoding="utf-8").replace("review_interval: 1\n", "")
    sample_card_no_qid.write_text(text, encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [str(sample_card_no_qid), "--status", "半会", "--today", TODAY])

    assert rc == 0
    data = json.loads(out)
    assert data["interval"] == 2


def test_qid_backfill(sample_card_no_qid):
    """回填 question_id 并重命名文件"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-aabbccddeeff", "--today", TODAY
    ])
    assert rc == 0
    data = json.loads(out)
    assert "renamed_from" in data
    assert "qid-aabbccddeeff" in data["updated"]
    # 原文件应该不存在了
    assert not sample_card_no_qid.exists()


def test_qid_conflict(sample_card):
    """传入不同的 question_id 应报错"""
    rc, out, _ = run_script("update_card.py", [
        str(sample_card), "--status", "会",
        "--question-id", "qid-999999999999", "--today", TODAY
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_rename_conflict_does_not_mutate_original(sample_card_no_qid, vault_root):
    """目标规范文件已存在时，原卡不应被半提交改写。"""
    existing = sample_card_no_qid.with_name("泰勒展开-660题-qid-aabbccddeeff.md")
    existing.write_text("---\nquestion_id: qid-aabbccddeeff\n---\n", encoding="utf-8")
    before = sample_card_no_qid.read_text(encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-aabbccddeeff", "--today", TODAY
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "目标文件已存在" in data["message"]
    assert sample_card_no_qid.read_text(encoding="utf-8") == before


def test_history_append(sample_card):
    """历史记录应追加新行"""
    run_script("update_card.py", [str(sample_card), "--status", "会", "--comment", "搞定", "--today", TODAY])
    text = sample_card.read_text()
    assert f"- {TODAY} - 会 - 搞定" in text


def test_file_not_found():
    rc, out, _ = run_script("update_card.py", [
        "/nonexistent/card.md", "--status", "不会", "--today", TODAY
    ])
    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_rejects_non_wrongbook_path(tmp_path):
    stray = tmp_path / "note.md"
    stray.write_text("---\nstatus: 半会\n---\n", encoding="utf-8")

    rc, out, _ = run_script("update_card.py", [
        str(stray), "--status", "会", "--today", TODAY
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "错题本目录下" in data["message"]


def test_invalid_question_id_is_rejected(sample_card_no_qid):
    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-../../escape", "--today", TODAY
    ])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True


def test_rename_preserves_single_updated_file(sample_card_no_qid):
    rc, out, _ = run_script("update_card.py", [
        str(sample_card_no_qid), "--status", "半会",
        "--question-id", "qid-aabbccddeeff", "--comment", "回填后继续复习", "--today", TODAY
    ])

    assert rc == 0
    data = json.loads(out)
    new_path = sample_card_no_qid.with_name(data["updated"])
    assert not sample_card_no_qid.exists()
    assert new_path.exists()
    content = new_path.read_text(encoding="utf-8")
    assert "question_id: qid-aabbccddeeff" in content
    assert f"- {TODAY} - 半会 - 回填后继续复习" in content
