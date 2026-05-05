"""test record_paper_score.py"""
import json

from helpers import run_script


def test_record_math_paper_score_with_breakdown(sample_archive, vault_root):
    rc, out, err = run_script("record_paper_score.py", [
        str(vault_root),
        "数学一",
        "--date", "2026-03-24",
        "--paper", "2024 真题二刷",
        "--paper-type", "真题",
        "--total", "130",
        "--issues", "二次型不等式、二重积分换序",
        "--note", "真题二刷能看出基础回来了",
        "--score-objective", "46",
        "--score-big", "84",
    ])
    assert rc == 0, err

    data = json.loads(out)
    assert data["subject"] == "数学一"
    assert data["paper_type"] == "真题"
    record_text = (vault_root / "成绩记录" / "数学一" / "2026-03-24-真题-2024-真题二刷.md").read_text(encoding="utf-8")
    assert "score_objective: 46" in record_text
    assert "score_big: 84" in record_text
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "| 2026-03-24 | 真题 | 2024 真题二刷 | 130 | 二次型不等式、二重积分换序 | 真题二刷能看出基础回来了 |" in archive_text


def test_record_408_paper_score_with_loss_metrics(sample_archive, vault_root):
    rc, out, err = run_script("record_paper_score.py", [
        str(vault_root),
        "408",
        "--date", "2026-03-24",
        "--paper", "王道8套卷1",
        "--paper-type", "模拟",
        "--total", "118",
        "--issues", "OS 调度、CO 指令系统",
        "--note", "结构还不稳",
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

    data = json.loads(out)
    record_text = (vault_root / "成绩记录" / "408" / "2026-03-24-模拟-王道8套卷1.md").read_text(encoding="utf-8")
    assert "score_choice_ds: 8" in record_text
    assert "loss_big_os: 1" in record_text
    assert data["paper_type"] == "模拟"
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "| 2026-03-24 | 模拟 | 王道8套卷1 | 118 | OS 调度、CO 指令系统 | 结构还不稳 |" in archive_text


def test_record_english_paper_score(sample_archive, vault_root):
    rc, out, err = run_script("record_paper_score.py", [
        str(vault_root),
        "英语一",
        "--date", "2026-03-24",
        "--paper", "张剑黄皮书 2018",
        "--paper-type", "真题",
        "--total", "78.5",
        "--issues", "翻译句子切分、作文表达单一",
        "--note", "阅读稳定，作文还差火候",
        "--score-cloze", "6",
        "--score-reading", "30",
        "--score-new-type", "8",
        "--score-translation", "6.5",
        "--score-short-essay", "11",
        "--score-long-essay", "17",
    ])
    assert rc == 0, err

    data = json.loads(out)
    assert data["subject"] == "英语一"
    record_text = (vault_root / "成绩记录" / "英语一" / "2026-03-24-真题-张剑黄皮书-2018.md").read_text(encoding="utf-8")
    assert "score_translation: 6.5" in record_text
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "| 2026-03-24 | 真题 | 张剑黄皮书 2018 | 78.5 | 翻译句子切分、作文表达单一 | 阅读稳定，作文还差火候 |" in archive_text


def test_record_paper_score_accepts_total_only(sample_archive, vault_root):
    rc, out, err = run_script("record_paper_score.py", [
        str(vault_root),
        "英语一",
        "--date", "2026-03-25",
        "--paper", "英语模拟卷 3",
        "--paper-type", "模拟",
        "--total", "81",
        "--issues", "新题型和翻译不稳",
    ])
    assert rc == 0, err

    data = json.loads(out)
    assert data["total_score"] == 81.0
    record_text = (vault_root / "成绩记录" / "英语一" / "2026-03-25-模拟-英语模拟卷-3.md").read_text(encoding="utf-8")
    assert "score_reading:" not in record_text
