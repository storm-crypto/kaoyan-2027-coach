#!/usr/bin/env python3
"""更新本周计划文件中某本教材的「当前」进度页码。"""
from __future__ import annotations

import argparse
import json

from env_util import json_error, resolve_obsidian_root
from study_ops import parse_today
from textbook_progress import update_current_page, week_plan_path


def main() -> None:
    parser = argparse.ArgumentParser(description="更新本周计划里教材当前进度")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--textbook", required=True, help="教材名称（支持包含匹配）")
    parser.add_argument("--current", required=True, help="新的当前进度，例如 p53")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    plan_path = week_plan_path(obsidian_root, today)

    ok, message = update_current_page(plan_path, args.textbook, args.current)
    if not ok:
        json_error(message)

    print(json.dumps({
        "path": str(plan_path),
        "textbook": args.textbook,
        "current": args.current,
        "message": message,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
