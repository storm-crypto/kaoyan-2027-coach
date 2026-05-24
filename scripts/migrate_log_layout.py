#!/usr/bin/env python3
"""一次性迁移老学习日志/老周复盘文件到新结构。

老结构:
- 学习日志/{YYYY-MM-DD}.md
- 复盘报告/{YYYY-Www}-周复盘.md

新结构:
- 学习日志/{YYYY-Www-MMDD-MMDD}/{YYYY-MM-DD}.md
- 复盘报告/{YYYY-Www-MMDD-MMDD}-周复盘.md

用法:
  python3 scripts/migrate_log_layout.py [OBSIDIAN_ROOT] [--dry-run]

输出 JSON 报告 {moved_logs: [...], moved_recaps: [...], skipped: [...]}。
幂等：已经在新结构里的文件原样保留。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from env_util import json_error, resolve_obsidian_root
from log_layout import (
    DATE_FILENAME_RE,
    LOG_ROOT_NAME,
    RECAP_ROOT_NAME,
    iso_week_range,
    is_new_weekly_recap_name,
    log_path_for,
    parse_legacy_weekly_recap_name,
    weekly_recap_path_for,
)


def migrate_logs(obsidian_root: Path, dry_run: bool):
    log_root = obsidian_root / LOG_ROOT_NAME
    moved = []
    skipped = []
    if not log_root.exists():
        return moved, skipped

    # 枚举根目录下的平铺 .md 文件
    for md_file in sorted(log_root.glob("*.md")):
        m = DATE_FILENAME_RE.match(md_file.name)
        if not m:
            skipped.append({"path": str(md_file.relative_to(obsidian_root)), "reason": "filename not YYYY-MM-DD.md"})
            continue
        try:
            from datetime import date
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            skipped.append({"path": str(md_file.relative_to(obsidian_root)), "reason": "invalid date"})
            continue
        target = log_path_for(obsidian_root, day)
        if target == md_file:
            continue  # 已经在新结构（理论上不会，因为我们在根目录扫的）
        if target.exists():
            skipped.append({
                "path": str(md_file.relative_to(obsidian_root)),
                "reason": f"new path already exists: {target.relative_to(obsidian_root)}",
            })
            continue
        target.parent.mkdir(parents=True, exist_ok=True) if not dry_run else None
        if not dry_run:
            md_file.rename(target)
        moved.append({
            "from": str(md_file.relative_to(obsidian_root)),
            "to": str(target.relative_to(obsidian_root)),
            "iso_week": iso_week_range(day).label,
        })
    return moved, skipped


def migrate_recaps(obsidian_root: Path, dry_run: bool):
    recap_root = obsidian_root / RECAP_ROOT_NAME
    moved = []
    skipped = []
    if not recap_root.exists():
        return moved, skipped

    for md_file in sorted(recap_root.glob("*.md")):
        if is_new_weekly_recap_name(md_file.name):
            continue  # already migrated
        wr = parse_legacy_weekly_recap_name(md_file.name)
        if wr is None:
            # 不是老周复盘格式：跳过（月复盘、模考分析等保留原状）
            continue
        target = recap_root / wr.weekly_recap_filename
        if target == md_file:
            continue
        if target.exists():
            skipped.append({
                "path": str(md_file.relative_to(obsidian_root)),
                "reason": f"new name already exists: {target.relative_to(obsidian_root)}",
            })
            continue
        if not dry_run:
            md_file.rename(target)
        moved.append({
            "from": str(md_file.relative_to(obsidian_root)),
            "to": str(target.relative_to(obsidian_root)),
        })
    return moved, skipped


def cleanup_empty_legacy_folders(obsidian_root: Path, dry_run: bool):
    """如果学习日志根目录下没剩任何 .md（全都搬走了），不删根目录本身。
    迁移产生的新周文件夹用 mkdir(parents=True) 创建，已经存在则保留。
    这个函数主要用来报告状态，不做实际清理。"""
    log_root = obsidian_root / LOG_ROOT_NAME
    if not log_root.exists():
        return {"legacy_md_remaining": 0}
    remaining = list(log_root.glob("*.md"))
    return {"legacy_md_remaining": len(remaining)}


def main():
    parser = argparse.ArgumentParser(description="迁移学习日志/周复盘到新结构")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不实际移动文件")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    if not obsidian_root.exists():
        json_error(f"obsidian_root 不存在: {obsidian_root}")

    moved_logs, skipped_logs = migrate_logs(obsidian_root, args.dry_run)
    moved_recaps, skipped_recaps = migrate_recaps(obsidian_root, args.dry_run)
    state = cleanup_empty_legacy_folders(obsidian_root, args.dry_run)

    print(json.dumps({
        "dry_run": args.dry_run,
        "moved_logs": moved_logs,
        "moved_recaps": moved_recaps,
        "skipped_logs": skipped_logs,
        "skipped_recaps": skipped_recaps,
        "state": state,
        "summary": {
            "logs_moved": len(moved_logs),
            "recaps_moved": len(moved_recaps),
            "logs_skipped": len(skipped_logs),
            "recaps_skipped": len(skipped_recaps),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
