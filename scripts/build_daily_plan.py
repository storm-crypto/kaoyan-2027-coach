#!/usr/bin/env python3
"""基于档案聚焦问题和到期复习生成今日计划。"""
import argparse
import json
from collections import Counter

from archive_ops import (
    extract_list_items,
    infer_subject_mentions,
    load_archive_text,
    load_template_markdown,
    parse_daily_hours,
)
from env_util import json_error, resolve_obsidian_root
from study_ops import PLAN_SUBJECTS, collect_due_cards, format_hours, parse_today


def parse_args():
    parser = argparse.ArgumentParser(description="生成今日计划")
    parser.add_argument("arg1", nargs="?", default=None, help="Obsidian vault 根目录或今日可用时长")
    parser.add_argument("arg2", nargs="?", default=None, help="今日可用时长（小时）")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root_arg = args.arg1
    available_hours_arg = args.arg2
    if args.arg1:
        try:
            float(args.arg1)
        except ValueError:
            pass
        else:
            obsidian_root_arg = None
            available_hours_arg = args.arg1
    return obsidian_root_arg, available_hours_arg, args.today
def rank_subjects(focus_counts, due_counts):
    return sorted(
        PLAN_SUBJECTS,
        key=lambda subject: (focus_counts.get(subject, 0) * 2 + due_counts.get(subject, 0), focus_counts.get(subject, 0), due_counts.get(subject, 0)),
        reverse=True,
    )


def build_task_list(available_hours, focus_items, due_cards):
    selected_due = due_cards[:10]
    due_counts = Counter(card["subject"] for card in selected_due)
    focus_counts = infer_subject_mentions(focus_items)
    ranked_subjects = rank_subjects(focus_counts, due_counts)

    if not any(focus_counts.values()) and selected_due:
        ranked_subjects = sorted(due_counts, key=lambda subject: (due_counts[subject], subject), reverse=True) + [
            subject for subject in PLAN_SUBJECTS if subject not in due_counts
        ]

    review_hours = 0.0
    if selected_due:
        review_hours = min(available_hours * 0.4, len(selected_due) * 0.25)
        if available_hours >= 1.5:
            review_hours = max(review_hours, 0.5)
        review_hours = min(review_hours, available_hours)
    deep_work_hours = max(available_hours - review_hours, 0.0)

    tasks = []
    for subject in ranked_subjects:
        count = due_counts.get(subject, 0)
        if not count:
            continue
        subject_review_hours = review_hours * count / len(selected_due)
        tasks.append({
            "type": "review",
            "subject": subject,
            "hours": round(subject_review_hours, 2),
            "title": f"先复习 {count} 道到期旧题",
            "detail": "优先处理 interval 最小、最容易继续拖延的卡片。",
        })

    major_subjects = ranked_subjects[:2] if available_hours >= 3 else ranked_subjects[:1]
    if deep_work_hours > 0 and major_subjects:
        split = [deep_work_hours] if len(major_subjects) == 1 else [deep_work_hours * 0.6, deep_work_hours * 0.4]
        for subject, hours in zip(major_subjects, split):
            focus_goal = next(
                (
                    item for item in focus_items
                    if subject in item or (subject == "数学一" and "数学" in item) or (subject == "英语一" and "英语" in item)
                ),
                "推进本周主线内容",
            )
            tasks.append({
                "type": "deep_work",
                "subject": subject,
                "hours": round(hours, 2),
                "title": f"{subject} 主攻时段",
                "detail": focus_goal,
            })

    if not tasks:
        tasks.append({
            "type": "deep_work",
            "subject": ranked_subjects[0],
            "hours": round(available_hours, 2),
            "title": f"{ranked_subjects[0]} 主攻时段",
            "detail": "今天没有到期复习，直接推进当前主线内容。",
        })

    return tasks, selected_due, ranked_subjects


def render_tasks(tasks):
    lines = []
    for index, task in enumerate(tasks, start=1):
        lines.append(
            f"{index}. [{task['subject']}] {task['title']}（{format_hours(task['hours'])} 小时）"
        )
        lines.append(f"   - {task['detail']}")
    return "\n".join(lines)


def main():
    obsidian_root_arg, available_hours_arg, today_arg = parse_args()
    obsidian_root = resolve_obsidian_root(obsidian_root_arg)
    _, archive_text = load_archive_text(obsidian_root)
    today = parse_today(today_arg)

    if available_hours_arg:
        available_hours = float(available_hours_arg)
    else:
        daily_hours = parse_daily_hours(archive_text)
        if daily_hours is None:
            json_error("缺少今日可用时长：请在档案中补充“每日可投入时长”，或执行 /plan_today 时显式传入今日可用时长")
        available_hours = daily_hours

    focus_items = extract_list_items(archive_text, "最近聚焦问题（只保留 3-5 条）")
    due_cards = collect_due_cards(obsidian_root, today)
    tasks, selected_due, ranked_subjects = build_task_list(available_hours, focus_items, due_cards)

    if due_cards:
        due_summary = f"共 {len(due_cards)} 道，今日先处理 {len(selected_due)} 道"
    else:
        due_summary = "今天没有到期旧题，可以把整块时间留给新内容"

    content = load_template_markdown("今日计划模板.md")
    replacements = {
        "today": today.isoformat(),
        "available_hours": format_hours(available_hours),
        "due_summary": due_summary,
        "focus_subjects": " / ".join(ranked_subjects[:2]),
        "tasks": render_tasks(tasks),
        "closing_notes": "\n".join([
            "- 每个科目时段都先清旧题，再进新内容。",
            "- 结束前留 10 分钟执行一次 `/progress`，把卡点和收获沉淀下来。",
        ]),
    }
    for key, value in replacements.items():
        content = content.replace(f"{{{key}}}", value)

    print(json.dumps({
        "date": today.isoformat(),
        "available_hours": round(available_hours, 2),
        "due_total": len(due_cards),
        "due_selected": len(selected_due),
        "tasks": tasks,
        "markdown": content + "\n",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
