"""同一作答历史在队列、计划和热力图中保持一致。"""
import json
from datetime import date

from helpers import run_script
from dashboard_payload import build_activity_payload, collect_cards
from study_ops import collect_due_cards


TODAY = date(2026, 11, 11)


def write_card(root, *, first="2026-11-01", interval=90, history=""):
    path = root / "错题本/数学一/高等数学/复习-qid-123456abcdef.md"
    path.write_text(f"""---
question_id: qid-123456abcdef
topic: 定积分
first_wrong_at: {first}
last_review_at: 2026-11-10
status: 会
review_interval: {interval}
next_review: 2026-11-01
---
### 题目
计算给定定积分。
### 历史记录
{history}
""", encoding="utf-8")
    return path


def heatmap(root):
    cards = collect_cards(root, TODAY)
    activity = build_activity_payload(
        [], cards, {"recap_reports": [], "mock_reports": []}, {"reports": []}, TODAY,
    )
    return {cell["date"]: cell["count"] for cell in activity["card_reviewed_heatmap_30"]}


def test_new_review_preserves_past_and_counts_each_card_once_per_day(vault_root):
    path = write_card(vault_root, history="""- 2026-11-01 - 不会 - 首次归档
- 2026-11-10 - 半会 - 需要提示
""")
    before = heatmap(vault_root)
    path.write_text(path.read_text() + "- 2026-11-11 - 会 - 独立完成\n"
                    + "- 2026-11-11 - 会 - 另一道无提示变式\n", encoding="utf-8")
    after = heatmap(vault_root)
    assert before["2026-11-01"] == after["2026-11-01"] == 0
    assert before["2026-11-10"] == after["2026-11-10"] == 1
    assert before["2026-11-11"] == 0
    assert after["2026-11-11"] == 1


def test_archive_and_real_review_on_same_day_are_distinct(vault_root):
    write_card(vault_root, history="""- 2026-11-01 - 不会 - 首次归档
- 2026-11-01 - 半会 - 提示后完成变式
- 2026-11-12 - 会 - 未来记录不算入当前快照
""")
    counts = heatmap(vault_root)
    assert counts["2026-11-01"] == 1
    assert sum(counts.values()) == 1


def test_last_review_field_alone_does_not_invent_activity(vault_root):
    write_card(vault_root)
    assert sum(heatmap(vault_root).values()) == 0


def test_all_due_entrypoints_include_long_interval_without_writing(sample_archive, vault_root):
    path = write_card(vault_root)
    before = path.read_bytes()
    expected = {str(path)}
    assert {str(card["path"]) for card in collect_cards(vault_root, TODAY) if card["is_due"]} == expected
    assert {card["path"] for card in collect_due_cards(vault_root, TODAY)} == expected
    rc, out, err = run_script("scan_due_reviews.py", [str(vault_root), "--today", TODAY.isoformat(), "--by-cluster"])
    assert rc == 0, err
    scanned = json.loads(out)
    assert {card["path"] for card in scanned["due"]} == expected
    assert scanned["degraded"] == 0 and scanned["pending_overdue"] == 1
    rc, out, err = run_script("build_daily_plan.py", [str(vault_root), "--today", TODAY.isoformat()])
    assert rc == 0, err
    groups = json.loads(out)["due_clusters"]
    assert {card["path"] for group in groups for card in group["cards"]} == expected
    assert groups[0]["cluster_id"] == "unclustered"
    assert path.read_bytes() == before


def test_legacy_scheduled_card_without_creation_date_still_appears(vault_root):
    path = write_card(vault_root, first="")
    (path.parent / "导航.md").write_text("---\ntitle: 章节导航\n---\n# 题目目录", encoding="utf-8")
    cards = collect_cards(vault_root, TODAY)
    assert len(cards) == 1
    assert cards[0]["path"] == str(path) and cards[0]["is_due"]
    assert cards[0]["created_at"] in (None, "", "-")
