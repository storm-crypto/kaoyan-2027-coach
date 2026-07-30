#!/usr/bin/env python3
"""基于档案聚焦问题和到期复习生成今日计划。"""
import argparse
import json
from collections import Counter
from typing import List, Mapping, Optional, Sequence, Tuple, TypedDict

from archive_ops import (
    extract_list_items,
    infer_subject_mentions,
    load_archive_text,
    load_template_markdown,
    parse_daily_hours,
)
from constants import (
    DAILY_PLAN_CARD_HOURS,
    DAILY_PLAN_DUE_LIMIT,
    DAILY_PLAN_MIN_REVIEW_HOURS,
    DAILY_PLAN_MIN_REVIEW_TRIGGER_HOURS,
    DAILY_PLAN_PRIMARY_SUBJECT_SHARE,
    DAILY_PLAN_PROGRESS_WRAPUP_MINUTES,
    DAILY_PLAN_REVIEW_HOURS_RATIO,
)
from env_util import json_error, resolve_obsidian_root, split_optional_root_and_value
from metaskill_index import (
    dominant_subject,
    group_due_by_cluster,
    load_index,
    pick_clusters_for_session,
)
from study_ops import DueCard, PLAN_SUBJECTS, collect_due_cards, format_hours, parse_today
from textbook_progress import (
    build_plan_items,
    load_week_textbook_rows,
    render_today_textbook_section,
)


class PlanTask(TypedDict):
    type: str
    subject: str
    hours: float
    title: str
    detail: str


def parse_args() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    parser = argparse.ArgumentParser(description="生成今日计划")
    parser.add_argument("arg1", nargs="?", default=None, help="Obsidian vault 根目录或今日可用时长")
    parser.add_argument("arg2", nargs="?", default=None, help="今日可用时长（小时）")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()
    obsidian_root_arg, available_hours_arg = split_optional_root_and_value(args.arg1, args.arg2)
    return obsidian_root_arg, available_hours_arg, args.today


def rank_subjects(focus_counts: Mapping[str, int], due_counts: Mapping[str, int]) -> List[str]:
    return sorted(
        PLAN_SUBJECTS,
        key=lambda subject: (focus_counts.get(subject, 0) * 2 + due_counts.get(subject, 0), focus_counts.get(subject, 0), due_counts.get(subject, 0)),
        reverse=True,
    )


def rank_due_only_subjects(due_counts: Mapping[str, int]) -> List[str]:
    # 这里故意沿用 PLAN_SUBJECTS 的稳定顺序做并列打破，避免无聚焦问题时被偶然的字典/扫描顺序左右。
    return sorted(PLAN_SUBJECTS, key=lambda subject: due_counts.get(subject, 0), reverse=True)


def build_task_list(
    available_hours: float,
    focus_items: Sequence[str],
    due_cards: Sequence[DueCard],
    cluster_groups: Optional[Sequence[dict]] = None,
) -> Tuple[List[PlanTask], List[DueCard], List[str]]:
    # 复习时段默认按元技能成串排：挑效率最高的 1-3 个簇，宁可略超 DAILY_PLAN_DUE_LIMIT
    # 也不把簇拆开——拆开就退化成逐卡复习，失去「同一动作换不同外衣」的检验作用。
    # 索引缺失时 cluster_groups 为空，自动退化为原来的扁平取前 N 张。
    picked_clusters: List[dict] = []
    if cluster_groups:
        picked_clusters = pick_clusters_for_session(cluster_groups, DAILY_PLAN_DUE_LIMIT)
        selected_due = [card for group in picked_clusters for card in group["cards"]]
    else:
        selected_due = list(due_cards[:DAILY_PLAN_DUE_LIMIT])
    selected_due_count = len(selected_due)
    due_counts = Counter(card["subject"] for card in selected_due)
    focus_counts = infer_subject_mentions(focus_items)
    ranked_subjects = rank_subjects(focus_counts, due_counts)

    if not any(focus_counts.values()) and selected_due:
        ranked_subjects = rank_due_only_subjects(due_counts)

    review_hours = 0.0
    if selected_due:
        # 有簇时用簇自带的耗时估算（它按「讲清动作 + 连做全簇」标定），否则退回按卡数估
        if picked_clusters:
            estimated = sum((group.get("min") or 30) for group in picked_clusters) / 60.0
        else:
            estimated = selected_due_count * DAILY_PLAN_CARD_HOURS
        review_hours = min(available_hours * DAILY_PLAN_REVIEW_HOURS_RATIO, estimated)
        if available_hours >= DAILY_PLAN_MIN_REVIEW_TRIGGER_HOURS:
            review_hours = max(review_hours, DAILY_PLAN_MIN_REVIEW_HOURS)
        review_hours = min(review_hours, available_hours)
    deep_work_hours = max(available_hours - review_hours, 0.0)

    tasks: List[PlanTask] = []
    if picked_clusters:
        # 一个簇一条复习任务，标题就是那句「看到 X → 做 Y」
        for group in picked_clusters:
            share = group["due_count"] / selected_due_count if selected_due_count else 0
            topics = "、".join(card["topic"] for card in group["cards"][:4] if card.get("topic"))
            if group["due_count"] > 4:
                topics += f" 等 {group['due_count']} 张"
            mark = " ⭐标杆弱项" if group.get("landmark") else ""
            tasks.append({
                "type": "review",
                "subject": dominant_subject(group),
                "hours": round(review_hours * share, 2),
                "title": f"元技能专题 {group['cluster_id']}：{group['skill']}{mark}",
                "detail": f"本簇到期 {group['due_count']} 张｜{group['ch']}｜{topics}"
                          f"\n先不看卡念一遍上面那句口令，再连做全簇——同一动作换不同外衣才算检验迁移。",
            })
    else:
        for subject in ranked_subjects:
            count = due_counts.get(subject, 0)
            if not count:
                continue
            subject_review_hours = review_hours * count / selected_due_count
            tasks.append({
                "type": "review",
                "subject": subject,
                "hours": round(subject_review_hours, 2),
                "title": f"先复习 {count} 道到期旧题",
                "detail": "元技能索引缺失，暂按 interval 最小排；建好索引后会自动改为按簇成串。",
            })

    major_subjects = ranked_subjects[:2] if available_hours >= 3 else ranked_subjects[:1]
    if deep_work_hours > 0 and major_subjects:
        split = (
            [deep_work_hours]
            if len(major_subjects) == 1
            else [
                deep_work_hours * DAILY_PLAN_PRIMARY_SUBJECT_SHARE,
                deep_work_hours * (1 - DAILY_PLAN_PRIMARY_SUBJECT_SHARE),
            ]
        )
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


def render_tasks(tasks: Sequence[PlanTask]) -> str:
    lines: List[str] = []
    for index, task in enumerate(tasks, start=1):
        lines.append(
            f"{index}. [{task['subject']}] {task['title']}（{format_hours(task['hours'])} 小时）"
        )
        # detail 可以是多行（如元技能专题会附卡片清单 + 口令提示）；
        # 每行都要缩进成同一个 bullet 的续行，否则会跳出列表破坏渲染。
        for part in str(task["detail"]).split("\n"):
            part = part.strip()
            if part:
                lines.append(f"   - {part}")
    return "\n".join(lines)


def main() -> None:
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
    index = load_index(obsidian_root)
    cluster_groups = group_due_by_cluster(due_cards, index) if index.get("clusters") else []
    tasks, selected_due, ranked_subjects = build_task_list(
        available_hours, focus_items, due_cards, cluster_groups
    )

    if due_cards:
        due_summary = f"共 {len(due_cards)} 道，今日先处理 {len(selected_due)} 道"
    else:
        due_summary = "今天没有到期旧题，可以把整块时间留给新内容"

    _, textbook_rows = load_week_textbook_rows(obsidian_root, today)
    textbook_items = build_plan_items(textbook_rows, today)
    textbook_section_md = render_today_textbook_section(textbook_items)
    textbook_section_block = (textbook_section_md + "\n\n") if textbook_section_md else ""

    content = load_template_markdown("今日计划模板.md")
    replacements = {
        "today": today.isoformat(),
        "available_hours": format_hours(available_hours),
        "due_summary": due_summary,
        "focus_subjects": " / ".join(ranked_subjects[:2]),
        "textbook_section": textbook_section_block,
        "tasks": render_tasks(tasks),
        "closing_notes": "\n".join([
            "- 每个科目时段都先清旧题，再进新内容。",
            f"- 结束前留 {DAILY_PLAN_PROGRESS_WRAPUP_MINUTES} 分钟执行一次 `/progress`，把卡点和收获沉淀下来。",
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
        "textbooks": [
            {
                "name": item.name,
                "current": item.current_page,
                "end": item.end_page,
                "remaining_pages": item.remaining_pages,
                "remaining_days": item.remaining_days,
                "today_pages": item.today_pages,
                "done": item.done,
                "note": item.note,
            }
            for item in textbook_items
        ],
        "markdown": content + "\n",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
