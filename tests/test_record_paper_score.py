"""test record_paper_score.py"""
import json
from pathlib import Path

import pytest

from helpers import run_script
from score_record_lib import parse_score_record


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
    assert "| 2026-03-24 | 模拟 | 王道8套卷1 | 34 | 24 | 27 | 33 | 118 | OS 调度、CO 指令系统 | 结构还不稳 |" in archive_text


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


def test_record_politics_paper_score(sample_archive, vault_root):
    rc, out, err = run_script("record_paper_score.py", [
        str(vault_root),
        "政治",
        "--date", "2026-03-26",
        "--paper", "肖四1",
        "--paper-type", "模拟",
        "--total", "62",
        "--issues", "选择失分多,马原概念混",
        "--note", "首次刷肖四,大题没背",
    ])
    assert rc == 0, err

    data = json.loads(out)
    assert data["subject"] == "政治"
    assert data["total_score"] == 62.0
    record_text = (vault_root / "成绩记录" / "政治" / "2026-03-26-模拟-肖四1.md").read_text(encoding="utf-8")
    assert "subject: 政治" in record_text
    assert "total_score: 62" in record_text
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "## 政治模拟成绩追踪" in archive_text
    assert "| 2026-03-26 | 模拟 | 肖四1 | 62 | 选择失分多,马原概念混 | 首次刷肖四,大题没背 |" in archive_text


def test_record_paper_score_unknown_subject_lists_legal_values(sample_archive, vault_root):
    rc, out, err = run_script("record_paper_score.py", [
        str(vault_root),
        "高数",
        "--paper", "x",
        "--paper-type", "模拟",
        "--total", "100",
        "--issues", "x",
    ])
    assert rc == 1, err
    data = json.loads(out)
    assert "不支持的科目" in data["message"]
    assert "数学一" in data["message"]
    assert "政治" in data["message"]


def test_wrong_questions_round_trip_and_score_only_update_preserves_them(sample_archive, vault_root):
    args = [str(vault_root), "数学一", "--paper", "2010卷", "--paper-type", "真题",
            "--total", "100", "--issues", "计算问题", "--date", "2026-10-12"]
    rc, out, err = run_script("record_paper_score.py", args + ["--wrong-questions", "3:没思路;8:算错:符号|含`引号\""])
    assert rc == 0, err
    path = Path(json.loads(out)["record_path"])
    errors = parse_score_record(path)["wrong_questions"]
    assert errors == [
        {"question_number": 3, "error_description": "没思路", "record_date": "2026-10-12"},
        {"question_number": 8, "error_description": "算错:符号|含`引号\"", "record_date": "2026-10-12"},
    ]
    rc, _, err = run_script("record_paper_score.py", args)
    assert rc == 0, err
    assert parse_score_record(path)["wrong_questions"] == errors
    rc, _, err = run_script("record_paper_score.py", args + ["--wrong-questions", ""])
    assert rc == 0, err
    assert parse_score_record(path)["wrong_questions"] == []


@pytest.mark.parametrize("subject,number", [("数学一", 22), ("408", 40), ("408", 41), ("408", 47)])
def test_wrong_question_number_boundaries(sample_archive, vault_root, subject, number):
    rc, out, err = run_script("record_paper_score.py", [str(vault_root), subject, "--paper", "测试卷",
        "--paper-type", "模拟", "--total", "100", "--issues", "测试", "--wrong-questions", f"{number}:不会"])
    assert rc == 0, (out, err)
    record = parse_score_record(Path(json.loads(out)["record_path"]))
    assert record["wrong_questions"][0]["question_number"] == number


@pytest.mark.parametrize("subject,errors,topics", [
    ("数学一", "23:不会", None), ("408", "48:不会", None),
    ("数学一", "0:不会", None), ("数学一", "-1:不会", None),
    ("数学一", "x:不会", None), ("数学一", "3:", None),
    ("数学一", "3:不会;3:算错", None), ("数学一", "3没思路", None),
    ("数学一", "3:不会", "8:积分"), ("英语一", "3:不会", None),
])
def test_invalid_wrong_questions_do_not_write(sample_archive, vault_root, subject, errors, topics):
    old_archive = sample_archive.read_bytes()
    args = [str(vault_root), subject, "--paper", "测试卷", "--paper-type", "模拟", "--total", "100",
            "--issues", "测试", "--wrong-questions", errors]
    if topics is not None:
        args += ["--question-topics", topics]
    rc, out, _ = run_script("record_paper_score.py", args)
    assert rc == 1 and json.loads(out)["error"]
    assert sample_archive.read_bytes() == old_archive
    assert not (vault_root / "成绩记录").exists()
