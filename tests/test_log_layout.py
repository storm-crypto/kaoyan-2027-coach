"""test log_layout.py"""
import sys
from datetime import date

from helpers import SCRIPTS_DIR  # noqa: F401

sys.path.insert(0, str(SCRIPTS_DIR))

from log_layout import (  # noqa: E402
    WeekRange,
    all_log_dates,
    iso_week_range,
    iter_all_log_files,
    iter_log_files_in_range,
    latest_log_file,
    log_path_for,
    parse_legacy_weekly_recap_name,
    weekly_recap_path_for,
)


def test_iso_week_range_for_midweek_day():
    wr = iso_week_range(date(2026, 5, 22))  # 周五
    assert wr.iso_year == 2026
    assert wr.iso_week == 21
    assert wr.monday == date(2026, 5, 18)
    assert wr.sunday == date(2026, 5, 24)


def test_iso_week_range_for_monday():
    wr = iso_week_range(date(2026, 5, 18))
    assert wr.monday == date(2026, 5, 18)
    assert wr.sunday == date(2026, 5, 24)


def test_iso_week_range_for_sunday():
    wr = iso_week_range(date(2026, 5, 24))
    assert wr.monday == date(2026, 5, 18)


def test_iso_week_range_cross_year():
    """ISO 周可能跨年。2025-12-29 (周一) 属于 ISO 2026-W01。"""
    wr = iso_week_range(date(2025, 12, 29))
    assert wr.iso_year == 2026
    assert wr.iso_week == 1
    assert wr.monday == date(2025, 12, 29)
    assert wr.sunday == date(2026, 1, 4)
    assert wr.folder_name == "2026-W01-1229-0104"


def test_weekrange_folder_name_and_recap_filename():
    wr = iso_week_range(date(2026, 5, 22))
    assert wr.folder_name == "2026-W21-0518-0524"
    assert wr.weekly_recap_filename == "2026-W21-0518-0524-周复盘.md"
    assert wr.label == "2026-W21"


def test_log_path_for_returns_nested_path(tmp_path):
    p = log_path_for(tmp_path, date(2026, 5, 22))
    assert p == tmp_path / "学习日志" / "2026-W21-0518-0524" / "2026-05-22.md"


def test_weekly_recap_path_for(tmp_path):
    p = weekly_recap_path_for(tmp_path, date(2026, 5, 22))
    assert p == tmp_path / "复盘报告" / "2026-W21-0518-0524-周复盘.md"


def test_iter_all_log_files_reads_both_layouts(vault_root):
    # 老结构：根目录下
    (vault_root / "学习日志" / "2026-05-01.md").write_text("legacy", encoding="utf-8")
    # 新结构：周文件夹下
    new_dir = vault_root / "学习日志" / "2026-W21-0518-0524"
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "2026-05-22.md").write_text("new", encoding="utf-8")
    (new_dir / "2026-05-24.md").write_text("new", encoding="utf-8")
    # 不属于日期格式的文件应被忽略
    (vault_root / "学习日志" / "readme.md").write_text("x", encoding="utf-8")

    results = list(iter_all_log_files(vault_root))
    dates = [d for d, _ in results]
    assert dates == [date(2026, 5, 1), date(2026, 5, 22), date(2026, 5, 24)]


def test_iter_log_files_in_range(vault_root):
    (vault_root / "学习日志" / "2026-05-01.md").write_text("x", encoding="utf-8")
    (vault_root / "学习日志" / "2026-05-15.md").write_text("x", encoding="utf-8")
    (vault_root / "学习日志" / "2026-05-22.md").write_text("x", encoding="utf-8")
    results = list(iter_log_files_in_range(vault_root, date(2026, 5, 10), date(2026, 5, 20)))
    assert len(results) == 1
    assert results[0][0] == date(2026, 5, 15)


def test_latest_log_file(vault_root):
    (vault_root / "学习日志" / "2026-05-01.md").write_text("x", encoding="utf-8")
    new_dir = vault_root / "学习日志" / "2026-W21-0518-0524"
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "2026-05-24.md").write_text("x", encoding="utf-8")
    latest = latest_log_file(vault_root)
    assert latest is not None
    assert latest[0] == date(2026, 5, 24)
    assert latest[1].parent.name == "2026-W21-0518-0524"


def test_all_log_dates(vault_root):
    (vault_root / "学习日志" / "2026-05-01.md").write_text("x", encoding="utf-8")
    (vault_root / "学习日志" / "2026-05-15.md").write_text("x", encoding="utf-8")
    assert all_log_dates(vault_root) == [date(2026, 5, 1), date(2026, 5, 15)]


def test_iter_all_log_files_handles_duplicate_prefers_new_layout(vault_root):
    """同一日期同时存在新旧两份时优先新结构。"""
    (vault_root / "学习日志" / "2026-05-22.md").write_text("legacy", encoding="utf-8")
    new_dir = vault_root / "学习日志" / "2026-W21-0518-0524"
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "2026-05-22.md").write_text("new", encoding="utf-8")
    results = list(iter_all_log_files(vault_root))
    assert len(results) == 1
    assert "2026-W21-0518-0524" in str(results[0][1])


def test_parse_legacy_weekly_recap_name():
    wr = parse_legacy_weekly_recap_name("2026-W21-周复盘.md")
    assert wr is not None
    assert wr.iso_year == 2026
    assert wr.iso_week == 21
    assert wr.monday == date(2026, 5, 18)
    assert parse_legacy_weekly_recap_name("2026-W21-0518-0524-周复盘.md") is None
    assert parse_legacy_weekly_recap_name("foo.md") is None
