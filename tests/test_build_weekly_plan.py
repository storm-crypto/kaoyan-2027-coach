"""test build_weekly_plan.py"""
import json
import textwrap

from helpers import run_script


def _make_due_card(vault_root, subject, filename, next_review):
    card_dir = vault_root / "错题本" / subject / "专题"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / filename
    card.write_text(textwrap.dedent(f"""\
        ---
        source: test
        question_id: qid-plan000001
        topic: test topic
        first_wrong_at: 2026-03-01
        last_review_at: 2026-03-10
        wrong_count: 1
        status: 半会
        next_review: {next_review}
        review_interval: 3
        ease_factor: 2.50
        ---

        test
    """), encoding="utf-8")
    return card


def test_build_weekly_plan(sample_archive, vault_root):
    _make_due_card(vault_root, "数学一", "math.md", "2026-03-18")
    _make_due_card(vault_root, "408", "408.md", "2026-03-17")

    rc, out, _ = run_script("build_weekly_plan.py", [
        str(vault_root), "24", "--today", "2026-03-18"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["week_label"] == "2026-W12"
    assert data["total_hours"] == 24.0
    output_path = vault_root / "周计划" / "2026-W12.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "数学一" in content
    assert "408" in content
    assert "24" in content


def test_build_weekly_plan_requires_hours_when_missing(vault_root):
    archive = vault_root / "我的学习者档案.md"
    archive.write_text(textwrap.dedent("""\
        # 我的学习者档案

        ## 基本信息
        - **每日可投入时长**：

        ## 最近聚焦问题（只保留 3-5 条）
        - 数学微分中值定理
    """), encoding="utf-8")

    rc, out, _ = run_script("build_weekly_plan.py", [str(vault_root)])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "每日可投入时长" in data["message"]
