#!/usr/bin/env python3
"""聚合每日计划候选池；所有排序、预算和计划正文由 AI 调用方决定。"""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import sys
from datetime import date
from typing import Optional

from archive_ops import extract_list_items, load_archive_text, parse_daily_hours
from breakthrough_ops import parse_breakthroughs
from env_util import atomic_write, json_error, resolve_obsidian_root, split_optional_root_and_value
from plan_ops import yesterday_completion_rate
from study_ops import parse_today
from textbook_progress import load_week_textbook_rows


def scan_due_clusters(obsidian_root: Path, today: date) -> list:
    """直接调用原扫描入口，保留题面 payload、SRS 行为和簇原始顺序。"""
    result = subprocess.run([
        sys.executable, str(Path(__file__).with_name('scan_due_reviews.py')),
        str(obsidian_root), '--today', today.isoformat(), '--by-cluster',
    ], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)['clusters']


def build_candidate_pool(obsidian_root: Path, today: date, available_hours: Optional[float] = None,
                         archive_text: Optional[str] = None) -> dict:
    if archive_text is None:
        _, archive_text = load_archive_text(obsidian_root)
    if available_hours is None:
        available_hours = parse_daily_hours(archive_text)
    if available_hours is None:
        raise ValueError('缺少今日可用时长：请在档案中填写“每日可投入时长”，或显式传入时长')
    if not math.isfinite(available_hours) or available_hours <= 0:
        raise ValueError('今日可用时长必须是大于 0 的有限数值')
    rate, unfinished = yesterday_completion_rate(obsidian_root, today)
    _, textbooks = load_week_textbook_rows(obsidian_root, today)
    return {
        'due_clusters': scan_due_clusters(obsidian_root, today),
        'breakthroughs': parse_breakthroughs(archive_text, active_only=True),
        'yesterday_unfinished': unfinished,
        'yesterday_completion_rate': rate,
        'focus_items': extract_list_items(archive_text, '最近聚焦问题（只保留 3-5 条）'),
        'textbook_progress': [asdict(row) for row in textbooks],
        'available_hours': available_hours,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='输出每日计划候选池 JSON')
    parser.add_argument('arg1', nargs='?', help='Obsidian vault 根目录或今日可用小时数')
    parser.add_argument('arg2', nargs='?', help='今日可用小时数')
    parser.add_argument('--today')
    parser.add_argument('--write', action='store_true', help='落盘到 周计划/_候选池-YYYY-MM-DD.json')
    args = parser.parse_args()
    root_arg, hours_arg = split_optional_root_and_value(args.arg1, args.arg2)
    try:
        root = resolve_obsidian_root(root_arg)
        today = parse_today(args.today)
        pool = build_candidate_pool(root, today, float(hours_arg) if hours_arg is not None else None)
        content = json.dumps(pool, ensure_ascii=False, indent=2, allow_nan=False)
        if args.write:
            target = root / '周计划' / f'_候选池-{today.isoformat()}.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, content + '\n')
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        json_error(str(exc))
    print(content)


if __name__ == '__main__':
    main()
