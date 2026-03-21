#!/usr/bin/env python3
"""基于学习者档案和到期错题生成周计划。"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from archive_ops import (
    extract_list_items,
    infer_subject_mentions,
    load_archive_text,
    load_template_markdown,
    parse_daily_hours,
)
from env_util import atomic_write, resolve_obsidian_root
from frontmatter import parse_frontmatter

SUBJECTS = ["数学一", "408", "英语一", "政治"]


def parse_today(value):
    return date.fromisoformat(value) if value else date.today()


def iso_week(today):
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso_year, iso_week_num, _ = monday.isocalendar()
    return monday, sunday, f"{iso_year}-W{iso_week_num:02d}"


def format_hours(value):
    rounded = round(value * 2) / 2
    if abs(rounded - int(rounded)) < 1e-9:
        return str(int(rounded))
    return f"{rounded:.1f}"


def count_due_reviews(obsidian_root, today):
    due_counts = {subject: 0 for subject in SUBJECTS}
    root = Path(obsidian_root) / "错题本"
    if not root.exists():
        return due_counts

    for md_file in root.rglob("*.md"):
        try:
            fm, _, _ = parse_frontmatter(md_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if "next_review" not in fm:
            continue
        try:
            next_review = date.fromisoformat(fm["next_review"])
            interval = int(fm.get("review_interval", "1") or "1")
        except (TypeError, ValueError):
            continue
        if next_review <= today and interval < 90:
            rel = md_file.relative_to(root)
            subject = rel.parts[0] if rel.parts else ""
            if subject in due_counts:
                due_counts[subject] += 1
    return due_counts


def allocate_hours(total_hours, focus_counts, due_counts):
    weights = {}
    for subject in SUBJECTS:
        weights[subject] = 1.0 + focus_counts.get(subject, 0) * 1.4 + min(due_counts.get(subject, 0), 5) * 0.8

    weight_sum = sum(weights.values()) or float(len(SUBJECTS))
    rounded = {
        subject: round((total_hours * weights[subject] / weight_sum) * 2) / 2
        for subject in SUBJECTS
    }
    diff = round((total_hours - sum(rounded.values())) * 2) / 2
    if abs(diff) > 1e-9:
        top_subject = max(SUBJECTS, key=lambda item: (weights[item], rounded[item]))
        rounded[top_subject] = round((rounded[top_subject] + diff) * 2) / 2
    return rounded


def subject_goal(subject, focus_items, due_count):
    aliases = {"数学一": "数学", "英语一": "英语"}
    for item in focus_items:
        if subject in item or aliases.get(subject, "") in item:
            return item
    if due_count:
        return f"清掉 {due_count} 道到期复习，避免旧题积压"
    return "推进本周主线内容"


def render_weekly_plan(template, mapping):
    content = template
    for key, value in mapping.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def main():
    parser = argparse.ArgumentParser(description="生成周计划")
    parser.add_argument("arg1", nargs="?", default=None, help="Obsidian vault 根目录或总时长")
    parser.add_argument("arg2", nargs="?", default=None, help="总时长（小时）")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root_arg = args.arg1
    total_hours_arg = args.arg2
    if args.arg1:
        try:
            float(args.arg1)
        except ValueError:
            pass
        else:
            obsidian_root_arg = None
            total_hours_arg = args.arg1

    obsidian_root = resolve_obsidian_root(obsidian_root_arg)
    _, archive_text = load_archive_text(obsidian_root)
    today = parse_today(args.today)
    monday, sunday, week_label = iso_week(today)
    focus_items = extract_list_items(archive_text, "最近聚焦问题（只保留 3-5 条）")
    focus_counts = infer_subject_mentions(focus_items)
    due_counts = count_due_reviews(obsidian_root, today)

    total_hours = float(total_hours_arg) if total_hours_arg else parse_daily_hours(archive_text) * 7
    allocations = allocate_hours(total_hours, focus_counts, due_counts)
    ranked_subjects = sorted(
        SUBJECTS,
        key=lambda item: (allocations[item], due_counts[item], focus_counts.get(item, 0)),
        reverse=True,
    )
    priority_summary = f"优先推进 {ranked_subjects[0]} / {ranked_subjects[1]}，并清理 {sum(due_counts.values())} 道到期复习"

    subject_rows = []
    for subject in SUBJECTS:
        subject_rows.append(
            f"| {subject} | {format_hours(allocations[subject])} | {due_counts[subject]} | {subject_goal(subject, focus_items, due_counts[subject])} |"
        )

    daily_rhythm = "\n".join([
        "- 周一到周五：每天先用 20-30 分钟处理到期复习，再进入当天主攻科目。",
        f"- 周中主攻：把整块时间优先留给 {ranked_subjects[0]} 和 {ranked_subjects[1]}，避免每科都浅尝即止。",
        f"- 周末收口：安排一次整块训练，并围绕 {ranked_subjects[0]} 做总结或回看。",
    ])
    checkpoints = "\n".join([
        f"1. 周三前清掉至少 {max(1, min(sum(due_counts.values()), 3))} 道到期复习。",
        f"2. 本周至少完成一次 {ranked_subjects[0]} 的计时训练或专题复盘。",
        "3. 周末执行一次 `/week_review`，把产出和卡点沉淀下来。",
    ])

    content = render_weekly_plan(load_template_markdown("周计划模板.md"), {
        "week_label": week_label,
        "week_range": f"{monday.isoformat()} ~ {sunday.isoformat()}",
        "total_hours": format_hours(total_hours),
        "priority_summary": priority_summary,
        "subject_rows": "\n".join(subject_rows),
        "daily_rhythm": daily_rhythm,
        "checkpoints": checkpoints,
    })

    plan_dir = Path(obsidian_root) / "周计划"
    plan_dir.mkdir(parents=True, exist_ok=True)
    output_path = plan_dir / f"{week_label}.md"
    atomic_write(output_path, content)

    print(json.dumps({
        "path": str(output_path),
        "week_label": week_label,
        "week_range": f"{monday.isoformat()} ~ {sunday.isoformat()}",
        "total_hours": round(total_hours, 2),
        "due_total": sum(due_counts.values()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
