#!/usr/bin/env python3
"""导出考研学习驾驶舱 HTML。

用法:
  python3 build_dashboard.py [OBSIDIAN_ROOT] [--output path] [--today YYYY-MM-DD]

特点:
- 只读取现有档案、日志、错题卡、知识地图和报告
- 输出一个自包含 HTML，可直接通过 file:// 或双击打开
- stdout 返回 JSON payload，便于后续调试或扩展
"""
import argparse
import html
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from archive_ops import (
    extract_heading_block,
    extract_list_items,
    infer_subject_mentions,
    parse_mock_rows,
    parse_score_cell,
    parse_subject_score_rows,
)
from constants import PLAN_SUBJECTS, SCORE_SUBJECTS, SRS_GRADUATED_INTERVAL_DAYS
from env_util import atomic_write, resolve_obsidian_root
from frontmatter import parse_frontmatter
from score_record_lib import collect_score_records, format_optional_number, top_weakness_from_408_record
from study_ops import iter_review_cards, parse_today

SUBJECT_TO_KM_FILE = {
    "数学一": "数学一.md",
    "408": "408.md",
    "英语一": "英语一.md",
    "政治": "政治.md",
}
SUBJECT_ALIAS_TEXT = {
    "数学一": ("数学一", "数学", "高数", "线代", "概率"),
    "408": ("408", "数据结构", "组成原理", "操作系统", "计算机网络", "计网", "计组"),
    "英语一": ("英语一", "英语", "阅读", "翻译", "写作", "完形"),
    "政治": ("政治", "马原", "毛中特", "史纲", "思修", "时政"),
}
STATUS_ORDER = ("不会", "半会", "会")
HISTORY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) - (不会|半会|会) -", re.M)
EXAM_DATE_RE = re.compile(r"考试日期\*\*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
UPDATE_DATE_RE = re.compile(r"最近更新日期\*\*[:：]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
STAGE_RE = re.compile(r"当前阶段关键词\*\*[:：]\s*(.+)")
LOG_HOURS_RE = re.compile(r"时长[^0-9]*([0-9]+(?:\.[0-9]+)?)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出考研学习驾驶舱 HTML")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--output", help="输出 HTML 文件路径；默认写到 OBSIDIAN_ROOT/可视化面板/index.html")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    return parser.parse_args()


def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_number(value: str) -> Optional[float]:
    match = re.search(r"[-+]?[0-9]+(?:\.[0-9]+)?", value or "")
    return float(match.group(0)) if match else None


def format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def format_date(value: Optional[date]) -> str:
    return value.isoformat() if value else "-"


def resolve_output_path(obsidian_root: Path, output_arg: Optional[str]) -> Path:
    if not output_arg:
        return obsidian_root / "可视化面板" / "index.html"

    output_path = Path(output_arg).expanduser()
    if output_path.suffix.lower() == ".html":
        return output_path
    return output_path / "index.html"


def parse_archive_progress(archive_text: str) -> Dict[str, Dict[str, object]]:
    block = extract_heading_block(archive_text, "各科当前状态", level=2)
    rows: Dict[str, Dict[str, object]] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != 5 or cells[0] == "科目" or set(cells[0]) == {"-"}:
            continue
        subject = cells[0]
        current = parse_number(cells[1])
        target = parse_number(cells[2])
        computed_gap = None
        if current is not None and target is not None:
            computed_gap = target - current
        else:
            computed_gap = parse_number(cells[3])
        rows[subject] = {
            "subject": subject,
            "current": current,
            "target": target,
            "gap": computed_gap,
            "judgement": cells[4],
        }
    return rows


def parse_archive_basic_info(archive_text: str, today: date) -> Dict[str, object]:
    exam_match = EXAM_DATE_RE.search(archive_text)
    update_match = UPDATE_DATE_RE.search(archive_text)
    stage_match = STAGE_RE.search(archive_text)
    exam_day = parse_iso_date(exam_match.group(1)) if exam_match else None
    latest_update = parse_iso_date(update_match.group(1)) if update_match else None
    return {
        "exam_date": format_date(exam_day),
        "days_until_exam": (exam_day - today).days if exam_day else None,
        "latest_archive_update": format_date(latest_update),
        "stage": stage_match.group(1).strip() if stage_match else "",
        "focus_problems": extract_list_items(archive_text, "最近聚焦问题（只保留 3-5 条）"),
        "next_steps": extract_list_items(archive_text, "下一步建议（只保留 3 条）"),
    }


def parse_log_entry(log_path: Path) -> Optional[Dict[str, object]]:
    log_day = parse_iso_date(log_path.stem)
    if log_day is None:
        return None
    text = safe_read_text(log_path)
    if not text:
        return None
    topic_match = re.search(r"\*\*主题\*\*:\s*(.+)", text)
    topic = topic_match.group(1).strip() if topic_match else ""
    hours_match = LOG_HOURS_RE.search(text)
    hours = float(hours_match.group(1)) if hours_match else None
    learned = extract_list_items(text, "学到了什么")
    blockers = extract_list_items(text, "卡壳与挣扎")
    review = extract_list_items(text, "下次需要复习")
    subject_counts = infer_subject_mentions([topic] + learned + blockers + review)
    return {
        "date": log_day,
        "topic": topic,
        "hours": hours,
        "path": str(log_path),
        "subject_counts": subject_counts,
    }


def collect_logs(obsidian_root: Path) -> List[Dict[str, object]]:
    log_dir = obsidian_root / "学习日志"
    if not log_dir.exists():
        return []
    entries = []
    for log_path in sorted(log_dir.glob("*.md")):
        entry = parse_log_entry(log_path)
        if entry:
            entries.append(entry)
    return entries


def compute_log_streak(log_dates: Sequence[date]) -> int:
    if not log_dates:
        return 0
    ordered = sorted(set(log_dates), reverse=True)
    streak = 1
    previous = ordered[0]
    for current in ordered[1:]:
        if previous - current == timedelta(days=1):
            streak += 1
            previous = current
            continue
        break
    return streak


def build_heatmap_series(days_with_counts: Mapping[date, int], today: date, span: int) -> List[Dict[str, object]]:
    start = today - timedelta(days=span - 1)
    cells = []
    for offset in range(span):
        current = start + timedelta(days=offset)
        count = days_with_counts.get(current, 0)
        level = 0
        if count >= 3:
            level = 3
        elif count == 2:
            level = 2
        elif count == 1:
            level = 1
        cells.append({
            "date": current.isoformat(),
            "count": count,
            "level": level,
            "weekday": current.weekday(),
        })
    return cells


def bucket_overdue_days(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "今天到期"
    if overdue_days <= 3:
        return "超期 1-3 天"
    if overdue_days <= 7:
        return "超期 4-7 天"
    return "超期 8 天+"


def extract_card_history_statuses(body: str) -> List[str]:
    return [status for _, status in HISTORY_RE.findall(body)]


def collect_cards(obsidian_root: Path, today: date) -> List[Dict[str, object]]:
    wrongbook_root = obsidian_root / "错题本"
    cards: List[Dict[str, object]] = []
    if not wrongbook_root.exists():
        return cards

    for item in iter_review_cards(obsidian_root):
        if item["icloud_placeholder"]:
            continue
        fm = item["frontmatter"]
        if not fm or not fm.get("first_wrong_at"):
            continue
        path = item["path"]
        try:
            rel = path.relative_to(wrongbook_root)
        except ValueError:
            rel = path
        chapter_parts = list(rel.parts[1:-1]) if len(rel.parts) >= 3 else []
        chapter = " / ".join(chapter_parts) if chapter_parts else "未分类"
        created_at = parse_iso_date(str(fm.get("first_wrong_at", "")))
        last_review_at = parse_iso_date(str(fm.get("last_review_at", "")))
        next_review = item["next_review"]
        review_interval = item["review_interval"] or 0
        status = str(fm.get("status", "")).strip()
        overdue_days = None
        is_due = False
        if next_review is not None and review_interval < SRS_GRADUATED_INTERVAL_DAYS:
            overdue_days = (today - next_review).days
            is_due = next_review <= today
        history_statuses = extract_card_history_statuses(item["body"])
        promoted = any(history in {"半会", "会"} for history in history_statuses)
        cards.append({
            "path": str(path),
            "subject": item["subject"],
            "topic": str(fm.get("topic", item["topic"])).strip() or item["topic"],
            "chapter": chapter,
            "created_at": format_date(created_at),
            "last_review_at": format_date(last_review_at),
            "next_review": format_date(next_review),
            "review_interval": review_interval,
            "status": status or "未标注",
            "is_due": is_due,
            "overdue_days": overdue_days,
            "overdue_bucket": bucket_overdue_days(overdue_days) if overdue_days is not None else "未排期",
            "graduated": review_interval >= SRS_GRADUATED_INTERVAL_DAYS,
            "promoted": promoted,
        })
    return cards


def collect_knowledge_maps(obsidian_root: Path) -> Dict[str, Dict[str, object]]:
    km_root = obsidian_root / "知识地图"
    result: Dict[str, Dict[str, object]] = {}
    for subject in PLAN_SUBJECTS:
        km_path = km_root / SUBJECT_TO_KM_FILE[subject]
        data = {
            "subject": subject,
            "path": str(km_path),
            "exists": km_path.exists(),
            "total_topics": 0,
            "不会": 0,
            "半会": 0,
            "会": 0,
            "unmarked": 0,
            "marked_topics": 0,
        }
        if not km_path.exists():
            result[subject] = data
            continue

        text = safe_read_text(km_path)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            if len(cells) < 4 or cells[0] == "考点" or set(cells[0]) == {"-"}:
                continue
            topic_cell = cells[0]
            if not topic_cell or "**" in topic_cell:
                continue
            status = cells[1].strip()
            data["total_topics"] += 1
            if status in STATUS_ORDER:
                data[status] += 1
                data["marked_topics"] += 1
            else:
                data["unmarked"] += 1

        result[subject] = data
    return result


def parse_report_date_from_filename(filename: str) -> Optional[date]:
    mock_match = re.match(r"(\d{4}-\d{2}-\d{2})-模考分析\.md$", filename)
    if mock_match:
        return parse_iso_date(mock_match.group(1))
    week_match = re.match(r"(\d{4})-W(\d{2})-周复盘\.md$", filename)
    if week_match:
        return date.fromisocalendar(int(week_match.group(1)), int(week_match.group(2)), 7)
    month_match = re.match(r"(\d{4})-(\d{2})-月复盘\.md$", filename)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if month == 12:
            return date(year, month, 31)
        next_month = date(year, month + 1, 1)
        return next_month - timedelta(days=1)
    return None


def collect_reports(obsidian_root: Path) -> Dict[str, object]:
    report_dir = obsidian_root / "复盘报告"
    mock_reports: List[Dict[str, object]] = []
    recap_reports: List[Dict[str, object]] = []
    recap_subject_counts = {subject: 0 for subject in PLAN_SUBJECTS}
    if not report_dir.exists():
        return {
            "mock_reports": mock_reports,
            "recap_reports": recap_reports,
            "recap_subject_counts": recap_subject_counts,
        }

    for report_path in sorted(report_dir.glob("*.md")):
        report_date = parse_report_date_from_filename(report_path.name)
        text = safe_read_text(report_path)
        if report_date is None:
            continue
        if report_path.name.endswith("-模考分析.md"):
            mock_reports.append({
                "date": report_date,
                "path": str(report_path),
            })
            continue

        counts = infer_subject_mentions(text.splitlines())
        for subject, count in counts.items():
            recap_subject_counts[subject] += count
        recap_reports.append({
            "date": report_date,
            "path": str(report_path),
            "subject_counts": counts,
        })

    return {
        "mock_reports": mock_reports,
        "recap_reports": recap_reports,
        "recap_subject_counts": recap_subject_counts,
    }


def collect_chapter_reports(obsidian_root: Path) -> Dict[str, object]:
    root = obsidian_root / "章节掌握报告" / "408"
    reports = []
    module_counts = Counter()
    if not root.exists():
        return {"reports": reports, "module_counts": module_counts}

    for report_path in sorted(root.rglob("*.md")):
        text = safe_read_text(report_path)
        if not text:
            continue
        fm, _, _ = parse_frontmatter(text)
        session_date = parse_iso_date(str(fm.get("session_date", "")))
        module = str(fm.get("module", "未标注模块")).strip() or "未标注模块"
        chapter = str(fm.get("chapter", report_path.stem)).strip() or report_path.stem
        mastery = str(fm.get("overall_mastery", "")).strip()
        reports.append({
            "date": format_date(session_date),
            "module": module,
            "chapter": chapter,
            "mastery": mastery,
            "path": str(report_path),
        })
        module_counts[module] += 1
    return {"reports": reports, "module_counts": dict(module_counts)}


def build_subject_logs_signal(logs: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    counts = {subject: 0 for subject in PLAN_SUBJECTS}
    for entry in logs:
        for subject, value in entry["subject_counts"].items():
            counts[subject] += value
    return counts


def build_subject_card_counts(cards: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    counts = {subject: 0 for subject in PLAN_SUBJECTS}
    for card in cards:
        if card["subject"] in counts:
            counts[card["subject"]] += 1
    return counts


def build_subject_due_counts(cards: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    counts = {subject: 0 for subject in PLAN_SUBJECTS}
    for card in cards:
        if card["is_due"] and card["subject"] in counts:
            counts[card["subject"]] += 1
    return counts


def build_subject_score_presence(archive_text: str) -> Dict[str, bool]:
    if not archive_text:
        return {subject: False for subject in PLAN_SUBJECTS}
    presence = {subject: False for subject in PLAN_SUBJECTS}
    mock_rows = parse_mock_rows(archive_text)
    if mock_rows:
        for subject in SCORE_SUBJECTS:
            for row in mock_rows:
                if parse_score_cell(row[subject]) is not None:
                    presence[subject] = True
                    break
    for subject in ("数学一", "408"):
        if parse_subject_score_rows(archive_text, subject):
            presence[subject] = True
    return presence


def build_subject_progress_rows(
    archive_progress: Mapping[str, Mapping[str, object]],
    subject_logs: Mapping[str, int],
    subject_cards: Mapping[str, int],
    subject_due: Mapping[str, int],
    knowledge_maps: Mapping[str, Mapping[str, object]],
    score_presence: Mapping[str, bool],
    chapter_reports: Mapping[str, object],
) -> Tuple[List[Dict[str, object]], List[str], List[str]]:
    rows = []
    structured_subjects = []
    blank_subjects = []
    max_gap = 0.0
    for subject in SCORE_SUBJECTS:
        progress = archive_progress.get(subject, {})
        gap = progress.get("gap")
        if isinstance(gap, (int, float)):
            max_gap = max(max_gap, float(abs(gap)))

    for subject in SCORE_SUBJECTS:
        progress = archive_progress.get(subject, {})
        km = knowledge_maps.get(subject, {})
        row = {
            "subject": subject,
            "current": progress.get("current"),
            "target": progress.get("target"),
            "gap": progress.get("gap"),
            "judgement": progress.get("judgement", ""),
            "log_signal": subject_logs.get(subject, 0),
            "cards": subject_cards.get(subject, 0),
            "due_cards": subject_due.get(subject, 0),
            "knowledge_marked": km.get("marked_topics", 0),
            "knowledge_total": km.get("total_topics", 0),
            "has_score": bool(score_presence.get(subject)),
            "has_chapter_reports": bool(chapter_reports["reports"]) if subject == "408" else False,
        }
        row["structure_score"] = sum([
            1 if row["log_signal"] else 0,
            1 if row["cards"] else 0,
            1 if row["knowledge_marked"] else 0,
            1 if row["has_score"] else 0,
            1 if row["has_chapter_reports"] else 0,
        ])
        rows.append(row)
        if row["structure_score"]:
            structured_subjects.append(subject)
        else:
            blank_subjects.append(subject)

    for row in rows:
        gap_value = row["gap"]
        row["gap_ratio"] = 0.0
        if isinstance(gap_value, (int, float)) and max_gap > 0:
            row["gap_ratio"] = round(abs(float(gap_value)) / max_gap, 4)

    return rows, structured_subjects, blank_subjects


def build_review_payload(cards: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    due_cards = [card for card in cards if card["is_due"]]
    by_subject = Counter(card["subject"] for card in due_cards)
    by_status = Counter(card["status"] for card in due_cards)
    overdue_buckets = Counter(card["overdue_bucket"] for card in due_cards)
    graduated_total = sum(1 for card in cards if card["graduated"])

    chapter_aggregate: Dict[Tuple[str, str], Dict[str, object]] = {}
    for card in cards:
        key = (card["subject"], card["chapter"])
        bucket = chapter_aggregate.setdefault(key, {
            "subject": card["subject"],
            "chapter": card["chapter"],
            "total_cards": 0,
            "due_cards": 0,
            "not_mastered_cards": 0,
        })
        bucket["total_cards"] += 1
        if card["is_due"]:
            bucket["due_cards"] += 1
        if card["status"] in {"不会", "半会"}:
            bucket["not_mastered_cards"] += 1

    top_chapters = sorted(
        chapter_aggregate.values(),
        key=lambda item: (item["due_cards"], item["not_mastered_cards"], item["total_cards"]),
        reverse=True,
    )[:6]

    return {
        "due_total": len(due_cards),
        "graduated_total": graduated_total,
        "by_subject": [{"label": subject, "value": by_subject.get(subject, 0)} for subject in PLAN_SUBJECTS],
        "by_status": [{"label": status, "value": by_status.get(status, 0)} for status in STATUS_ORDER],
        "overdue_buckets": [
            {"label": label, "value": overdue_buckets.get(label, 0)}
            for label in ("今天到期", "超期 1-3 天", "超期 4-7 天", "超期 8 天+")
        ],
        "top_chapters": top_chapters,
    }


def build_knowledge_payload(knowledge_maps: Mapping[str, Mapping[str, object]]) -> Dict[str, object]:
    rows = []
    totals = {"会": 0, "半会": 0, "不会": 0, "unmarked": 0, "total_topics": 0}
    for subject in PLAN_SUBJECTS:
        data = knowledge_maps.get(subject, {})
        row = {
            "subject": subject,
            "exists": bool(data.get("exists")),
            "total_topics": data.get("total_topics", 0),
            "会": data.get("会", 0),
            "半会": data.get("半会", 0),
            "不会": data.get("不会", 0),
            "unmarked": data.get("unmarked", 0),
            "marked_topics": data.get("marked_topics", 0),
        }
        row["marked_ratio"] = 0.0
        if row["total_topics"]:
            row["marked_ratio"] = round(row["marked_topics"] / row["total_topics"], 4)
        rows.append(row)
        for key in totals:
            totals[key] += row.get(key, 0)
    return {"by_subject": rows, "totals": totals}


def build_activity_payload(
    logs: Sequence[Mapping[str, object]],
    cards: Sequence[Mapping[str, object]],
    reports: Mapping[str, object],
    chapter_reports: Mapping[str, object],
    today: date,
) -> Dict[str, object]:
    log_dates = [entry["date"] for entry in logs]
    log_counts = Counter(log_dates)
    created_counts = Counter(parse_iso_date(card["created_at"]) for card in cards if parse_iso_date(card["created_at"]))
    reviewed_counts = Counter(parse_iso_date(card["last_review_at"]) for card in cards if parse_iso_date(card["last_review_at"]))

    latest_log = max(log_dates) if log_dates else None
    active_days_14 = sum(1 for day in set(log_dates) if today - timedelta(days=13) <= day <= today)
    recent_logs_30 = build_heatmap_series(log_counts, today, 30)
    card_created_30 = build_heatmap_series(created_counts, today, 30)
    card_reviewed_30 = build_heatmap_series(reviewed_counts, today, 30)

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def within_period(day: Optional[date], start: date) -> bool:
        return day is not None and start <= day <= today

    recent_outputs = {
        "week": {
            "logs": sum(1 for day in log_dates if within_period(day, week_start)),
            "cards": sum(1 for card in cards if within_period(parse_iso_date(card["created_at"]), week_start)),
            "recaps": sum(1 for item in reports["recap_reports"] if within_period(item["date"], week_start)),
            "mock_reports": sum(1 for item in reports["mock_reports"] if within_period(item["date"], week_start)),
            "chapter_reports": sum(1 for item in chapter_reports["reports"] if within_period(parse_iso_date(item["date"]), week_start)),
        },
        "month": {
            "logs": sum(1 for day in log_dates if within_period(day, month_start)),
            "cards": sum(1 for card in cards if within_period(parse_iso_date(card["created_at"]), month_start)),
            "recaps": sum(1 for item in reports["recap_reports"] if within_period(item["date"], month_start)),
            "mock_reports": sum(1 for item in reports["mock_reports"] if within_period(item["date"], month_start)),
            "chapter_reports": sum(1 for item in chapter_reports["reports"] if within_period(parse_iso_date(item["date"]), month_start)),
        },
    }

    return {
        "latest_log_date": format_date(latest_log),
        "log_streak_days": compute_log_streak(log_dates),
        "active_days_14": active_days_14,
        "log_heatmap_30": recent_logs_30,
        "card_created_heatmap_30": card_created_30,
        "card_reviewed_heatmap_30": card_reviewed_30,
        "recent_outputs": recent_outputs,
    }


def build_quality_payload(
    archive_exists: bool,
    logs: Sequence[Mapping[str, object]],
    cards: Sequence[Mapping[str, object]],
    knowledge_maps: Mapping[str, Mapping[str, object]],
    reports: Mapping[str, object],
    chapter_reports: Mapping[str, object],
    score_presence: Mapping[str, bool],
    today: date,
) -> Dict[str, object]:
    subject_logs = build_subject_logs_signal(logs)
    subject_cards = build_subject_card_counts(cards)

    subject_matrix = []
    for subject in PLAN_SUBJECTS:
        km = knowledge_maps.get(subject, {})
        row = {
            "subject": subject,
            "logs": subject_logs.get(subject, 0) > 0,
            "wrong_cards": subject_cards.get(subject, 0) > 0,
            "knowledge_map": bool(km.get("exists")),
            "marked_topics": km.get("marked_topics", 0) > 0,
            "mock": bool(score_presence.get(subject)),
            "recap": reports["recap_subject_counts"].get(subject, 0) > 0,
            "chapter_report": bool(chapter_reports["reports"]) if subject == "408" else False,
        }
        subject_matrix.append(row)

    latest_log = max((entry["date"] for entry in logs), default=None)
    warnings: List[str] = []
    if not archive_exists:
        warnings.append("还没有学习者档案，驾驶舱会先展示空骨架。")
    if latest_log is None:
        warnings.append("还没有学习日志，连续性和时段活跃度暂时无法判断。")
    elif (today - latest_log).days >= 7:
        warnings.append(f"最近一次学习日志距今天已有 {(today - latest_log).days} 天，当前状态可能滞后。")
    if not reports["recap_reports"]:
        warnings.append("还没有周/月复盘报告，阶段性策略回看仍是空白。")
    if not reports["mock_reports"]:
        warnings.append("还没有模考分析报告，趋势判断暂时只能依赖档案和日志。")
    if sum(1 for card in cards if card["is_due"]) >= 10:
        warnings.append("到期复习已经形成积压，今天应先止损旧题。")
    for subject in PLAN_SUBJECTS:
        row = next(item for item in subject_matrix if item["subject"] == subject)
        if not row["wrong_cards"]:
            warnings.append(f"{subject} 还没有结构化错题卡，后续判断会偏粗。")
        if row["knowledge_map"] and not row["marked_topics"]:
            warnings.append(f"{subject} 的知识地图还没开始标注掌握度。")
    return {"warnings": warnings, "subject_matrix": subject_matrix}


def build_results_payload(cards: Sequence[Mapping[str, object]], chapter_reports: Mapping[str, object]) -> Dict[str, object]:
    total_cards = len(cards)
    promoted_cards = sum(1 for card in cards if card["promoted"])
    mastered_cards = sum(1 for card in cards if card["status"] == "会")
    covered_chapters = len({(card["subject"], card["chapter"]) for card in cards})
    covered_modules_408 = len({report["module"] for report in chapter_reports["reports"]})
    return {
        "total_cards": total_cards,
        "promoted_cards": promoted_cards,
        "mastered_cards": mastered_cards,
        "covered_chapters": covered_chapters,
        "covered_modules_408": covered_modules_408,
    }


def build_overview_payload(
    archive_basic: Mapping[str, object],
    logs: Sequence[Mapping[str, object]],
    cards: Sequence[Mapping[str, object]],
    reports: Mapping[str, object],
    activity: Mapping[str, object],
    structured_subjects: Sequence[str],
    today: date,
) -> Dict[str, object]:
    week_start = today - timedelta(days=today.weekday())
    new_cards_this_week = sum(1 for card in cards if parse_iso_date(card["created_at"]) and parse_iso_date(card["created_at"]) >= week_start)
    recap_count = len(reports["recap_reports"])
    mock_count = len(reports["mock_reports"])
    return {
        "today": today.isoformat(),
        "exam_date": archive_basic.get("exam_date", "-"),
        "days_until_exam": archive_basic.get("days_until_exam"),
        "latest_log_date": activity["latest_log_date"],
        "log_streak_days": activity["log_streak_days"],
        "active_days_14": activity["active_days_14"],
        "due_total": sum(1 for card in cards if card["is_due"]),
        "new_cards_this_week": new_cards_this_week,
        "reports_status": {
            "recap_count": recap_count,
            "mock_count": mock_count,
            "has_any": recap_count > 0 or mock_count > 0,
        },
        "total_cards": len(cards),
        "covered_subjects_count": len(structured_subjects),
        "stage": archive_basic.get("stage", ""),
    }


def build_overall_mock_trend(archive_text: str) -> Dict[str, object]:
    colors = {
        "政治": "#6b7280",
        "数学一": "#b7791f",
        "英语一": "#0f766e",
        "408": "#1d4ed8",
    }
    rows = parse_mock_rows(archive_text) if archive_text else []
    series = []
    for subject in SCORE_SUBJECTS:
        points = []
        for row in rows:
            score = parse_score_cell(row[subject])
            if score is None:
                continue
            note = row.get("备注", "") or "总模考"
            points.append({
                "date": row["date"],
                "paper": "总模考",
                "paper_type": "总模考",
                "paper_label": f"总模考 / {note}",
                "score": score,
            })
        series.append({
            "subject": subject,
            "color": colors[subject],
            "points": points,
        })
    total_points = []
    for row in rows:
        total_score = parse_score_cell(row["总分"])
        if total_score is None:
            continue
        note = row.get("备注", "") or "总模考"
        total_points.append({
            "exam_date": row["date"],
            "paper_type": "总模考",
            "paper": "总分",
            "paper_label": f"总模考 / {note}",
            "total_score": total_score,
            "issues": note,
            "note": note,
        })
    return {
        "series": series,
        "total_points": total_points,
        "has_data": any(item["points"] for item in series),
    }


def build_legacy_subject_points(archive_text: str, subject: str) -> List[Dict[str, object]]:
    points = []
    if not archive_text:
        return points
    for row in parse_subject_score_rows(archive_text, subject):
        score = parse_score_cell(row["total"])
        if score is None:
            continue
        points.append({
            "subject": subject,
            "exam_date": row["date"],
            "paper_type": row.get("paper_type", "模拟"),
            "paper": row["paper"],
            "paper_label": f"{row.get('paper_type', '模拟')} / {row['paper']}",
            "total_score": score,
            "issues": row.get("issues", ""),
            "note": row.get("note", ""),
            "source": "archive_summary",
            "score_objective": None,
            "score_big": None,
            "loss_objective": None,
            "loss_big": None,
            "score_choice_ds": None,
            "score_choice_co": None,
            "score_choice_os": None,
            "score_choice_cn": None,
            "score_big_ds": None,
            "score_big_co": None,
            "score_big_os": None,
            "score_big_cn": None,
            "loss_choice_ds": None,
            "loss_choice_co": None,
            "loss_choice_os": None,
            "loss_choice_cn": None,
            "loss_big_ds": None,
            "loss_big_co": None,
            "loss_big_os": None,
            "loss_big_cn": None,
            "score_cloze": None,
            "score_reading": None,
            "score_new_type": None,
            "score_translation": None,
            "score_short_essay": None,
            "score_long_essay": None,
        })
    return points


def merge_score_points(
    detailed_records: Sequence[Mapping[str, object]],
    archive_text: str,
    subject: str,
) -> List[Dict[str, object]]:
    merged: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for record in build_legacy_subject_points(archive_text, subject):
        key = (record["exam_date"], record["paper_type"], record["paper"])
        merged[key] = dict(record)

    for record in detailed_records:
        if record["subject"] != subject:
            continue
        key = (str(record["exam_date"]), str(record["paper_type"]), str(record["paper"]))
        merged[key] = {
            "subject": subject,
            "exam_date": str(record["exam_date"]),
            "paper_type": str(record["paper_type"]),
            "paper": str(record["paper"]),
            "paper_label": f"{record['paper_type']} / {record['paper']}",
            "total_score": record["total_score"],
            "issues": str(record.get("issues", "")),
            "note": str(record.get("note", "")),
            "source": "record",
            "score_objective": record.get("score_objective"),
            "score_big": record.get("score_big"),
            "loss_objective": record.get("loss_objective"),
            "loss_big": record.get("loss_big"),
            "score_choice_ds": record.get("score_choice_ds"),
            "score_choice_co": record.get("score_choice_co"),
            "score_choice_os": record.get("score_choice_os"),
            "score_choice_cn": record.get("score_choice_cn"),
            "score_big_ds": record.get("score_big_ds"),
            "score_big_co": record.get("score_big_co"),
            "score_big_os": record.get("score_big_os"),
            "score_big_cn": record.get("score_big_cn"),
            "loss_choice_ds": record.get("loss_choice_ds"),
            "loss_choice_co": record.get("loss_choice_co"),
            "loss_choice_os": record.get("loss_choice_os"),
            "loss_choice_cn": record.get("loss_choice_cn"),
            "loss_big_ds": record.get("loss_big_ds"),
            "loss_big_co": record.get("loss_big_co"),
            "loss_big_os": record.get("loss_big_os"),
            "loss_big_cn": record.get("loss_big_cn"),
            "score_cloze": record.get("score_cloze"),
            "score_reading": record.get("score_reading"),
            "score_new_type": record.get("score_new_type"),
            "score_translation": record.get("score_translation"),
            "score_short_essay": record.get("score_short_essay"),
            "score_long_essay": record.get("score_long_essay"),
        }

    rows = list(merged.values())
    rows.sort(key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]))
    return rows


def filter_points_by_type(points: Sequence[Mapping[str, object]], paper_type: str) -> List[Dict[str, object]]:
    if paper_type == "all":
        return list(points)
    return [dict(point) for point in points if point["paper_type"] == paper_type]


def build_subject_score_trend(points: Sequence[Mapping[str, object]], subject: str) -> Dict[str, object]:
    latest = points[-1] if points else None
    recent_rows = []
    for point in sorted(points, key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]), reverse=True)[:5]:
        row = {
            "date": point["exam_date"],
            "paper_type": point["paper_type"],
            "paper": point["paper"],
            "paper_label": point["paper_label"],
            "total_score": point["total_score"],
            "issues": point["issues"],
            "note": point["note"],
        }
        if subject == "数学一":
            row["score_objective"] = point.get("score_objective")
            row["score_big"] = point.get("score_big")
        elif subject == "408":
            row["main_weakness"] = top_weakness_from_408_record(point) or point["issues"]
        elif subject == "英语一":
            row["score_cloze"] = point.get("score_cloze")
            row["score_reading"] = point.get("score_reading")
            row["score_new_type"] = point.get("score_new_type")
            row["score_translation"] = point.get("score_translation")
            row["score_short_essay"] = point.get("score_short_essay")
            row["score_long_essay"] = point.get("score_long_essay")
        recent_rows.append(row)

    return {
        "points": list(points),
        "has_data": bool(points),
        "latest": latest,
        "filters": {
            "all": filter_points_by_type(points, "all"),
            "真题": filter_points_by_type(points, "真题"),
            "模拟": filter_points_by_type(points, "模拟"),
        },
        "recent_rows": recent_rows,
    }


def build_score_trends_payload(obsidian_root: Path, archive_text: str) -> Dict[str, object]:
    detailed_records = collect_score_records(obsidian_root, ("数学一", "408", "英语一"))
    math_points = merge_score_points(detailed_records, archive_text, "数学一")
    cs_points = merge_score_points(detailed_records, archive_text, "408")
    english_points = merge_score_points(detailed_records, archive_text, "英语一")
    overall = build_overall_mock_trend(archive_text)
    politics_series = next((item for item in overall["series"] if item["subject"] == "政治"), {"points": []})
    politics_points = [
        {
            "exam_date": point["date"],
            "paper_type": point["paper_type"],
            "paper": point["paper"],
            "paper_label": point["paper_label"],
            "total_score": point["score"],
            "issues": point["paper_label"],
            "note": point["paper_label"],
        }
        for point in politics_series["points"]
    ]

    recent_records = []
    all_records = math_points + cs_points + english_points
    for point in sorted(all_records, key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]), reverse=True)[:5]:
        recent_records.append({
            "subject": point["subject"],
            "date": point["exam_date"],
            "paper_type": point["paper_type"],
            "paper": point["paper"],
            "total_score": point["total_score"],
            "paper_label": point["paper_label"],
        })

    return {
        "overall": overall,
        "total": build_subject_score_trend(overall["total_points"], "总分"),
        "math1": build_subject_score_trend(math_points, "数学一"),
        "408": {
            **build_subject_score_trend(cs_points, "408"),
            "has_loss_metrics": any(
                point.get(field) is not None
                for point in cs_points
                for field in (
                    "loss_choice_ds",
                    "loss_choice_co",
                    "loss_choice_os",
                    "loss_choice_cn",
                    "loss_big_ds",
                    "loss_big_co",
                    "loss_big_os",
                    "loss_big_cn",
                )
            ),
        },
        "english1": build_subject_score_trend(english_points, "英语一"),
        "politics": build_subject_score_trend(politics_points, "政治"),
        "recent_records": recent_records,
    }


def build_payload(obsidian_root: Path, today: date) -> Dict[str, object]:
    archive_path = obsidian_root / "我的学习者档案.md"
    archive_exists = archive_path.exists()
    archive_text = safe_read_text(archive_path) if archive_exists else ""
    archive_basic = parse_archive_basic_info(archive_text, today) if archive_text else {
        "exam_date": "-",
        "days_until_exam": None,
        "latest_archive_update": "-",
        "stage": "",
        "focus_problems": [],
        "next_steps": [],
    }
    archive_progress = parse_archive_progress(archive_text) if archive_text else {}

    logs = collect_logs(obsidian_root)
    cards = collect_cards(obsidian_root, today)
    knowledge_maps = collect_knowledge_maps(obsidian_root)
    reports = collect_reports(obsidian_root)
    chapter_reports = collect_chapter_reports(obsidian_root)
    subject_logs = build_subject_logs_signal(logs)
    subject_cards = build_subject_card_counts(cards)
    subject_due = build_subject_due_counts(cards)
    score_presence = build_subject_score_presence(archive_text)
    subject_rows, structured_subjects, blank_subjects = build_subject_progress_rows(
        archive_progress,
        subject_logs,
        subject_cards,
        subject_due,
        knowledge_maps,
        score_presence,
        chapter_reports,
    )
    reviews = build_review_payload(cards)
    knowledge_payload = build_knowledge_payload(knowledge_maps)
    activity = build_activity_payload(logs, cards, reports, chapter_reports, today)
    score_trends = build_score_trends_payload(obsidian_root, archive_text)
    quality = build_quality_payload(
        archive_exists,
        logs,
        cards,
        knowledge_maps,
        reports,
        chapter_reports,
        score_presence,
        today,
    )
    results = build_results_payload(cards, chapter_reports)
    overview = build_overview_payload(archive_basic, logs, cards, reports, activity, structured_subjects, today)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "overview": overview,
        "subjects": {
            "progress": subject_rows,
            "structured_subjects": structured_subjects,
            "blank_subjects": blank_subjects,
        },
        "reviews": reviews,
        "score_trends": score_trends,
        "knowledge_maps": knowledge_payload,
        "activity": activity,
        "quality": quality,
        "results": results,
        "archive": {
            "exists": archive_exists,
            "path": str(archive_path),
            "focus_problems": archive_basic.get("focus_problems", []),
            "next_steps": archive_basic.get("next_steps", []),
            "latest_archive_update": archive_basic.get("latest_archive_update", "-"),
        },
    }


def e(value: object) -> str:
    return html.escape(str(value))


def render_metric_card(title: str, value: str, caption: str, tone: str) -> str:
    return (
        f'<article class="metric-card tone-{tone}">'
        f'<div class="metric-title">{e(title)}</div>'
        f'<div class="metric-value">{e(value)}</div>'
        f'<div class="metric-caption">{e(caption)}</div>'
        "</article>"
    )


def render_empty_state(message: str) -> str:
    return f'<div class="empty-state">{e(message)}</div>'


def render_bar_rows(rows: Sequence[Mapping[str, object]], empty_message: str) -> str:
    if not rows or all(int(row.get("value", 0)) == 0 for row in rows):
        return render_empty_state(empty_message)

    max_value = max(int(row.get("value", 0)) for row in rows) or 1
    parts = ['<div class="bar-list">']
    for row in rows:
        value = int(row.get("value", 0))
        ratio = value / max_value if max_value else 0
        parts.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{e(row.get("label", ""))}</div>'
            '<div class="bar-track">'
            f'<div class="bar-fill" style="width: {ratio * 100:.1f}%"></div>'
            "</div>"
            f'<div class="bar-value">{value}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)

def build_axis_ticks(min_value: float, max_value: float, tick_count: int) -> List[float]:
    if tick_count <= 1:
        return [min_value, max_value]
    if abs(max_value - min_value) < 1e-9:
        return [min_value]
    step = (max_value - min_value) / (tick_count - 1)
    return [min_value + step * index for index in range(tick_count)]


def build_x_tick_labels(labels: Sequence[str]) -> List[Tuple[int, str]]:
    if not labels:
        return []
    if len(labels) <= 6:
        return list(enumerate(labels))
    candidates = [0, len(labels) // 2, len(labels) - 1]
    unique_indexes: List[int] = []
    for index in candidates:
        if index not in unique_indexes:
            unique_indexes.append(index)
    return [(index, labels[index]) for index in unique_indexes]


def render_line_chart(
    points: Sequence[Mapping[str, object]],
    color: str,
    empty_message: str,
    y_min: float,
    y_max: float,
    y_step: float,
) -> str:
    valid_points = [point for point in points if isinstance(point.get("total_score"), (int, float))]
    if not valid_points:
        return render_empty_state(empty_message)

    width = 720
    height = 280
    pad_x = 48
    pad_y = 24
    bottom_pad = 54
    inner_width = width - pad_x * 2
    inner_height = height - pad_y - bottom_pad
    labels = [point["exam_date"] for point in valid_points]

    def x_at(index: int) -> float:
        if len(valid_points) == 1:
            return width / 2
        return pad_x + inner_width * index / (len(valid_points) - 1)

    def y_at(value: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return pad_y + inner_height * (1 - ratio)

    polyline = " ".join(f"{x_at(index):.1f},{y_at(float(point['total_score'])):.1f}" for index, point in enumerate(valid_points))
    circles = []
    for index, point in enumerate(valid_points):
        x = x_at(index)
        y = y_at(float(point["total_score"]))
        tooltip = f'{point["exam_date"]} {point["paper_label"]} {format_number(point["total_score"])}'
        circles.append(
            f'<circle class="tooltip-point" data-tooltip="{e(tooltip)}" cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"><title>{e(tooltip)}</title></circle>'
        )

    y_grid = []
    for tick in build_axis_ticks(y_min, y_max, int((y_max - y_min) / y_step) + 1):
        y = y_at(tick)
        y_grid.append(f'<line x1="{pad_x}" y1="{y:.1f}" x2="{width - pad_x}" y2="{y:.1f}" stroke="rgba(20,33,61,0.08)" stroke-width="1" />')
        y_grid.append(f'<text x="{pad_x - 8}" y="{y + 4:.1f}" fill="#5f6b7a" font-size="11" text-anchor="end">{e(format_number(tick))}</text>')

    x_labels = []
    baseline_y = height - bottom_pad
    for index, label in build_x_tick_labels(labels):
        x = x_at(index)
        x_labels.append(f'<line x1="{x:.1f}" y1="{baseline_y}" x2="{x:.1f}" y2="{baseline_y + 4}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />')
        x_labels.append(f'<text x="{x:.1f}" y="{height - 18}" fill="#5f6b7a" font-size="11" text-anchor="middle">{e(label)}</text>')
    return (
        f'<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" aria-label="成绩趋势图">'
        + "".join(y_grid)
        + f'<line x1="{pad_x}" y1="{baseline_y}" x2="{width - pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        + f'<line x1="{pad_x}" y1="{pad_y}" x2="{pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{polyline}" />'
        + "".join(circles)
        + "".join(x_labels)
        + f'<text x="{width / 2:.1f}" y="{height - 2}" fill="#5f6b7a" font-size="11" text-anchor="middle">日期</text>'
        + f'<text x="16" y="{pad_y + inner_height / 2:.1f}" fill="#5f6b7a" font-size="11" text-anchor="middle" transform="rotate(-90 16 {pad_y + inner_height / 2:.1f})">分数</text>'
        + "</svg>"
    )


def render_multi_line_chart(
    series: Sequence[Mapping[str, object]],
    empty_message: str,
    y_min: float,
    y_max: float,
    y_step: float,
) -> str:
    dated_scores: Dict[str, Dict[str, float]] = {}
    for item in series:
        for point in item["points"]:
            dated_scores.setdefault(point["date"], {})[item["subject"]] = float(point["score"])
    all_dates = sorted(dated_scores)
    if not all_dates:
        return render_empty_state(empty_message)

    width = 720
    height = 300
    pad_x = 52
    pad_y = 24
    bottom_pad = 54
    inner_width = width - pad_x * 2
    inner_height = height - pad_y - bottom_pad

    date_to_index = {day: index for index, day in enumerate(all_dates)}

    def x_at(day: str) -> float:
        if len(all_dates) == 1:
            return width / 2
        return pad_x + inner_width * date_to_index[day] / (len(all_dates) - 1)

    def y_at(value: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return pad_y + inner_height * (1 - ratio)

    paths = []
    circles = []
    legends = []
    for item in series:
        points = item["points"]
        if not points:
            continue
        polyline = " ".join(f"{x_at(point['date']):.1f},{y_at(float(point['score'])):.1f}" for point in points)
        paths.append(f'<polyline fill="none" stroke="{item["color"]}" stroke-width="3" points="{polyline}" />')
        legends.append(f'<span class="legend-pill"><span class="legend-dot" style="background:{item["color"]}"></span>{e(item["subject"])}</span>')
        for point in points:
            x = x_at(point["date"])
            y = y_at(float(point["score"]))
            tooltip = f'{item["subject"]} {point["date"]} {point["paper_label"]} {format_number(point["score"])}'
            circles.append(
                f'<circle class="tooltip-point" data-tooltip="{e(tooltip)}" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{item["color"]}"><title>{e(tooltip)}</title></circle>'
            )

    y_grid = []
    for tick in build_axis_ticks(y_min, y_max, int((y_max - y_min) / y_step) + 1):
        y = y_at(tick)
        y_grid.append(f'<line x1="{pad_x}" y1="{y:.1f}" x2="{width - pad_x}" y2="{y:.1f}" stroke="rgba(20,33,61,0.08)" stroke-width="1" />')
        y_grid.append(f'<text x="{pad_x - 8}" y="{y + 4:.1f}" fill="#5f6b7a" font-size="11" text-anchor="end">{e(format_number(tick))}</text>')
    baseline_y = height - bottom_pad
    x_labels = []
    for index, label in build_x_tick_labels(all_dates):
        x = x_at(label)
        x_labels.append(f'<line x1="{x:.1f}" y1="{baseline_y}" x2="{x:.1f}" y2="{baseline_y + 4}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />')
        x_labels.append(f'<text x="{x:.1f}" y="{height - 18}" fill="#5f6b7a" font-size="11" text-anchor="middle">{e(label)}</text>')

    svg = (
        f'<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" aria-label="四科总模考趋势图">'
        + "".join(y_grid)
        + f'<line x1="{pad_x}" y1="{baseline_y}" x2="{width - pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        + f'<line x1="{pad_x}" y1="{pad_y}" x2="{pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        + "".join(paths)
        + "".join(circles)
        + "".join(x_labels)
        + f'<text x="{width / 2:.1f}" y="{height - 2}" fill="#5f6b7a" font-size="11" text-anchor="middle">日期</text>'
        + f'<text x="18" y="{pad_y + inner_height / 2:.1f}" fill="#5f6b7a" font-size="11" text-anchor="middle" transform="rotate(-90 18 {pad_y + inner_height / 2:.1f})">分数</text>'
        + "</svg>"
    )
    return '<div class="chart-with-legend">' + svg + '<div class="chart-legend">' + "".join(legends) + "</div></div>"


def render_recent_score_records(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("还没有卷子级成绩记录。")
    parts = [
        '<table class="score-table"><thead><tr><th>科目</th><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th></tr></thead><tbody>'
    ]
    for row in rows:
        parts.append(
            f"<tr><td>{e(row['subject'])}</td><td>{e(row['date'])}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def render_total_score_panel(score_trends: Mapping[str, object]) -> str:
    chart = render_line_chart(
        score_trends["total"]["points"],
        "#8b5e34",
        "还没有四科完整模考总分趋势数据。",
        0.0,
        500.0,
        100.0,
    )
    recent_rows = [
        {
            "subject": "总分",
            "date": row["date"],
            "paper_type": row["paper_type"],
            "paper": row["paper_label"],
            "total_score": row["total_score"],
        }
        for row in score_trends["total"]["recent_rows"]
    ]
    return (
        '<div class="panel-grid">'
        f'<div class="mini-panel"><h3>总分趋势</h3>{chart}</div>'
        f'<div class="mini-panel"><h3>最近完整模考</h3>{render_recent_score_records(recent_rows)}</div>'
        '</div>'
    )


def render_politics_panel(score_trends: Mapping[str, object]) -> str:
    chart = render_line_chart(
        score_trends["politics"]["points"],
        "#6b7280",
        "还没有政治套卷趋势数据。",
        0.0,
        100.0,
        20.0,
    )
    return (
        '<div class="panel-grid">'
        f'<div class="mini-panel"><h3>政治总分趋势</h3>{chart}</div>'
        f'<div class="mini-panel"><h3>最近政治成绩</h3>{render_subject_score_table("politics", score_trends["politics"]["recent_rows"])}</div>'
        '</div>'
    )


def render_math_breakdown_rows(points: Sequence[Mapping[str, object]]) -> str:
    rows = [point for point in points if point.get("score_objective") is not None or point.get("score_big") is not None]
    if not rows:
        return render_empty_state("当前没有数学一的选填/大题细分得分。")
    parts = ['<div class="breakdown-list">']
    for point in rows:
        objective = point.get("score_objective") or 0
        big = point.get("score_big") or 0
        total = objective + big or point["total_score"] or 1
        parts.append(
            '<article class="breakdown-card">'
            f'<div class="breakdown-head"><strong>{e(point["paper_label"])}</strong><span>{e(point["exam_date"])}</span></div>'
            '<div class="stack-track">'
            f'<div class="stack-seg seg-objective" style="width:{objective / total * 100:.1f}%"></div>'
            f'<div class="stack-seg seg-big" style="width:{big / total * 100:.1f}%"></div>'
            '</div>'
            f'<div class="breakdown-meta">选填 {e(format_optional_number(point.get("score_objective")) or "-")} · 大题 {e(format_optional_number(point.get("score_big")) or "-")} · 总分 {e(format_number(point["total_score"]))}</div>'
            '</article>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_408_metric_rows(points: Sequence[Mapping[str, object]], metric_prefix: str) -> str:
    labels = [("DS", "ds"), ("CO", "co"), ("OS", "os"), ("CN", "cn")]
    if metric_prefix == "score":
        choice_prefix = "score_choice_"
        big_prefix = "score_big_"
        empty_message = "当前没有 408 的实际得分细分。"
    else:
        choice_prefix = "loss_choice_"
        big_prefix = "loss_big_"
        empty_message = "当前没有 408 的失分/错题数细分。"

    rows = []
    for point in points:
        if any(point.get(f"{choice_prefix}{suffix}") is not None for _, suffix in labels) or any(point.get(f"{big_prefix}{suffix}") is not None for _, suffix in labels):
            rows.append(point)
    if not rows:
        return render_empty_state(empty_message)

    parts = ['<div class="breakdown-list">']
    for point in rows:
        choice_text = " / ".join(
            f"{label} {format_optional_number(point.get(f'{choice_prefix}{suffix}')) or '-'}"
            for label, suffix in labels
        )
        big_text = " / ".join(
            f"{label} {format_optional_number(point.get(f'{big_prefix}{suffix}')) or '-'}"
            for label, suffix in labels
        )
        parts.append(
            '<article class="breakdown-card">'
            f'<div class="breakdown-head"><strong>{e(point["paper_label"])}</strong><span>{e(point["exam_date"])}</span></div>'
            f'<div class="breakdown-meta">选择题：{e(choice_text)}</div>'
            f'<div class="breakdown-meta">大题：{e(big_text)}</div>'
            f'<div class="breakdown-meta">总分 {e(format_number(point["total_score"]))}</div>'
            '</article>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_english_breakdown_rows(points: Sequence[Mapping[str, object]]) -> str:
    rows = [
        point for point in points
        if any(point.get(field) is not None for field in ("score_cloze", "score_reading", "score_new_type", "score_translation", "score_short_essay", "score_long_essay"))
    ]
    if not rows:
        return render_empty_state("当前没有英语一的六板块细分得分。")
    parts = ['<div class="breakdown-list">']
    for point in rows:
        detail = " / ".join([
            f"完形 {format_optional_number(point.get('score_cloze')) or '-'}",
            f"阅读 {format_optional_number(point.get('score_reading')) or '-'}",
            f"新题型 {format_optional_number(point.get('score_new_type')) or '-'}",
            f"翻译 {format_optional_number(point.get('score_translation')) or '-'}",
            f"小作文 {format_optional_number(point.get('score_short_essay')) or '-'}",
            f"大作文 {format_optional_number(point.get('score_long_essay')) or '-'}",
        ])
        parts.append(
            '<article class="breakdown-card">'
            f'<div class="breakdown-head"><strong>{e(point["paper_label"])}</strong><span>{e(point["exam_date"])}</span></div>'
            f'<div class="breakdown-meta">{e(detail)}</div>'
            f'<div class="breakdown-meta">总分 {e(format_number(point["total_score"]))}</div>'
            '</article>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_subject_score_table(subject_key: str, rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("还没有可展示的卷子记录。")
    if subject_key == "politics":
        parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>分数</th></tr></thead><tbody>']
        for row in rows:
            row_date = row.get("date") or row.get("exam_date") or "-"
            parts.append(
                f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)
    if subject_key == "math1":
        parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th><th>选填</th><th>大题</th><th>主要问题</th></tr></thead><tbody>']
        for row in rows:
            row_date = row.get("date") or row.get("exam_date") or "-"
            parts.append(
                f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td><td>{e(format_optional_number(row.get('score_objective')) or '-')}</td><td>{e(format_optional_number(row.get('score_big')) or '-')}</td><td>{e(row['issues'])}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)
    if subject_key == "408":
        parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th><th>主要薄弱科</th><th>备注</th></tr></thead><tbody>']
        for row in rows:
            row_date = row.get("date") or row.get("exam_date") or "-"
            main_weakness = row.get("main_weakness") or top_weakness_from_408_record(row) or row.get("issues", "")
            parts.append(
                f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td><td>{e(main_weakness)}</td><td>{e(row['note'])}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)
    parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th><th>六项分解</th></tr></thead><tbody>']
    for row in rows:
        row_date = row.get("date") or row.get("exam_date") or "-"
        detail = " / ".join([
            f"完形 {format_optional_number(row.get('score_cloze')) or '-'}",
            f"阅读 {format_optional_number(row.get('score_reading')) or '-'}",
            f"新题型 {format_optional_number(row.get('score_new_type')) or '-'}",
            f"翻译 {format_optional_number(row.get('score_translation')) or '-'}",
            f"小作文 {format_optional_number(row.get('score_short_essay')) or '-'}",
            f"大作文 {format_optional_number(row.get('score_long_essay')) or '-'}",
        ])
        parts.append(
            f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td><td>{e(detail)}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def render_subject_filter_panels(subject_key: str, trend_data: Mapping[str, object], color: str) -> str:
    labels = [("all", "全部"), ("真题", "真题"), ("模拟", "模拟")]
    axis_configs = {
        "math1": (0.0, 150.0, 30.0),
        "408": (0.0, 150.0, 30.0),
        "english1": (0.0, 100.0, 20.0),
    }
    y_min, y_max, y_step = axis_configs[subject_key]
    button_parts = ['<div class="chip-row">']
    panel_parts = []
    has_loss_metrics = bool(trend_data.get("has_loss_metrics"))
    for index, (filter_key, label) in enumerate(labels):
        target = f"{subject_key}-{filter_key}"
        button_parts.append(
            f'<button type="button" class="chip-button{" active" if index == 0 else ""}" data-chip-group="{subject_key}" data-target="{target}">{e(label)}</button>'
        )
        rows = trend_data["filters"][filter_key]
        chart = render_line_chart(rows, color, "当前筛选下还没有成绩记录。", y_min, y_max, y_step)
        if subject_key == "math1":
            breakdown = render_math_breakdown_rows(rows)
        elif subject_key == "408":
            score_view = render_408_metric_rows(rows, "score")
            if has_loss_metrics:
                loss_view = render_408_metric_rows(rows, "loss")
                breakdown = (
                    f'<div class="chip-row compact">'
                    f'<button type="button" class="chip-button active" data-chip-group="{target}-metric" data-target="{target}-score">实际得分</button>'
                    f'<button type="button" class="chip-button" data-chip-group="{target}-metric" data-target="{target}-loss">失分/错题数</button>'
                    f'</div>'
                    f'<div id="{target}-score" class="metric-subpanel active">{score_view}</div>'
                    f'<div id="{target}-loss" class="metric-subpanel">{loss_view}</div>'
                )
            else:
                breakdown = score_view
        else:
            breakdown = render_english_breakdown_rows(rows)
        panel_parts.append(
            f'<div id="{target}" class="subject-filter-panel{" active" if index == 0 else ""}">'
            f'<div class="mini-panel"><h3>总分趋势</h3>{chart}</div>'
            f'<div class="mini-panel"><h3>板块分解</h3>{breakdown}</div>'
            f'<div class="mini-panel"><h3>最近卷子成绩</h3>{render_subject_score_table(subject_key, sorted(rows, key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]), reverse=True)[:6])}</div>'
            '</div>'
        )
    button_parts.append("</div>")
    return "".join(button_parts) + "".join(panel_parts)


def render_subject_progress(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("尚无结构化数据")
    parts = ['<div class="subject-list">']
    for row in rows:
        ratio = float(row.get("gap_ratio", 0.0)) * 100
        gap = row.get("gap")
        gap_text = "-" if gap is None else f"{format_number(abs(float(gap)))} 分差距"
        cards = int(row.get("cards", 0))
        marked = int(row.get("knowledge_marked", 0))
        total = int(row.get("knowledge_total", 0))
        score_badges = []
        if cards:
            score_badges.append(f"{cards} 张错题卡")
        if total:
            score_badges.append(f"知识地图 {marked}/{total}")
        if row.get("has_score"):
            score_badges.append("已有成绩记录")
        if row.get("has_chapter_reports"):
            score_badges.append("已有章节报告")
        badges = " · ".join(score_badges) if score_badges else "尚无结构化沉淀"
        parts.append(
            '<article class="subject-card">'
            '<div class="subject-head">'
            f'<h3>{e(row["subject"])}</h3>'
            f'<span class="subject-gap">{e(gap_text)}</span>'
            "</div>"
            '<div class="subject-scoreline">'
            f'<span>当前 {e(format_number(row.get("current")))}</span>'
            f'<span>目标 {e(format_number(row.get("target")))}</span>'
            "</div>"
            '<div class="subject-gap-track">'
            f'<div class="subject-gap-fill" style="width: {ratio:.1f}%"></div>'
            "</div>"
            f'<p class="subject-judge">{e(row.get("judgement", ""))}</p>'
            f'<p class="subject-badges">{e(badges)}</p>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_heatmap(cells: Sequence[Mapping[str, object]], empty_message: str) -> str:
    if not cells:
        return render_empty_state(empty_message)
    parts = ['<div class="heatmap">']
    for cell in cells:
        parts.append(
            f'<div class="heat-cell level-{int(cell["level"])}" '
            f'title="{e(cell["date"])}: {e(cell["count"])}"></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_top_chapters(rows: Sequence[Mapping[str, object]], empty_message: str) -> str:
    if not rows:
        return render_empty_state(empty_message)
    parts = ['<div class="chapter-list">']
    for row in rows:
        parts.append(
            '<article class="chapter-card">'
            f'<div class="chapter-title">{e(row["subject"])} / {e(row["chapter"])}</div>'
            f'<div class="chapter-meta">到期 {int(row["due_cards"])} · 未掌握 {int(row["not_mastered_cards"])} · 累计 {int(row["total_cards"])}</div>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_knowledge_rows(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("尚无结构化数据")
    parts = ['<div class="knowledge-list">']
    for row in rows:
        total = int(row.get("total_topics", 0))
        if not total:
            parts.append(
                '<article class="knowledge-card">'
                f'<div class="knowledge-title">{e(row["subject"])}</div>'
                '<div class="knowledge-empty">尚无知识地图数据</div>'
                "</article>"
            )
            continue
        segments = []
        for key, klass in (("会", "seg-mastered"), ("半会", "seg-partial"), ("不会", "seg-weak"), ("unmarked", "seg-unmarked")):
            value = int(row.get(key, 0))
            width = value / total * 100 if total else 0
            label = key if key != "unmarked" else "未标注"
            segments.append(
                f'<div class="km-seg {klass}" style="width: {width:.1f}%" title="{e(label)} {value}"></div>'
            )
        parts.append(
            '<article class="knowledge-card">'
            f'<div class="knowledge-title">{e(row["subject"])}</div>'
            f'<div class="knowledge-subtitle">已标注 {int(row["marked_topics"])}/{total}</div>'
            '<div class="km-track">' + "".join(segments) + "</div>"
            f'<div class="knowledge-legend">会 {int(row["会"])} · 半会 {int(row["半会"])} · 不会 {int(row["不会"])} · 未标注 {int(row["unmarked"])}</div>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_quality_table(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("尚无结构化数据")
    headers = ["日志", "错题", "地图", "已标注", "模考", "复盘", "章节报告"]
    keys = ["logs", "wrong_cards", "knowledge_map", "marked_topics", "mock", "recap", "chapter_report"]
    parts = [
        '<table class="quality-table"><thead><tr><th>科目</th>' +
        "".join(f"<th>{e(header)}</th>" for header in headers) +
        "</tr></thead><tbody>"
    ]
    for row in rows:
        parts.append(f"<tr><td>{e(row['subject'])}</td>")
        for key in keys:
            mark = "●" if row[key] else "○"
            klass = "ok" if row[key] else "missing"
            parts.append(f'<td class="{klass}">{mark}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_warning_list(items: Sequence[str]) -> str:
    if not items:
        return render_empty_state("当前没有明显的结构化缺口。")
    return "<ul class=\"warning-list\">" + "".join(f"<li>{e(item)}</li>" for item in items) + "</ul>"


def render_focus_list(items: Sequence[str], empty_message: str) -> str:
    if not items:
        return render_empty_state(empty_message)
    return "<ol class=\"focus-list\">" + "".join(f"<li>{e(item)}</li>" for item in items[:5]) + "</ol>"


def render_recent_outputs(recent_outputs: Mapping[str, Mapping[str, int]]) -> str:
    parts = ['<div class="output-grid">']
    for label, payload in (("最近一周", recent_outputs["week"]), ("最近一月", recent_outputs["month"])):
        parts.append(
            '<article class="output-card">'
            f'<h3>{e(label)}</h3>'
            f'<p>日志 {payload["logs"]} · 新卡 {payload["cards"]} · 复盘 {payload["recaps"]} · 模考 {payload["mock_reports"]} · 章节报告 {payload["chapter_reports"]}</p>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_html(payload: Mapping[str, object]) -> str:
    overview = payload["overview"]
    subjects = payload["subjects"]
    reviews = payload["reviews"]
    score_trends = payload["score_trends"]
    knowledge_maps = payload["knowledge_maps"]
    activity = payload["activity"]
    quality = payload["quality"]
    results = payload["results"]
    archive = payload["archive"]

    days_until_exam = overview["days_until_exam"]
    days_text = "-" if days_until_exam is None else str(days_until_exam)
    recap_status = f'复盘 {overview["reports_status"]["recap_count"]} / 模考 {overview["reports_status"]["mock_count"]}'

    metric_cards = "".join([
        render_metric_card("距考试", days_text, f'考试日 {overview["exam_date"]}', "gold"),
        render_metric_card("最近学习", overview["latest_log_date"], f'连续 {overview["log_streak_days"]} 天', "ink"),
        render_metric_card("14 天活跃", str(overview["active_days_14"]), "最近两周有记录的天数", "mint"),
        render_metric_card("到期复习", str(overview["due_total"]), "今天该先止损多少旧题", "alert"),
        render_metric_card("本周新卡", str(overview["new_cards_this_week"]), "这一周新增的结构化错题", "rose"),
        render_metric_card("报告状态", recap_status, "复盘与模考是否在推进", "slate"),
    ])
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kaoyan Coach 学习驾驶舱</title>
  <style>
    :root {{
      --bg: #f6f0e7;
      --paper: rgba(255, 250, 244, 0.86);
      --ink: #14213d;
      --muted: #5f6b7a;
      --gold: #b7791f;
      --gold-soft: #f2d3a1;
      --alert: #c2410c;
      --alert-soft: #fdba74;
      --mint: #156f62;
      --mint-soft: #99f6e4;
      --rose: #9f1239;
      --rose-soft: #fda4af;
      --slate: #334155;
      --line: rgba(20, 33, 61, 0.1);
      --shadow: 0 24px 80px rgba(20, 33, 61, 0.08);
      --radius: 22px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(242, 211, 161, 0.55), transparent 30%),
        radial-gradient(circle at 80% 10%, rgba(153, 246, 228, 0.35), transparent 25%),
        linear-gradient(180deg, #f8f4ed 0%, #efe5d8 100%);
      font-family: "Hiragino Sans GB", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      line-height: 1.5;
    }}
    .shell {{
      width: min(1240px, calc(100% - 32px));
      margin: 24px auto 60px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(135deg, rgba(20, 33, 61, 0.96), rgba(34, 49, 84, 0.92));
      color: #fff6eb;
      border-radius: 32px;
      padding: 32px;
      box-shadow: var(--shadow);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -40px -60px auto;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 255, 255, 0.18), transparent 70%);
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-family: Georgia, "Songti SC", "STSong", serif;
      font-size: clamp(32px, 4vw, 48px);
      line-height: 1.02;
      letter-spacing: -0.02em;
    }}
    .hero p {{
      margin: 0;
      max-width: 760px;
      color: rgba(255, 246, 235, 0.8);
      font-size: 16px;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
      color: rgba(255, 246, 235, 0.86);
    }}
    .hero-meta span {{
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(12px);
    }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 16px 0 0;
    }}
    .nav a, .nav button {{
      border: 0;
      cursor: pointer;
      text-decoration: none;
      color: #fff8ef;
      background: rgba(255, 255, 255, 0.1);
      padding: 10px 14px;
      border-radius: 999px;
      font-size: 14px;
    }}
    .section {{
      margin-top: 22px;
      background: var(--paper);
      border: 1px solid rgba(255, 255, 255, 0.5);
      border-radius: 28px;
      padding: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }}
    .section h2 {{
      margin: 0 0 6px;
      font-family: Georgia, "Songti SC", "STSong", serif;
      font-size: 28px;
      letter-spacing: -0.02em;
    }}
    .section .lede {{
      margin: 0 0 18px;
      color: var(--muted);
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 14px;
    }}
    .metric-card {{
      border-radius: 22px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid var(--line);
      min-height: 152px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .metric-title {{
      color: var(--muted);
      font-size: 13px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .metric-value {{
      font-size: clamp(28px, 3vw, 38px);
      font-weight: 700;
      line-height: 1;
      margin: 10px 0 6px;
    }}
    .metric-caption {{
      color: var(--muted);
      font-size: 14px;
    }}
    .tone-gold .metric-value {{ color: var(--gold); }}
    .tone-ink .metric-value {{ color: var(--ink); }}
    .tone-mint .metric-value {{ color: var(--mint); }}
    .tone-alert .metric-value {{ color: var(--alert); }}
    .tone-rose .metric-value {{ color: var(--rose); }}
    .tone-slate .metric-value {{ color: var(--slate); }}
    .split {{
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 18px;
    }}
    .subject-list, .knowledge-list, .output-grid {{
      display: grid;
      gap: 14px;
    }}
    .subject-card, .knowledge-card, .output-card, .chapter-card {{
      border-radius: 20px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
    }}
    .subject-head, .subject-scoreline {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
    }}
    .subject-head h3, .output-card h3 {{
      margin: 0;
      font-size: 20px;
    }}
    .subject-gap {{
      color: var(--gold);
      font-weight: 700;
    }}
    .subject-scoreline {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .subject-gap-track, .km-track, .bar-track {{
      position: relative;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(20, 33, 61, 0.08);
    }}
    .subject-gap-track {{
      height: 10px;
      margin-top: 12px;
    }}
    .subject-gap-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--gold), #f0b35c);
    }}
    .subject-judge, .subject-badges, .knowledge-subtitle, .knowledge-legend, .chapter-meta {{
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .bar-list {{
      display: grid;
      gap: 12px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 110px minmax(0, 1fr) 40px;
      gap: 10px;
      align-items: center;
    }}
    .bar-label, .bar-value {{
      font-size: 14px;
    }}
    .bar-track {{
      height: 12px;
    }}
    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--ink), #5876b8);
      border-radius: inherit;
    }}
    .panel-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .mini-panel {{
      border-radius: 22px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
    }}
    .mini-panel h3 {{
      margin: 0 0 10px;
      font-size: 19px;
    }}
    .trend-chart {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .chart-with-legend {{
      display: grid;
      gap: 12px;
    }}
    .chart-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .legend-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(20, 33, 61, 0.06);
      color: var(--muted);
      font-size: 13px;
    }}
    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }}
    .score-table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.92);
      border-radius: 18px;
      overflow: hidden;
    }}
    .score-table th, .score-table td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 14px;
      vertical-align: top;
    }}
    .score-table th {{
      color: var(--muted);
      font-weight: 700;
    }}
    .score-summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }}
    .subject-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 16px 0;
    }}
    .tab-button, .chip-button {{
      border: 1px solid rgba(20, 33, 61, 0.12);
      background: rgba(255, 255, 255, 0.9);
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 14px;
      cursor: pointer;
    }}
    .tab-button.active, .chip-button.active {{
      background: var(--ink);
      color: #fff8ef;
      border-color: var(--ink);
    }}
    .trend-tab-panel, .subject-filter-panel, .metric-subpanel {{
      display: none;
    }}
    .trend-tab-panel.active, .subject-filter-panel.active, .metric-subpanel.active {{
      display: block;
    }}
    .trend-tab-panel {{
      margin-top: 12px;
    }}
    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .chip-row.compact {{
      margin-top: 4px;
    }}
    .breakdown-list {{
      display: grid;
      gap: 10px;
    }}
    .breakdown-card {{
      padding: 14px;
      border-radius: 18px;
      background: rgba(20, 33, 61, 0.04);
      border: 1px solid rgba(20, 33, 61, 0.06);
    }}
    .breakdown-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 14px;
      margin-bottom: 10px;
    }}
    .breakdown-meta {{
      color: var(--muted);
      font-size: 14px;
      margin-top: 8px;
    }}
    .stack-track {{
      display: flex;
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(20, 33, 61, 0.08);
    }}
    .stack-seg {{
      height: 100%;
    }}
    .seg-objective {{
      background: #b7791f;
    }}
    .seg-big {{
      background: #1d4ed8;
    }}
    .heatmap {{
      display: grid;
      grid-template-columns: repeat(10, minmax(0, 1fr));
      gap: 6px;
    }}
    .heat-cell {{
      aspect-ratio: 1 / 1;
      border-radius: 8px;
      background: rgba(20, 33, 61, 0.06);
      border: 1px solid rgba(20, 33, 61, 0.03);
    }}
    .level-1 {{ background: rgba(183, 121, 31, 0.28); }}
    .level-2 {{ background: rgba(183, 121, 31, 0.48); }}
    .level-3 {{ background: rgba(183, 121, 31, 0.78); }}
    .chapter-list {{
      display: grid;
      gap: 10px;
    }}
    .chapter-title {{
      font-size: 16px;
      font-weight: 700;
    }}
    .km-track {{
      height: 12px;
      margin-top: 12px;
      display: flex;
    }}
    .km-seg {{ height: 100%; }}
    .seg-mastered {{ background: #0f766e; }}
    .seg-partial {{ background: #eab308; }}
    .seg-weak {{ background: #dc2626; }}
    .seg-unmarked {{ background: rgba(20, 33, 61, 0.12); }}
    .quality-table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.92);
      border-radius: 18px;
      overflow: hidden;
    }}
    .quality-table th, .quality-table td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: center;
      font-size: 14px;
    }}
    .quality-table th:first-child, .quality-table td:first-child {{
      text-align: left;
      font-weight: 700;
    }}
    .quality-table .ok {{
      color: var(--mint);
      font-weight: 700;
    }}
    .quality-table .missing {{
      color: var(--alert);
      font-weight: 700;
    }}
    .warning-list, .focus-list {{
      margin: 0;
      padding-left: 20px;
      color: var(--ink);
    }}
    .warning-list li + li, .focus-list li + li {{
      margin-top: 8px;
    }}
    .results-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }}
    .result-card {{
      padding: 18px;
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
    }}
    .result-card .value {{
      font-size: 34px;
      font-weight: 700;
      margin-top: 8px;
    }}
    .empty-state {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(20, 33, 61, 0.05);
      color: var(--muted);
      font-size: 14px;
    }}
    .payload-drawer {{
      display: none;
      margin-top: 16px;
      border-radius: 20px;
      background: rgba(7, 14, 30, 0.92);
      color: #f8f4ed;
      padding: 18px;
      overflow: auto;
      max-height: 420px;
      font-size: 13px;
    }}
    .tooltip-floating {{
      position: fixed;
      pointer-events: none;
      z-index: 9999;
      max-width: 320px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(20, 33, 61, 0.94);
      color: #fff8ef;
      box-shadow: 0 10px 30px rgba(20, 33, 61, 0.2);
      font-size: 12px;
      line-height: 1.4;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 120ms ease, transform 120ms ease;
    }}
    .tooltip-floating.visible {{
      opacity: 1;
      transform: translateY(0);
    }}
    .payload-drawer.open {{
      display: block;
    }}
    @media (max-width: 1100px) {{
      .metric-grid, .results-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .split {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 760px) {{
      .shell {{
        width: min(100% - 20px, 1240px);
        margin-top: 12px;
      }}
      .hero, .section {{
        padding: 18px;
        border-radius: 22px;
      }}
      .metric-grid, .results-grid, .panel-grid {{
        grid-template-columns: 1fr;
      }}
      .bar-row {{
        grid-template-columns: 90px minmax(0, 1fr) 34px;
      }}
      .heatmap {{
        grid-template-columns: repeat(6, minmax(0, 1fr));
      }}
      .quality-table {{
        display: block;
        overflow-x: auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>Kaoyan Coach 学习驾驶舱</h1>
      <p>先把真实学习状态摊开，再决定今天该补哪里。这个页面只消费你已经沉淀下来的档案、日志、错题卡、知识地图和报告，不美化空白，也不替你脑补进步。</p>
      <div class="hero-meta">
        <span>生成时间 {e(payload["generated_at"])}</span>
        <span>档案更新 {e(archive["latest_archive_update"])}</span>
        <span>当前阶段 {e(overview["stage"] or "未记录")}</span>
      </div>
      <div class="nav">
        <a href="#overview">总览</a>
        <a href="#subjects">科目进度</a>
        <a href="#score-trends">成绩趋势</a>
        <a href="#reviews">复习止损</a>
        <a href="#quality">沉淀质量</a>
        <a href="#results">成果感</a>
        <button id="toggle-payload" type="button">查看原始数据</button>
      </div>
      <pre id="payload-drawer" class="payload-drawer"></pre>
    </section>

    <section class="section" id="overview">
      <h2>总览卡片</h2>
      <p class="lede">第一屏只回答一件事：你现在的系统状态是在向前推进，还是在悄悄失真。</p>
      <div class="metric-grid">{metric_cards}</div>
    </section>

    <section class="section" id="subjects">
      <h2>科目进度总览</h2>
      <p class="lede">先看分差，再看结构化沉淀是否跟上。当前差距最大的不一定最危险，但长期空白的一定最危险。</p>
      <div class="split">
        <div>
          {render_subject_progress(subjects["progress"])}
        </div>
        <div class="mini-panel">
          <h3>聚焦问题</h3>
          {render_focus_list(archive["focus_problems"], "档案里还没有最近聚焦问题。")}
          <h3 style="margin-top: 18px;">结构化沉淀覆盖</h3>
          <p>{e("、".join(subjects["structured_subjects"]) if subjects["structured_subjects"] else "尚无结构化沉淀")}</p>
          <p style="color: var(--muted);">{e("空白科目：" + "、".join(subjects["blank_subjects"]) if subjects["blank_subjects"] else "当前四科都至少有一层结构化数据。")}</p>
        </div>
      </div>
    </section>

    <section class="section" id="score-trends">
      <h2>成绩趋势面板</h2>
      <p class="lede">一次只看一个维度：总分、单科趋势和模块分数分开读，图表才不会挤成一团。</p>
      <div class="subject-tabs">
        <button type="button" class="tab-button active" data-chip-group="score-tabs" data-target="score-tab-total">总分</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-math1">数学一</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-408">408</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-english1">英语一</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-politics">政治</button>
      </div>
      <div id="score-tab-total" class="trend-tab-panel active">
        {render_total_score_panel(score_trends)}
      </div>
      <div id="score-tab-math1" class="trend-tab-panel">
        {render_subject_filter_panels("math1", score_trends["math1"], "#b7791f")}
      </div>
      <div id="score-tab-408" class="trend-tab-panel">
        {render_subject_filter_panels("408", score_trends["408"], "#1d4ed8")}
      </div>
      <div id="score-tab-english1" class="trend-tab-panel">
        {render_subject_filter_panels("english1", score_trends["english1"], "#0f766e")}
      </div>
      <div id="score-tab-politics" class="trend-tab-panel">
        {render_politics_panel(score_trends)}
      </div>
    </section>

    <section class="section" id="reviews">
      <h2>复习止损面板</h2>
      <p class="lede">这里不是展示“我有多少题”，而是暴露“哪一堆旧题再不清就会继续恶化”。</p>
      <div class="panel-grid">
        <div class="mini-panel">
          <h3>到期卡按科目分布</h3>
          {render_bar_rows(reviews["by_subject"], "当前没有到期复习。")}
        </div>
        <div class="mini-panel">
          <h3>到期卡按状态分布</h3>
          {render_bar_rows(reviews["by_status"], "当前没有到期复习。")}
        </div>
        <div class="mini-panel">
          <h3>超期严重度分层</h3>
          {render_bar_rows(reviews["overdue_buckets"], "当前没有到期复习。")}
        </div>
        <div class="mini-panel">
          <h3>最该先清的章节 / 考点</h3>
          {render_top_chapters(reviews["top_chapters"], "尚无错题热点。")}
        </div>
      </div>
    </section>

    <section class="section" id="quality">
      <h2>沉淀质量面板</h2>
      <p class="lede">你的学习系统值不值钱，取决于哪些事实被记下来了，哪些仍然只是聊过但没沉淀。</p>
      <div class="panel-grid">
        <div class="mini-panel">
          <h3>最近 30 天学习日志</h3>
          {render_heatmap(activity["log_heatmap_30"], "还没有学习日志。")}
        </div>
        <div class="mini-panel">
          <h3>最近 30 天错题创建</h3>
          {render_heatmap(activity["card_created_heatmap_30"], "还没有错题创建记录。")}
        </div>
        <div class="mini-panel">
          <h3>最近 30 天错题复习</h3>
          {render_heatmap(activity["card_reviewed_heatmap_30"], "还没有错题复习记录。")}
        </div>
        <div class="mini-panel">
          <h3>知识地图掌握分布</h3>
          {render_knowledge_rows(knowledge_maps["by_subject"])}
        </div>
      </div>
      <div style="margin-top: 16px;">
        <h3 style="margin: 0 0 10px;">数据完整度图</h3>
        {render_quality_table(quality["subject_matrix"])}
      </div>
      <div style="margin-top: 16px;">
        <h3 style="margin: 0 0 10px;">缺失提醒</h3>
        {render_warning_list(quality["warnings"])}
      </div>
    </section>

    <section class="section" id="results">
      <h2>成果感面板</h2>
      <p class="lede">成果感不靠鼓励词，靠能数出来的沉淀：你到底留下了多少可回看的学习资产。</p>
      <div class="results-grid">
        <article class="result-card"><div>已沉淀卡片总数</div><div class="value">{e(results["total_cards"])}</div></article>
        <article class="result-card"><div>推进到半会/会的卡</div><div class="value">{e(results["promoted_cards"])}</div></article>
        <article class="result-card"><div>已覆盖章节数</div><div class="value">{e(results["covered_chapters"])}</div></article>
        <article class="result-card"><div>408 已覆盖模块</div><div class="value">{e(results["covered_modules_408"])}</div></article>
      </div>
      {render_recent_outputs(activity["recent_outputs"])}
      <div style="margin-top: 16px;">
        <h3 style="margin: 0 0 10px;">下一步建议</h3>
        {render_focus_list(archive["next_steps"], "档案里还没有下一步建议。")}
      </div>
    </section>
  </div>

  <script id="payload-json" type="application/json">{payload_json}</script>
  <script>
    const toggle = document.getElementById("toggle-payload");
    const drawer = document.getElementById("payload-drawer");
    const payload = document.getElementById("payload-json").textContent;
    drawer.textContent = payload;
    const tooltip = document.createElement("div");
    tooltip.className = "tooltip-floating";
    document.body.appendChild(tooltip);
    toggle.addEventListener("click", () => {{
      drawer.classList.toggle("open");
    }});
    document.querySelectorAll("[data-chip-group]").forEach((button) => {{
      button.addEventListener("click", () => {{
        const group = button.dataset.chipGroup;
        const target = button.dataset.target;
        document.querySelectorAll(`[data-chip-group="${{group}}"]`).forEach((peer) => peer.classList.remove("active"));
        button.classList.add("active");
        if (!target) return;
        if (group === "score-tabs") {{
          document.querySelectorAll(".trend-tab-panel").forEach((panel) => panel.classList.remove("active"));
        }} else if (group.endsWith("-metric")) {{
          document.querySelectorAll(`#${{CSS.escape(group.replace("-metric", ""))}} .metric-subpanel`).forEach((panel) => panel.classList.remove("active"));
        }} else {{
          document.querySelectorAll(".subject-filter-panel").forEach((panel) => {{
            if (panel.id.startsWith(group + "-")) panel.classList.remove("active");
          }});
        }}
        const targetEl = document.getElementById(target);
        if (targetEl) targetEl.classList.add("active");
      }});
    }});
    const moveTooltip = (event) => {{
      tooltip.style.left = (event.clientX + 14) + "px";
      tooltip.style.top = (event.clientY + 14) + "px";
    }};
    document.querySelectorAll(".tooltip-point").forEach((point) => {{
      point.addEventListener("mouseenter", (event) => {{
        tooltip.textContent = point.dataset.tooltip || "";
        tooltip.classList.add("visible");
        moveTooltip(event);
      }});
      point.addEventListener("mousemove", moveTooltip);
      point.addEventListener("mouseleave", () => {{
        tooltip.classList.remove("visible");
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    payload = build_payload(obsidian_root, today)

    output_path = resolve_output_path(obsidian_root, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = render_html(payload)
    atomic_write(output_path, html_content)

    result = dict(payload)
    result["path"] = str(output_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
