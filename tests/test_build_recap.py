"""test build_recap.py (周复盘 + 月复盘)"""
import json
import textwrap

from helpers import run_script


def _write_log(vault_root, day, hours, learned, blocker, scores=None):
    log_path = vault_root / "学习日志" / f"{day}.md"
    score_section = "## 训练成绩记录\n- 今天没有单独记录训练成绩。\n"
    if scores:
        rows = [
            "## 训练成绩记录",
            "| 科目 | 类型 | 来源 | 得分 | 满分 | 完成率 | 备注 |",
            "|------|------|------|------|------|--------|------|",
        ]
        for score in scores:
            rows.append(
                f"| {score['subject']} | {score['kind']} | {score['source']} | "
                f"{score['score']} | {score['total']} | {score['rate']} | {score['note']} |"
            )
        score_section = "\n".join(rows) + "\n"
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

        {score_section}
    """), encoding="utf-8")


def _write_review_card(vault_root, history_dates):
    card = vault_root / "错题本" / "数学一" / "高等数学" / "review-card.md"
    history_lines = "\n".join(f"- {d} - 半会 - 复习中" for d in history_dates)
    content = (
        "---\n"
        "source: test\n"
        "question_id: qid-weekreview1\n"
        "topic: 二重积分\n"
        "first_wrong_at: 2026-03-01\n"
        "last_review_at: 2026-03-18\n"
        "wrong_count: 2\n"
        "status: 半会\n"
        "next_review: 2026-03-21\n"
        "review_interval: 3\n"
        "ease_factor: 2.50\n"
        "---\n"
        "\n"
        "### 历史记录\n"
        f"{history_lines}\n"
    )
    card.write_text(content, encoding="utf-8")


def test_week_recap(vault_root):
    """周复盘：扫描本周一到周日的日志和错题卡历史。"""
    _write_log(
        vault_root,
        "2026-03-16",
        4,
        "数学二重积分拆清楚了",
        "408 进程调度还是容易混",
        scores=[{
            "subject": "数学一",
            "kind": "真题",
            "source": "2024 数学一真题",
            "score": "138",
            "total": "150",
            "rate": "92.0%",
            "note": "计算有点急",
        }],
    )
    _write_log(
        vault_root,
        "2026-03-18",
        3.5,
        "英语阅读定位更快了",
        "数学计算还是会慌",
        scores=[{
            "subject": "数学一",
            "kind": "真题",
            "source": "2025 数学一真题",
            "score": "145",
            "total": "150",
            "rate": "96.7%",
            "note": "整体更稳",
        }],
    )
    _write_review_card(vault_root, ["2026-03-17", "2026-03-19"])

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "week"
    assert data["label"] == "2026-W12"
    assert data["logged_days"] == 2
    assert data["review_count"] == 2
    assert data["score_count"] == 2
    output_path = vault_root / "复盘报告" / "2026-W12-周复盘.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "7.5 小时" in content
    assert "数学" in content
    assert "## 成绩趋势" in content
    assert "数学一·真题：2 次，首次 138/150，最近 145/150，最高 145/150" in content


def test_week_recap_default_period(vault_root):
    """不传 --period 默认就是周复盘。"""
    _write_log(vault_root, "2026-03-16", 2, "学了点东西", "没啥卡点")

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "week"


def test_month_recap(vault_root):
    """月复盘：扫描当月 1 日到月末的日志和错题卡历史。"""
    # 写 3 月的多天日志
    _write_log(vault_root, "2026-03-05", 3, "数学极限搞懂了", "408 还是有点乱")
    _write_log(vault_root, "2026-03-12", 4, "线性代数开始有感觉", "政治马原太绕")
    _write_log(
        vault_root,
        "2026-03-20",
        5,
        "英语阅读提速",
        "数学积分还需练",
        scores=[{
            "subject": "英语一",
            "kind": "阅读",
            "source": "张剑阅读 08",
            "score": "17",
            "total": "20",
            "rate": "85.0%",
            "note": "第四篇两题犹豫",
        }],
    )
    _write_review_card(vault_root, ["2026-03-05", "2026-03-12", "2026-03-20"])

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["period"] == "month"
    assert data["label"] == "2026年03月"
    assert data["logged_days"] == 3
    assert data["review_count"] == 3
    assert data["score_count"] == 1
    assert "2026-03-01 ~ 2026-03-31" in data["date_range"]
    output_path = vault_root / "复盘报告" / "2026-03-月复盘.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "12 小时" in content
    assert "# 月复盘：2026年03月" in content
    assert "## 本月概览" in content
    assert "## 成绩趋势" in content
    assert "## 下月建议" in content


def test_month_recap_empty(vault_root):
    """月复盘：没有任何日志和错题也不报错。"""
    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "month", "--today", "2026-03-20"
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["logged_days"] == 0
    assert data["review_count"] == 0


def test_week_recap_supports_legacy_indented_score_heading(vault_root):
    log_path = vault_root / "学习日志" / "2026-03-16.md"
    log_path.write_text(textwrap.dedent("""\
        # Session: 2026-03-16

        ## 今日概览
        - **主题**: 数学
        - **时长**: 2

          ## 训练成绩记录
          | 科目 | 类型 | 来源 | 得分 | 满分 | 完成率 | 备注 |
          |------|------|------|------|------|--------|------|
          | 数学一 | 真题 | 2024 数学一真题 | 138 | 150 | 92.0% | legacy heading |
    """), encoding="utf-8")

    rc, out, _ = run_script("build_recap.py", [
        str(vault_root), "--period", "week", "--today", "2026-03-20"
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["score_count"] == 1
