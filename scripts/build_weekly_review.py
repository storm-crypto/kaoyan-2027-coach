#!/usr/bin/env python3
"""汇总本周日志与复习记录，生成周复盘。"""
import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

from archive_ops import extract_list_items, infer_subject_mentions, load_template_markdown
from env_util import atomic_write, resolve_obsidian_root
from frontmatter import parse_frontmatter

SUBJECTS = ["数学一", "408", "英语一", "政治"]
HISTORY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) - (不会|半会|会) -", re.M)


def parse_today(value):
    return date.fromisoformat(value) if value else date.today()


def iso_week(today):
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso_year, iso_week_num, _ = monday.isocalendar()
    return monday, sunday, f"{iso_year}-W{iso_week_num:02d}"


def parse_logged_hours(text):
    match = re.search(r"时长[^0-9]*([0-9]+(?:\.[0-9]+)?)", text)
    return float(match.group(1)) if match else 0.0


def format_hours(value):
    if abs(value - int(value)) < 1e-9:
        return f"{int(value)} 小时"
    return f"{value:.1f} 小时"


def build_bullets(items, fallback):
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items[:3])


def collect_week_logs(obsidian_root, monday, sunday):
    log_dir = Path(obsidian_root) / "学习日志"
    highlights = []
    blockers = []
    logged_days = 0
    total_hours = 0.0

    current = monday
    while current <= sunday:
        log_path = log_dir / f"{current.isoformat()}.md"
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8")
            logged_days += 1
            total_hours += parse_logged_hours(text)
            highlights.extend(extract_list_items(text, "学到了什么"))
            blockers.extend(extract_list_items(text, "卡壳与挣扎"))
        current += timedelta(days=1)
    return highlights, blockers, logged_days, total_hours


def collect_review_stats(obsidian_root, monday, sunday):
    root = Path(obsidian_root) / "错题本"
    status_counts = {"不会": 0, "半会": 0, "会": 0}
    subject_counts = {subject: 0 for subject in SUBJECTS}

    if not root.exists():
        return 0, status_counts, subject_counts

    for md_file in root.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        _, body, _ = parse_frontmatter(text)
        rel = md_file.relative_to(root)
        subject = rel.parts[0] if rel.parts else ""
        for history_date, status in HISTORY_RE.findall(body):
            day = date.fromisoformat(history_date)
            if monday <= day <= sunday:
                status_counts[status] += 1
                if subject in subject_counts:
                    subject_counts[subject] += 1

    return sum(status_counts.values()), status_counts, subject_counts


def render_weekly_review(template, mapping):
    content = template
    for key, value in mapping.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def main():
    parser = argparse.ArgumentParser(description="生成周复盘")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    monday, sunday, week_label = iso_week(today)

    highlights, blockers, logged_days, total_hours = collect_week_logs(obsidian_root, monday, sunday)
    total_reviews, status_counts, subject_counts = collect_review_stats(obsidian_root, monday, sunday)
    subject_signal = infer_subject_mentions(highlights + blockers)
    combined_subject_counts = {
        subject: subject_counts[subject] + subject_signal.get(subject, 0)
        for subject in SUBJECTS
    }
    active_subjects = [
        subject for subject, count in sorted(combined_subject_counts.items(), key=lambda item: item[1], reverse=True)
        if count > 0
    ]
    active_subjects_text = "、".join(active_subjects[:3]) if active_subjects else "记录不足"

    review_stats = build_bullets([
        f"本周共记录 {total_reviews} 次复习更新。",
        f"状态分布：不会 {status_counts['不会']} / 半会 {status_counts['半会']} / 会 {status_counts['会']}。",
        "涉及科目：" + ("、".join(f"{subject} {subject_counts[subject]} 次" for subject in SUBJECTS if subject_counts[subject]) or "暂无。"),
    ], "- 本周暂未检索到复习更新。")

    next_actions = []
    if blockers:
        next_actions.append(f"优先拆解：{blockers[0]}")
    if active_subjects:
        next_actions.append(f"下周继续给 {active_subjects[0]} 留整块时间，别被碎任务切散。")
    if total_reviews == 0:
        next_actions.append("把 `/review` 固定到周中和周末各一次，避免旧题积压。")
    else:
        next_actions.append("保留一次周中检查点，及时把新卡点写回错题本或知识地图。")

    content = render_weekly_review(load_template_markdown("周复盘模板.md"), {
        "week_label": week_label,
        "week_range": f"{monday.isoformat()} ~ {sunday.isoformat()}",
        "logged_days": str(logged_days),
        "total_hours": format_hours(total_hours),
        "active_subjects": active_subjects_text,
        "highlights": build_bullets(highlights, "- 本周日志产出较少，优先补齐关键学习记录。"),
        "review_stats": review_stats,
        "blockers": build_bullets(blockers, "- 本周未显式记录卡点，建议下周把“卡在哪一步”写得更具体。"),
        "next_actions": build_bullets(next_actions, "- 下周先保证日志和复盘的连续性。"),
    })

    report_dir = Path(obsidian_root) / "复盘报告"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"{week_label}-周复盘.md"
    atomic_write(output_path, content)

    print(json.dumps({
        "path": str(output_path),
        "week_label": week_label,
        "logged_days": logged_days,
        "total_hours": round(total_hours, 2),
        "review_count": total_reviews,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
