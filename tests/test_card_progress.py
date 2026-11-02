"""红绿灯的真实历史、断连、过关后失误，以及旧卡展示迁移。"""
from datetime import date
import json
import re
from urllib.parse import unquote

import pytest

from helpers import run_script
from card_history import history_entries
from card_progress import card_progress, PROGRESS_RE, upsert_card_progress
from dashboard_payload import collect_cards
from frontmatter import parse_frontmatter
from metaskill_browser import build_metaskills, render_metaskill_markdown
from sync_card_progress import sync_progress
from test_metaskill_browser import cluster, put_index


def history(statuses):
    return "### 历史记录\n" + "\n".join(
        f"- 2026-11-{i + 1:02d} - {status} - 第{i + 1}次"
        for i, status in enumerate(statuses)) + "\n"


@pytest.mark.parametrize("statuses,streak,passed", [
    (["不会", "半会", "会", "会"], 2, False),
    (["不会", "会", "会", "会"], 3, True),
    (["会", "会", "会", "会"], 4, True),
    (["不会", "会", "会", "半会", "会"], 1, False),
    (["会", "半会", "会", "不会", "会"], 1, False),
    (["会", "会", "会", "不会"], 0, False),
    (["会", "会", "会", "半会"], 0, False),
])
def test_trailing_greens_only(statuses, streak, passed):
    result = card_progress(history(statuses))
    assert result["attempts"] == len(statuses)
    assert result["green_streak"] == streak
    assert result["passed"] == passed


def test_no_history_does_not_guess_from_status_or_other_sections():
    result = card_progress("## 题\nstatus: 会\nreview_interval: 90\n### 解析\n- 2026-11-01 - 会 - 示例")
    assert result["attempts"] == 0
    assert not result["passed"]
    assert "未知" in result["summary"]


def test_same_day_distinct_attempts_remain_visible():
    body = "### 历史记录\n" + "- 2026-11-01 - 会 - 独立完成\n" * 3
    assert card_progress(body)["attempts"] == 3
    assert card_progress(body)["passed"]


def test_upsert_does_not_alter_source_and_is_idempotent():
    body = "\n## 题目标题\n\n### 题目\n原题\n\n" + history(["不会", "会"])
    updated = upsert_card_progress(body)
    assert updated.index("做题轨迹") < updated.index("### 题目")
    assert upsert_card_progress(updated) == updated
    assert re.sub(r"\n" + PROGRESS_RE.pattern + r"\n", "", updated, flags=re.S) == body
    assert history_entries(updated) == history_entries(body)


def test_new_card_counts_its_actual_initial_result(vault_root):
    args = [str(vault_root), "英语一", "--chapter", "阅读", "--topic", "主旨题",
            "--source", "真题", "--question-id", "qid-123456789abc", "--question", "选出主旨",
            "--wrong-reason", "漏看转折", "--solution", "先找转折后的核心论点",
            "--pitfall", "不以偏概全", "--status", "半会", "--today", "2026-11-01"]
    rc, out, err = run_script("create_wrong_card.py", args)
    assert rc == 0, out + err
    from pathlib import Path
    text = Path(json.loads(out)["path"]).read_text()
    assert "做题轨迹：** 🟡" in text
    assert "0 / 3" in text
    assert len(history_entries(text)) == 1


def test_update_records_inside_history_and_resets_after_pass(sample_card):
    text = sample_card.read_text() + "\n### 所属元技能\n保留导航\n"
    sample_card.write_text(text)
    for i, status in enumerate(["会", "会", "会", "半会", "会"], 1):
        rc, out, err = run_script("update_card.py", [str(sample_card), "--status", status,
            "--comment", "独立完成" if status == "会" else "提示后完成", "--today", f"2026-11-{i:02d}"])
        assert rc == 0, out + err
        result = json.loads(out)["progress"]
        assert result["green_streak"] == [1, 2, 3, 0, 1][i - 1]
        assert result["passed"] == (i == 3)
    text = sample_card.read_text()
    assert len(history_entries(text)) == 8
    assert text.count("<!-- review-progress:start -->") == 1
    assert text.endswith("### 所属元技能\n保留导航\n")


def test_migration_preview_preserves_records_then_stays_idempotent(vault_root, sample_card):
    original = sample_card.read_text()
    assert sync_progress(vault_root)["updated_cards"] == 1
    assert sample_card.read_text() == original
    assert sync_progress(vault_root, apply=True)["written"] == 1
    updated = sample_card.read_text()
    assert parse_frontmatter(updated)[0] == parse_frontmatter(original)[0]
    assert history_entries(updated) == history_entries(original)
    assert re.sub(r"\n" + PROGRESS_RE.pattern + r"\n", "", updated, flags=re.S) == original
    assert sync_progress(vault_root, apply=True)["written"] == 0
    # 手工纠正真实历史后重建，只更新显示，计数不累加。
    sample_card.write_text(updated.replace("- 2026-03-15 - 半会", "- 2026-03-15 - 会"))
    sync_progress(vault_root, apply=True)
    assert card_progress(sample_card.read_text())["green_streak"] == 1


def test_directory_uses_history_for_clustered_and_unclustered_cards(vault_root, sample_card):
    text = sample_card.read_text()
    extra = sample_card.with_name("未归簇-qid-123456789abc.md")
    extra.write_text(text.replace("f728c5b18974", "123456789abc"))
    sample_card.write_text(text.replace("- 2026-03-15 - 半会", "- 2026-03-15 - 会"))
    put_index(vault_root, [cluster("m01-01", ["f728c5b18974"])])
    cards = collect_cards(vault_root, date(2026, 11, 2))
    data = build_metaskills(vault_root, cards, lambda *_: None)
    assert data["clusters"][0]["members"][0]["progress"]["green_streak"] == 1
    markdown = render_metaskill_markdown(data, "2026-11-02")
    assert "| 题目 | 做题轨迹 | 连绿进度 |" in markdown
    assert "🔴 → 🟡 → 🟢 | 1 / 3" in markdown
    assert "🔴 → 🟡 → 🟡 | 0 / 3" in markdown
    assert "未归簇-qid-123456789abc.md" in unquote(markdown)
