"""test scan_due_reviews.py"""
import json
import textwrap
from datetime import date, timedelta
from helpers import run_script

TODAY = "2026-06-15"
TODAY_DATE = date.fromisoformat(TODAY)


def _make_card(vault_root, name, next_review, interval, status="半会"):
    card_dir = vault_root / "错题本" / "数学一" / "高等数学"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / name
    card.write_text(textwrap.dedent(f"""\
        ---
        source: test
        question_id: qid-000000000001
        topic: test topic
        first_wrong_at: 2026-01-01
        last_review_at: 2026-01-01
        wrong_count: 1
        status: {status}
        next_review: {next_review}
        review_interval: {interval}
        ease_factor: 2.50
        ---

        Test card
    """), encoding="utf-8")
    return card


def test_due_today(vault_root):
    _make_card(vault_root, "due-today.md", TODAY, 2)
    rc, out, _ = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY])
    assert rc == 0
    data = json.loads(out)
    assert len(data["due"]) == 1
    assert data["due"][0]["filename"] == "due-today"


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
