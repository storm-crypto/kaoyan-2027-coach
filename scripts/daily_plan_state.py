"""今日计划的日期、任务与完成状态；Markdown 是唯一事实源。"""
import re

from archive_ops import extract_heading_block

DATE_RE = re.compile(r"^# 今日计划[：:]\s*(\d{4}-\d{2}-\d{2})", re.M)
TASK_RE = re.compile(r"^(?:\d+\.\s+|-\s+)(?:\[([ xX])\]\s+)?\[([^\]]+)\]\s+(.+)$")
HOURS_RE = re.compile(r"[（(]([\d.]+)\s*小时[）)]\s*$")


def parse_daily_plan(text):
    match = DATE_RE.search(text)
    tasks = []
    for line in extract_heading_block(text, "任务清单").splitlines():
        task = TASK_RE.match(line)
        if task:
            title = task.group(3).strip()
            hours = HOURS_RE.search(title)
            title = HOURS_RE.sub("", title).strip()
            tasks.append({
                "subject": task.group(2), "title": title,
                "hours": float(hours.group(1)) if hours else None,
                "done": (task.group(1) or "").lower() == "x",
                "detail": [], "block": line,
            })
        elif tasks and line.strip():
            tasks[-1]["detail"].append(line.strip().removeprefix("- "))
            tasks[-1]["block"] += "\n" + line
    return {"date": match.group(1) if match else None, "tasks": tasks}


def preserve_completed_tasks(markdown, previous):
    """同日重排保留已完成任务及其原始备注，即使新计划不再含该任务。"""
    old, new = parse_daily_plan(previous), parse_daily_plan(markdown)
    if not old["date"] or old["date"] != new["date"]:
        return markdown
    completed = {(t["subject"], t["title"]): t for t in old["tasks"] if t["done"]}
    for task in new["tasks"]:
        previous_task = completed.pop((task["subject"], task["title"]), None)
        if previous_task:
            markdown = markdown.replace(task["block"], previous_task["block"], 1)
    if completed:
        from archive_ops import replace_heading_block
        block = extract_heading_block(markdown, "任务清单").rstrip()
        block += "\n" + "\n".join(t["block"] for t in completed.values())
        markdown = replace_heading_block(markdown, "任务清单", block)
    return markdown
