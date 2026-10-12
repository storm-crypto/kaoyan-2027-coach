#!/usr/bin/env python3
"""每日 6 点 AI 调用方的唯一上下文入口；输出候选池与档案事实摘要。"""
import argparse
import json
import subprocess

from archive_ops import archive_daily_plan, load_archive_text
from build_daily_plan import build_candidate_pool
from env_util import json_error, resolve_obsidian_root
from load_context import build_archive_summary
from study_ops import parse_today


def main() -> None:
    parser = argparse.ArgumentParser(description='聚合每日计划上下文 JSON')
    parser.add_argument('obsidian_root', nargs='?')
    parser.add_argument('--today')
    parser.add_argument('--available-hours', type=float, help='覆盖档案中的每日可投入时长')
    args = parser.parse_args()
    try:
        root = resolve_obsidian_root(args.obsidian_root)
        today = parse_today(args.today)
        _, archive_text = load_archive_text(root)
        # 昨日计划通常仍在固定文件中；先快照才能在本次上下文里计算昨日完成率。
        archive_daily_plan(root, today)
        context = build_candidate_pool(root, today, args.available_hours, archive_text)
        context['archive_summary'] = build_archive_summary(root, today, archive_text)
        print(json.dumps(context, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        json_error(str(exc))


if __name__ == '__main__':
    main()
