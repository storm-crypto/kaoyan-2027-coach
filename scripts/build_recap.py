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

from archive_ops import extract_list_items, extract_section_block, infer_subject_mentions, load_template_markdown
from env_util import atomic_write, resolve_obsidian_root
from frontmatter import parse_frontmatter
from study_ops import PLAN_SUBJECTS, format_hours, parse_today

HISTORY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) - (不会|半会|会) -", re.M)
LEGACY_HEADING_INDENT_LIMIT = 200
LEGACY_SCORE_SECTION_RE = re.compile(
    rf"^[ \t]{{0,{LEGACY_HEADING_INDENT_LIMIT}}}## 训练成绩记录\r?\n"
    rf"(.*?)(?=^[ \t]{{0,{LEGACY_HEADING_INDENT_LIMIT}}}## |\Z)",
    re.M | re.S,
)


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
def recap_hours(value):
    return f"{format_hours(value)} 小时"


def build_bullets(items, fallback):
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items[:5])


def format_number(value):
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def parse_score_records(text, log_day):
    block = extract_section_block(text, "训练成绩记录")
    if not block:
        legacy_match = LEGACY_SCORE_SECTION_RE.search(text)
        block = legacy_match.group(1).strip("\r\n") if legacy_match else ""
    records = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != 7 or cells[0] in {"科目", "------"} or set(cells[0]) == {"-"}:
            continue
        if not cells[3] or not cells[4]:
            continue
        score_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cells[3])
        total_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cells[4])
        if not score_match or not total_match:
            continue
        score = float(score_match.group(1))
        total = float(total_match.group(1))
        if total <= 0:
            continue
        records.append({
            "date": log_day,
            "subject": cells[0],
            "kind": cells[1],
            "source": cells[2],
            "score": score,
            "total": total,
            "note": cells[6] if cells[6] != "-" else "",
        })
    return records


def collect_logs(obsidian_root, start, end):
    """扫描日期范围内的学习日志。"""
    log_dir = Path(obsidian_root) / "学习日志"
    highlights, blockers = [], []
    logged_days = 0
    total_hours = 0.0
    score_records = []

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
            score_records.extend(parse_score_records(text, current))
        current += timedelta(days=1)
    return highlights, blockers, logged_days, total_hours, score_records


def collect_review_stats(obsidian_root, start, end):
    """扫描日期范围内的错题卡复习历史。"""
    root = Path(obsidian_root) / "错题本"
    status_counts = {"不会": 0, "半会": 0, "会": 0}
    subject_counts = {subject: 0 for subject in PLAN_SUBJECTS}

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


def build_score_summary(score_records, period_name):
    if not score_records:
        return f"- 本{period_name}没有结构化记录训练成绩；后续可在 `/progress` 里补成绩项。", {}

    grouped = {}
    for item in score_records:
        key = (item["subject"], item["kind"])
        grouped.setdefault(key, []).append(item)

    lines = [f"- 本{period_name}共记录 {len(score_records)} 条训练成绩。"]
    subject_counts = {}
    ordered_groups = []

    for key, records in grouped.items():
        records.sort(key=lambda item: (item["date"], item["source"]))
        subject, kind = key
        subject_counts[subject] = subject_counts.get(subject, 0) + len(records)
        first = records[0]
        latest = records[-1]
        best = max(records, key=lambda item: (item["score"] / item["total"], item["score"], item["date"]))
        avg_rate = sum(item["score"] / item["total"] for item in records) / len(records)
        delta = (latest["score"] / latest["total"] - first["score"] / first["total"]) * 100
        ordered_groups.append({
            "subject": subject,
            "kind": kind,
            "count": len(records),
            "first": first,
            "latest": latest,
            "best": best,
            "avg_rate": avg_rate,
            "delta": delta,
        })

    ordered_groups.sort(
        key=lambda item: (item["latest"]["date"], item["count"], item["latest"]["score"] / item["latest"]["total"]),
        reverse=True,
    )

    for item in ordered_groups[:5]:
        latest = item["latest"]
        first = item["first"]
        best = item["best"]
        if item["count"] == 1:
            lines.append(
                "- {subject}·{kind}：1 次，最近 {score}/{total}，完成率 {rate:.1f}%。".format(
                    subject=item["subject"],
                    kind=item["kind"],
                    score=format_number(latest["score"]),
                    total=format_number(latest["total"]),
                    rate=latest["score"] / latest["total"] * 100,
                )
            )
            continue

        delta_text = "持平"
        if abs(item["delta"]) >= 0.05:
            sign = "+" if item["delta"] > 0 else ""
            delta_text = f"{sign}{item['delta']:.1f}pct"
        lines.append(
            "- {subject}·{kind}：{count} 次，首次 {first_score}/{first_total}，最近 {latest_score}/{latest_total}，"
            "最高 {best_score}/{best_total}，平均完成率 {avg_rate:.1f}%（{delta_text}）。".format(
                subject=item["subject"],
                kind=item["kind"],
                count=item["count"],
                first_score=format_number(first["score"]),
                first_total=format_number(first["total"]),
                latest_score=format_number(latest["score"]),
                latest_total=format_number(latest["total"]),
                best_score=format_number(best["score"]),
                best_total=format_number(best["total"]),
                avg_rate=item["avg_rate"] * 100,
                delta_text=delta_text,
            )
        )

    return "\n".join(lines), subject_counts


def render_recap(template, mapping):
    content = template
    for key, value in mapping.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def generate_recap(obsidian_root, target_date, period, force=False):
    start, end, label, filename = get_date_range(target_date, period)
    report_dir = Path(obsidian_root) / "复盘报告"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / filename

    if output_path.exists() and not force:
        return None  # 已存在，不重复生成

    period_name = "月" if period == "month" else "周"
    template_name = "月复盘模板.md" if period == "month" else "周复盘模板.md"

    highlights, blockers, logged_days, total_hours, score_records = collect_logs(obsidian_root, start, end)
    total_reviews, status_counts, subject_counts = collect_review_stats(obsidian_root, start, end)
    score_stats, score_subject_counts = build_score_summary(score_records, period_name)
    subject_signal = infer_subject_mentions(highlights + blockers)
    combined = {
        s: subject_counts[s] + subject_signal.get(s, 0) + score_subject_counts.get(s, 0)
        for s in PLAN_SUBJECTS
    }
    active_subjects = [s for s, c in sorted(combined.items(), key=lambda x: x[1], reverse=True) if c > 0]
    active_subjects_text = "、".join(active_subjects[:3]) if active_subjects else "记录不足"

    review_stats = build_bullets([
        f"本{period_name}共记录 {total_reviews} 次复习更新。",
        f"状态分布：不会 {status_counts['不会']} / 半会 {status_counts['半会']} / 会 {status_counts['会']}。",
        "涉及科目：" + ("、".join(f"{s} {subject_counts[s]} 次" for s in PLAN_SUBJECTS if subject_counts[s]) or "暂无。"),
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
        "period_label": label,
        "period_range": f"{start.isoformat()} ~ {end.isoformat()}",
        "logged_days": str(logged_days),
        "total_hours": recap_hours(total_hours),
        "active_subjects": active_subjects_text,
        "highlights": build_bullets(highlights, f"- 本{period_name}日志产出较少，优先补齐关键学习记录。"),
        "score_stats": score_stats,
        "review_stats": review_stats,
        "blockers": build_bullets(blockers, f"- 本{period_name}未显式记录卡点，建议把卡点写得更具体。"),
        "next_actions": build_bullets(next_actions, f"- 下{period_name}先保证日志和复盘的连续性。"),
    })

    atomic_write(output_path, content)

    return {
        "path": str(output_path),
        "period": period,
        "label": label,
        "date_range": f"{start.isoformat()} ~ {end.isoformat()}",
        "logged_days": logged_days,
        "total_hours": round(total_hours, 2),
        "review_count": total_reviews,
        "score_count": len(score_records),
    }


def main():
    parser = argparse.ArgumentParser(description="生成周/月复盘")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--period", choices=["week", "month"], default="week", help="复盘周期（默认 week）")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    
    # 自动补齐上一周期的复盘（不强制覆盖已有的）
    if args.period == "month":
        # 找上个月某一天
        first_day_of_this_month = today.replace(day=1)
        prev_target_date = first_day_of_this_month - timedelta(days=1)
    else:
        # 找上周某一天
        monday = today - timedelta(days=today.weekday())
        prev_target_date = monday - timedelta(days=1)
        
    prev_result = generate_recap(obsidian_root, prev_target_date, args.period, force=False)
    
    # 生成当前周期的复盘（强制覆盖更新）
    current_result = generate_recap(obsidian_root, today, args.period, force=True)

    out = dict(current_result or {})
    out["backfilled"] = prev_result

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
