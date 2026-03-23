"""test build_daily_plan.py"""
import json
import textwrap

from helpers import run_script


def _make_due_card(vault_root, subject, filename, next_review, interval=2):
    card_dir = vault_root / "错题本" / subject / "专题"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / filename
    card.write_text(textwrap.dedent(f"""\
        ---
        source: test
        question_id: qid-daily-{filename.replace('.md', '')}
        topic: {filename}
        first_wrong_at: 2026-03-01
        last_review_at: 2026-03-10
        wrong_count: 1
        status: 半会
        next_review: {next_review}
        review_interval: {interval}
        ease_factor: 2.50
        ---

        test
    """), encoding="utf-8")
    return card


def test_build_daily_plan(sample_archive, vault_root):
    _make_due_card(vault_root, "数学一", "math-1.md", "2026-03-23", interval=1)
    _make_due_card(vault_root, "408", "408-1.md", "2026-03-21", interval=2)

    rc, out, _ = run_script("build_daily_plan.py", [
        str(vault_root), "4", "--today", "2026-03-23"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["available_hours"] == 4.0
    assert data["due_total"] == 2
    assert data["due_selected"] == 2
    assert "今日计划：2026-03-23" in data["markdown"]
    assert any(task["type"] == "review" for task in data["tasks"])
    assert any(task["subject"] == "数学一" for task in data["tasks"])


def test_build_daily_plan_caps_due_selection(sample_archive, vault_root):
    for index in range(12):
        _make_due_card(vault_root, "数学一", f"math-{index}.md", "2026-03-23", interval=index % 3 + 1)

    rc, out, _ = run_script("build_daily_plan.py", [
        str(vault_root), "5", "--today", "2026-03-23"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["due_total"] == 12
    assert data["due_selected"] == 10
