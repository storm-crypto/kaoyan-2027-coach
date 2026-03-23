"""test study_ops.py"""
import sys
import textwrap
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from study_ops import collect_due_cards, count_due_reviews, iter_review_cards


def _write_card(vault_root, subject, filename, next_review, interval):
    card_dir = vault_root / "错题本" / subject / "专题"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / filename
    card.write_text(textwrap.dedent(f"""\
        ---
        source: test
        question_id: qid-study-{filename.replace('.md', '')}
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


def test_iter_review_cards_marks_icloud_placeholder(vault_root):
    card_dir = vault_root / "错题本" / "数学一" / "专题"
    card_dir.mkdir(parents=True, exist_ok=True)
    target = card_dir / "占位卡.md"
    target.write_text("placeholder target", encoding="utf-8")
    (card_dir / ".占位卡.md.icloud").write_text("", encoding="utf-8")

    items = list(iter_review_cards(vault_root))
    placeholder = next(item for item in items if item["path"] == target)

    assert placeholder["icloud_placeholder"] is True
    assert placeholder["review_interval"] is None


def test_collect_due_cards_skips_placeholder_and_graduated(vault_root):
    due_card = _write_card(vault_root, "数学一", "due.md", "2026-03-20", interval=2)
    _write_card(vault_root, "408", "graduated.md", "2026-03-20", interval=90)
    cloud_target = _write_card(vault_root, "英语一", "cloud.md", "2026-03-20", interval=2)
    (cloud_target.parent / f".{cloud_target.name}.icloud").write_text("", encoding="utf-8")

    due_cards = collect_due_cards(vault_root, date(2026, 3, 23))

    assert len(due_cards) == 1
    assert {item["filename"] for item in due_cards} == {due_card.stem}


def test_count_due_reviews_returns_subject_breakdown(vault_root):
    _write_card(vault_root, "数学一", "math.md", "2026-03-20", interval=2)
    _write_card(vault_root, "408", "408.md", "2026-03-22", interval=1)
    _write_card(vault_root, "政治", "future.md", "2026-03-25", interval=1)

    due_total, due_counts = count_due_reviews(
        vault_root,
        date(2026, 3, 23),
        ("数学一", "408", "英语一", "政治"),
    )

    assert due_total == 2
    assert due_counts == {"数学一": 1, "408": 1, "英语一": 0, "政治": 0}
