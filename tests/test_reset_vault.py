"""test reset_vault.py"""
import json

from helpers import run_script


def test_reset_vault_soft_preserves_profile_and_clears_generated_data(
    vault_root, sample_archive, knowledge_map, sample_card
):
    log_path = vault_root / "学习日志" / "2026-03-23.md"
    plan_path = vault_root / "周计划" / "2026-W12.md"
    report_path = vault_root / "复盘报告" / "2026-W12-周复盘.md"
    note_path = vault_root / "知识笔记" / "408" / "调度.md"

    log_path.write_text("# test log\n", encoding="utf-8")
    plan_path.write_text("# test plan\n", encoding="utf-8")
    report_path.write_text("# test report\n", encoding="utf-8")
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("# 手写笔记\n", encoding="utf-8")
    (knowledge_map / "数学一.md").write_text(
        "# 数学一 知识地图\n\n| 考点 | 掌握度 | 信心 | 备注 |\n|------|--------|------|------|\n| 二重积分 | 会 | 高 | 已经刷完 |\n",
        encoding="utf-8",
    )

    rc, out, _ = run_script("reset_vault.py", [str(vault_root), "--yes", "--today", "2026-03-23"])
    assert rc == 0
    data = json.loads(out)

    assert data["mode"] == "soft"
    assert "目标院校/专业" in data["preserved_profile_fields"]
    assert not log_path.exists()
    assert not plan_path.exists()
    assert not report_path.exists()
    assert not sample_card.exists()
    assert note_path.exists()
    assert (vault_root / "错题本" / "数学一").is_dir()
    assert (vault_root / "复盘报告").is_dir()

    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "计算机科学与技术" in archive_text
    assert "360" in archive_text
    assert "2026-12-20" in archive_text
    assert "6" in archive_text
    assert "408重构期 / 数学提速期" in archive_text
    assert "2026-03-23" in archive_text
    assert "OS 调度 | 408 | 高" not in archive_text
    assert "积分上下限混乱 | 数学一 | 3 次 | 2026-03-18" not in archive_text
    assert "| 2026-03-01 | 60 | 110 | 76 | 92 | 338 | 阶段基准 |" not in archive_text

    knowledge_text = (vault_root / "知识地图" / "数学一.md").read_text(encoding="utf-8")
    assert "二重积分 | 会 | 高 | 已经刷完" not in knowledge_text
    assert "05.5 二重积分（直角坐标/极坐标）" in knowledge_text


def test_reset_vault_hard_clears_profile(vault_root, sample_archive):
    rc, out, _ = run_script("reset_vault.py", [str(vault_root), "--yes", "--hard", "--today", "2026-03-23"])
    assert rc == 0
    data = json.loads(out)

    assert data["mode"] == "hard"
    assert data["preserved_profile_fields"] == []

    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "计算机科学与技术" not in archive_text
    assert "360" not in archive_text
    assert "2026-03-23" not in archive_text
    assert "- **目标院校/专业**：" in archive_text
    assert "- **考试日期**：（以当年公告为准）" in archive_text
    assert "- **最近更新日期**：YYYY-MM-DD" in archive_text


def test_reset_vault_requires_explicit_confirmation(vault_root, sample_archive):
    rc, out, _ = run_script("reset_vault.py", [str(vault_root)])
    assert rc != 0
    data = json.loads(out)
    assert data["error"] is True
    assert "--yes" in data["message"]
