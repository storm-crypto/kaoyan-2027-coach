"""test build_dashboard.py"""
import json
import textwrap

from helpers import run_script


def _write_log(vault_root, day, topic, hours, learned="", blocker=""):
    log_path = vault_root / "学习日志" / f"{day}.md"
    log_path.write_text(textwrap.dedent(f"""\
        # Session: {day}

        ## 今日概览
        - **主题**: {topic}
        - **时长**: {hours}
        - **模式**: 综合学习

        ## 学到了什么
        - {learned or topic}

        ## 卡壳与挣扎
        - {blocker or "暂无"}
    """), encoding="utf-8")


def _write_408_card(vault_root, filename, created_at, last_review_at, next_review, status, review_interval, chapter="数据结构"):
    card = vault_root / "错题本" / "408" / chapter / filename
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(textwrap.dedent(f"""\
        ---
        source: 王道
        question_id: qid-123456abcdef
        topic: 树的遍历
        error_tags: [遍历]
        first_wrong_at: {created_at}
        last_review_at: {last_review_at}
        wrong_count: 2
        status: {status}
        next_review: {next_review}
        review_interval: {review_interval}
        ease_factor: 2.50
        ---

        ### 历史记录
        - {created_at} - 不会 - 首次归档
        - {last_review_at} - {status} - 再看一遍
    """), encoding="utf-8")
    return card


def test_build_dashboard_outputs_payload_and_html(sample_archive, sample_card, knowledge_map, vault_root):
    _write_log(vault_root, "2026-03-16", "数学一 + 408", "4", "数学二重积分", "408 调度")
    _write_log(vault_root, "2026-03-17", "英语一阅读", "2.5", "英语阅读定位", "速度偏慢")
    _write_408_card(
        vault_root,
        "tree-review-qid-123456abcdef.md",
        "2026-03-18",
        "2026-03-19",
        "2026-03-19",
        "不会",
        1,
    )
    rc, _, err = run_script("record_paper_score.py", [
        str(vault_root),
        "408",
        "--date", "2026-03-20",
        "--paper", "王道8套卷1",
        "--paper-type", "模拟",
        "--total", "118",
        "--issues", "OS 调度、CO 指令系统",
        "--score-choice-ds", "8",
        "--score-choice-co", "6",
        "--score-choice-os", "5",
        "--score-choice-cn", "7",
        "--score-big-ds", "26",
        "--score-big-co", "18",
        "--score-big-os", "22",
        "--score-big-cn", "26",
        "--loss-choice-os", "2",
        "--loss-big-os", "1",
    ])
    assert rc == 0, err
    rc, _, err = run_script("record_paper_score.py", [
        str(vault_root),
        "数学一",
        "--date", "2026-03-20",
        "--paper", "2024 真题二刷",
        "--paper-type", "真题",
        "--total", "128",
        "--issues", "中值定理、线积分",
        "--score-objective", "44",
        "--score-big", "84",
    ])
    assert rc == 0, err
    rc, _, err = run_script("record_paper_score.py", [
        str(vault_root),
        "英语一",
        "--date", "2026-03-19",
        "--paper", "张剑黄皮书 2018",
        "--paper-type", "真题",
        "--total", "78",
        "--issues", "翻译句子切分、作文表达单一",
    ])
    assert rc == 0, err

    rc, out, err = run_script("build_dashboard.py", [str(vault_root), "--today", "2026-03-20"])
    assert rc == 0, err

    data = json.loads(out)
    assert {"overview", "subjects", "reviews", "score_trends", "knowledge_maps", "activity", "quality"}.issubset(data.keys())
    assert data["overview"]["due_total"] == 2
    assert data["overview"]["new_cards_this_week"] == 1
    assert data["reviews"]["due_total"] == 2
    assert data["reviews"]["by_subject"][0]["label"] == "数学一"
    assert data["score_trends"]["408"]["has_loss_metrics"] is True
    assert data["score_trends"]["math1"]["latest"]["paper"] == "2024 真题二刷"
    assert data["score_trends"]["english1"]["latest"]["total_score"] == 78.0
    assert data["path"].endswith("可视化面板/index.html")

    output_path = vault_root / "可视化面板" / "index.html"
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "Kaoyan Coach 学习驾驶舱" in html
    assert "总览卡片" in html
    assert "科目进度总览" in html
    assert "成绩趋势面板" in html
    assert "实际得分" in html
    assert "失分/错题数" in html
    assert "复习止损面板" in html
    assert "沉淀质量面板" in html
    assert "成果感面板" in html
    assert "到期卡按状态分布" in html
    assert "最近 5 条卷子记录" in html
    assert "查看原始数据" in html


def test_build_dashboard_handles_empty_vault(vault_root):
    rc, out, err = run_script("build_dashboard.py", [str(vault_root), "--today", "2026-03-20"])
    assert rc == 0, err

    data = json.loads(out)
    assert data["overview"]["due_total"] == 0
    assert data["results"]["total_cards"] == 0
    assert data["quality"]["warnings"]
    output_path = vault_root / "可视化面板" / "index.html"
    html = output_path.read_text(encoding="utf-8")
    assert "尚无结构化沉淀" in html or "尚无知识地图数据" in html
    assert "还没有学习者档案" in html


def test_build_dashboard_marks_single_subject_structure(knowledge_map, sample_card, vault_root):
    _write_log(vault_root, "2026-03-16", "数学一极限", "3", "数学函数极限", "极限证明")

    rc, out, err = run_script("build_dashboard.py", [str(vault_root), "--today", "2026-03-20"])
    assert rc == 0, err

    data = json.loads(out)
    assert data["subjects"]["structured_subjects"] == ["数学一"]
    assert "408" in data["subjects"]["blank_subjects"]
    km_math = next(row for row in data["knowledge_maps"]["by_subject"] if row["subject"] == "数学一")
    assert km_math["total_topics"] == 5
    assert km_math["unmarked"] == 5
    matrix_math = next(row for row in data["quality"]["subject_matrix"] if row["subject"] == "数学一")
    matrix_408 = next(row for row in data["quality"]["subject_matrix"] if row["subject"] == "408")
    assert matrix_math["wrong_cards"] is True
    assert matrix_408["wrong_cards"] is False


def test_build_dashboard_buckets_overdue_reviews(sample_card, vault_root):
    _write_408_card(
        vault_root,
        "os-review-qid-123456abcdef.md",
        "2026-03-10",
        "2026-03-18",
        "2026-03-17",
        "半会",
        2,
        chapter="操作系统",
    )

    rc, out, err = run_script("build_dashboard.py", [str(vault_root), "--today", "2026-03-28"])
    assert rc == 0, err

    data = json.loads(out)
    overdue = {item["label"]: item["value"] for item in data["reviews"]["overdue_buckets"]}
    assert overdue["超期 8 天+"] == 2
    assert overdue["超期 4-7 天"] == 0
    top_chapters = data["reviews"]["top_chapters"]
    assert any(item["subject"] == "数学一" for item in top_chapters)
    assert any(item["subject"] == "408" for item in top_chapters)
