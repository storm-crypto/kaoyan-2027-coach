"""test migrate_log_layout.py"""
import json
from datetime import date

from helpers import run_script


def test_migrate_logs_moves_legacy_to_week_folders(vault_root):
    # 老结构：根目录平铺的日志
    (vault_root / "学习日志" / "2026-05-18.md").write_text("week21 mon", encoding="utf-8")
    (vault_root / "学习日志" / "2026-05-22.md").write_text("week21 fri", encoding="utf-8")
    (vault_root / "学习日志" / "2026-03-16.md").write_text("week12 mon", encoding="utf-8")

    rc, out, _ = run_script("migrate_log_layout.py", [str(vault_root)])
    assert rc == 0
    data = json.loads(out)
    assert data["summary"]["logs_moved"] == 3

    # 验证新路径
    assert (vault_root / "学习日志" / "2026-W21-0518-0524" / "2026-05-18.md").exists()
    assert (vault_root / "学习日志" / "2026-W21-0518-0524" / "2026-05-22.md").exists()
    assert (vault_root / "学习日志" / "2026-W12-0316-0322" / "2026-03-16.md").exists()
    # 老路径已删
    assert not (vault_root / "学习日志" / "2026-05-18.md").exists()


def test_migrate_logs_dry_run_does_not_move(vault_root):
    (vault_root / "学习日志" / "2026-05-22.md").write_text("x", encoding="utf-8")
    rc, out, _ = run_script("migrate_log_layout.py", [str(vault_root), "--dry-run"])
    assert rc == 0
    data = json.loads(out)
    assert data["dry_run"] is True
    assert data["summary"]["logs_moved"] == 1
    # 实际文件没动
    assert (vault_root / "学习日志" / "2026-05-22.md").exists()
    assert not (vault_root / "学习日志" / "2026-W21-0518-0524" / "2026-05-22.md").exists()


def test_migrate_recaps_renames_legacy_weekly(vault_root):
    (vault_root / "复盘报告" / "2026-W21-周复盘.md").write_text("legacy", encoding="utf-8")
    (vault_root / "复盘报告" / "2026-W12-周复盘.md").write_text("legacy", encoding="utf-8")
    # 月复盘应保留原状
    (vault_root / "复盘报告" / "2026-03-月复盘.md").write_text("month", encoding="utf-8")

    rc, out, _ = run_script("migrate_log_layout.py", [str(vault_root)])
    assert rc == 0
    data = json.loads(out)
    assert data["summary"]["recaps_moved"] == 2

    assert (vault_root / "复盘报告" / "2026-W21-0518-0524-周复盘.md").exists()
    assert (vault_root / "复盘报告" / "2026-W12-0316-0322-周复盘.md").exists()
    assert not (vault_root / "复盘报告" / "2026-W21-周复盘.md").exists()
    # 月复盘保持
    assert (vault_root / "复盘报告" / "2026-03-月复盘.md").exists()


def test_migrate_is_idempotent(vault_root):
    (vault_root / "学习日志" / "2026-05-22.md").write_text("x", encoding="utf-8")
    run_script("migrate_log_layout.py", [str(vault_root)])

    # 再跑一次应该是 no-op
    rc, out, _ = run_script("migrate_log_layout.py", [str(vault_root)])
    assert rc == 0
    data = json.loads(out)
    assert data["summary"]["logs_moved"] == 0
    assert data["summary"]["recaps_moved"] == 0


def test_migrate_skips_when_target_exists(vault_root):
    """如果同一日期新老两个路径都有，跳过且记录原因，不覆盖新路径。"""
    (vault_root / "学习日志" / "2026-05-22.md").write_text("legacy content", encoding="utf-8")
    new_dir = vault_root / "学习日志" / "2026-W21-0518-0524"
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "2026-05-22.md").write_text("new content", encoding="utf-8")

    rc, out, _ = run_script("migrate_log_layout.py", [str(vault_root)])
    data = json.loads(out)
    assert data["summary"]["logs_moved"] == 0
    assert data["summary"]["logs_skipped"] == 1
    # 新文件内容没被覆盖
    assert (new_dir / "2026-05-22.md").read_text() == "new content"
    # 老文件保留
    assert (vault_root / "学习日志" / "2026-05-22.md").exists()


def test_migrate_handles_cross_year_iso_week(vault_root):
    """2025-12-29 (周一) 属于 ISO 2026-W01。"""
    (vault_root / "学习日志" / "2025-12-29.md").write_text("x", encoding="utf-8")
    rc, out, _ = run_script("migrate_log_layout.py", [str(vault_root)])
    data = json.loads(out)
    assert data["summary"]["logs_moved"] == 1
    target = vault_root / "学习日志" / "2026-W01-1229-0104" / "2025-12-29.md"
    assert target.exists()
