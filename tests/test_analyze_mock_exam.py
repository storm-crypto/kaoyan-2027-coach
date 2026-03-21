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
