#!/usr/bin/env python3
"""汇总指定周期的日志与复习记录，生成复盘报告。

用法:
  python3 build_recap.py [OBSIDIAN_ROOT] [--period week|month] [--today YYYY-MM-DD]
  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

默认为周复盘。加 --period month 做月复盘。
"""
import argparse
import calendar
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


def get_date_range(today, period):
    """根据周期返回 (start, end, label, filename)。"""
    if period == "month":
        start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day)
        label = f"{today.year}年{today.month:02d}月"
        filename = f"{today.strftime('%Y-%m')}-月复盘.md"
    else:
        monday = today - timedelta(days=today.weekday())
        end = monday + timedelta(days=6)
        start = monday
        iso_year, iso_week_num, _ = monday.isocalendar()
        label = f"{iso_year}-W{iso_week_num:02d}"
        filename = f"{label}-周复盘.md"
    return start, end, label, filename


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
    return "\n".join(f"- {item}" for item in items[:5])


def collect_logs(obsidian_root, start, end):
    """扫描日期范围内的学习日志。"""
    log_dir = Path(obsidian_root) / "学习日志"
    highlights, blockers = [], []
    logged_days = 0
    total_hours = 0.0

    current = start
    while current <= end:
        log_path = log_dir / f"{current.isoformat()}.md"
        if log_path.exists():
            try:
                text = log_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                current += timedelta(days=1)
                continue
            logged_days += 1
            total_hours += parse_logged_hours(text)
            highlights.extend(extract_list_items(text, "学到了什么"))
            blockers.extend(extract_list_items(text, "卡壳与挣扎"))
        current += timedelta(days=1)
    return highlights, blockers, logged_days, total_hours


def collect_review_stats(obsidian_root, start, end):
    """扫描日期范围内的错题卡复习历史。"""
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
            try:
                day = date.fromisoformat(history_date)
            except ValueError:
                continue
            if start <= day <= end:
                status_counts[status] += 1
                if subject in subject_counts:
                    subject_counts[subject] += 1

    return sum(status_counts.values()), status_counts, subject_counts


def render_recap(template, mapping):
    content = template
    for key, value in mapping.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def main():
    parser = argparse.ArgumentParser(description="生成周/月复盘")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--period", choices=["week", "month"], default="week", help="复盘周期（默认 week）")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    start, end, label, filename = get_date_range(today, args.period)
    period_name = "月" if args.period == "month" else "周"
    template_name = "月复盘模板.md" if args.period == "month" else "周复盘模板.md"

    highlights, blockers, logged_days, total_hours = collect_logs(obsidian_root, start, end)
    total_reviews, status_counts, subject_counts = collect_review_stats(obsidian_root, start, end)
    subject_signal = infer_subject_mentions(highlights + blockers)
    combined = {s: subject_counts[s] + subject_signal.get(s, 0) for s in SUBJECTS}
    active_subjects = [s for s, c in sorted(combined.items(), key=lambda x: x[1], reverse=True) if c > 0]
    active_subjects_text = "、".join(active_subjects[:3]) if active_subjects else "记录不足"

    review_stats = build_bullets([
        f"本{period_name}共记录 {total_reviews} 次复习更新。",
        f"状态分布：不会 {status_counts['不会']} / 半会 {status_counts['半会']} / 会 {status_counts['会']}。",
        "涉及科目：" + ("、".join(f"{s} {subject_counts[s]} 次" for s in SUBJECTS if subject_counts[s]) or "暂无。"),
    ], f"- 本{period_name}暂未检索到复习更新。")

    next_actions = []
    if blockers:
        next_actions.append(f"优先拆解：{blockers[0]}")
    if active_subjects:
        next_actions.append(f"下{period_name}继续给 {active_subjects[0]} 留整块时间。")
    if total_reviews == 0:
        next_actions.append("把 `/review` 固定到常规节奏，避免旧题积压。")
    else:
        next_actions.append("保留检查点，及时把新卡点写回错题本或知识地图。")

    content = render_recap(load_template_markdown(template_name), {
        "week_label": label,
        "week_range": f"{start.isoformat()} ~ {end.isoformat()}",
        "logged_days": str(logged_days),
        "total_hours": format_hours(total_hours),
        "active_subjects": active_subjects_text,
        "highlights": build_bullets(highlights, f"- 本{period_name}日志产出较少，优先补齐关键学习记录。"),
        "review_stats": review_stats,
        "blockers": build_bullets(blockers, f"- 本{period_name}未显式记录卡点，建议把卡点写得更具体。"),
        "next_actions": build_bullets(next_actions, f"- 下{period_name}先保证日志和复盘的连续性。"),
    })

    report_dir = Path(obsidian_root) / "复盘报告"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / filename
    atomic_write(output_path, content)

    print(json.dumps({
        "path": str(output_path),
        "period": args.period,
        "label": label,
        "date_range": f"{start.isoformat()} ~ {end.isoformat()}",
        "logged_days": logged_days,
        "total_hours": round(total_hours, 2),
        "review_count": total_reviews,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
