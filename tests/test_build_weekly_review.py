"""test build_weekly_review.py"""
import json
import textwrap

from helpers import run_script


def _write_log(vault_root, day, hours, learned, blocker):
    log_path = vault_root / "学习日志" / f"{day}.md"
    log_path.write_text(textwrap.dedent(f"""\
        # Session: {day}

        ## 今日概览
        - **主题**: 数学 + 408
        - **时长**: {hours}
        - **模式**: 错题解析 / 复习

        ## 学到了什么
        - {learned}

        ## 卡壳与挣扎
        - {blocker}
    """), encoding="utf-8")


def _write_review_card(vault_root):
    card = vault_root / "错题本" / "数学一" / "高等数学" / "review-card.md"
    card.write_text(textwrap.dedent("""\
        ---
        source: test
        question_id: qid-weekreview1
        topic: 二重积分
        first_wrong_at: 2026-03-01
        last_review_at: 2026-03-18
        wrong_count: 2
        status: 半会
        next_review: 2026-03-21
        review_interval: 3
        ease_factor: 2.50
        ---

        ### 历史记录
        - 2026-03-17 - 半会 - 极坐标还不稳
        - 2026-03-19 - 会 - 思路清楚了
    """), encoding="utf-8")


def test_build_weekly_review(vault_root):
    _write_log(vault_root, "2026-03-16", 4, "数学二重积分拆清楚了", "408 进程调度还是容易混")
    _write_log(vault_root, "2026-03-18", 3.5, "英语阅读定位更快了", "数学计算还是会慌")
    _write_review_card(vault_root)

    rc, out, _ = run_script("build_weekly_review.py", [
        str(vault_root), "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["week_label"] == "2026-W12"
    assert data["logged_days"] == 2
    assert data["review_count"] == 2
    output_path = vault_root / "复盘报告" / "2026-W12-周复盘.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "7.5 小时" in content
    assert "数学" in content
