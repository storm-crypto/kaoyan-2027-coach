"""每日计划完成率计算和 AI 已生成正文的安全写入。"""
import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from archive_ops import archive_daily_plan
from constants import DAILY_PLAN_RELATIVE_PATH
from daily_plan_state import preserve_completed_tasks
from env_util import atomic_write, json_error, resolve_obsidian_root
from study_ops import parse_today


def yesterday_completion_rate(obsidian_root: Path, today: date) -> Tuple[Optional[float], List[str]]:
    """只统计昨日归档中「任务清单」二级标题区的任务；空清单完成率为 0。"""
    path = Path(obsidian_root) / Path(DAILY_PLAN_RELATIVE_PATH).parent / f"_今日计划-{(today - timedelta(days=1)).isoformat()}.md"
    if not path.exists():
        return None, []
    text = path.read_text(encoding="utf-8")
    in_tasks = False
    fenced = False
    total = done = 0
    unfinished = []
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            in_tasks = heading.group(1) == "任务清单"
            continue
        if re.match(r"^#\s+", line):
            in_tasks = False
        task = re.match(r"^\s*-\s+\[([ xX])\]\s+(.+?)\s*$", line)
        if in_tasks and task:
            total += 1
            if task.group(1).lower() == "x":
                done += 1
            else:
                unfinished.append(task.group(2))
    return (done / total if total else 0.0), unfinished


def write_daily_plan(obsidian_root: Path, today: date, markdown: str) -> Path:
    """先归档，再原子写入 AI 生成的正文；同日保留已完成任务与备注。"""
    if not re.search(rf"^# 今日计划[：:]\s*{today.isoformat()}\s*$", markdown, re.M):
        raise ValueError("计划标题日期必须与 today 一致")
    target = Path(obsidian_root) / DAILY_PLAN_RELATIVE_PATH
    if target.exists():
        markdown = preserve_completed_tasks(markdown, target.read_text(encoding="utf-8"))
    archive_daily_plan(obsidian_root, today)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, markdown)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="归档或写入 AI 生成的今日计划")
    parser.add_argument("obsidian_root", nargs="?")
    parser.add_argument("--today")
    parser.add_argument("--content-file", help="AI 已生成的 Markdown 文件；省略则仅归档")
    args = parser.parse_args()
    try:
        root = resolve_obsidian_root(args.obsidian_root)
        today = parse_today(args.today)
        if args.content_file:
            path = write_daily_plan(root, today, Path(args.content_file).read_text(encoding="utf-8"))
            result = {"plan_path": str(path)}
        else:
            path = archive_daily_plan(root, today)
            result = {"archive_path": str(path) if path else None}
    except (OSError, ValueError) as exc:
        json_error(str(exc))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
