"""学习日志与复盘报告的目录结构管理。

新结构：
- 学习日志/{YYYY-Www-MMDD-MMDD}/{YYYY-MM-DD}.md
  例：学习日志/2026-W21-0518-0524/2026-05-24.md
- 复盘报告/{YYYY-Www-MMDD-MMDD}-周复盘.md
  例：复盘报告/2026-W21-0518-0524-周复盘.md
- 复盘报告/{YYYY-MM}-月复盘.md（不带日期范围，月份本身已经明确）

老结构（迁移前/兼容期）：
- 学习日志/{YYYY-MM-DD}.md
- 复盘报告/{YYYY-Www}-周复盘.md

`iter_log_files` / `latest_log_file` 同时扫描两种结构，老文件未迁移完也能读到。
新写入一律走新结构（`log_path_for` / `weekly_recap_filename`）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

DATE_FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
WEEK_FOLDER_RE = re.compile(r"^(\d{4})-W(\d{2})(?:-(\d{2})(\d{2})-(\d{2})(\d{2}))?$")
LEGACY_WEEK_RECAP_RE = re.compile(r"^(\d{4})-W(\d{2})-周复盘\.md$")
NEW_WEEK_RECAP_RE = re.compile(r"^(\d{4})-W(\d{2})-(\d{2})(\d{2})-(\d{2})(\d{2})-周复盘\.md$")

LOG_ROOT_NAME = "学习日志"
RECAP_ROOT_NAME = "复盘报告"


@dataclass(frozen=True)
class WeekRange:
    iso_year: int
    iso_week: int
    monday: date
    sunday: date

    @property
    def label(self) -> str:
        """ISO 周标签：2026-W21"""
        return f"{self.iso_year}-W{self.iso_week:02d}"

    @property
    def folder_name(self) -> str:
        """学习日志周文件夹名：2026-W21-0518-0524"""
        return (
            f"{self.iso_year}-W{self.iso_week:02d}"
            f"-{self.monday.month:02d}{self.monday.day:02d}"
            f"-{self.sunday.month:02d}{self.sunday.day:02d}"
        )

    @property
    def weekly_recap_filename(self) -> str:
        """周复盘文件名：2026-W21-0518-0524-周复盘.md"""
        return f"{self.folder_name}-周复盘.md"


def iso_week_range(day: date) -> WeekRange:
    """根据任意日期，返回它所在的 ISO 周区间（周一 ~ 周日）。

    使用 `date.isocalendar()` 计算 ISO 年/周（注意 ISO 年和日历年在 12/1 月交界处可能不同）。
    """
    iso_year, iso_week, _ = day.isocalendar()
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)
    return WeekRange(iso_year=iso_year, iso_week=iso_week, monday=monday, sunday=sunday)


def log_path_for(obsidian_root: Path, day: date) -> Path:
    """返回 day 对应的学习日志写入路径（新结构）。"""
    root = Path(obsidian_root) / LOG_ROOT_NAME
    folder = iso_week_range(day).folder_name
    return root / folder / f"{day.isoformat()}.md"


def find_existing_log_path(obsidian_root: Path, day: date) -> Optional[Path]:
    """查找 day 对应的现有日志文件，优先新结构，回退老结构。无则 None。"""
    new_path = log_path_for(obsidian_root, day)
    if new_path.exists():
        return new_path
    legacy = Path(obsidian_root) / LOG_ROOT_NAME / f"{day.isoformat()}.md"
    if legacy.exists():
        return legacy
    return None


def weekly_recap_path_for(obsidian_root: Path, day: date) -> Path:
    """返回 day 对应的周复盘文件路径（新结构）。"""
    root = Path(obsidian_root) / RECAP_ROOT_NAME
    return root / iso_week_range(day).weekly_recap_filename


def _try_parse_filename_date(name: str) -> Optional[date]:
    m = DATE_FILENAME_RE.match(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def iter_all_log_files(obsidian_root: Path) -> Iterator[Tuple[date, Path]]:
    """枚举所有学习日志文件（新旧结构皆扫），按日期升序排序。

    返回 (date, Path) 元组。同一日期同时存在新旧两份时，**优先采用新结构那份**
    （理论上迁移后不该有这种重复，但兜底防止覆盖）。
    """
    root = Path(obsidian_root) / LOG_ROOT_NAME
    if not root.exists():
        return iter(())

    found: dict[date, Path] = {}

    # 新结构：子文件夹下
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        if not WEEK_FOLDER_RE.match(sub.name):
            # 不像周文件夹的目录跳过（比如用户自己建的其他子目录）
            continue
        for md in sorted(sub.glob("*.md")):
            day = _try_parse_filename_date(md.name)
            if day is not None:
                found[day] = md

    # 老结构：根目录平铺
    for md in sorted(root.glob("*.md")):
        day = _try_parse_filename_date(md.name)
        if day is None:
            continue
        # 只在 found 里没有时才记入（不覆盖已收集的新结构文件）
        found.setdefault(day, md)

    for day in sorted(found):
        yield day, found[day]


def iter_log_files_in_range(
    obsidian_root: Path, start: date, end: date
) -> Iterator[Tuple[date, Path]]:
    """枚举日期范围内的学习日志文件（新旧结构皆扫）。"""
    for day, path in iter_all_log_files(obsidian_root):
        if start <= day <= end:
            yield day, path


def latest_log_file(obsidian_root: Path) -> Optional[Tuple[date, Path]]:
    """返回最新一份学习日志的 (date, Path)。无日志返回 None。"""
    latest: Optional[Tuple[date, Path]] = None
    for day, path in iter_all_log_files(obsidian_root):
        if latest is None or day > latest[0]:
            latest = (day, path)
    return latest


def all_log_dates(obsidian_root: Path) -> List[date]:
    """枚举所有有日志的日期。供 dashboard 热力图用。"""
    return [day for day, _ in iter_all_log_files(obsidian_root)]


# ---------------------------------------------------------------------------
# 复盘报告
# ---------------------------------------------------------------------------


def parse_legacy_weekly_recap_name(name: str) -> Optional[WeekRange]:
    """解析老周复盘文件名 `YYYY-Www-周复盘.md`。返回对应 WeekRange，无法解析时 None。"""
    m = LEGACY_WEEK_RECAP_RE.match(name)
    if not m:
        return None
    iso_year, iso_week = int(m.group(1)), int(m.group(2))
    try:
        monday = date.fromisocalendar(iso_year, iso_week, 1)
    except ValueError:
        return None
    return iso_week_range(monday)


def is_new_weekly_recap_name(name: str) -> bool:
    return bool(NEW_WEEK_RECAP_RE.match(name))


__all__ = [
    "WeekRange",
    "LOG_ROOT_NAME",
    "RECAP_ROOT_NAME",
    "iso_week_range",
    "log_path_for",
    "weekly_recap_path_for",
    "iter_all_log_files",
    "iter_log_files_in_range",
    "latest_log_file",
    "all_log_dates",
    "parse_legacy_weekly_recap_name",
    "is_new_weekly_recap_name",
]
