"""test analyze_mock_exam.py"""
import json

from helpers import run_script


def test_analyze_mock_exam(sample_archive, vault_root):
    rc, out, _ = run_script("analyze_mock_exam.py", [
        str(vault_root),
        "政治=62",
        "数学一=118",
        "英语一=80",
        "408=95",
        "--date", "2026-03-21",
        "--note", "三月模考",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["total_score"] == 355.0
    output_path = vault_root / "复盘报告" / "2026-03-21-模考分析.md"
    assert output_path.exists()
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "| 2026-03-21 | 62 | 118 | 80 | 95 | 355 | 三月模考 |" in archive_text
    report = output_path.read_text(encoding="utf-8")
    assert "总分" in report
    assert "355" in report


def test_analyze_mock_exam_same_day_is_upsert(sample_archive, vault_root):
    run_script("analyze_mock_exam.py", [
        str(vault_root),
        "政治=62",
        "数学一=118",
        "英语一=80",
        "408=95",
        "--date", "2026-03-21",
        "--note", "初版",
    ])

    rc, out, _ = run_script("analyze_mock_exam.py", [
        str(vault_root),
        "政治=63",
        "数学一=120",
        "英语一=80",
        "408=95",
        "--date", "2026-03-21",
        "--note", "修正版",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["total_delta"] == "+20"
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert archive_text.count("| 2026-03-21 |") == 1
    assert "| 2026-03-21 | 63 | 120 | 80 | 95 | 358 | 修正版 |" in archive_text


def test_analyze_mock_exam_with_partial_targets(sample_archive, vault_root):
    text = sample_archive.read_text(encoding="utf-8")
    text = text.replace("| 数学一 | 105 | 125 | 20 | 计算和方法都要提速 |", "| 数学一 | 105 | | | 计算和方法都要提速 |")
    text = text.replace("| 英语一 | 72 | 80 | 8 | 阅读速度偏慢 |", "| 英语一 | 72 | | | 阅读速度偏慢 |")
    text = text.replace("| 408 | 92 | 100 | 8 | OS 和计网容易失分 |", "| 408 | 92 | | | OS 和计网容易失分 |")
    sample_archive.write_text(text, encoding="utf-8")

    rc, out, _ = run_script("analyze_mock_exam.py", [
        str(vault_root),
        "政治=62",
        "数学一=118",
        "英语一=80",
        "408=95",
        "--date", "2026-03-21",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["total_score"] == 355.0
    report = (vault_root / "复盘报告" / "2026-03-21-模考分析.md").read_text(encoding="utf-8")
    assert "各科目标分尚未补全" in report
